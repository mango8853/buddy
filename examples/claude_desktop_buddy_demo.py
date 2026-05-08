#!/usr/bin/env python3
import os

try:
    from bridge import BuddyClient, ClaudeDesktopBuddyCompatAdapter
except ImportError:
    import pathlib
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from bridge import BuddyClient, ClaudeDesktopBuddyCompatAdapter


def main():
    buddy_host = os.environ.get("BUDDY_HOST")
    if not buddy_host:
        raise SystemExit("Set BUDDY_HOST before running this example.")
    buddy = BuddyClient(host=buddy_host, port=int(os.environ.get("BUDDY_PORT", "8787")))
    adapter = ClaudeDesktopBuddyCompatAdapter(stream_id="claude-desktop-demo-1")

    native_payloads = [
        {
            "total": 2,
            "running": 1,
            "waiting": 0,
            "msg": "reading file...",
            "entries": [
                "10:42 reading file...",
                "10:41 planning next step...",
            ],
            "tokens": 184502,
            "tokens_today": 31200,
        },
        {
            "total": 2,
            "running": 0,
            "waiting": 1,
            "msg": "approve: Bash",
            "entries": [
                "10:43 approve: Bash",
                "10:42 reading file...",
            ],
            "prompt": {
                "id": "req_abc123",
                "tool": "Bash",
                "hint": "rm -rf /tmp/foo",
            },
        },
        {
            "evt": "turn",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Approved. Continuing the task."},
                {"type": "text", "text": "All checks passed."},
            ],
        },
    ]

    for payload in native_payloads:
        for event in adapter.translate(payload):
            buddy.send_event(event)


if __name__ == "__main__":
    main()
