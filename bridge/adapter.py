#!/usr/bin/env python3
import argparse
import os
import json
import subprocess
import sys
import time

try:
    from bridge import BuddyClient
except ImportError:
    from client import BuddyClient


def env_default(name, fallback):
    value = os.environ.get(name)
    if value is None or value == "":
        return fallback
    return value


def flush_buffer(session, buffer, last_flush, interval, force=False):
    if not buffer:
        return last_flush
    now = time.monotonic()
    if not force and (now - last_flush) < interval:
        return last_flush
    text = "".join(buffer)
    buffer[:] = []
    session.log(text)
    return now


def build_session(args):
    client = BuddyClient(host=args.host, port=args.port, timeout=args.timeout)
    stream_id = args.id or f"agent-{int(time.time() * 1000)}"
    session = client.agent(
        stream_id,
        name=args.name,
        status=args.status,
        body=args.body or "",
    )
    return session


def command_run(args):
    session = build_session(args)
    interval = max(0.04, args.flush_ms / 1000.0)
    command = list(args.exec)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("run requires a command after --exec")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None
    buffer = []
    last_flush = time.monotonic()
    try:
        for line in iter(process.stdout.readline, ""):
            if not line:
                break
            buffer.append(line)
            last_flush = flush_buffer(session, buffer, last_flush, interval, force=False)
    finally:
        process.stdout.close()
    exit_code = process.wait()
    flush_buffer(session, buffer, last_flush, interval, force=True)
    session.end(status=args.end_status or ("done" if exit_code == 0 else "failed"), exit_code=exit_code)
    if exit_code:
        raise SystemExit(exit_code)


def command_stdin(args):
    if sys.stdin.isatty():
        raise SystemExit("stdin mode expects piped input")
    session = build_session(args)
    interval = max(0.04, args.flush_ms / 1000.0)
    buffer = []
    last_flush = time.monotonic()
    for line in sys.stdin:
        buffer.append(line)
        last_flush = flush_buffer(session, buffer, last_flush, interval, force=False)
    flush_buffer(session, buffer, last_flush, interval, force=True)
    if not args.no_end:
        session.end(status=args.end_status or "done", exit_code=0)


def command_jsonl(args):
    if sys.stdin.isatty():
        raise SystemExit("jsonl mode expects piped JSON lines")
    session = build_session(args)
    ended = False
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"invalid JSON line: {line}") from exc
        event_type = str(event.get("type", "log"))
        if event_type in ("log", "chunk", "append"):
            session.log(str(event.get("text", event.get("append", ""))))
        elif event_type in ("status", "meta"):
            session.status_update(
                str(event.get("status", "running")),
                name=str(event.get("name", "")),
                body=str(event.get("body", "")),
            )
        elif event_type == "approval":
            session.approval(
                str(event.get("title", "Need approval")),
                str(event.get("body", "")),
                approval_id=event.get("approvalId"),
                approve_label=str(event.get("approveLabel", "确认")),
                deny_label=str(event.get("denyLabel", "拒绝")),
            )
        elif event_type == "end":
            session.end(
                status=str(event.get("status", args.end_status or "done")),
                exit_code=int(event.get("exitCode", 0)),
            )
            ended = True
            break
        else:
            raise SystemExit(f"unsupported event type: {event_type}")
    if not ended and not args.no_end:
        session.end(status=args.end_status or "done", exit_code=0)


def parser():
    root = argparse.ArgumentParser(description="Local adapter for mirroring agent activity to Buddy.")
    root.add_argument("--host", default=env_default("BUDDY_HOST", "10.214.75.86"))
    root.add_argument("--port", type=int, default=int(env_default("BUDDY_PORT", 8787)))
    root.add_argument("--timeout", type=float, default=float(env_default("BUDDY_TIMEOUT", 5)))
    root.add_argument("--id")
    root.add_argument("--name", default=env_default("BUDDY_NAME", "Agent"))
    root.add_argument("--status", default=env_default("BUDDY_STATUS", "running"))
    root.add_argument("--body", default=env_default("BUDDY_BODY", ""))
    root.add_argument("--flush-ms", type=float, default=float(env_default("BUDDY_FLUSH_MS", 120)))
    root.add_argument("--end-status", default=env_default("BUDDY_END_STATUS", ""))
    root.add_argument("--no-end", action="store_true")

    sub = root.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run")
    run.add_argument("--exec", nargs=argparse.REMAINDER, required=True, help="command to run; use --exec <cmd> ...")
    run.set_defaults(func=command_run)

    stdin_mode = sub.add_parser("stdin")
    stdin_mode.set_defaults(func=command_stdin)

    jsonl = sub.add_parser("jsonl")
    jsonl.set_defaults(func=command_jsonl)

    return root


def main(argv=None):
    args = parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
