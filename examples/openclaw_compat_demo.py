#!/usr/bin/env python3
import os

from bridge import BuddyClient, OpenClawCompatAdapter


def main():
    buddy_host = os.environ.get("BUDDY_HOST")
    if not buddy_host:
        raise SystemExit("Set BUDDY_HOST before running this example.")
    buddy = BuddyClient(host=buddy_host, port=int(os.environ.get("BUDDY_PORT", "8787")))
    adapter = OpenClawCompatAdapter(stream_id="openclaw-demo-1")

    native_payloads = [
        {"type": "start", "status": "running", "body": "openclaw booting"},
        {"type": "log", "text": "Loading tools...\n"},
        {"type": "status", "status": "waiting", "body": "Need approval"},
        {
            "type": "approval",
            "id": "approval-1",
            "title": "Allow continue?",
            "body": "Need your approval before the next step.",
        },
        {"type": "end", "status": "done", "exitCode": 0},
    ]

    for payload in native_payloads:
        for event in adapter.translate(payload):
            buddy.send_event(event)


if __name__ == "__main__":
    main()
