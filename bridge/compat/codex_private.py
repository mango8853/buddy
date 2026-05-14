from __future__ import annotations

from typing import Any, Dict, List

from .base import BuddyCompatAdapter, BuddyEvent


class CodexPrivateCompatAdapter(BuddyCompatAdapter):
    """
    Experimental compatibility layer for Codex Desktop's private host state.

    This adapter is intentionally tiny: it accepts already-inferred lifecycle
    payloads from a local monitor and converts them into Buddy protocol events.
    The monitor itself lives outside the adapter because it depends on private
    local Codex storage and is not part of the stable Buddy wire protocol.
    """

    STATUS_MAP = {
        "thinking": "thinking",
        "running": "running",
        "waiting": "waiting",
        "done": "done",
        "idle": "done",
        "failed": "failed",
    }

    def __init__(
        self,
        stream_id: str,
        name: str = "Codex",
        pet_id: str = "",
        pet_spritesheet_url: str = "",
    ) -> None:
        super().__init__(
            stream_id=stream_id,
            name=name,
            agent_kind="codex",
            pet_id=pet_id,
            pet_spritesheet_url=pet_spritesheet_url,
        )
        self.started = False

    def translate(self, payload: Dict[str, Any]) -> List[BuddyEvent]:
        payload_type = str(payload.get("type") or "")
        if payload_type == "start":
            self.started = True
            return [
                self._stream_start(
                    body=str(payload.get("body") or ""),
                    status=self.STATUS_MAP.get(str(payload.get("status") or "thinking"), "thinking"),
                    max_lines=int(payload.get("maxLines") or 160),
                    max_chars=int(payload.get("maxChars") or 12000),
                )
            ]
        if payload_type == "status":
            if not self.started:
                self.started = True
                return [
                    self._stream_start(
                        body=str(payload.get("body") or ""),
                        status=self.STATUS_MAP.get(str(payload.get("status") or "thinking"), "thinking"),
                    )
                ]
            return [
                self._stream_meta(
                    status=self.STATUS_MAP.get(str(payload.get("status") or "running"), "running"),
                    title=str(payload.get("title") or self.name),
                    body=str(payload.get("body") or ""),
                )
            ]
        if payload_type == "log":
            text = str(payload.get("text") or "")
            if not text:
                return []
            if not self.started:
                self.started = True
                return [self._stream_start(status="thinking"), self._stream_chunk(self.ensure_trailing_newline(text))]
            return [self._stream_chunk(self.ensure_trailing_newline(text))]
        if payload_type == "end":
            if not self.started:
                return []
            return [
                self._stream_end(
                    status=self.STATUS_MAP.get(str(payload.get("status") or "done"), "done"),
                    exit_code=int(payload.get("exitCode") or 0),
                )
            ]
        return []
