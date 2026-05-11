#!/usr/bin/env python3
"""Bridge Claude Code stream-json output to Buddy device.

Usage:
  claude -p "your prompt" --output-format stream-json | python3 scripts/claude-code-bridge.py

  Or with a file:
  python3 scripts/claude-code-bridge.py < stream-json.log

Environment:
  BUDDY_HOST   - Buddy device IP (required)
  BUDDY_PORT   - Buddy device port (default 8787)
  BRIDGE_PORT  - Local bridge server port (default 8799)
"""

import json
import os
import subprocess
import sys
import time
import urllib.request


def buddy_host():
    host = os.environ.get("BUDDY_HOST")
    if not host:
        raise SystemExit("Set BUDDY_HOST environment variable")
    return host


def buddy_port():
    return int(os.environ.get("BUDDY_PORT", "8787"))


def bridge_port():
    return int(os.environ.get("BRIDGE_PORT", "8799"))


def ensure_bridge():
    """Start the local bridge server if not already running."""
    bp = bridge_port()
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{bp}/health", timeout=2)
        return
    except Exception:
        pass

    bh = buddy_host()
    subprocess.Popen(
        [sys.executable, "-m", "bridge.buddy", "--host", bh, "--port", str(bp), "serve"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{bp}/health", timeout=1)
            return
        except Exception:
            time.sleep(0.25)
    raise SystemExit("Failed to start bridge server")


def post(path, payload):
    bp = bridge_port()
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{bp}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"[buddy-bridge] post error: {e}", file=sys.stderr)


def main():
    ensure_bridge()

    stream_id = f"claude-{int(time.time())}"
    name = os.environ.get("BUDDY_NAME", "Claude Code")
    started = False
    ended = False

    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type", "")

        if event_type == "assistant":
            msg = event.get("message", {})
            content = msg.get("content", [])
            text_parts = []
            has_tool = False
            for block in content:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    has_tool = True
                    text_parts.append(f"[Tool: {block.get('name', '')}] ")

            text = "".join(text_parts)
            if not text:
                continue

            if not started:
                post("/agent/start", {
                    "id": stream_id,
                    "name": name,
                    "body": text[:200],
                    "status": "running",
                })
                started = True
            else:
                if has_tool:
                    post("/agent/status", {
                        "id": stream_id,
                        "status": "running",
                        "body": text[:200],
                    })
                post("/agent/log", {"id": stream_id, "text": text})

        elif event_type == "user":
            msg = event.get("message", {})
            content = msg.get("content", [])
            for block in content:
                if block.get("type") == "tool_result":
                    for sub in block.get("content", []):
                        if sub.get("type") == "text":
                            snippet = sub.get("text", "")[:300]
                            if snippet:
                                post("/agent/log", {
                                    "id": stream_id,
                                    "text": f"[Result] {snippet}\n",
                                })

        elif event_type in ("result", "done"):
            if started:
                post("/agent/end", {"id": stream_id, "status": "done", "exitCode": 0})
                ended = True
            break

    if started and not ended:
        post("/agent/end", {"id": stream_id, "status": "done", "exitCode": 0})


if __name__ == "__main__":
    main()
