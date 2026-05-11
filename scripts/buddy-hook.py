#!/usr/bin/env python3
"""Claude Code hook -> Buddy bridge. Pure hook-driven, no transcript tailing.

Hooks config:
  UserPromptSubmit  -> python3 buddy-hook.py prompt   (start stream)
  PostToolUse       -> python3 buddy-hook.py tool      (update status)
  Stop              -> python3 buddy-hook.py stop       (end stream, send text)
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

BRIDGE_PORT = int(os.environ.get("BUDDY_BRIDGE_PORT", "8799"))
PET_ID = os.environ.get("BUDDY_PET_ID", "rocky")
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


def handle_prompt(payload):
    session_id = payload.get("session_id", "")
    if not session_id:
        return
    stream_id = f"cc-{session_id[:8]}"

    # End any previous stream first
    state = read_state()
    for sid, entry in list(state.items()):
        if entry.get("active"):
            post("/agent/end", {"id": entry.get("stream_id", ""), "status": "done", "exitCode": 0})
            entry["active"] = False

    state[session_id] = {"stream_id": stream_id, "active": True, "ts": time.time()}
    write_state(state)

    post("/agent/start", {
        "id": stream_id,
        "name": "Claude Code",
        "body": "Thinking...",
        "status": "thinking",
        "petId": PET_ID,
    })
    log(f"prompt -> stream start {stream_id}")


def handle_tool(payload):
    session_id = payload.get("session_id", "")
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    state = read_state()
    entry = state.get(session_id)
    if not entry or not entry.get("active"):
        # No active stream - start one
        if session_id:
            handle_prompt(payload)
            state = read_state()
            entry = state.get(session_id)
        if not entry:
            return

    stream_id = entry["stream_id"]
    label = TOOL_LABELS.get(tool_name, tool_name)
    detail = tool_detail(tool_name, tool_input)

    # Left panel: just status label
    post("/agent/status", {"id": stream_id, "status": "running", "body": label})
    # Right panel: tool detail as output
    log_text = f"{label}: {detail}" if detail else label
    post("/agent/log", {"id": stream_id, "text": log_text + "\n"})


def handle_stop(payload):
    session_id = payload.get("session_id", "")
    last_msg = payload.get("last_assistant_message", {}) or {}

    state = read_state()
    entry = state.get(session_id)
    if not entry or not entry.get("active"):
        log(f"stop: no active stream for {session_id}")
        return

    stream_id = entry["stream_id"]

    # Extract text from the last assistant message
    content = last_msg.get("content", [])
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if block.get("type") in ("text", "thinking"):
                t = block.get("text", "") or block.get("thinking", "")
                if t:
                    text_parts.append(t)
        if text_parts:
            # Send as log (don't re-send what's already been sent by tools)
            pass  # Text is usually already shown via tool updates

    post("/agent/end", {"id": stream_id, "status": "done", "exitCode": 0})
    entry["active"] = False
    write_state(state)
    log(f"stop -> stream end {stream_id}")


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
