#!/usr/bin/env python3
"""Real-time transcript tailer -> Buddy bridge.

Runs as a subprocess. Tails a Claude Code transcript file and streams
assistant text/thinking blocks to Buddy as they appear.

Usage: python3 buddy-transcript-tail.py <transcript_path> <stream_id>
"""

import json
import os
import signal
import sys
import time
import urllib.request
import urllib.error

BRIDGE_PORT = int(os.environ.get("BUDDY_BRIDGE_PORT", "8799"))
LOG_FILE = os.path.expanduser("~/.claude/buddy-tailer.log")


def log(msg):
    ts = time.strftime("%H:%M:%S.%f")[:-3]
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


def extract_text(message):
    if message.get("role") != "assistant":
        return ""
    content = message.get("content", [])
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if block.get("type") in ("text", "thinking"):
            t = block.get("text", "") or block.get("thinking", "")
            if t:
                parts.append(t)
    return "".join(parts)


def main():
    transcript_path = sys.argv[1] if len(sys.argv) > 1 else ""
    stream_id = sys.argv[2] if len(sys.argv) > 2 else ""

    if not transcript_path or not stream_id:
        log("missing transcript_path or stream_id")
        sys.exit(1)

    log(f"start transcript={os.path.basename(transcript_path)} stream={stream_id}")

    # Wait for file
    for _ in range(200):
        if os.path.exists(transcript_path):
            break
        time.sleep(0.3)
    else:
        log("transcript never appeared")
        sys.exit(0)

    sent_uuids = set()
    shutdown = False

    def on_term(signum, frame):
        nonlocal shutdown
        shutdown = True
        log("received SIGTERM")

    signal.signal(signal.SIGTERM, on_term)

    with open(transcript_path) as f:
        f.seek(0, 2)  # Start at current end

        while not shutdown:
            line = f.readline()
            if not line:
                time.sleep(0.15)
                continue

            try:
                event = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            if event.get("type") != "assistant":
                continue

            uuid = event.get("uuid", "")
            if uuid in sent_uuids:
                continue
            sent_uuids.add(uuid)

            text = extract_text(event.get("message", {}))
            if text:
                post("/agent/log", {"id": stream_id, "text": text})

    log(f"exit stream={stream_id}")


if __name__ == "__main__":
    main()
