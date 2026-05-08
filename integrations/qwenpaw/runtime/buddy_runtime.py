from __future__ import annotations

import json
import queue
import sys
import threading
import time
import urllib.parse
import urllib.request
from functools import wraps
from pathlib import Path
from typing import Any, Dict


INSTALL_DIR = Path("__INSTALL_DIR__")
if str(INSTALL_DIR) not in sys.path:
    sys.path.insert(0, str(INSTALL_DIR))

ENV_PATH = INSTALL_DIR / "buddy.env"
DEFAULT_QWENPAW_URL = "http://127.0.0.1:8088"
_lock = threading.Lock()
_event_queue: queue.Queue = queue.Queue()
_sender_started = False
_poller_started = False
_adapters: Dict[str, QwenPawCompatAdapter] = {}
_pending_approvals: Dict[str, Dict[str, Any]] = {}
_relay_installed = False
_relay_state: Dict[str, Dict[str, Any]] = {}


def _buddy_client_class():
    from bridge import BuddyClient

    return BuddyClient


def _qwenpaw_compat_adapter_class():
    from bridge import QwenPawCompatAdapter

    return QwenPawCompatAdapter


def _load_env() -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _config() -> Dict[str, str]:
    return _load_env()


def _enabled() -> bool:
    cfg = _config()
    return bool(cfg.get("BUDDY_HOST"))


def _build_client() -> BuddyClient:
    cfg = _config()
    BuddyClient = _buddy_client_class()
    return BuddyClient(
        host=cfg.get("BUDDY_HOST", "localhost"),
        port=int(cfg.get("BUDDY_PORT", "8787")),
        timeout=float(cfg.get("BUDDY_TIMEOUT", "5")),
    )


def _name() -> str:
    return _config().get("BUDDY_NAME", "QwenPaw")


def _qwenpaw_url() -> str:
    return _config().get("QWENPAW_URL", DEFAULT_QWENPAW_URL)


def _idle_timeout_ms() -> int:
    raw = _config().get("BUDDY_IDLE_TIMEOUT_MS", "")
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def _include_reasoning() -> bool:
    return _config().get("QWENPAW_BUDDY_INCLUDE_REASONING", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _responses_url() -> str:
    return _config().get("BUDDY_RESPONSES_URL", "")


def _approval_poll_interval() -> float:
    raw = _config().get("BUDDY_APPROVAL_POLL_INTERVAL", "1.0")
    try:
        return max(0.2, float(raw))
    except ValueError:
        return 1.0


def _post_json_absolute(url: str, payload: Dict[str, Any], timeout: float = 10) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"content-type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout):
        return


def _get_json_absolute(url: str, timeout: float = 10) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace") or "{}")


def _ensure_sender_thread() -> None:
    global _sender_started
    if _sender_started or not _enabled():
        return
    with _lock:
        if _sender_started:
            return
        thread = threading.Thread(target=_sender_loop, daemon=True, name="qwenpaw-buddy-sender")
        thread.start()
        _sender_started = True


def _ensure_poller_thread() -> None:
    global _poller_started
    if _poller_started or not _enabled() or not _responses_url():
        return
    with _lock:
        if _poller_started:
            return
        thread = threading.Thread(target=_approval_poller_loop, daemon=True, name="qwenpaw-buddy-approval-poller")
        thread.start()
        _poller_started = True


def relay_console_sse(event_line: str, session_id: str) -> None:
    if not _enabled() or not event_line or not session_id:
        return
    _ensure_sender_thread()
    _event_queue.put(("sse", session_id, event_line))


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _session_id_from_context(
    *,
    channel_name: str,
    request: Any = None,
    to_handle: str = "",
    meta: Dict[str, Any] | None = None,
) -> str:
    if request is not None:
        session_id = getattr(request, "session_id", "") or ""
        if session_id:
            return str(session_id)
        request_meta = getattr(request, "channel_meta", None) or {}
        for key in ("session_id", "conversation_id", "chat_id"):
            if request_meta.get(key):
                return str(request_meta[key])
        user_id = getattr(request, "user_id", "") or ""
        if user_id:
            to_handle = to_handle or user_id
    meta = meta or {}
    for key in ("session_id", "conversation_id", "chat_id"):
        if meta.get(key):
            return str(meta[key])
    if to_handle:
        return f"{channel_name}:{to_handle}"
    return channel_name or "buddy"


def _text_from_parts(parts: Any) -> str:
    if not parts:
        return ""
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, str):
            if part.strip():
                chunks.append(part)
            continue
        part_type = getattr(part, "type", None)
        if part_type == "text" and getattr(part, "text", None):
            chunks.append(_normalize_text(getattr(part, "text")))
        elif part_type == "refusal" and getattr(part, "refusal", None):
            chunks.append(_normalize_text(getattr(part, "refusal")))
        elif part_type == "image" and getattr(part, "image_url", None):
            chunks.append(f"[Image: {getattr(part, 'image_url')}]")
        elif part_type == "video" and getattr(part, "video_url", None):
            chunks.append(f"[Video: {getattr(part, 'video_url')}]")
        elif part_type == "audio" and getattr(part, "data", None):
            chunks.append("[Audio]")
        elif part_type == "file":
            file_url = getattr(part, "file_url", None) or getattr(part, "file_id", None)
            if file_url:
                chunks.append(f"[File: {file_url}]")
    return "\n".join(chunk for chunk in chunks if str(chunk).strip())


def _queue_generic_event(kind: str, payload: Dict[str, Any]) -> None:
    if not _enabled():
        return
    _ensure_sender_thread()
    _event_queue.put((kind, payload))


def relay_channel_start(
    *,
    channel_name: str,
    session_id: str,
    title: str,
    body: str = "",
    status: str = "running",
) -> None:
    if not session_id or not _enabled():
        return
    with _lock:
        existing = _relay_state.get(session_id)
        if existing and existing.get("active"):
            return
        _relay_state[session_id] = {
            "active": True,
            "title": title,
            "channel": channel_name,
        }
    _queue_generic_event(
        "channel_start",
        {
            "channel_name": channel_name,
            "session_id": session_id,
            "title": title,
            "body": body,
            "status": status,
        },
    )


def relay_channel_chunk(
    *,
    channel_name: str,
    session_id: str,
    text: str,
    title: str,
    body: str = "",
) -> None:
    if not session_id or not _enabled():
        return
    chunk = _normalize_text(text).rstrip()
    if not chunk:
        return
    with _lock:
        existing = _relay_state.get(session_id)
        if not existing or not existing.get("active"):
            _relay_state[session_id] = {
                "active": True,
                "title": title,
                "channel": channel_name,
            }
            kind = "channel_start"
        else:
            kind = "channel_chunk"
    _queue_generic_event(
        kind,
        {
            "channel_name": channel_name,
            "session_id": session_id,
            "title": title,
            "body": body or chunk,
            "text": chunk,
        },
    )


def relay_channel_end(
    *,
    channel_name: str,
    session_id: str,
    title: str,
    status: str = "done",
    exit_code: int = 0,
    body: str = "",
) -> None:
    if not session_id or not _enabled():
        return
    with _lock:
        existing = _relay_state.pop(session_id, None)
        if existing is None:
            return
    _queue_generic_event(
        "channel_end",
        {
            "channel_name": channel_name,
            "session_id": session_id,
            "title": title,
            "body": body,
            "status": status,
            "exit_code": int(exit_code),
        },
    )


def _wrap_async_method(cls: Any, method_name: str, relay_kind: str) -> None:
    original = getattr(cls, method_name, None)
    if not callable(original) or getattr(original, "__buddy_wrapped__", False):
        return

    @wraps(original)
    async def wrapped(self, *args, **kwargs):
        try:
            if relay_kind == "send":
                to_handle = _normalize_text(args[0]) if args else _normalize_text(kwargs.get("to_handle", ""))
                text = _normalize_text(args[1]) if len(args) > 1 else _normalize_text(kwargs.get("text", ""))
                meta = kwargs.get("meta") if "meta" in kwargs else (args[2] if len(args) > 2 else None)
                session_id = _session_id_from_context(
                    channel_name=getattr(self, "channel", cls.__name__.lower()),
                    to_handle=to_handle,
                    meta=meta if isinstance(meta, dict) else None,
                )
                relay_channel_chunk(
                    channel_name=getattr(self, "channel", cls.__name__.lower()),
                    session_id=session_id,
                    text=text,
                    title=_name(),
                )
            elif relay_kind == "send_content_parts":
                to_handle = _normalize_text(args[0]) if args else _normalize_text(kwargs.get("to_handle", ""))
                parts = args[1] if len(args) > 1 else kwargs.get("parts")
                meta = kwargs.get("meta") if "meta" in kwargs else (args[2] if len(args) > 2 else None)
                session_id = _session_id_from_context(
                    channel_name=getattr(self, "channel", cls.__name__.lower()),
                    to_handle=to_handle,
                    meta=meta if isinstance(meta, dict) else None,
                )
                text = _text_from_parts(parts)
                relay_channel_chunk(
                    channel_name=getattr(self, "channel", cls.__name__.lower()),
                    session_id=session_id,
                    text=text,
                    title=_name(),
                )
            elif relay_kind == "_on_process_completed":
                request = args[0] if args else kwargs.get("request")
                to_handle = _normalize_text(args[1]) if len(args) > 1 else _normalize_text(kwargs.get("to_handle", ""))
                meta = kwargs.get("send_meta") if "send_meta" in kwargs else (args[2] if len(args) > 2 else None)
                session_id = _session_id_from_context(
                    channel_name=getattr(self, "channel", cls.__name__.lower()),
                    request=request,
                    to_handle=to_handle,
                    meta=meta if isinstance(meta, dict) else None,
                )
                relay_channel_end(
                    channel_name=getattr(self, "channel", cls.__name__.lower()),
                    session_id=session_id,
                    title=_name(),
                    status="done",
                    exit_code=0,
                )
            elif relay_kind == "_on_consume_error":
                request = args[0] if args else kwargs.get("request")
                to_handle = _normalize_text(args[1]) if len(args) > 1 else _normalize_text(kwargs.get("to_handle", ""))
                err_text = _normalize_text(args[2]) if len(args) > 2 else _normalize_text(kwargs.get("err_text", ""))
                meta = getattr(request, "channel_meta", None) if request is not None else None
                session_id = _session_id_from_context(
                    channel_name=getattr(self, "channel", cls.__name__.lower()),
                    request=request,
                    to_handle=to_handle,
                    meta=meta if isinstance(meta, dict) else None,
                )
                relay_channel_chunk(
                    channel_name=getattr(self, "channel", cls.__name__.lower()),
                    session_id=session_id,
                    text=err_text,
                    title=_name(),
                )
                relay_channel_end(
                    channel_name=getattr(self, "channel", cls.__name__.lower()),
                    session_id=session_id,
                    title=_name(),
                    status="failed",
                    exit_code=1,
                )
        except Exception:
            pass
        return await original(self, *args, **kwargs)

    wrapped.__buddy_wrapped__ = True  # type: ignore[attr-defined]
    setattr(cls, method_name, wrapped)


def _iter_subclasses(cls: type[Any]):
    for subcls in cls.__subclasses__():
        yield subcls
        yield from _iter_subclasses(subcls)


def install_channel_relay() -> None:
    """Install a broad Buddy relay on QwenPaw channel output paths.

    This mirrors channel output from the shared BaseChannel lifecycle and
    send helpers, so Buddy can show non-console sessions too.
    """
    global _relay_installed
    if _relay_installed or not _enabled():
        return
    with _lock:
        if _relay_installed:
            return
        try:
            from qwenpaw.app.channels.base import BaseChannel
            from qwenpaw.app.channels.registry import get_channel_registry

            # Force channel modules to load so subclasses are available for
            # wrapping. This is safe to call multiple times.
            get_channel_registry()

            classes = {BaseChannel, *set(_iter_subclasses(BaseChannel))}
            for cls in classes:
                if getattr(cls, "__buddy_relay_installed__", False):
                    continue
                _wrap_async_method(cls, "send_content_parts", "send_content_parts")
                _wrap_async_method(cls, "send", "send")
                _wrap_async_method(cls, "_on_process_completed", "_on_process_completed")
                _wrap_async_method(cls, "_on_consume_error", "_on_consume_error")
                setattr(cls, "__buddy_relay_installed__", True)
            _relay_installed = True
        except Exception:
            logger.exception("failed to install Buddy channel relay")


def relay_approval_created(pending: Any) -> None:
    if not _enabled():
        return
    record = {
        "request_id": getattr(pending, "request_id", ""),
        "session_id": getattr(pending, "session_id", ""),
        "root_session_id": getattr(pending, "root_session_id", ""),
        "tool_name": getattr(pending, "tool_name", ""),
        "severity": getattr(pending, "severity", ""),
        "findings_count": getattr(pending, "findings_count", 0),
        "result_summary": getattr(pending, "result_summary", ""),
    }
    with _lock:
        _pending_approvals[record["request_id"]] = record
    _ensure_sender_thread()
    _ensure_poller_thread()
    _event_queue.put(("approval_created", record))


def relay_approval_resolved(pending: Any, decision: str) -> None:
    if not _enabled():
        return
    request_id = getattr(pending, "request_id", "")
    with _lock:
        _pending_approvals.pop(request_id, None)
    _ensure_sender_thread()
    _event_queue.put(
        (
            "approval_resolved",
            {
                "request_id": request_id,
                "root_session_id": getattr(pending, "root_session_id", ""),
                "tool_name": getattr(pending, "tool_name", "tool"),
                "decision": decision,
            },
        )
    )


def _sender_loop() -> None:
    client = _build_client()
    QwenPawCompatAdapter = _qwenpaw_compat_adapter_class()
    while True:
        item = _event_queue.get()
        kind = item[0]
        try:
            if kind == "sse":
                _, session_id, event_line = item
                payload = QwenPawCompatAdapter.parse_sse_line(event_line)
                if not payload:
                    continue
                with _lock:
                    adapter = _adapters.get(session_id)
                    if adapter is None:
                        adapter = QwenPawCompatAdapter(
                            stream_id=session_id,
                            name=_name(),
                            include_reasoning=_include_reasoning(),
                        )
                        _adapters[session_id] = adapter
                for event in adapter.translate(payload):
                    if event.get("type") == "stream_start":
                        idle_timeout_ms = _idle_timeout_ms()
                        if idle_timeout_ms:
                            event["idleTimeoutMs"] = idle_timeout_ms
                    client.send_event(event)
                if payload.get("object") == "response" and str(payload.get("status") or "") in {
                    "completed",
                    "failed",
                    "error",
                    "cancelled",
                }:
                    with _lock:
                        _adapters.pop(session_id, None)
            elif kind == "approval_created":
                _, record = item
                adapter = QwenPawCompatAdapter(
                    stream_id=record.get("root_session_id") or "qwenpaw-approval",
                    name=_name(),
                )
                client.send_event(adapter.approval_record_to_event(record))
            elif kind == "approval_resolved":
                _, record = item
                decision = str(record.get("decision") or "")
                tool_name = str(record.get("tool_name") or "tool")
                root_session_id = str(record.get("root_session_id") or "")
                if root_session_id:
                    line = f"[approval] {decision}: {tool_name}\n"
                    client.send_event(
                        {
                            "type": "stream_chunk",
                            "streamId": root_session_id,
                            "text": line,
                        }
                    )
            elif kind in {"channel_start", "channel_chunk", "channel_end"}:
                _, record = item
                stream_id = str(record.get("session_id") or "")
                title = str(record.get("title") or _name())
                body = str(record.get("body") or "")
                if kind == "channel_start":
                    client.agent_start(
                        stream_id,
                        name=title,
                        status=str(record.get("status") or "running"),
                        body=body,
                    )
                elif kind == "channel_chunk":
                    text = str(record.get("text") or "")
                    if text:
                        client.agent_log(stream_id, text if text.endswith("\n") else f"{text}\n")
                elif kind == "channel_end":
                    client.agent_end(
                        stream_id,
                        status=str(record.get("status") or "done"),
                        exit_code=int(record.get("exit_code") or 0),
                    )
        except Exception:
            continue


def _approval_poller_loop() -> None:
    while True:
        try:
            base = _responses_url()
            if not base:
                time.sleep(_approval_poll_interval())
                continue
            with _lock:
                items = list(_pending_approvals.items())
            for request_id, record in items:
                url = f"{base}?id={urllib.parse.quote(request_id)}&consume=1"
                try:
                    result = _get_json_absolute(url, timeout=5)
                except Exception:
                    continue
                for response in result.get("responses", []):
                    path, payload = QwenPawCompatAdapter.buddy_response_to_qwenpaw_action(response, record)
                    target = urllib.parse.urljoin(_qwenpaw_url(), path)
                    try:
                        _post_json_absolute(target, payload, timeout=10)
                    except Exception:
                        continue
                    with _lock:
                        _pending_approvals.pop(request_id, None)
        finally:
            time.sleep(_approval_poll_interval())
