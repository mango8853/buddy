#!/usr/bin/env python3
"""Claude Code hook -> Buddy bridge.

Usage in settings.json hooks:
  UserPromptSubmit:  python3 buddy-hook.py prompt
  Stop:              python3 buddy-hook.py stop
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
WATCH_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "buddy-transcript-watch.py",
)
PID_FILE = os.path.expanduser("~/.claude/buddy-watch.pid")
STATE_FILE = os.path.expanduser("~/.claude/buddy-stream.json")
LOG_FILE = os.path.expanduser("~/.claude/buddy-hook.log")


def log(msg):
    ts = time.strftime("%H:%M:%S")
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except OSError:
        pass


def bridge_url(path):
    return f"http://127.0.0.1:{BRIDGE_PORT}{path}"


def post(path, payload, timeout=3):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        bridge_url(path), data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        log(f"POST {path} -> {resp.status}")
    except Exception as e:
        log(f"POST {path} FAILED: {e}")


def read_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE + ".tmp", "w") as f:
        json.dump(state, f)
    os.replace(STATE_FILE + ".tmp", STATE_FILE)


def stop_watcher():
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGTERM)
        log(f"killed watcher pid={pid}")
    except (FileNotFoundError, ValueError, ProcessLookupError, OSError) as e:
        log(f"stop_watcher: {e}")
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass


def start_watcher(session_id, stream_id):
    stop_watcher()
    env = os.environ.copy()
    env["BUDDY_PET_ID"] = PET_ID
    proc = subprocess.Popen(
        [sys.executable, WATCH_SCRIPT, session_id, stream_id],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    log(f"started watcher pid={proc.pid} session={session_id} stream={stream_id}")


def handle_prompt(payload):
    session_id = payload.get("session_id", "")
    log(f"prompt session_id={session_id} payload_keys={list(payload.keys())}")

    if not session_id:
        return

    stream_id = f"cc-{session_id[:8]}"

    # Record active stream for stop handler
    state = read_state()
    state[session_id] = {"stream_id": stream_id, "active": True, "ts": time.time()}
    # Clean stale entries (>1 hour)
    cutoff = time.time() - 3600
    for k in list(state.keys()):
        if state[k].get("ts", 0) < cutoff:
            del state[k]
    write_state(state)

    start_watcher(session_id, stream_id)


def handle_stop(payload):
    session_id = payload.get("session_id", "")
    log(f"stop session_id={session_id} payload_keys={list(payload.keys())}")

    state = read_state()
    log(f"stop: state has {len(state)} entries")

    for sid, entry in list(state.items()):
        if entry.get("active"):
            sid_stream = entry.get("stream_id", "")
            log(f"ending stream {sid_stream} for session {sid}")
            post("/agent/end", {
                "id": sid_stream,
                "status": "done",
                "exitCode": 0,
            })
            entry["active"] = False

    write_state(state)
    stop_watcher()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "prompt"

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, IOError):
        payload = {}

    log(f"mode={mode}")
    if mode == "prompt":
        handle_prompt(payload)
    elif mode == "stop":
        handle_stop(payload)


if __name__ == "__main__":
    main()
