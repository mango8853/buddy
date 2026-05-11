#!/usr/bin/env python3
"""Persistent transcript watcher -> Buddy bridge.

Kept alive for the whole Claude Code session. Tails the transcript
file continuously, detects turn boundaries, and streams assistant
text to Buddy.

Started by SessionStart hook. Killed by SessionEnd/Stop hook.
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
LOG_FILE = os.path.expanduser("~/.claude/buddy-watch.log")


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


def extract_text(message):
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
    transcript_path = sys.argv[1] if len(sys.argv) > 1 else ""
    session_id = sys.argv[2] if len(sys.argv) > 2 else ""

    if not transcript_path:
        # Try to find it
        session_id = sys.argv[1] if len(sys.argv) > 1 else ""
        if not session_id:
            log("no transcript_path or session_id")
            sys.exit(1)
        # Search for transcript
        projects_dir = os.path.expanduser("~/.claude/projects")
        for root, dirs, files in os.walk(projects_dir):
            for f in files:
                if f == f"{session_id}.jsonl":
                    transcript_path = os.path.join(root, f)
                    break
        if not transcript_path:
            log(f"transcript not found for session={session_id}")
            sys.exit(0)

    log(f"watching transcript={transcript_path} pet={PET_ID}")

    stream_id_base = f"cc-{os.path.basename(transcript_path).replace('.jsonl', '')[:8]}"
    stream_active = False
    turn_index = 0
    sent_uuids = set()
    shutdown = False

    def on_term(signum, frame):
        nonlocal shutdown
        shutdown = True

    signal.signal(signal.SIGTERM, on_term)

    # Wait for file to exist
    for _ in range(120):
        if os.path.exists(transcript_path):
            break
        if shutdown:
            sys.exit(0)
        time.sleep(0.5)

    if not os.path.exists(transcript_path):
        log("transcript never appeared")
        sys.exit(0)

    with open(transcript_path) as f:
        f.seek(0, 2)  # Start at end

        while not shutdown:
            line = f.readline()
            if not line:
                time.sleep(0.2)
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = event.get("type", "")

            if etype == "user" and not event.get("isMeta"):
                # User message = new turn. End previous stream if active.
                if stream_active:
                    sid = f"{stream_id_base}-{turn_index}"
                    post("/agent/end", {"id": sid, "status": "done", "exitCode": 0})
                    stream_active = False
                turn_index += 1
                continue

            if etype != "assistant":
                continue

            uuid = event.get("uuid", "")
            if uuid in sent_uuids:
                continue
            sent_uuids.add(uuid)

            text = extract_text(event.get("message", {}))
            if not text:
                continue

            sid = f"{stream_id_base}-{turn_index}"

            if not stream_active:
                post("/agent/start", {
                    "id": sid,
                    "name": "Claude Code",
                    "body": text[:200],
                    "status": "running",
                    "petId": PET_ID,
                })
                stream_active = True
                log(f"stream start sid={sid}")

            post("/agent/log", {"id": sid, "text": text})

    # Cleanup
    if stream_active:
        sid = f"{stream_id_base}-{turn_index}"
        post("/agent/end", {"id": sid, "status": "done", "exitCode": 0})
        log(f"stream end (shutdown) sid={sid}")


if __name__ == "__main__":
    main()
