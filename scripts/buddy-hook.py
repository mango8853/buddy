#!/usr/bin/env python3
"""Claude Code hook -> Buddy bridge.

Usage in settings.json hooks:
  SessionStart:  python3 buddy-hook.py start  (launch persistent transcript watcher)
  Stop:          python3 buddy-hook.py stop   (kill watcher, end any active stream)
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
TURN_DONE_FILE = os.path.expanduser("~/.claude/buddy-turn-done")
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
        urllib.request.urlopen(req, timeout=timeout)
    except Exception as e:
        log(f"POST {path} FAILED: {e}")


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


def start_watcher(transcript_path, session_id):
    # Check if existing watcher is alive and watching the same file
    try:
        with open(PID_FILE) as f:
            existing_pid = int(f.read().strip())
        os.kill(existing_pid, 0)  # Check if alive
        # Read the PID file's transcript path to compare
        try:
            with open(PID_FILE + ".path") as pf:
                old_path = pf.read().strip()
            if old_path == transcript_path:
                log(f"watcher already watching same file pid={existing_pid}")
                return
            else:
                log(f"transcript changed, restarting watcher (old={old_path} new={transcript_path})")
        except FileNotFoundError:
            pass
        # Kill old watcher since transcript changed
        os.kill(existing_pid, signal.SIGTERM)
        try:
            os.waitpid(existing_pid, 0)
        except ChildProcessError:
            pass
    except (FileNotFoundError, ValueError, ProcessLookupError, OSError):
        pass
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass

    env = os.environ.copy()
    env["BUDDY_PET_ID"] = PET_ID
    proc = subprocess.Popen(
        [sys.executable, WATCH_SCRIPT, transcript_path, session_id],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    with open(PID_FILE + ".path", "w") as f:
        f.write(transcript_path)
    log(f"started watcher pid={proc.pid} transcript={transcript_path}")


def handle_start(payload):
    transcript_path = payload.get("transcript_path", "")
    session_id = payload.get("session_id", "")
    log(f"start transcript_path={transcript_path} session_id={session_id}")

    if transcript_path:
        start_watcher(transcript_path, session_id)


def handle_stop(payload):
    # Signal watcher that current turn is done (don't kill the watcher)
    try:
        with open(TURN_DONE_FILE, "w") as f:
            f.write(str(int(time.time())))
        log("stop: signalled turn done")
    except OSError as e:
        log(f"stop: failed to write turn-done: {e}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "start"

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, IOError):
        payload = {}

    log(f"mode={mode} keys={list(payload.keys())}")

    if mode == "start":
        handle_start(payload)
    elif mode == "stop":
        handle_stop(payload)


if __name__ == "__main__":
    main()
