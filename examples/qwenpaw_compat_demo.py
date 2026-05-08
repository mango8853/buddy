#!/usr/bin/env python3
from bridge import BuddyClient, QwenPawCompatAdapter


def main():
    buddy = BuddyClient()
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
