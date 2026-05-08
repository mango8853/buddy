from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .base import BuddyCompatAdapter, BuddyEvent


class QwenPawCompatAdapter(BuddyCompatAdapter):
    """
    Translate QwenPaw console SSE events and approval records into Buddy
    protocol events.

    QwenPaw emits SSE lines from /api/console/chat using payloads shaped like:
    - {"object":"response","status":"created|in_progress|completed", ...}
    - {"object":"message","type":"reasoning|message", "id":"msg_...", ...}
    - {"object":"content","type":"text","msg_id":"msg_...","delta":true,...}
    """

    def __init__(
        self,
        stream_id: str,
        name: str = "QwenPaw",
        *,
        include_reasoning: bool = False,
    ) -> None:
        super().__init__(stream_id=stream_id, name=name, agent_kind="qwenpaw")
        self.include_reasoning = include_reasoning
        self.started = False
        self.message_types: Dict[str, str] = {}

    def translate(self, payload: Dict[str, Any]) -> List[BuddyEvent]:
        obj = payload.get("object")
        if obj == "response":
            return self._translate_response(payload)
        if obj == "message":
            return self._translate_message(payload)
        if obj == "content":
            return self._translate_content(payload)
        return []

    def _translate_response(self, payload: Dict[str, Any]) -> List[BuddyEvent]:
        status = str(payload.get("status") or "")
        session_id = str(payload.get("session_id") or "")
        if status == "created":
            if self.started:
                return []
            self.started = True
            body = f"QwenPaw session {session_id}" if session_id else "QwenPaw console stream"
            return [self._stream_start(body=body, status="running")]
        if status == "in_progress":
            if not self.started:
                self.started = True
                return [self._stream_start(body="QwenPaw console stream", status="running")]
            return [self._stream_meta(status="running", body="Streaming console output")]
        if status == "completed":
            usage = payload.get("usage") or {}
            summary = ""
            total_tokens = usage.get("total_tokens")
            if total_tokens:
                summary = f"Completed, total tokens {total_tokens}"
            return [
                self._stream_meta(status="done", body=summary),
                self._stream_end(status="done", exit_code=0),
            ]
        if status in {"failed", "error", "cancelled"}:
            error = payload.get("error")
            body = str(error) if error else "QwenPaw stream failed"
            return [
                self._stream_meta(status="failed", body=body),
                self._stream_end(status="failed", exit_code=1),
            ]
        return []

    def _translate_message(self, payload: Dict[str, Any]) -> List[BuddyEvent]:
        message_id = str(payload.get("id") or "")
        message_type = str(payload.get("type") or "message")
        if message_id:
            self.message_types[message_id] = message_type
        if message_type == "reasoning":
            return [self._stream_meta(status="thinking", body="QwenPaw is reasoning")]
        if message_type == "message":
            return [self._stream_meta(status="running", body="QwenPaw is replying")]
        return []

    def _translate_content(self, payload: Dict[str, Any]) -> List[BuddyEvent]:
        if str(payload.get("type") or "") != "text":
            return []
        message_id = str(payload.get("msg_id") or "")
        message_type = self.message_types.get(message_id, "message")
        if message_type == "reasoning" and not self.include_reasoning:
            return []
        text = str(payload.get("text") or "")
        if not text:
            return []
        if not self.started:
            self.started = True
            return [self._stream_start(status="running"), self._stream_chunk(text)]
        return [self._stream_chunk(text)]

    @staticmethod
    def parse_sse_line(line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line.startswith("data:"):
            return None
        raw = line[5:].strip()
        if not raw:
            return None
        return json.loads(raw)

    def approval_record_to_event(self, record: Dict[str, Any]) -> BuddyEvent:
        request_id = str(record.get("request_id") or "")
        root_session_id = str(record.get("root_session_id") or record.get("session_id") or self.stream_id)
        tool_name = str(record.get("tool_name") or "tool")
        severity = str(record.get("severity") or "").upper()
        findings = record.get("findings_count")
        summary = str(record.get("result_summary") or "").strip()

        pieces = []
        if summary:
            pieces.append(summary)
        if severity:
            pieces.append(f"Severity: {severity}")
        if findings not in (None, ""):
            pieces.append(f"Findings: {findings}")

        body = "\n".join(pieces) if pieces else f"QwenPaw requests approval for `{tool_name}`."
        event: BuddyEvent = {
            "type": "approval",
            "id": request_id,
            "streamId": root_session_id,
            "mood": "waiting",
            "title": f"Approve {tool_name}?",
            "body": body,
            "approveLabel": "确认",
            "denyLabel": "拒绝",
        }
        if self.agent_kind:
            event["agentKind"] = self.agent_kind
        return event

    @staticmethod
    def buddy_response_to_qwenpaw_action(
        response: Dict[str, Any],
        record: Dict[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        action = str(response.get("action") or "").lower()
        request_id = str(record.get("request_id") or "")
        session_id = str(record.get("root_session_id") or record.get("session_id") or "")

        if action == "approve":
            return (
                "/api/approval/approve",
                {
                    "request_id": request_id,
                    "session_id": session_id,
                },
            )
        return (
            "/api/approval/deny",
            {
                "request_id": request_id,
                "session_id": session_id,
                "reason": "Denied from Buddy",
            },
        )
