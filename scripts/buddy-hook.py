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
    transcript_path = payload.get("transcript_path", "")

    # End any previous stream first, sending unsent text if available
    state = read_state()
    for sid, entry in list(state.items()):
        if entry.get("active"):
            old_stream = entry.get("stream_id", "")
            old_transcript = entry.get("transcript", "")
            # Try to send text from transcript (in case Stop hook didn't fire)
            if old_transcript and os.path.exists(old_transcript):
                try:
                    text = read_latest_assistant_text(old_transcript)
                    if text:
                        post("/agent/log", {"id": old_stream, "text": text})
                        log(f"prompt: flushed {len(text)} chars for {old_stream}")
                except Exception:
                    pass
            post("/agent/end", {"id": old_stream, "status": "done", "exitCode": 0})
            log(f"prompt: ended previous stream {old_stream}")
            entry["active"] = False

    # Use turn counter for unique stream IDs
    turn = state.get(session_id, {}).get("turn", 0) + 1
    stream_id = f"cc-{session_id[:8]}-{turn}"

    state[session_id] = {"stream_id": stream_id, "active": True, "turn": turn, "ts": time.time(), "transcript": transcript_path}
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
    log(f"tool: {tool_name} session={session_id[:8]}")

    state = read_state()
    entry = state.get(session_id)
    if not entry or not entry.get("active"):
        log(f"tool: no active stream, calling handle_prompt")
        if session_id:
            handle_prompt(payload)
            state = read_state()
            entry = state.get(session_id)
        if not entry:
            log(f"tool: still no entry after prompt, giving up")
            return

    stream_id = entry["stream_id"]
    label = TOOL_LABELS.get(tool_name, tool_name)
    detail = tool_detail(tool_name, tool_input)
    log(f"tool: stream={stream_id} label={label} detail={detail[:60] if detail else ''}")

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
        log(f"stop: no active stream for {session_id[:8]}")
        return

    stream_id = entry["stream_id"]

    # Extract text from last_assistant_message (always available, no file read)
    content = last_msg.get("content", [])
    text_parts = []
    if isinstance(content, list):
        for block in content:
            if block.get("type") in ("text", "thinking"):
                t = block.get("text", "") or block.get("thinking", "")
                if t:
                    text_parts.append(t)

    if text_parts:
        full_text = "".join(text_parts)
        post("/agent/log", {"id": stream_id, "text": full_text})
        log(f"stop: sent {len(full_text)} chars from last_assistant_message")
    else:
        # Fallback: try reading transcript
        transcript_path = payload.get("transcript_path", "")
        if transcript_path and os.path.exists(transcript_path):
            try:
                text = read_latest_assistant_text(transcript_path)
                if text:
                    post("/agent/log", {"id": stream_id, "text": text})
                    log(f"stop: sent {len(text)} chars from transcript")
                else:
                    log(f"stop: no text found in last_assistant_message or transcript")
            except Exception as e:
                log(f"stop: error: {e}")
        else:
            log(f"stop: no text source available (content_types={[c.get('type','?') for c in content] if isinstance(content, list) else 'N/A'})")

    post("/agent/end", {"id": stream_id, "status": "done", "exitCode": 0})
    entry["active"] = False
    write_state(state)
    log(f"stop -> stream end {stream_id}")


def read_latest_assistant_text(transcript_path):
    """Read assistant messages since the last user message, extract text/thinking."""
    if not os.path.exists(transcript_path):
        return ""
    try:
        with open(transcript_path) as f:
            f.seek(0, 2)
            size = f.tell()
            start = max(0, size - 80000)
            f.seek(start)
            if start > 0:
                f.readline()
            lines = f.readlines()
    except Exception:
        return ""

    # Collect all assistant entries since the last non-meta user message
    parts = []
    for line in reversed(lines):
        try:
            event = json.loads(line.strip())
        except json.JSONDecodeError:
            continue
        etype = event.get("type", "")
        if etype == "user" and not event.get("isMeta"):
            break  # Stop at user message boundary
        if etype == "assistant":
            msg = event.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if block.get("type") in ("text", "thinking"):
                        t = block.get("text", "") or block.get("thinking", "")
                        if t:
                            parts.append(t)
    return "".join(reversed(parts))


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
