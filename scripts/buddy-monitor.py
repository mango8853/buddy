#!/usr/bin/env python3
"""Claude Code persistent monitor for Buddy.

One self-contained process: watches transcript files, detects
turns, streams assistant text. No hooks needed for streaming.

Usage:
  python3 buddy-monitor.py --buddy-host 10.214.75.86 --pet rocky

Started by SessionStart hook, runs for the entire session.
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

DEFAULT_POLL = 0.3
DEFAULT_QUIET_DONE = 4.0
DEFAULT_COOLDOWN = 3.0


def log(msg):
    ts = time.strftime("%H:%M:%S")
    try:
        with open(os.path.expanduser("~/.claude/buddy-monitor.log"), "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except OSError:
        pass


def post_json(host, port, path, payload, timeout=5):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://{host}:{port}{path}",
        data=data, headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception as e:
        log(f"POST {path} FAILED: {e}")
        return False


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


class ClaudeCodeMonitor:
    def __init__(self, buddy_host, buddy_port=8787, pet="rocky",
                 poll_interval=DEFAULT_POLL, quiet_done=DEFAULT_QUIET_DONE,
                 cooldown=DEFAULT_COOLDOWN):
        self.buddy_host = buddy_host
        self.buddy_port = buddy_port
        self.pet = pet
        self.poll_interval = poll_interval
        self.quiet_done = quiet_done
        self.cooldown = cooldown

        self.projects_dir = os.path.expanduser("~/.claude/projects")
        self.current_file = None
        self.last_pos = 0
        self.stream_active = False
        self.stream_id = ""
        self.turn = 0
        self.last_active_at = 0.0
        self.stream_ended_at = 0.0
        self.sent_uuids = set()
        self.watching_session = ""

    def run(self):
        log(f"monitor start host={self.buddy_host} pet={self.pet}")
        while True:
            try:
                self.tick()
            except Exception as e:
                log(f"tick error: {e}")
            time.sleep(self.poll_interval)

    def tick(self):
        # Find active transcript
        tf = self.find_latest_transcript()
        if tf != self.current_file:
            self.switch_file(tf)

        if not self.current_file:
            return

        # Read new content
        try:
            size = os.path.getsize(self.current_file)
        except OSError:
            return

        if size > self.last_pos:
            self.read_new_content(size)

        # Stream ends only on explicit turn boundary (user message).
        # This keeps text displayed until the user sends their next prompt.

    def find_latest_transcript(self):
        if not os.path.isdir(self.projects_dir):
            return None
        best = None
        best_mtime = 0
        for root, dirs, files in os.walk(self.projects_dir):
            for f in files:
                if f.endswith(".jsonl"):
                    fp = os.path.join(root, f)
                    try:
                        mtime = os.path.getmtime(fp)
                        if mtime > best_mtime:
                            best_mtime = mtime
                            best = fp
                    except OSError:
                        pass
        return best

    def switch_file(self, new_file):
        if self.current_file and self.stream_active:
            self.end_stream()
        self.current_file = new_file
        self.last_pos = 0
        self.sent_uuids.clear()
        if new_file:
            try:
                self.last_pos = os.path.getsize(new_file)
            except OSError:
                self.last_pos = 0
            self.watching_session = os.path.basename(new_file).replace(".jsonl", "")
            log(f"watching {self.watching_session}")

    def read_new_content(self, size):
        try:
            with open(self.current_file, "rb") as f:
                f.seek(self.last_pos)
                raw = f.read(size - self.last_pos)
                self.last_pos = size
        except Exception:
            return

        if not raw:
            return

        for raw_line in raw.split(b"\n"):
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line.decode("utf-8", errors="replace"))
            except Exception:
                continue
            self.handle_event(event)

    def is_real_user_prompt(self, event):
        """Real user prompts, not tool results or meta messages."""
        if event.get("isMeta"):
            return False
        msg = event.get("message", {})
        content = msg.get("content", []) if isinstance(msg, dict) else []
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    return False  # Tool result, not a real prompt
        return True

    def handle_event(self, event):
        etype = event.get("type", "")

        if etype == "user" and self.is_real_user_prompt(event):
            # Turn boundary: user sent a new message, current turn is done
            if self.stream_active:
                self.end_stream()
            return

        if etype != "assistant":
            return

        uuid = event.get("uuid", "")
        if uuid in self.sent_uuids:
            return
        self.sent_uuids.add(uuid)

        text = extract_text(event.get("message", {}))
        if not text:
            return

        if not self.stream_active:
            # Check cooldown
            if self.stream_ended_at > 0:
                if time.time() - self.stream_ended_at < self.cooldown:
                    return  # Still in cooldown
            self.start_stream()

        post_json(self.buddy_host, self.buddy_port, "/api/event", {
            "type": "stream_chunk",
            "streamId": self.stream_id,
            "text": text,
        })
        self.last_active_at = time.time()

    def start_stream(self):
        # Respect cooldown between turns
        if self.stream_ended_at > 0:
            if time.time() - self.stream_ended_at < self.cooldown:
                return
        self.turn += 1
        sid = self.watching_session[:8] if self.watching_session else "unknown"
        self.stream_id = f"cc-{sid}-{self.turn}"
        self.stream_active = True
        self.last_active_at = time.time()

        post_json(self.buddy_host, self.buddy_port, "/api/event", {
            "type": "stream_start",
            "streamId": self.stream_id,
            "title": "Claude Code",
            "body": "Working...",
            "mood": "running",
            "petId": self.pet,
            "maxLines": 160,
            "maxChars": 12000,
        })
        log(f"stream start {self.stream_id}")

    def end_stream(self):
        if not self.stream_active:
            return
        post_json(self.buddy_host, self.buddy_port, "/api/event", {
            "type": "stream_end",
            "streamId": self.stream_id,
            "status": "done",
            "exitCode": 0,
        })
        log(f"stream end {self.stream_id}")
        self.stream_active = False
        self.last_active_at = 0.0
        self.stream_ended_at = time.time()


def main():
    parser = argparse.ArgumentParser(description="Claude Code Buddy Monitor")
    parser.add_argument("--buddy-host", default=os.environ.get("BUDDY_HOST", "localhost"))
    parser.add_argument("--buddy-port", type=int, default=int(os.environ.get("BUDDY_PORT", "8787")))
    parser.add_argument("--pet", default=os.environ.get("BUDDY_PET_ID", "rocky"))
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL)
    parser.add_argument("--quiet-done", type=float, default=DEFAULT_QUIET_DONE)
    parser.add_argument("--cooldown", type=float, default=DEFAULT_COOLDOWN)
    args = parser.parse_args()

    monitor = ClaudeCodeMonitor(
        buddy_host=args.buddy_host,
        buddy_port=args.buddy_port,
        pet=args.pet,
        poll_interval=args.poll_interval,
        quiet_done=args.quiet_done,
        cooldown=args.cooldown,
    )
    monitor.run()


if __name__ == "__main__":
    main()
