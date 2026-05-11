#!/usr/bin/env python3
"""Real-time transcript tailer -> Buddy bridge.

Polls the transcript file and reads new content as it appears.
Avoids Python's buffered readline() which can miss content from
files being written by another process.

Usage: python3 buddy-transcript-tail.py <transcript_path> <stream_id> [start_offset]
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
    pos = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    if not transcript_path or not stream_id:
        log("missing transcript_path or stream_id")
        sys.exit(1)

    log(f"start transcript={os.path.basename(transcript_path)} stream={stream_id} pos={pos}")

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
    line_count = 0

    def on_term(signum, frame):
        nonlocal shutdown
        shutdown = True

    signal.signal(signal.SIGTERM, on_term)

    while not shutdown:
        try:
            cur_size = os.path.getsize(transcript_path)
        except OSError:
            time.sleep(0.3)
            continue

        if cur_size <= pos:
            time.sleep(0.3)
            continue

        # New content available - open fresh and read from last position
        try:
            with open(transcript_path, "rb") as f:
                f.seek(pos)
                raw = f.read(cur_size - pos)
                pos = cur_size
        except Exception:
            time.sleep(0.3)
            continue

        if not raw:
            continue

        # Split into lines and process
        lines = raw.split(b"\n")
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line.decode("utf-8", errors="replace"))
            except Exception:
                continue

            line_count += 1
            etype = event.get("type", "")

            if etype == "assistant":
                uuid = event.get("uuid", "")
                if uuid in sent_uuids:
                    continue
                sent_uuids.add(uuid)

                text = extract_text(event.get("message", {}))
                if text:
                    post("/agent/log", {"id": stream_id, "text": text})
                    if line_count <= 5 or len(sent_uuids) % 10 == 0:
                        log(f"sent {len(text)} chars (total {len(sent_uuids)} messages)")

    log(f"exit stream={stream_id} lines={line_count} messages={len(sent_uuids)}")


if __name__ == "__main__":
    main()
