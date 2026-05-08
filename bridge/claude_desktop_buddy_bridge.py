#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Iterable

try:
    from bridge import BuddyClient, ClaudeDesktopBuddyCompatAdapter
except ImportError:
    from client import BuddyClient
    from compat.claude_desktop_buddy import ClaudeDesktopBuddyCompatAdapter


def iter_ndjson_lines(lines: Iterable[str]):
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        yield json.loads(line)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Translate Claude Desktop Buddy newline-delimited JSON into Buddy events.",
    )
    parser.add_argument("--buddy-host", default=os.environ.get("BUDDY_HOST", "localhost"))
    parser.add_argument("--buddy-port", type=int, default=8787)
    parser.add_argument("--stream-id", default="claude-desktop")
    parser.add_argument("--name", default="Claude")
    parser.add_argument(
        "--echo-decisions",
        action="store_true",
        help="Print Claude permission command JSON examples to stdout when approval payloads are seen.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    buddy = BuddyClient(host=args.buddy_host, port=args.buddy_port)
    adapter = ClaudeDesktopBuddyCompatAdapter(stream_id=args.stream_id, name=args.name)

    for payload in iter_ndjson_lines(sys.stdin):
        for event in adapter.translate(payload):
            buddy.send_event(event)
            if args.echo_decisions and event.get("type") == "approval":
                example = ClaudeDesktopBuddyCompatAdapter.buddy_response_to_permission_command(
                    {"action": "approve"},
                    str(event.get("id") or ""),
                )
                print(json.dumps(example, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
