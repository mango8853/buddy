#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from typing import Dict

try:
    from bridge import BuddyClient, QwenPawCompatAdapter
except ImportError:
    from client import BuddyClient
    from compat.qwenpaw import QwenPawCompatAdapter


DEFAULT_QWENPAW_URL = "http://127.0.0.1:8088"


def post_json(base_url: str, path: str, payload: Dict, timeout: float = 60):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        urllib.parse.urljoin(base_url, path),
        data=data,
        headers={"content-type": "application/json; charset=utf-8"},
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=timeout)


def get_json(base_url: str, path: str, timeout: float = 15) -> Dict:
    with urllib.request.urlopen(urllib.parse.urljoin(base_url, path), timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace") or "{}")


def qwenpaw_chat_payload(args) -> Dict:
    return {
        "channel": "console",
        "user_id": args.user_id,
        "session_id": args.session_id,
        "input": [
            {
                "content": [
                    {"type": "text", "text": args.text},
                ]
            }
        ],
    }


def command_chat(args):
    buddy = BuddyClient(host=args.buddy_host, port=args.buddy_port, timeout=args.buddy_timeout)
    adapter = QwenPawCompatAdapter(
        stream_id=args.session_id,
        name=args.name,
        include_reasoning=args.include_reasoning,
    )

    with post_json(args.qwenpaw_url, "/api/console/chat", qwenpaw_chat_payload(args), timeout=args.timeout) as response:
        for raw in response:
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            payload = adapter.parse_sse_line(line)
            if not payload:
                continue
            for event in adapter.translate(payload):
                if args.idle_timeout_ms and event.get("type") == "stream_start":
                    event["idleTimeoutMs"] = int(args.idle_timeout_ms)
                buddy.send_event(event)


def command_watch_approvals(args):
    buddy = BuddyClient(host=args.buddy_host, port=args.buddy_port, timeout=args.buddy_timeout)
    adapter = QwenPawCompatAdapter(stream_id="qwenpaw-approval", name=args.name)
    seen: Dict[str, Dict] = {}

    while True:
        listing = get_json(args.qwenpaw_url, "/api/approval/list", timeout=args.timeout)
        pending = listing.get("pending_approvals", [])
        for record in pending:
            request_id = str(record.get("request_id") or "")
            if not request_id:
                continue
            if request_id not in seen:
                seen[request_id] = record
                buddy.send_event(adapter.approval_record_to_event(record))

            responses_url = f"{args.responses_url}?id={urllib.parse.quote(request_id)}&consume=1"
            result = get_json("", responses_url, timeout=args.timeout) if responses_url.startswith("http") else {}
            for response in result.get("responses", []):
                path, payload = adapter.buddy_response_to_qwenpaw_action(response, record)
                with post_json(args.qwenpaw_url, path, payload, timeout=args.timeout):
                    pass
                seen.pop(request_id, None)

        if args.once:
            break
        time.sleep(args.interval)


def parser():
    root = argparse.ArgumentParser(description="Mirror QwenPaw output into Buddy.")
    root.add_argument("--qwenpaw-url", default=DEFAULT_QWENPAW_URL)
    root.add_argument("--buddy-host", default=os.environ.get("BUDDY_HOST", "localhost"))
    root.add_argument("--buddy-port", type=int, default=8787)
    root.add_argument("--buddy-timeout", type=float, default=5)
    root.add_argument("--timeout", type=float, default=60)
    root.add_argument("--name", default="QwenPaw")

    sub = root.add_subparsers(dest="command", required=True)

    chat = sub.add_parser("chat")
    chat.add_argument("--text", required=True)
    chat.add_argument("--user-id", default="buddy-qwenpaw")
    chat.add_argument("--session-id", default=f"qwenpaw-{int(time.time())}")
    chat.add_argument("--include-reasoning", action="store_true")
    chat.add_argument("--idle-timeout-ms", type=int, default=0)
    chat.set_defaults(func=command_chat)

    approvals = sub.add_parser("watch-approvals")
    approvals.add_argument("--responses-url", default="http://localhost:8799/responses")
    approvals.add_argument("--interval", type=float, default=1.0)
    approvals.add_argument("--once", action="store_true")
    approvals.set_defaults(func=command_watch_approvals)

    return root


def main(argv=None):
    args = parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
