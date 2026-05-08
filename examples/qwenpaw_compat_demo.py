#!/usr/bin/env python3
import os

from bridge import BuddyClient, QwenPawCompatAdapter


def main():
    buddy_host = os.environ.get("BUDDY_HOST")
    if not buddy_host:
        raise SystemExit("Set BUDDY_HOST before running this example.")
    buddy = BuddyClient(host=buddy_host, port=int(os.environ.get("BUDDY_PORT", "8787")))
    adapter = QwenPawCompatAdapter(stream_id="qwenpaw-demo-1", include_reasoning=False)

    sse_payloads = [
        {
            "object": "response",
            "status": "created",
            "session_id": "qwenpaw-demo-1",
        },
        {
            "object": "message",
            "status": "in_progress",
            "id": "msg_1",
            "type": "message",
        },
        {
            "object": "content",
            "status": "in_progress",
            "type": "text",
            "msg_id": "msg_1",
            "delta": True,
            "text": "Hello from QwenPaw.\n",
        },
        {
            "object": "response",
            "status": "completed",
            "session_id": "qwenpaw-demo-1",
            "usage": {"total_tokens": 123},
        },
    ]

    for payload in sse_payloads:
        for event in adapter.translate(payload):
            buddy.send_event(event)


if __name__ == "__main__":
    main()
