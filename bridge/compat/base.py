from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


BuddyEvent = Dict[str, Any]


class BuddyCompatAdapter:
    """
    Base class for host-specific compatibility layers.

    A compatibility layer translates the host's native events into the
    stable Buddy protocol described in docs/protocol.md.
    """

    def __init__(
        self,
        stream_id: str,
        name: str = "Agent",
        agent_kind: str = "",
        pet_id: str = "",
        pet_spritesheet_url: str = "",
    ) -> None:
        self.stream_id = stream_id
        self.name = name
        self.agent_kind = str(agent_kind or "").strip()
        self.pet_id = str(pet_id or "").strip()
        self.pet_spritesheet_url = str(pet_spritesheet_url or "").strip()

    def translate(self, payload: Dict[str, Any]) -> List[BuddyEvent]:
        raise NotImplementedError

    def _stream_start(
        self,
        *,
        body: str = "",
        status: str = "thinking",
        pet_url: str = "",
        max_lines: int = 160,
        max_chars: int = 12000,
    ) -> BuddyEvent:
        event: BuddyEvent = {
            "type": "stream_start",
            "streamId": self.stream_id,
            "title": self.name,
            "body": body,
            "mood": status,
            "maxLines": int(max_lines),
            "maxChars": int(max_chars),
        }
        if self.agent_kind:
            event["agentKind"] = self.agent_kind
        if self.pet_id:
            event["petId"] = self.pet_id
        if self.pet_spritesheet_url:
            event["petSpritesheetUrl"] = self.pet_spritesheet_url
        if pet_url:
            event["petUrl"] = pet_url
        return event

    def _stream_chunk(self, text: str) -> BuddyEvent:
        event: BuddyEvent = {
            "type": "stream_chunk",
            "streamId": self.stream_id,
            "text": text,
        }
        if self.agent_kind:
            event["agentKind"] = self.agent_kind
        if self.pet_id:
            event["petId"] = self.pet_id
        if self.pet_spritesheet_url:
            event["petSpritesheetUrl"] = self.pet_spritesheet_url
        return event

    def _stream_meta(self, *, status: str, title: Optional[str] = None, body: str = "") -> BuddyEvent:
        event: BuddyEvent = {
            "type": "stream_meta",
            "streamId": self.stream_id,
            "status": status,
            "title": title if title is not None else self.name,
            "body": body,
        }
        if self.agent_kind:
            event["agentKind"] = self.agent_kind
        return event

    def _approval(
        self,
        *,
        approval_id: str,
        title: str,
        body: str,
        approve_label: str = "确认",
        deny_label: str = "拒绝",
    ) -> BuddyEvent:
        event: BuddyEvent = {
            "type": "approval",
            "id": approval_id,
            "streamId": self.stream_id,
            "mood": "waiting",
            "title": title,
            "body": body,
            "approveLabel": approve_label,
            "denyLabel": deny_label,
        }
        if self.agent_kind:
            event["agentKind"] = self.agent_kind
        return event

    def _stream_end(self, *, status: str = "done", exit_code: int = 0) -> BuddyEvent:
        event: BuddyEvent = {
            "type": "stream_end",
            "streamId": self.stream_id,
            "status": status,
            "exitCode": int(exit_code),
        }
        if self.agent_kind:
            event["agentKind"] = self.agent_kind
        return event

    @staticmethod
    def ensure_trailing_newline(text: str) -> str:
        if not text:
            return ""
        return text if text.endswith("\n") else f"{text}\n"

    @staticmethod
    def flatten_text_blocks(blocks: Iterable[Any]) -> str:
        parts: List[str] = []
        for block in blocks:
            if isinstance(block, str):
                parts.append(block)
                continue
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text" and block.get("text"):
                parts.append(str(block["text"]))
            elif block_type == "tool_use":
                name = block.get("name") or "tool"
                parts.append(f"[tool] {name}")
            elif block_type == "tool_result":
                if block.get("content"):
                    parts.append(str(block["content"]))
        return "\n".join(part for part in parts if part)
