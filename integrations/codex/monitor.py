#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.client import BuddyClient
from bridge.compat.codex_private import CodexPrivateCompatAdapter


DEFAULT_STATE_DB = Path.home() / ".codex" / "state_5.sqlite"
DEFAULT_LOG_DB = Path.home() / ".codex" / "logs_2.sqlite"
DEFAULT_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
DEFAULT_STATUS_FILE = Path.home() / ".codex" / "buddy-codex-private.status.json"
RECENT_ROLLOUT_SCAN_BYTES = 1024 * 1024
FINAL_ANSWER_PHASE = "final_answer"


RUN_MARKERS = (
    "run_sampling_request",
    "session_task.turn",
)
DONE_MARKERS = (
    "Agent loop exited",
    "interrupt received: abort current task",
)
WAITING_MARKERS = (
    "waitingOnUserInput",
)


@dataclass
class ThreadInfo:
    thread_id: str
    title: str
    updated_at_ms: int


class CodexPrivateMonitor:
    def __init__(
        self,
        *,
        buddy: BuddyClient,
        state_db: Path,
        log_db: Path,
        thread_id: Optional[str],
        poll_interval: float,
        quiet_done_seconds: float,
        sessions_dir: Path,
        status_file: Path,
    ) -> None:
        self.buddy = buddy
        self.state_db = state_db
        self.log_db = log_db
        self.thread_id = thread_id
        self.poll_interval = poll_interval
        self.quiet_done_seconds = quiet_done_seconds
        self.sessions_dir = sessions_dir
        self.status_file = status_file
        self.last_log_id = 0
        self.last_active_at = 0.0
        self.current_thread: Optional[ThreadInfo] = None
        self.adapter: Optional[CodexPrivateCompatAdapter] = None
        self.started = False
        self.ended = False
        self.rollout_path: Optional[Path] = None
        self.seen_response_keys: Set[str] = set()
        self.last_assistant_text = ""
        self.last_assistant_ts = 0.0
        self.last_assistant_phase = ""
        self.waiting_announced = False
        self.last_error = ""
        self.last_emit_ok_at = 0.0
        self.last_status = "idle"

    def run(self) -> None:
        while True:
            try:
                thread = self.resolve_thread()
                if thread is None:
                    self.last_status = "idle"
                    self.write_status()
                    time.sleep(self.poll_interval)
                    continue
                if self.current_thread is None or self.current_thread.thread_id != thread.thread_id:
                    self.switch_thread(thread)
                new_rows = self.fetch_new_logs(thread.thread_id)
                self.handle_rows(new_rows)
                self.poll_rollout_text()
                self.maybe_finish_due_to_quiet()
                self.write_status()
                time.sleep(self.poll_interval)
            except Exception:
                self.last_error = traceback.format_exc()
                self.write_status()
                time.sleep(max(1.0, self.poll_interval))

    def resolve_thread(self) -> Optional[ThreadInfo]:
        with sqlite3.connect(self.state_db) as conn:
            conn.row_factory = sqlite3.Row
            if self.thread_id:
                row = conn.execute(
                    "SELECT id, title, updated_at_ms FROM threads WHERE id = ? LIMIT 1",
                    (self.thread_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id, title, updated_at_ms FROM threads ORDER BY updated_at_ms DESC LIMIT 1"
                ).fetchone()
            if row is None:
                return None
            return ThreadInfo(
                thread_id=str(row["id"]),
                title=str(row["title"] or "Codex"),
                updated_at_ms=int(row["updated_at_ms"] or 0),
            )

    def switch_thread(self, thread: ThreadInfo) -> None:
        if self.adapter is not None and self.started and not self.ended:
            self.emit({"type": "end", "status": "done", "exitCode": 0})
        self.current_thread = thread
        self.adapter = CodexPrivateCompatAdapter(stream_id=thread.thread_id, name="Codex")
        self.started = False
        self.ended = False
        self.last_active_at = 0.0
        self.last_log_id = self.latest_log_id(thread.thread_id)
        self.rollout_path = self.find_rollout_path(thread.thread_id)
        self.seen_response_keys.clear()
        self.last_assistant_text = ""
        self.last_assistant_ts = 0.0
        self.last_assistant_phase = ""
        self.waiting_announced = False
        self.last_error = ""
        self.prime_recent_rollout_state()
        if self.last_assistant_text:
            title = self.current_thread.title if self.current_thread else "Codex"
            self.emit({"type": "start", "status": "thinking", "body": title})
            self.started = True
            self.ended = False
            self.emit({"type": "log", "text": self.last_assistant_text})

    def latest_log_id(self, thread_id: str) -> int:
        with sqlite3.connect(self.log_db) as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(id), 0) FROM logs WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        return int(row[0] or 0)

    def find_rollout_path(self, thread_id: str) -> Optional[Path]:
        if not self.sessions_dir.exists():
            return None
        matches = sorted(self.sessions_dir.rglob(f"*{thread_id}*.jsonl"))
        return matches[-1] if matches else None

    def prime_recent_rollout_state(self) -> None:
        latest_text = ""
        latest_ts = 0.0
        latest_phase = ""
        for key, ts, phase, text in self.iter_recent_assistant_messages():
            self.seen_response_keys.add(key)
            latest_text = text
            latest_ts = ts
            latest_phase = phase
        if latest_text:
            self.last_assistant_text = latest_text
            self.last_assistant_ts = latest_ts
            self.last_assistant_phase = latest_phase

    def fetch_new_logs(self, thread_id: str) -> List[sqlite3.Row]:
        with sqlite3.connect(self.log_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, ts, level, target, feedback_log_body
                FROM logs
                WHERE thread_id = ? AND id > ?
                ORDER BY id ASC
                """,
                (thread_id, self.last_log_id),
            ).fetchall()
        if rows:
            self.last_log_id = int(rows[-1]["id"])
        return rows

    def handle_rows(self, rows: Iterable[sqlite3.Row]) -> None:
        for row in rows:
            body = str(row["feedback_log_body"] or "")
            if not body:
                continue
            if any(marker in body for marker in RUN_MARKERS):
                self.last_active_at = time.time()
                self.waiting_announced = False
                if not self.started:
                    title = self.current_thread.title if self.current_thread else "Codex"
                    self.emit({"type": "start", "status": "thinking", "body": title})
                    self.started = True
                    self.ended = False
                else:
                    self.emit({"type": "status", "status": "thinking", "body": "Thinking"})
                continue
            if any(marker in body for marker in WAITING_MARKERS):
                self.last_active_at = time.time()
                self.waiting_announced = True
                if not self.started:
                    title = self.current_thread.title if self.current_thread else "Codex"
                    self.emit({"type": "start", "status": "waiting", "body": title})
                    self.started = True
                    self.ended = False
                else:
                    self.emit({"type": "status", "status": "waiting", "body": "Needs input"})
                continue
            if any(marker in body for marker in DONE_MARKERS):
                if self.started and not self.ended:
                    if self.emit({"type": "end", "status": "done", "exitCode": 0}):
                        self.ended = True
                        self.last_active_at = 0.0

    def poll_rollout_text(self) -> None:
        for key, ts, phase, text in self.iter_recent_assistant_messages():
            if key in self.seen_response_keys:
                continue
            self.seen_response_keys.add(key)
            self.last_assistant_text = text
            self.last_assistant_ts = ts
            self.last_assistant_phase = phase
            self.last_active_at = time.time()
            self.waiting_announced = False
            if not self.started:
                title = self.current_thread.title if self.current_thread else "Codex"
                self.emit({"type": "start", "status": "thinking", "body": title})
                self.started = True
                self.ended = False
            self.emit({"type": "log", "text": text})

    def iter_recent_assistant_messages(self) -> List[Tuple[str, float, str, str]]:
        path = self.rollout_path
        if path is None or not path.exists():
            return []
        try:
            size = path.stat().st_size
            start = max(0, size - RECENT_ROLLOUT_SCAN_BYTES)
            with path.open("r", encoding="utf-8", errors="ignore") as fh:
                fh.seek(start)
                if start > 0:
                    fh.readline()
                data = fh.read()
        except Exception:
            return []

        items: List[Tuple[str, float, str, str]] = []
        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            payload = obj.get("payload") or {}
            if obj.get("type") != "response_item":
                continue
            if payload.get("type") != "message" or payload.get("role") != "assistant":
                continue
            text = self.extract_assistant_text(payload)
            if not text:
                continue
            phase = str(payload.get("phase") or "")
            key = f"{obj.get('timestamp','')}|{phase}|{json.dumps(payload.get('content') or [], ensure_ascii=False)}"
            items.append((key, self.parse_timestamp(obj.get("timestamp")), phase, text))
        return items

    @staticmethod
    def extract_assistant_text(payload: Dict[str, object]) -> str:
        content = payload.get("content") or []
        parts: List[str] = []
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "output_text":
                    text = str(block.get("text") or "")
                    if text:
                        parts.append(text)
        return "\n".join(parts).strip()

    def maybe_finish_due_to_quiet(self) -> None:
        if not self.started or self.ended or self.last_active_at <= 0:
            return
        quiet_for = time.time() - max(self.last_active_at, self.last_assistant_ts or 0.0)
        if quiet_for < self.quiet_done_seconds:
            return
        if self.should_mark_waiting():
            if self.emit({"type": "status", "status": "waiting", "body": "Needs input"}):
                self.waiting_announced = True
                self.ended = False
                self.last_active_at = 0.0
            return
        if self.last_assistant_phase != FINAL_ANSWER_PHASE:
            return
        if self.emit({"type": "end", "status": "done", "exitCode": 0}):
            self.ended = True
            self.last_active_at = 0.0

    def should_mark_waiting(self) -> bool:
        if self.waiting_announced:
            return False
        text = (self.last_assistant_text or "").strip()
        if not text:
            return False
        if self.last_assistant_phase == FINAL_ANSWER_PHASE:
            return False
        age = time.time() - self.last_assistant_ts if self.last_assistant_ts else None
        if age is not None and age > 300:
            return False
        return self.looks_like_waiting_prompt(text)

    def emit(self, payload: Dict[str, object]) -> bool:
        if self.adapter is None:
            return False
        ok = True
        for event in self.adapter.translate(payload):
            try:
                self.buddy.send_event(event)
                self.last_emit_ok_at = time.time()
                status = str(event.get("status") or event.get("mood") or "")
                if event.get("type") == "stream_end":
                    self.last_status = status or "done"
                elif status:
                    self.last_status = status
                self.last_error = ""
            except Exception:
                ok = False
                self.last_error = traceback.format_exc()
                traceback.print_exc()
        return ok

    @staticmethod
    def parse_timestamp(value: object) -> float:
        if not value:
            return 0.0
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    @staticmethod
    def looks_like_waiting_prompt(text: str) -> bool:
        lowered = text.lower()
        prompt_markers = [
            "?",
            "？",
            "please confirm",
            "need your approval",
            "do you want",
            "let me know",
            "which one",
            "tell me",
            "confirm",
            "choose",
            "告诉我",
            "请确认",
            "需要你的确认",
            "请选择",
            "要不要",
            "如果你愿意",
            "请提供",
            "请告诉我",
            "你来定",
            "继续吗",
        ]
        return any(marker in lowered for marker in prompt_markers)

    def write_status(self) -> None:
        thread_id = self.current_thread.thread_id if self.current_thread else ""
        title = self.current_thread.title if self.current_thread else ""
        payload = {
            "pid": os.getpid(),
            "threadId": thread_id,
            "threadTitle": title,
            "rolloutPath": str(self.rollout_path) if self.rollout_path else "",
            "started": self.started,
            "ended": self.ended,
            "status": self.last_status,
            "lastActiveAt": self.last_active_at,
            "lastAssistantAt": self.last_assistant_ts,
            "lastAssistantPhase": self.last_assistant_phase,
            "lastAssistantPreview": (self.last_assistant_text or "")[:240],
            "lastEmitOkAt": self.last_emit_ok_at,
            "waitingAnnounced": self.waiting_announced,
            "lastError": self.last_error,
            "updatedAt": time.time(),
        }
        try:
            self.status_file.parent.mkdir(parents=True, exist_ok=True)
            self.status_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Experimental Codex Desktop private-state bridge for Buddy."
    )
    parser.add_argument("--buddy-host", default="10.214.75.86", help="Buddy device host")
    parser.add_argument("--buddy-port", type=int, default=8787, help="Buddy device port")
    parser.add_argument("--state-db", default=str(DEFAULT_STATE_DB), help="Path to Codex state sqlite DB")
    parser.add_argument("--log-db", default=str(DEFAULT_LOG_DB), help="Path to Codex log sqlite DB")
    parser.add_argument("--sessions-dir", default=str(DEFAULT_SESSIONS_DIR), help="Path to Codex sessions directory")
    parser.add_argument("--status-file", default=str(DEFAULT_STATUS_FILE), help="Path to Codex Buddy status json file")
    parser.add_argument("--thread-id", default="", help="Optional Codex thread id to follow")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Polling interval in seconds")
    parser.add_argument(
        "--quiet-done-seconds",
        type=float,
        default=4.0,
        help="Mark the stream done after this many quiet seconds following sampling logs",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    monitor = CodexPrivateMonitor(
        buddy=BuddyClient(host=args.buddy_host, port=args.buddy_port),
        state_db=Path(args.state_db),
        log_db=Path(args.log_db),
        sessions_dir=Path(args.sessions_dir),
        status_file=Path(args.status_file),
        thread_id=args.thread_id or None,
        poll_interval=float(args.poll_interval),
        quiet_done_seconds=float(args.quiet_done_seconds),
    )
    monitor.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
