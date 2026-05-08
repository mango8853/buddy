from __future__ import annotations

from typing import Any, Dict, List

from .base import BuddyCompatAdapter, BuddyEvent


class ClaudeCodeCompatAdapter(BuddyCompatAdapter):
    """
    Translate Claude Code-style host snapshots and turn events into Buddy
    protocol events.

    This adapter is intentionally host-facing: it does not fetch Claude data
    itself. A host integration should obtain the native payloads and pass them
    through `translate()`.
    """

    STATUS_MAP = {
        "thinking": "thinking",
        "running": "running",
        "waiting": "waiting",
        "idle": "done",
        "complete": "done",
        "done": "done",
        "error": "failed",
        "failed": "failed",
    }

    def __init__(self, stream_id: str, name: str = "Claude Code") -> None:
        super().__init__(stream_id=stream_id, name=name, agent_kind="claude-code")
        self.started = False

    def translate(self, payload: Dict[str, Any]) -> List[BuddyEvent]:
        event_type = payload.get("type")
        if event_type == "snapshot":
            return self.translate_snapshot(payload)
        if event_type == "turn":
            return self.translate_turn(payload)
        if event_type == "response":
            return []
        return []

    def translate_snapshot(self, snapshot: Dict[str, Any]) -> List[BuddyEvent]:
        events: List[BuddyEvent] = []
        status = self.STATUS_MAP.get(snapshot.get("status"), "running")
        body = snapshot.get("msg") or ""

        if not self.started:
            events.append(self._stream_start(body=body, status=status))
            self.started = True
        else:
            events.append(self._stream_meta(status=status, body=body))

        entries = snapshot.get("entries") or []
        text = self.flatten_text_blocks(entries)
        if text:
            events.append(self._stream_chunk(self.ensure_trailing_newline(text)))

        prompt = snapshot.get("prompt") or {}
        if prompt:
            approval_id = str(prompt.get("id") or f"{self.stream_id}-approval")
            title = str(prompt.get("title") or prompt.get("tool") or "Approval requested")
            prompt_body = str(prompt.get("body") or prompt.get("hint") or body or "Waiting for user approval.")
            events.append(self._approval(approval_id=approval_id, title=title, body=prompt_body))
        return events

    def translate_turn(self, turn: Dict[str, Any]) -> List[BuddyEvent]:
        events: List[BuddyEvent] = []
        content = turn.get("content") or []
        text = self.flatten_text_blocks(content)
        if not self.started:
            events.append(self._stream_start(status="running"))
            self.started = True
        if text:
            events.append(self._stream_chunk(self.ensure_trailing_newline(text)))

        turn_status = self.STATUS_MAP.get(turn.get("status"), "")
        if turn_status in {"done", "failed"}:
            exit_code = 0 if turn_status == "done" else 1
            events.append(self._stream_end(status=turn_status, exit_code=exit_code))
        return events
