from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import BuddyCompatAdapter, BuddyEvent


class ClaudeDesktopBuddyCompatAdapter(BuddyCompatAdapter):
    """
    Translate Anthropic's Claude Desktop Hardware Buddy protocol payloads into
    Buddy protocol events.

    Native payloads are newline-delimited JSON objects described in
    claude-desktop-buddy/REFERENCE.md. The two most important host-facing
    payload families are:

    - heartbeat snapshots:
      {
        "total": 3,
        "running": 1,
        "waiting": 1,
        "msg": "approve: Bash",
        "entries": ["10:42 git push", "10:41 yarn test"],
        "tokens": 184502,
        "tokens_today": 31200,
        "prompt": {"id": "req_abc123", "tool": "Bash", "hint": "rm -rf /tmp/foo"}
      }

    - completed turn events:
      {
        "evt": "turn",
        "role": "assistant",
        "content": [{"type": "text", "text": "..."}]
      }
    """

    def __init__(self, stream_id: str, name: str = "Claude") -> None:
        super().__init__(stream_id=stream_id, name=name, agent_kind="claude")
        self.started = False
        self.last_entries: List[str] = []
        self.last_prompt_id: str = ""

    def translate(self, payload: Dict[str, Any]) -> List[BuddyEvent]:
        if payload.get("evt") == "turn":
            return self.translate_turn(payload)
        if any(key in payload for key in ("total", "running", "waiting", "entries", "prompt", "tokens", "tokens_today", "msg")):
            return self.translate_snapshot(payload)
        return []

    def translate_snapshot(self, snapshot: Dict[str, Any]) -> List[BuddyEvent]:
        events: List[BuddyEvent] = []
        status = self._snapshot_status(snapshot)
        body = self._snapshot_body(snapshot)

        if not self.started:
            events.append(self._stream_start(body=body, status=status))
            self.started = True
        else:
            events.append(self._stream_meta(status=status, body=body))

        new_lines = self._extract_new_entry_lines(snapshot.get("entries") or [])
        if new_lines:
            events.append(self._stream_chunk(self.ensure_trailing_newline("\n".join(new_lines))))

        prompt = snapshot.get("prompt") or {}
        prompt_id = str(prompt.get("id") or "")
        if prompt_id and prompt_id != self.last_prompt_id:
            self.last_prompt_id = prompt_id
            title = str(prompt.get("title") or prompt.get("tool") or "Approval requested")
            prompt_body = str(prompt.get("body") or prompt.get("hint") or body or "Waiting for permission.")
            events.append(self._approval(approval_id=prompt_id, title=title, body=prompt_body))
        elif not prompt_id:
            self.last_prompt_id = ""

        return events

    def translate_turn(self, turn: Dict[str, Any]) -> List[BuddyEvent]:
        events: List[BuddyEvent] = []
        role = str(turn.get("role") or "")
        content = turn.get("content") or []
        text = self.flatten_text_blocks(content)

        if not self.started:
            events.append(self._stream_start(status="running"))
            self.started = True

        if text:
            events.append(self._stream_chunk(self.ensure_trailing_newline(text)))

        if role == "assistant":
            events.append(self._stream_meta(status="done", body="Claude completed a turn"))
            events.append(self._stream_end(status="done", exit_code=0))
        return events

    @staticmethod
    def buddy_response_to_permission_command(response: Dict[str, Any], approval_id: str) -> Dict[str, Any]:
        action = str(response.get("action") or "").lower()
        decision = "once" if action == "approve" else "deny"
        return {
            "cmd": "permission",
            "id": approval_id,
            "decision": decision,
        }

    @staticmethod
    def _snapshot_status(snapshot: Dict[str, Any]) -> str:
        waiting = int(snapshot.get("waiting") or 0)
        running = int(snapshot.get("running") or 0)
        total = int(snapshot.get("total") or 0)
        if waiting > 0:
            return "waiting"
        if running > 0:
            return "thinking"
        if total > 0:
            return "done"
        return "idle"

    @staticmethod
    def _snapshot_body(snapshot: Dict[str, Any]) -> str:
        msg = str(snapshot.get("msg") or "").strip()
        if msg:
            return msg
        total = int(snapshot.get("total") or 0)
        running = int(snapshot.get("running") or 0)
        waiting = int(snapshot.get("waiting") or 0)
        if total <= 0:
            return "No Claude sessions open"
        if waiting > 0:
            return f"{waiting} Claude session(s) waiting for permission"
        if running > 0:
            return f"{running} Claude session(s) running"
        return f"{total} Claude session(s) connected"

    def _extract_new_entry_lines(self, raw_entries: List[Any]) -> List[str]:
        entries = [str(entry).strip() for entry in raw_entries if str(entry).strip()]
        if not entries:
            self.last_entries = []
            return []

        novel_newest_first: List[str] = []
        seen = set(self.last_entries)
        for entry in entries:
            if entry in seen:
                break
            novel_newest_first.append(entry)

        self.last_entries = entries
        if not novel_newest_first:
            return []
        return list(reversed(novel_newest_first))
