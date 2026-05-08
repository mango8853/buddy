from __future__ import annotations

from typing import Any, Dict, List

from .base import BuddyCompatAdapter, BuddyEvent


class OpenClawCompatAdapter(BuddyCompatAdapter):
    """
    Translate a typical openclaw-style lifecycle payload into Buddy events.

    Expected payload shape:
    - {"type": "start", "body": "...", "status": "running"}
    - {"type": "log", "text": "..."}
    - {"type": "status", "status": "waiting", "body": "..."}
    - {"type": "approval", "id": "...", "title": "...", "body": "..."}
    - {"type": "end", "status": "done", "exitCode": 0}
    """

    def __init__(self, stream_id: str, name: str = "openclaw") -> None:
        super().__init__(stream_id=stream_id, name=name, agent_kind="openclaw")

    def translate(self, payload: Dict[str, Any]) -> List[BuddyEvent]:
        payload_type = payload.get("type")
        if payload_type == "start":
            return [
                self._stream_start(
                    body=str(payload.get("body") or ""),
                    status=str(payload.get("status") or "running"),
                    pet_url=str(payload.get("petUrl") or ""),
                    max_lines=int(payload.get("maxLines") or 160),
                    max_chars=int(payload.get("maxChars") or 12000),
                )
            ]
        if payload_type == "log":
            return [self._stream_chunk(self.ensure_trailing_newline(str(payload.get("text") or "")))]
        if payload_type == "status":
            return [
                self._stream_meta(
                    status=str(payload.get("status") or "running"),
                    title=str(payload.get("title") or self.name),
                    body=str(payload.get("body") or ""),
                )
            ]
        if payload_type == "approval":
            approval_id = str(payload.get("id") or f"{self.stream_id}-approval")
            return [
                self._approval(
                    approval_id=approval_id,
                    title=str(payload.get("title") or "Approval requested"),
                    body=str(payload.get("body") or "Waiting for user approval."),
                    approve_label=str(payload.get("approveLabel") or "确认"),
                    deny_label=str(payload.get("denyLabel") or "拒绝"),
                )
            ]
        if payload_type == "end":
            return [
                self._stream_end(
                    status=str(payload.get("status") or "done"),
                    exit_code=int(payload.get("exitCode") or 0),
                )
            ]
        return []
