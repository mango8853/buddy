#!/usr/bin/env python3
"""Claude Code hook -> Buddy bridge.

Hooks:
  UserPromptSubmit -> prompt  (start stream + transcript tailer)
  PostToolUse      -> tool    (update left status)
  Stop             -> stop    (end stream gracefully)

The transcript tailer runs as a background subprocess, streaming
assistant text blocks to Buddy in real-time as they appear in the
transcript file.
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error

BRIDGE_PORT = int(os.environ.get("BUDDY_BRIDGE_PORT", "8799"))
PET_ID = os.environ.get("BUDDY_PET_ID", "rocky")
TAILER_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "buddy-transcript-tail.py",
)
PID_FILE = os.path.expanduser("~/.claude/buddy-tailer.pid")
STATE_FILE = os.path.expanduser("~/.claude/buddy-stream.json")
LOG_FILE = os.path.expanduser("~/.claude/buddy-hook.log")

TOOL_LABELS = {
    "Read": "Reading", "Write": "Writing", "Edit": "Editing",
    "Bash": "Running", "Glob": "Searching", "Grep": "Searching",
    "WebFetch": "Fetching", "WebSearch": "Searching", "Agent": "Subagent",
    "TaskCreate": "Task", "TaskUpdate": "Task",
}


def log(msg):
    ts = time.strftime("%H:%M:%S")
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except OSError:
        pass


def post(path, payload, timeout=3):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{BRIDGE_PORT}{path}",
        data=data, headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=timeout)
    except Exception as e:
        log(f"POST {path} FAILED: {e}")


def read_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_state(s):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE + ".tmp", "w") as f:
        json.dump(s, f)
    os.replace(STATE_FILE + ".tmp", STATE_FILE)


def tool_detail(name, inp):
    if not isinstance(inp, dict):
        return ""
    if name in ("Read", "Write", "Edit"):
        return inp.get("file_path", "")
    if name == "Bash":
        return (inp.get("command", "") or "")[:200]
    if name in ("Glob", "Grep"):
        return inp.get("pattern", "")
    if name in ("WebFetch", "WebSearch"):
        return inp.get("url", "") or inp.get("query", "")
    if name == "Agent":
        return inp.get("description", "")
    return ""


# ── tailer management ───────────────────────────────────────────

def stop_tailer():
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGTERM)
        log(f"tailer: sent SIGTERM to pid={pid}")
    except (FileNotFoundError, ValueError, ProcessLookupError, OSError):
        pass
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass


def start_tailer(transcript_path, stream_id):
    stop_tailer()  # Kill any existing tailer
    # Pass current file size so tailer starts from here, not missing
    # anything written between prompt and tailer startup
    try:
        offset = os.path.getsize(transcript_path)
    except OSError:
        offset = 0
    env = os.environ.copy()
    env["BUDDY_PET_ID"] = PET_ID
    proc = subprocess.Popen(
        [sys.executable, TAILER_SCRIPT, transcript_path, stream_id, str(offset)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))


# ── hook handlers ────────────────────────────────────────────────

def handle_prompt(payload):
    session_id = payload.get("session_id", "")
    transcript_path = payload.get("transcript_path", "")
    if not session_id:
        return

    # End any previous stream
    state = read_state()
    for sid, entry in list(state.items()):
        if entry.get("active"):
            post("/agent/end", {
                "id": entry.get("stream_id", ""),
                "status": "done", "exitCode": 0,
            })
            entry["active"] = False

    turn = state.get(session_id, {}).get("turn", 0) + 1
    stream_id = f"cc-{session_id[:8]}-{turn}"

    state[session_id] = {"stream_id": stream_id, "active": True, "turn": turn, "ts": time.time()}
    write_state(state)

    # Start stream
    post("/agent/start", {
        "id": stream_id, "name": "Claude Code",
        "body": "Thinking...", "status": "thinking", "petId": PET_ID,
    })

    # Start transcript tailer for real-time text streaming
    if transcript_path:
        start_tailer(transcript_path, stream_id)

    log(f"prompt -> stream {stream_id}")


def handle_tool(payload):
    session_id = payload.get("session_id", "")
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    state = read_state()
    entry = state.get(session_id)
    if not entry or not entry.get("active"):
        return

    label = TOOL_LABELS.get(tool_name, tool_name)
    detail = tool_detail(tool_name, tool_input)
    stream_id = entry["stream_id"]

    post("/agent/status", {"id": stream_id, "status": "running", "body": label})
    if detail:
        post("/agent/log", {"id": stream_id, "text": f"{label}: {detail}\n"})

    log(f"tool: {label} stream={stream_id}")


def handle_stop(payload):
    session_id = payload.get("session_id", "")

    state = read_state()
    entry = state.get(session_id)
    if not entry or not entry.get("active"):
        # Try to end stream for any active entry
        for sid, e in list(state.items()):
            if e.get("active"):
                post("/agent/end", {
                    "id": e.get("stream_id", ""),
                    "status": "done", "exitCode": 0,
                })
                e["active"] = False
                log(f"stop: ended {e.get('stream_id','')} (fallback)")
        write_state(state)
        stop_tailer()
        return

    stream_id = entry["stream_id"]

    # Signal tailer to stop gracefully (it will flush any remaining text)
    stop_tailer()
    # Give tailer a moment to send final text
    time.sleep(0.3)

    post("/agent/end", {"id": stream_id, "status": "done", "exitCode": 0})
    entry["active"] = False
    write_state(state)
    log(f"stop -> stream end {stream_id}")


# ── main ─────────────────────────────────────────────────────────

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "prompt"
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, IOError):
        payload = {}

    if mode == "prompt":
        handle_prompt(payload)
    elif mode == "tool":
        handle_tool(payload)
    elif mode == "stop":
        handle_stop(payload)


if __name__ == "__main__":
    main()
