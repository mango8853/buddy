#!/usr/bin/env python3
import argparse
import copy
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock


DEFAULT_HOST = "10.214.75.86"
DEFAULT_PORT = 8787
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUSTOM_PETS_DIR = os.path.join(REPO_ROOT, "pets", "custom")
CUSTOM_PETS_REGISTRY = os.path.join(CUSTOM_PETS_DIR, "registry.json")
BUILTIN_PETS = [
    {"id": "claw", "displayName": "Claw", "description": "A round red chibi digital companion with cyan eyes and mitten claws."},
    {"id": "codex", "displayName": "Codex", "description": "The original Codex companion."},
    {"id": "dewey", "displayName": "Dewey", "description": "A tidy duck for calm workspace days."},
    {"id": "fireball", "displayName": "Fireball", "description": "Hot path energy for fast iteration."},
    {"id": "rocky", "displayName": "Rocky", "description": "A steady rock when the diff gets large."},
    {"id": "seedy", "displayName": "Seedy", "description": "Small green shoots for new ideas."},
    {"id": "stacky", "displayName": "Stacky", "description": "A balanced stack for deep work."},
    {"id": "bsod", "displayName": "BSOD", "description": "A tiny blue-screen gremlin."},
    {"id": "null-signal", "displayName": "Null Signal", "description": "Quiet signal from the void."},
]

AGENT_KIND_ALIASES = {
    "claude": "claude",
    "claude-code": "claude-code",
    "claudecode": "claude-code",
    "codex": "codex",
    "openclaw": "openclaw",
    "qwenpaw": "qwenpaw",
    "shell": "shell",
    "terminal": "cli",
    "cli": "cli",
}


def ensure_custom_pets_dir():
    os.makedirs(CUSTOM_PETS_DIR, exist_ok=True)


def built_in_pet_map():
    return {pet["id"]: pet for pet in BUILTIN_PETS}


def load_custom_pets():
    ensure_custom_pets_dir()
    if not os.path.exists(CUSTOM_PETS_REGISTRY):
        return []
    with open(CUSTOM_PETS_REGISTRY, "r", encoding="utf-8") as input_file:
        payload = json.load(input_file)
    pets = payload.get("pets", []) if isinstance(payload, dict) else payload
    if not isinstance(pets, list):
        raise SystemExit(f"invalid custom pet registry: {CUSTOM_PETS_REGISTRY}")
    normalized = []
    for pet in pets:
        if not isinstance(pet, dict) or not pet.get("id") or not pet.get("file"):
            continue
        item = copy.deepcopy(pet)
        item["type"] = "custom"
        item["displayName"] = item.get("displayName") or item["id"]
        item["description"] = item.get("description") or "Custom Codex-format pet."
        item["file"] = resolve_registry_file(item["file"])
        normalized.append(item)
    return normalized


def save_custom_pets(pets):
    ensure_custom_pets_dir()
    payload = {
        "version": 1,
        "pets": [
            {
                "id": pet["id"],
                "displayName": pet.get("displayName", pet["id"]),
                "description": pet.get("description", ""),
                "file": registry_path_for_storage(pet["file"]),
            }
            for pet in sorted(pets, key=lambda item: item["id"])
        ],
    }
    with open(CUSTOM_PETS_REGISTRY, "w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")


def all_pet_specs():
    pets = [dict(item, type="built-in") for item in BUILTIN_PETS]
    pets.extend(load_custom_pets())
    return pets


def find_custom_pet(pet_id):
    for pet in load_custom_pets():
        if pet["id"] == pet_id:
            return pet
    return None


def find_pet_spec(pet_id):
    pet_id = (pet_id or "").strip()
    if not pet_id:
        return None
    built_in = built_in_pet_map().get(pet_id)
    if built_in:
        return dict(built_in, type="built-in")
    return find_custom_pet(pet_id)


def sanitize_pet_id(value):
    pet_id = (value or "").strip().lower()
    if not pet_id:
        raise SystemExit("pet id is required")
    safe = []
    for ch in pet_id:
        if ch.isalnum() or ch in ("-", "_"):
            safe.append(ch)
        else:
            safe.append("-")
    normalized = "".join(safe).strip("-")
    if not normalized:
        raise SystemExit(f"invalid pet id: {value!r}")
    return normalized


def resolve_registry_file(path_value):
    raw = str(path_value or "").strip()
    if not raw:
        return ""
    if os.path.isabs(raw):
        return os.path.abspath(raw)
    return os.path.abspath(os.path.join(REPO_ROOT, raw))


def registry_path_for_storage(path_value):
    absolute = os.path.abspath(path_value)
    try:
        relative = os.path.relpath(absolute, REPO_ROOT)
    except ValueError:
        return absolute
    if relative.startswith(".."):
        return absolute
    return relative


def normalize_agent_kind(value):
    text = (value or "").strip().lower()
    if not text:
        return ""
    safe = []
    for ch in text:
        if ch.isalnum() or ch in ("-", "_"):
            safe.append(ch)
        else:
            safe.append("-")
    normalized = "".join(safe).strip("-")
    return AGENT_KIND_ALIASES.get(normalized, normalized)


def infer_agent_kind(*values):
    haystack = " ".join(str(value or "") for value in values).strip().lower()
    if not haystack:
        return ""
    if "qwenpaw" in haystack:
        return "qwenpaw"
    if "openclaw" in haystack:
        return "openclaw"
    if "claude code" in haystack or "claude-code" in haystack:
        return "claude-code"
    if "claude" in haystack:
        return "claude"
    if "codex" in haystack:
        return "codex"
    if "shell" in haystack or "terminal" in haystack or "cli" in haystack:
        return "cli"
    return ""


def post_json(host, port, path, payload, timeout=5):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"http://{host}:{port}{path}",
        data=data,
        headers={"content-type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        return response.status, body


def post_bytes(host, port, path, data, headers=None, timeout=10):
    request = urllib.request.Request(
        f"http://{host}:{port}{path}",
        data=data,
        headers=headers or {},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        return response.status, body


def get_text(host, port, path, timeout=5):
    with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def send_event(args, payload):
    status, body = post_json(args.host, args.port, "/api/event", payload, args.timeout)
    if args.json:
        print(json.dumps({"status": status, "body": body}, ensure_ascii=False))
    else:
        print(body or f"HTTP {status}")


def send_payload(host, port, timeout, payload):
    return post_json(host, port, "/api/event", payload, timeout)


def upload_file(args, path):
    with open(path, "rb") as input_file:
        data = input_file.read()
    name = os.path.basename(path)
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    status, body = post_bytes(
        args.host,
        args.port,
        "/api/upload",
        data,
        {
            "content-type": content_type,
            "x-buddy-name": name,
        },
        max(args.timeout, 60),
    )
    try:
        payload = json.loads(body or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"upload returned invalid JSON: {body}") from exc
    if status >= 400 or not payload.get("ok"):
        raise SystemExit(f"upload failed: HTTP {status} {body}")
    if not payload.get("url"):
        raise SystemExit(f"upload response missing url: {body}")
    return payload


def with_media_text(args, payload):
    if args.title is not None:
        payload["title"] = args.title
    if args.body is not None:
        payload["body"] = args.body
    if args.mood is not None:
        payload["mood"] = args.mood
    return payload


def add_pet_fields(args, payload):
    pet_id = (getattr(args, "pet_id", "") or "").strip()
    pet_url = (getattr(args, "pet_url", "") or "").strip()
    pet_spritesheet_url = (getattr(args, "pet_spritesheet_url", "") or "").strip()
    if pet_id:
        pet_spec = find_pet_spec(pet_id)
        if pet_spec is None:
            raise SystemExit(
                f"unknown pet id: {pet_id}. Use `python3 bridge/buddy.py --host {args.host} pet list` to see available pets."
            )
        if pet_spec["type"] == "custom":
            upload = upload_file(args, pet_spec["file"])
            payload["petId"] = pet_spec["id"]
            payload["petSpritesheetUrl"] = upload["url"]
        else:
            payload["petId"] = pet_spec["id"]
    if pet_url:
        payload["petUrl"] = pet_url
    if pet_spritesheet_url:
        payload["petSpritesheetUrl"] = pet_spritesheet_url
    return payload


def add_agent_kind_fields(args, payload):
    explicit = normalize_agent_kind(getattr(args, "agent_kind", "") or "")
    inferred = infer_agent_kind(
        getattr(args, "name", ""),
        getattr(args, "title", ""),
        getattr(args, "body", ""),
    )
    agent_kind = explicit or inferred
    if agent_kind:
        payload["agentKind"] = agent_kind
    return payload


def resolve_payload_pet_fields(host, port, timeout, payload):
    pet_id = (payload.get("petId") or "").strip()
    if pet_id:
        pet_spec = find_pet_spec(pet_id)
        if pet_spec is None:
            raise SystemExit(f"unknown pet id: {pet_id}")
        if pet_spec["type"] == "custom":
            upload = upload_file(argparse.Namespace(host=host, port=port, timeout=timeout), pet_spec["file"])
            payload["petSpritesheetUrl"] = upload["url"]
        payload["petId"] = pet_spec["id"]
    return payload


def add_pet_args(parser):
    parser.add_argument("--pet-id", help="built-in or imported custom pet id")
    parser.add_argument("--pet-url", help="static image pet override")
    parser.add_argument("--pet-spritesheet-url", help="Codex-format animated spritesheet URL or uploaded /media path")


def add_media_options(args, payload, include_playback=False, default_fit="contain"):
    payload["fullscreen"] = bool(getattr(args, "fullscreen", False))
    payload["fit"] = getattr(args, "fit", default_fit)
    if include_playback:
        payload["loop"] = bool(getattr(args, "loop", False))
        payload["controls"] = bool(getattr(args, "controls", False))
        payload["muted"] = bool(getattr(args, "muted", False))
        payload["autoplay"] = not bool(getattr(args, "no_autoplay", False))
    return payload


def as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return bool(value)


def copy_media_fields(source, target, include_playback=False, default_fit="contain"):
    target["fullscreen"] = as_bool(source.get("fullscreen", source.get("fullScreen")), False)
    target["fit"] = source.get("fit", default_fit)
    if include_playback:
        target["loop"] = as_bool(source.get("loop"), False)
        target["controls"] = as_bool(source.get("controls"), False)
        target["muted"] = as_bool(source.get("muted"), False)
        target["autoplay"] = as_bool(source.get("autoplay"), True)
    return target


def command_health(args):
    status, body = get_text(args.host, args.port, "/health", args.timeout)
    print(body or f"HTTP {status}")


def command_state(args):
    status, body = get_text(args.host, args.port, "/state", args.timeout)
    print(body or f"HTTP {status}")


def command_version(args):
    status, body = get_text(args.host, args.port, "/version", args.timeout)
    print(body or f"HTTP {status}")


def command_message(args):
    payload = {
        "type": "message",
        "mood": args.mood,
        "title": args.title,
        "body": args.text,
    }
    send_event(args, add_pet_fields(args, add_agent_kind_fields(args, payload)))


def command_mood(args):
    payload = {
        "type": "mood",
        "mood": args.mood,
        "title": args.title or args.mood,
        "body": args.body or "",
    }
    send_event(args, add_pet_fields(args, add_agent_kind_fields(args, payload)))


def command_approval(args):
    payload = {
        "type": "approval",
        "id": args.id or f"approval-{int(time.time())}",
        "mood": "waiting",
        "title": args.title,
        "body": args.body,
        "approveLabel": args.approve_label,
        "denyLabel": args.deny_label,
    }
    send_event(args, add_pet_fields(args, add_agent_kind_fields(args, payload)))


def command_image(args):
    upload = upload_file(args, args.file)
    payload = with_media_text(args, add_media_options(args, {
        "type": "image",
        "url": upload["url"],
        "title": os.path.basename(args.file),
        "body": "",
        "mood": "image",
    }, default_fit="contain"))
    send_event(args, add_pet_fields(args, add_agent_kind_fields(args, payload)))


def command_video(args):
    upload = upload_file(args, args.file)
    payload = with_media_text(args, add_media_options(args, {
        "type": "video",
        "url": upload["url"],
        "title": os.path.basename(args.file),
        "body": "",
        "mood": "video",
    }, include_playback=True, default_fit="contain"))
    send_event(args, add_pet_fields(args, add_agent_kind_fields(args, payload)))


def command_audio(args):
    upload = upload_file(args, args.file)
    payload = with_media_text(args, {
        "type": "audio",
        "url": upload["url"],
        "title": os.path.basename(args.file),
        "body": "",
        "mood": "audio",
        "loop": args.loop,
    })
    send_event(args, add_pet_fields(args, add_agent_kind_fields(args, payload)))


def command_html(args):
    html = args.html
    if args.file:
        with open(args.html, "r", encoding="utf-8") as input_file:
            html = input_file.read()
    payload = with_media_text(args, add_media_options(args, {
        "type": "html",
        "html": html,
        "title": args.title or "HTML",
        "body": args.body or "",
        "mood": args.mood or "html",
    }))
    send_event(args, add_pet_fields(args, add_agent_kind_fields(args, payload)))


def command_event(args):
    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON: {exc}") from exc
    send_event(args, payload)


def command_clear(args):
    status, body = post_json(args.host, args.port, "/api/clear", {}, args.timeout)
    print(body or f"HTTP {status}")


def command_stop_audio(args):
    send_event(args, {"type": "stop_audio"})


def command_pet_list(args):
    pets = all_pet_specs()
    if args.json:
        print(json.dumps({"pets": pets}, ensure_ascii=False))
    else:
        for pet in pets:
            print(f'{pet["id"]}\t{pet["displayName"]}\t{pet["type"]}\t{pet["description"]}')


def command_pet_import(args):
    pet_id = sanitize_pet_id(args.id)
    if pet_id in built_in_pet_map():
        raise SystemExit(f"cannot overwrite built-in pet id: {pet_id}")
    source = os.path.abspath(args.file)
    if not os.path.exists(source):
        raise SystemExit(f"pet file not found: {source}")
    ensure_custom_pets_dir()
    extension = os.path.splitext(source)[1].lower() or ".webp"
    destination = os.path.join(CUSTOM_PETS_DIR, pet_id + extension)
    shutil.copyfile(source, destination)
    pets = [pet for pet in load_custom_pets() if pet["id"] != pet_id]
    pets.append({
        "id": pet_id,
        "displayName": args.display_name or pet_id,
        "description": args.description or "Custom Codex-format pet.",
        "file": destination,
    })
    save_custom_pets(pets)
    if args.json:
        print(json.dumps({"ok": True, "id": pet_id, "file": destination}, ensure_ascii=False))
    else:
        print(f"Imported custom pet {pet_id} -> {destination}")


def command_pet_remove(args):
    pet_id = sanitize_pet_id(args.id)
    if pet_id in built_in_pet_map():
        raise SystemExit(f"cannot remove built-in pet id: {pet_id}")
    pets = load_custom_pets()
    kept = [pet for pet in pets if pet["id"] != pet_id]
    if len(kept) == len(pets):
        raise SystemExit(f"custom pet not found: {pet_id}")
    removed = next(pet for pet in pets if pet["id"] == pet_id)
    save_custom_pets(kept)
    if os.path.exists(removed["file"]):
        os.remove(removed["file"])
    if args.json:
        print(json.dumps({"ok": True, "id": pet_id}, ensure_ascii=False))
    else:
        print(f"Removed custom pet {pet_id}")


def command_pet_set(args):
    payload = {
        "type": "pet",
        "title": args.title or "Ready",
        "body": args.body if args.body is not None else "",
        "mood": args.mood or "idle",
    }
    if args.file:
        upload = upload_file(args, args.file)
        payload["petSpritesheetUrl"] = upload["url"]
        if args.pet_id:
            payload["petId"] = args.pet_id
    else:
        add_pet_fields(args, payload)
    send_event(args, add_agent_kind_fields(args, payload))


def send_stream_event(args, payload):
    status, body = send_payload(args.host, args.port, args.timeout, payload)
    if status >= 400:
        raise SystemExit(body or f"HTTP {status}")


def command_stream(args):
    stream_id = args.id or f"stream-{int(time.time() * 1000)}"
    flush_interval = max(0.04, args.flush_ms / 1000.0)
    max_lines = max(20, args.max_lines)
    max_chars = max(2000, args.max_chars)
    start_payload = {
        "type": "stream_start",
        "streamId": stream_id,
        "title": args.title or "Agent",
        "body": args.body or "",
        "mood": args.mood or "thinking",
        "maxLines": max_lines,
        "maxChars": max_chars,
    }
    add_agent_kind_fields(args, start_payload)
    add_pet_fields(args, start_payload)
    send_stream_event(args, start_payload)

    buffer = []
    last_flush = time.monotonic()

    def flush(force=False):
        nonlocal last_flush
        if not buffer:
            return
        if not force and (time.monotonic() - last_flush) < flush_interval:
            return
        text = "".join(buffer)
        buffer[:] = []
        send_stream_event(args, {
            "type": "stream_chunk",
            "streamId": stream_id,
            "text": text,
        })
        last_flush = time.monotonic()

    exit_code = 0
    if args.exec:
        command = list(args.exec)
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            raise SystemExit("stream --exec requires a command after --")
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
        try:
            for line in iter(process.stdout.readline, ""):
                if not line:
                    break
                buffer.append(line)
                flush(False)
        finally:
            process.stdout.close()
        exit_code = process.wait()
    else:
        if sys.stdin.isatty():
            raise SystemExit("stream expects piped stdin or --exec -- <command>")
        for line in sys.stdin:
            buffer.append(line)
            flush(False)

    flush(True)
    end_payload = {
        "type": "stream_end",
        "streamId": stream_id,
        "status": args.end_status or ("done" if exit_code == 0 else "failed"),
        "exitCode": exit_code,
    }
    send_stream_event(args, end_payload)
    if args.json:
        print(json.dumps({"ok": True, "streamId": stream_id, "exitCode": exit_code}, ensure_ascii=False))
    if exit_code:
        raise SystemExit(exit_code)


def command_agent_start(args):
    payload = {
        "type": "stream_start",
        "streamId": args.id,
        "title": args.name,
        "body": args.body or "",
        "mood": args.status,
        "maxLines": args.max_lines,
        "maxChars": args.max_chars,
    }
    add_agent_kind_fields(args, payload)
    send_event(args, add_pet_fields(args, payload))


def command_agent_log(args):
    text = args.text
    if args.file:
        with open(args.text, "r", encoding="utf-8") as input_file:
            text = input_file.read()
    send_event(args, {
        "type": "stream_chunk",
        "streamId": args.id,
        "text": text,
    })


def command_agent_status(args):
    payload = {
        "type": "stream_meta",
        "streamId": args.id,
        "status": args.status,
        "title": args.name or "",
        "body": args.body or "",
    }
    send_event(args, add_agent_kind_fields(args, payload))


def command_agent_approval(args):
    payload = {
        "type": "approval",
        "id": args.approval_id or f"{args.id}-approval-{int(time.time())}",
        "streamId": args.id,
        "mood": "waiting",
        "title": args.title,
        "body": args.body,
        "approveLabel": args.approve_label,
        "denyLabel": args.deny_label,
    }
    send_event(args, add_agent_kind_fields(args, payload))


def command_agent_end(args):
    payload = {
        "type": "stream_end",
        "streamId": args.id,
        "status": args.status,
        "exitCode": args.exit_code,
    }
    send_event(args, add_agent_kind_fields(args, payload))


def command_agent_run(args):
    stream_args = argparse.Namespace(**vars(args))
    stream_args.title = args.name
    stream_args.mood = args.status
    stream_args.end_status = args.end_status
    stream_args.exec = list(args.exec or [])
    command_stream(stream_args)


def command_scene(args):
    payload = {
        "type": "scene",
        "scene": args.scene,
        "title": args.title or "",
        "body": args.body or "",
    }
    if args.id:
        payload["id"] = args.id
    add_agent_kind_fields(args, payload)
    add_pet_fields(args, payload)
    if args.html:
        payload["html"] = args.html
    if args.panel_text:
        payload["text"] = args.panel_text
    payload["panel"] = {"side": args.panel_side}
    payload["actions"] = {
        "left": {"id": args.left_action, "label": args.left_label},
        "right": {"id": args.right_action, "label": args.right_label},
    }
    send_event(args, payload)


def command_scene_demo(args):
    demos = [
        {
            "type": "scene",
            "scene": "idle",
            "title": "Idle Scene",
            "body": "宠物在舞台中央待机",
            "petId": args.pet_id or "",
            "petSpritesheetUrl": args.pet_spritesheet_url or "",
            "petUrl": args.pet_url or "",
        },
        {
            "type": "scene",
            "scene": "decision",
            "id": "scene-demo",
            "title": "允许继续吗？",
            "body": "拖动宠物到左侧确认，右侧拒绝。",
            "petId": args.pet_id or "",
            "petSpritesheetUrl": args.pet_spritesheet_url or "",
            "petUrl": args.pet_url or "",
        },
        {
            "type": "scene",
            "scene": "side-panel",
            "title": "侧边信息面板",
            "body": "宠物退到左边，右侧承载 HTML/日志/图片等内容。",
            "petId": args.pet_id or "",
            "petSpritesheetUrl": args.pet_spritesheet_url or "",
            "petUrl": args.pet_url or "",
            "html": "<h2>Agent Status</h2><div>正在执行任务，右侧信息面板已展开。</div>",
        },
        {
            "type": "scene",
            "scene": "bottom-sheet",
            "title": "底部抽屉",
            "body": "适合进度、歌词、日志流。",
            "petId": args.pet_id or "",
            "petSpritesheetUrl": args.pet_spritesheet_url or "",
            "petUrl": args.pet_url or "",
            "html": "<h2>Progress</h2><div>步骤 3 / 5：正在验证输出。</div>",
        },
    ]
    for event in demos:
        send_event(args, event)
        time.sleep(args.delay)


def command_demo(args):
    events = [
        {"type": "mood", "mood": "thinking", "title": "Thinking", "body": "正在整理上下文"},
        {"type": "message", "mood": "noted", "title": "小屏已连接", "body": "Python bridge 可以把任意 agent 的状态推到音箱。"},
        {"type": "approval", "id": "demo", "title": "允许继续吗？", "body": "这是一次触摸确认测试。", "approveLabel": "允许", "denyLabel": "取消"},
    ]
    for event in events:
        send_event(args, event)
        time.sleep(args.delay)


def command_serve(args):
    target_host = args.host
    target_port = args.port
    timeout = args.timeout
    queued_events = []
    responses = []
    lock = Lock()

    def enqueue(payload):
        with lock:
            queued_events.append(payload)

    def pop_all():
        with lock:
            events = list(queued_events)
            queued_events.clear()
            return events

    class Handler(BaseHTTPRequestHandler):
        def _read_json(self):
            length = int(self.headers.get("content-length", "0"))
            raw = self.rfile.read(length).decode("utf-8", errors="replace") if length else "{}"
            return json.loads(raw or "{}")

        def _write(self, status, payload):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("access-control-allow-origin", "*")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("access-control-allow-origin", "*")
            self.send_header("access-control-allow-methods", "GET,POST,OPTIONS")
            self.send_header("access-control-allow-headers", "content-type")
            self.end_headers()

        def do_GET(self):
            try:
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                if parsed.path.startswith("/next"):
                    self._write(200, {"ok": True, "events": pop_all(), "ts": int(time.time())})
                    return
                if parsed.path == "/responses":
                    only_id = query.get("id", [""])[0]
                    consume = query.get("consume", ["0"])[0].lower() in ("1", "true", "yes")
                    with lock:
                        if only_id:
                            payload = [item for item in responses if str(item.get("id", "")) == only_id]
                        else:
                            payload = list(responses)
                        if consume and payload:
                            consumed_keys = {str(item.get("ts", "")) + ":" + str(item.get("id", "")) for item in payload}
                            responses[:] = [
                                item for item in responses
                                if (str(item.get("ts", "")) + ":" + str(item.get("id", ""))) not in consumed_keys
                            ]
                    self._write(200, {"ok": True, "responses": payload})
                    return
                if parsed.path == "/health":
                    status, body = get_text(target_host, target_port, "/health", timeout)
                elif parsed.path == "/version":
                    status, body = get_text(target_host, target_port, "/version", timeout)
                else:
                    status, body = get_text(target_host, target_port, "/state", timeout)
                self._write(200, {"ok": True, "target_status": status, "body": json.loads(body or "{}")})
            except Exception as exc:
                self._write(502, {"ok": False, "error": str(exc)})

        def do_POST(self):
            try:
                payload = self._read_json()
                if self.path == "/message":
                    payload = {
                        "type": "message",
                        "title": payload.get("title", "Message"),
                        "body": payload.get("body", payload.get("text", "")),
                        "mood": payload.get("mood", "noted"),
                        "petId": payload.get("petId", ""),
                        "petUrl": payload.get("petUrl", ""),
                        "petSpritesheetUrl": payload.get("petSpritesheetUrl", ""),
                    }
                elif self.path == "/approval":
                    payload = {
                        "type": "approval",
                        "id": payload.get("id", f"approval-{int(time.time())}"),
                        "title": payload.get("title", "需要确认"),
                        "body": payload.get("body", ""),
                        "approveLabel": payload.get("approveLabel", "确认"),
                        "denyLabel": payload.get("denyLabel", "拒绝"),
                        "petId": payload.get("petId", ""),
                        "petUrl": payload.get("petUrl", ""),
                        "petSpritesheetUrl": payload.get("petSpritesheetUrl", ""),
                    }
                elif self.path == "/image":
                    payload = copy_media_fields(payload, {
                        "type": "image",
                        "url": payload.get("url", ""),
                        "title": payload.get("title", "Image"),
                        "body": payload.get("body", ""),
                        "mood": payload.get("mood", "image"),
                        "petId": payload.get("petId", ""),
                        "petUrl": payload.get("petUrl", ""),
                        "petSpritesheetUrl": payload.get("petSpritesheetUrl", ""),
                    }, default_fit="contain")
                elif self.path == "/video":
                    payload = copy_media_fields(payload, {
                        "type": "video",
                        "url": payload.get("url", ""),
                        "title": payload.get("title", "Video"),
                        "body": payload.get("body", ""),
                        "mood": payload.get("mood", "video"),
                        "petId": payload.get("petId", ""),
                        "petUrl": payload.get("petUrl", ""),
                        "petSpritesheetUrl": payload.get("petSpritesheetUrl", ""),
                    }, include_playback=True, default_fit="contain")
                elif self.path == "/audio":
                    payload = {
                        "type": "audio",
                        "url": payload.get("url", ""),
                        "title": payload.get("title", "Audio"),
                        "body": payload.get("body", ""),
                        "mood": payload.get("mood", "audio"),
                        "loop": as_bool(payload.get("loop"), False),
                        "petId": payload.get("petId", ""),
                        "petUrl": payload.get("petUrl", ""),
                        "petSpritesheetUrl": payload.get("petSpritesheetUrl", ""),
                    }
                elif self.path == "/html":
                    payload = copy_media_fields(payload, {
                        "type": "html",
                        "html": payload.get("html", ""),
                        "title": payload.get("title", "HTML"),
                        "body": payload.get("body", ""),
                        "mood": payload.get("mood", "html"),
                        "petId": payload.get("petId", ""),
                        "petUrl": payload.get("petUrl", ""),
                        "petSpritesheetUrl": payload.get("petSpritesheetUrl", ""),
                    })
                elif self.path == "/pet":
                    payload = {
                        "type": "pet",
                        "title": payload.get("title", "Ready"),
                        "body": payload.get("body", ""),
                        "mood": payload.get("mood", "idle"),
                        "petId": payload.get("petId", ""),
                        "petUrl": payload.get("petUrl", ""),
                        "petSpritesheetUrl": payload.get("petSpritesheetUrl", ""),
                    }
                elif self.path == "/scene":
                    payload = {
                        "type": "scene",
                        "scene": payload.get("scene", payload.get("name", "idle")),
                        "id": payload.get("id", f"scene-{int(time.time())}"),
                        "title": payload.get("title", ""),
                        "body": payload.get("body", ""),
                        "petId": payload.get("petId", ""),
                        "petUrl": payload.get("petUrl", ""),
                        "petSpritesheetUrl": payload.get("petSpritesheetUrl", ""),
                        "html": payload.get("html", ""),
                        "text": payload.get("text", ""),
                        "panel": payload.get("panel", {}),
                        "actions": payload.get("actions", {}),
                    }
                elif self.path in ("/stream", "/stream/start"):
                    action = payload.get("action", "start")
                    if self.path == "/stream/start":
                        action = "start"
                    if action == "chunk":
                        payload = {
                            "type": "stream_chunk",
                            "streamId": payload.get("streamId", payload.get("id", "")),
                            "text": payload.get("text", payload.get("append", "")),
                        }
                    elif action == "end":
                        payload = {
                            "type": "stream_end",
                            "streamId": payload.get("streamId", payload.get("id", "")),
                            "status": payload.get("status", "done"),
                            "exitCode": payload.get("exitCode", 0),
                        }
                    else:
                        payload = {
                            "type": "stream_start",
                            "streamId": payload.get("streamId", payload.get("id", f"stream-{int(time.time())}")),
                            "title": payload.get("title", "Agent"),
                            "body": payload.get("body", ""),
                            "mood": payload.get("mood", "thinking"),
                            "petId": payload.get("petId", ""),
                            "petUrl": payload.get("petUrl", ""),
                            "petSpritesheetUrl": payload.get("petSpritesheetUrl", ""),
                            "maxLines": int(payload.get("maxLines", 160)),
                            "maxChars": int(payload.get("maxChars", 12000)),
                        }
                elif self.path == "/stream/chunk":
                    payload = {
                        "type": "stream_chunk",
                        "streamId": payload.get("streamId", payload.get("id", "")),
                        "text": payload.get("text", payload.get("append", "")),
                    }
                elif self.path == "/stream/end":
                    payload = {
                        "type": "stream_end",
                        "streamId": payload.get("streamId", payload.get("id", "")),
                        "status": payload.get("status", "done"),
                        "exitCode": payload.get("exitCode", 0),
                    }
                elif self.path == "/agent/start":
                    payload = {
                        "type": "stream_start",
                        "streamId": payload.get("id", payload.get("streamId", f"agent-{int(time.time())}")),
                        "title": payload.get("name", payload.get("title", "Agent")),
                        "body": payload.get("body", ""),
                        "mood": payload.get("status", payload.get("mood", "thinking")),
                        "petId": payload.get("petId", ""),
                        "petUrl": payload.get("petUrl", ""),
                        "petSpritesheetUrl": payload.get("petSpritesheetUrl", ""),
                        "maxLines": int(payload.get("maxLines", 160)),
                        "maxChars": int(payload.get("maxChars", 12000)),
                    }
                elif self.path == "/agent/log":
                    payload = {
                        "type": "stream_chunk",
                        "streamId": payload.get("id", payload.get("streamId", "")),
                        "text": payload.get("text", payload.get("append", "")),
                    }
                elif self.path == "/agent/status":
                    payload = {
                        "type": "stream_meta",
                        "streamId": payload.get("id", payload.get("streamId", "")),
                        "status": payload.get("status", payload.get("mood", "running")),
                        "title": payload.get("name", payload.get("title", "")),
                        "body": payload.get("body", ""),
                    }
                elif self.path == "/agent/approval":
                    payload = {
                        "type": "approval",
                        "id": payload.get("approvalId", f"{payload.get('id', payload.get('streamId', 'agent'))}-approval-{int(time.time())}"),
                        "streamId": payload.get("id", payload.get("streamId", "")),
                        "title": payload.get("title", "需要确认"),
                        "body": payload.get("body", ""),
                        "approveLabel": payload.get("approveLabel", "确认"),
                        "denyLabel": payload.get("denyLabel", "拒绝"),
                        "petId": payload.get("petId", ""),
                        "petUrl": payload.get("petUrl", ""),
                        "petSpritesheetUrl": payload.get("petSpritesheetUrl", ""),
                    }
                elif self.path == "/agent/end":
                    payload = {
                        "type": "stream_end",
                        "streamId": payload.get("id", payload.get("streamId", "")),
                        "status": payload.get("status", "done"),
                        "exitCode": payload.get("exitCode", 0),
                    }
                elif self.path == "/clear":
                    payload = {"type": "clear"}
                elif self.path == "/stop_audio":
                    payload = {"type": "stop_audio"}
                if self.path != "/response":
                    payload = resolve_payload_pet_fields(target_host, target_port, timeout, payload)
                if self.path == "/response":
                    with lock:
                        payload["ts"] = int(time.time() * 1000)
                        responses.append(payload)
                else:
                    enqueue(payload)
                    try:
                        post_json(target_host, target_port, "/api/event", payload, timeout)
                    except Exception:
                        pass
                self._write(200, {"ok": True})
            except Exception as exc:
                self._write(502, {"ok": False, "error": str(exc)})

        def log_message(self, fmt, *args):
            if args and not getattr(self.server, "quiet", False):
                super().log_message(fmt, *args)

    server = ThreadingHTTPServer((args.listen, args.listen_port), Handler)
    server.quiet = args.quiet
    print(f"Buddy bridge listening on http://{args.listen}:{args.listen_port} -> {target_host}:{target_port}")
    server.serve_forever()


def parser():
    root = argparse.ArgumentParser(description="Send events to Buddy.")
    root.add_argument("--host", default=DEFAULT_HOST)
    root.add_argument("--port", type=int, default=DEFAULT_PORT)
    root.add_argument("--timeout", type=float, default=5)
    root.add_argument("--json", action="store_true", help="print machine-readable responses")

    sub = root.add_subparsers(dest="command", required=True)

    def add_display_args(command, default_fit="contain"):
        command.add_argument("--fullscreen", action="store_true", help="render media across the whole speaker screen")
        command.add_argument("--fit", choices=("contain", "cover", "fill"), default=default_fit, help="media object-fit mode")

    def add_playback_args(command):
        command.add_argument("--loop", action="store_true", help="loop playback")
        command.add_argument("--controls", action="store_true", help="show video controls")
        command.add_argument("--muted", action="store_true", help="mute video playback")
        command.add_argument("--no-autoplay", action="store_true", help="render media without autoplay")

    health = sub.add_parser("health")
    health.set_defaults(func=command_health)

    state = sub.add_parser("state")
    state.set_defaults(func=command_state)

    version = sub.add_parser("version")
    version.set_defaults(func=command_version)

    message = sub.add_parser("message")
    message.add_argument("text")
    message.add_argument("--title", default="Message")
    message.add_argument("--mood", default="noted")
    add_pet_args(message)
    message.set_defaults(func=command_message)

    mood = sub.add_parser("mood")
    mood.add_argument("mood")
    mood.add_argument("--title")
    mood.add_argument("--body")
    add_pet_args(mood)
    mood.set_defaults(func=command_mood)

    approval = sub.add_parser("approval")
    approval.add_argument("title")
    approval.add_argument("body")
    approval.add_argument("--id")
    approval.add_argument("--approve-label", default="确认")
    approval.add_argument("--deny-label", default="拒绝")
    add_pet_args(approval)
    approval.set_defaults(func=command_approval)

    image = sub.add_parser("image")
    image.add_argument("file")
    image.add_argument("--title")
    image.add_argument("--body")
    image.add_argument("--mood")
    add_display_args(image, default_fit="contain")
    add_pet_args(image)
    image.set_defaults(func=command_image)

    video = sub.add_parser("video")
    video.add_argument("file")
    video.add_argument("--title")
    video.add_argument("--body")
    video.add_argument("--mood")
    add_display_args(video, default_fit="contain")
    add_playback_args(video)
    add_pet_args(video)
    video.set_defaults(func=command_video)

    audio = sub.add_parser("audio")
    audio.add_argument("file")
    audio.add_argument("--title")
    audio.add_argument("--body")
    audio.add_argument("--mood")
    audio.add_argument("--loop", action="store_true", help="loop audio playback")
    add_pet_args(audio)
    audio.set_defaults(func=command_audio)

    html = sub.add_parser("html")
    html.add_argument("html", help="HTML string, or a file path with --file")
    html.add_argument("--file", action="store_true", help="read HTML from a local file")
    html.add_argument("--title")
    html.add_argument("--body")
    html.add_argument("--mood")
    add_display_args(html)
    add_pet_args(html)
    html.set_defaults(func=command_html)

    event = sub.add_parser("event")
    event.add_argument("payload", help="raw JSON event")
    event.set_defaults(func=command_event)

    clear = sub.add_parser("clear")
    clear.set_defaults(func=command_clear)

    stop_audio = sub.add_parser("stop-audio")
    stop_audio.set_defaults(func=command_stop_audio)

    pet = sub.add_parser("pet")
    pet_sub = pet.add_subparsers(dest="pet_command", required=True)

    pet_list = pet_sub.add_parser("list")
    pet_list.set_defaults(func=command_pet_list)

    pet_import = pet_sub.add_parser("import")
    pet_import.add_argument("--id", required=True, help="custom pet id")
    pet_import.add_argument("--display-name", help="human-readable pet name")
    pet_import.add_argument("--description", help="short description")
    pet_import.add_argument("file", help="local Codex-format spritesheet to copy into pets/custom/")
    pet_import.set_defaults(func=command_pet_import)

    pet_remove = pet_sub.add_parser("remove")
    pet_remove.add_argument("--id", required=True, help="custom pet id to delete")
    pet_remove.set_defaults(func=command_pet_remove)

    pet_set = pet_sub.add_parser("set")
    pet_set.add_argument("--pet-id", help="built-in or imported custom pet id")
    pet_set.add_argument("--pet-url", help="static image pet override")
    pet_set.add_argument("--pet-spritesheet-url", help="animated spritesheet URL or /media path")
    pet_set.add_argument("--file", help="upload a local Codex-format spritesheet file and set it")
    pet_set.add_argument("--title")
    pet_set.add_argument("--body")
    pet_set.add_argument("--mood", default="idle")
    pet_set.set_defaults(func=command_pet_set)

    scene = sub.add_parser("scene")
    scene.add_argument("scene", choices=("idle", "decision", "side-panel", "bottom-sheet"))
    scene.add_argument("--id")
    scene.add_argument("--title")
    scene.add_argument("--body")
    scene.add_argument("--html")
    scene.add_argument("--panel-text")
    scene.add_argument("--panel-side", choices=("right", "bottom"), default="right")
    scene.add_argument("--left-action", default="approve")
    scene.add_argument("--right-action", default="deny")
    scene.add_argument("--left-label", default="确认")
    scene.add_argument("--right-label", default="拒绝")
    add_pet_args(scene)
    scene.set_defaults(func=command_scene)

    scene_demo = sub.add_parser("scene-demo")
    scene_demo.add_argument("--delay", type=float, default=1.4)
    add_pet_args(scene_demo)
    scene_demo.set_defaults(func=command_scene_demo)

    stream = sub.add_parser("stream")
    stream.add_argument("--id")
    stream.add_argument("--title")
    stream.add_argument("--body")
    stream.add_argument("--mood", default="thinking")
    add_pet_args(stream)
    stream.add_argument("--flush-ms", type=float, default=120, help="flush buffered output every N milliseconds")
    stream.add_argument("--max-lines", type=int, default=160, help="max lines kept on the speaker")
    stream.add_argument("--max-chars", type=int, default=12000, help="max characters kept on the speaker")
    stream.add_argument("--end-status", default="", help="override final status label")
    stream.add_argument("--exec", nargs=argparse.REMAINDER, help="run a command and stream stdout/stderr; use --exec -- <cmd> ...")
    stream.set_defaults(func=command_stream)

    agent = sub.add_parser("agent")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)

    agent_start = agent_sub.add_parser("start")
    agent_start.add_argument("--id", required=True)
    agent_start.add_argument("--name", default="Agent")
    agent_start.add_argument("--status", default="thinking")
    agent_start.add_argument("--body")
    add_pet_args(agent_start)
    agent_start.add_argument("--max-lines", type=int, default=160)
    agent_start.add_argument("--max-chars", type=int, default=12000)
    agent_start.set_defaults(func=command_agent_start)

    agent_log = agent_sub.add_parser("log")
    agent_log.add_argument("--id", required=True)
    agent_log.add_argument("text", help="text to append, or a file path with --file")
    agent_log.add_argument("--file", action="store_true")
    agent_log.set_defaults(func=command_agent_log)

    agent_status = agent_sub.add_parser("status")
    agent_status.add_argument("--id", required=True)
    agent_status.add_argument("status")
    agent_status.add_argument("--name")
    agent_status.add_argument("--body")
    agent_status.set_defaults(func=command_agent_status)

    agent_approval = agent_sub.add_parser("approval")
    agent_approval.add_argument("--id", required=True, help="stream/agent id to resume after approval")
    agent_approval.add_argument("title")
    agent_approval.add_argument("body")
    agent_approval.add_argument("--approval-id")
    agent_approval.add_argument("--approve-label", default="确认")
    agent_approval.add_argument("--deny-label", default="拒绝")
    agent_approval.set_defaults(func=command_agent_approval)

    agent_end = agent_sub.add_parser("end")
    agent_end.add_argument("--id", required=True)
    agent_end.add_argument("--status", default="done")
    agent_end.add_argument("--exit-code", type=int, default=0)
    agent_end.set_defaults(func=command_agent_end)

    agent_run = agent_sub.add_parser("run")
    agent_run.add_argument("--id")
    agent_run.add_argument("--name", default="Agent")
    agent_run.add_argument("--status", default="running")
    agent_run.add_argument("--body")
    add_pet_args(agent_run)
    agent_run.add_argument("--flush-ms", type=float, default=120)
    agent_run.add_argument("--max-lines", type=int, default=160)
    agent_run.add_argument("--max-chars", type=int, default=12000)
    agent_run.add_argument("--end-status", default="")
    agent_run.add_argument("--exec", nargs=argparse.REMAINDER, required=True, help="command to run; use --exec -- <cmd> ...")
    agent_run.set_defaults(func=command_agent_run)

    demo = sub.add_parser("demo")
    demo.add_argument("--delay", type=float, default=1.2)
    demo.set_defaults(func=command_demo)

    serve = sub.add_parser("serve")
    serve.add_argument("--listen", default="127.0.0.1")
    serve.add_argument("--listen-port", type=int, default=8799)
    serve.add_argument("--quiet", action="store_true")
    serve.set_defaults(func=command_serve)

    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        args.func(args)
    except urllib.error.URLError as exc:
        raise SystemExit(f"connection failed: {exc}") from exc


if __name__ == "__main__":
    main()
