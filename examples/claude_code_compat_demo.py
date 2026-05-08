#!/usr/bin/env python3
import os

from bridge import BuddyClient, ClaudeCodeCompatAdapter


def main():
    buddy_host = os.environ.get("BUDDY_HOST")
    if not buddy_host:
        raise SystemExit("Set BUDDY_HOST before running this example.")
    buddy = BuddyClient(host=buddy_host, port=int(os.environ.get("BUDDY_PORT", "8787")))
    adapter = ClaudeCodeCompatAdapter(stream_id="claude-demo-1")

    native_payloads = [
        {
            "type": "snapshot",
            "status": "running",
            "msg": "Checking environment...",
            "entries": [
                "Preparing command...",
                "Checking environment...",
            ],
        },
        {
            "type": "snapshot",
            "status": "waiting",
            "msg": "Approval requested...",
            "entries": [
                "Approval requested...",
                "Waiting for user...",
            ],
            "prompt": {
                "id": "approval-1",
                "title": "Allow continue?",
                "body": "Need your approval before the next step.",
            },
        },
        {
            "type": "turn",
            "status": "done",
            "content": [
                {"type": "text", "text": "Approved. Resuming stream..."},
                {"type": "text", "text": "Running next step..."},
            ],
        },
    ]

    for payload in native_payloads:
        for event in adapter.translate(payload):
            buddy.send_event(event)


if __name__ == "__main__":
    main()
