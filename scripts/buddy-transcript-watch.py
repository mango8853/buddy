#!/usr/bin/env python3
"""Watch Claude Code transcript and stream assistant text to Buddy.

Usage (started by SessionStart hook):
  python3 buddy-transcript-watch.py <session-id>

Reads the .jsonl transcript file for a session, extracts assistant text
blocks, and sends them to the Buddy bridge server for display.
"""

import json
import os
import signal
import sys
import time
import urllib.request
import urllib.error

BRIDGE_PORT = int(os.environ.get("BUDDY_BRIDGE_PORT", "8799"))
PET_ID = os.environ.get("BUDDY_PET_ID", "rocky")
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
SENTINEL = os.environ.get("BUDDY_WATCH_SENTINEL", "")


def find_transcript(session_id):
    """Find the transcript file for a session."""
    if not os.path.isdir(PROJECTS_DIR):
        return None
    for root, dirs, files in os.walk(PROJECTS_DIR):
        for f in files:
            if f == f"{session_id}.jsonl":
                return os.path.join(root, f)
    return None


def bridge_url(path):
    return f"http://127.0.0.1:{BRIDGE_PORT}{path}"


LOG_FILE = os.path.expanduser("~/.claude/buddy-watch.log")

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
        bridge_url(path), data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=timeout)
    except (urllib.error.URLError, OSError) as e:
        log(f"POST {path} FAILED: {e}")


def extract_text(message):
    """Extract text content from an assistant message."""
    if message.get("role") != "assistant":
        return ""
    content = message.get("content", [])
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


def main():
    session_id = sys.argv[1] if len(sys.argv) > 1 else ""
    stream_id = sys.argv[2] if len(sys.argv) > 2 else f"cc-{session_id[:8]}"
    if not session_id:
        print("Usage: buddy-transcript-watch.py <session-id> [stream-id]", file=sys.stderr)
        sys.exit(1)

    # Wait for transcript file to appear (max 30s)
    transcript_path = None
    for _ in range(60):
        transcript_path = find_transcript(session_id)
        if transcript_path:
            break
        time.sleep(0.5)

    if not transcript_path:
        log(f"transcript not found for session={session_id}")
        sys.exit(0)

    log(f"watching session={session_id} stream={stream_id} pet={PET_ID} transcript={transcript_path}")
    sent_uuids = set()
    started = False
    exit_after_idle = False
    idle_count = 0
    shutdown = False

    def on_term(signum, frame):
        nonlocal shutdown
        shutdown = True

    signal.signal(signal.SIGTERM, on_term)

    with open(transcript_path) as f:
        f.seek(0, 2)

        while not shutdown:
            line = f.readline()
            if not line:
                time.sleep(0.3)
                if exit_after_idle:
                    idle_count += 1
                    if idle_count > 10:
                        break
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") != "assistant":
                continue

            uuid = event.get("uuid", "")
            if uuid in sent_uuids:
                continue
            sent_uuids.add(uuid)

            text = extract_text(event.get("message", {}))
            if not text:
                continue

            if not started:
                start_payload = {
                    "id": stream_id,
                    "name": "Claude Code",
                    "body": text[:200],
                    "status": "running",
                    "petId": PET_ID,
                }
                log(f"agent/start petId={PET_ID} stream={stream_id}")
                post("/agent/start", start_payload)
                started = True

            post("/agent/log", {"id": stream_id, "text": text})

        if started:
            log(f"agent/end stream={stream_id}")
            post("/agent/end", {"id": stream_id, "status": "done", "exitCode": 0})


if __name__ == "__main__":
    main()
