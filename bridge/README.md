# Buddy Bridge

Send status events from a Mac or any local agent to the Buddy Android app.

```sh
python3 bridge/buddy.py --host <buddy-ip> health
python3 bridge/buddy.py --host <buddy-ip> version
python3 bridge/buddy.py --host <buddy-ip> message "开始处理任务" --title "Codex"
python3 bridge/buddy.py --host <buddy-ip> approval "允许执行？" "是否继续运行这条命令？"
python3 bridge/buddy.py --host <buddy-ip> image ./photo.png --title "图片"
python3 bridge/buddy.py --host <buddy-ip> video ./clip.mp4 --title "视频" --loop --fullscreen --fit cover
python3 bridge/buddy.py --host <buddy-ip> audio ./ding.wav --title "提示音" --loop
python3 bridge/buddy.py --host <buddy-ip> html '<div style="font-size:30px">任务完成</div>' --title "HTML" --fullscreen
python3 bridge/buddy.py --host <buddy-ip> stop-audio
python3 bridge/buddy.py --host <buddy-ip> pet list
python3 bridge/buddy.py --host <buddy-ip> pet import --id moss ./my-codex-spritesheet.webp
python3 bridge/buddy.py --host <buddy-ip> pet set --pet-id moss
python3 bridge/buddy.py --host <buddy-ip> demo
```

Run a small local HTTP bridge for other tools:

```sh
python3 bridge/buddy.py --host <buddy-ip> serve
curl -X POST http://localhost:8799/message \
  -H 'content-type: application/json' \
  -d '{"title":"Agent","body":"hello"}'
curl -X POST http://localhost:8799/html \
  -H 'content-type: application/json' \
  -d '{"title":"Agent","html":"<b>hello</b>"}'
curl -X POST http://localhost:8799/video \
  -H 'content-type: application/json' \
  -d '{"url":"http://example.local/clip.mp4","loop":true,"fullscreen":true,"fit":"cover"}'

curl 'http://localhost:8799/responses?id=approval-123&consume=1'
```

The CLI uploads local media files to the Android app and sends an event with the returned `/media/...` URL. The local HTTP bridge is JSON-only, so other tools can push already-hosted URLs or HTML snippets without knowing about Android internals.

Media parameters:

- `fullscreen`: render across the whole 800x480 screen instead of inside the right panel.
- `fit`: `contain`, `cover`, or `fill`.
- `loop`: supported by video and audio.
- `controls`, `muted`, `autoplay`: supported by video.

## Pet API

Buddy mirrors the Codex desktop pet system:

- built-in pets by `petId`
- persistent custom spritesheets imported into [pets/custom/README.md](../pets/custom/README.md)
- static image overrides with `petUrl`

Built-in pet ids:

```text
claw, codex, dewey, fireball, rocky, seedy, stacky, bsod, null-signal
```

Import a custom pet once and then reuse it anywhere the bridge accepts `--pet-id`:

```sh
python3 bridge/buddy.py --host <buddy-ip> pet import --id moss ./my-codex-spritesheet.webp
python3 bridge/buddy.py --host <buddy-ip> stream --pet-id moss --title "Build" --exec zsh -lc 'make'
python3 bridge/buddy.py --host <buddy-ip> pet remove --id moss
```

The local HTTP bridge accepts the same pet fields:

- `petId`
- `petSpritesheetUrl`
- `petUrl`

## Agent API

For agent integrations, treat Buddy as a simple stream lifecycle:

1. `stream_start`: open the left-status / right-output scene
2. `stream_chunk`: append output
3. `stream_meta`: update the left-side state such as `thinking`, `running`, `waiting`, `done`
4. `approval`: temporarily overlay approval controls while keeping the stream underneath
5. `stream_end`: mark the stream complete

CLI:

```sh
python3 bridge/buddy.py --host <buddy-ip> agent start --id run1 --name Codex --status running --body "Working..."
python3 bridge/buddy.py --host <buddy-ip> agent log --id run1 "Scanning repository...\n"
python3 bridge/buddy.py --host <buddy-ip> agent status --id run1 waiting --body "Need approval"
python3 bridge/buddy.py --host <buddy-ip> agent approval --id run1 "Allow continue?" "Need your approval."
python3 bridge/buddy.py --host <buddy-ip> agent end --id run1 --status done
```

HTTP:

```sh
curl -X POST http://localhost:8799/agent/start \
  -H 'content-type: application/json' \
  -d '{"id":"run1","name":"Codex","status":"running","body":"Working..."}'

curl -X POST http://localhost:8799/agent/log \
  -H 'content-type: application/json' \
  -d '{"id":"run1","text":"Scanning repository...\n"}'

curl -X POST http://localhost:8799/agent/status \
  -H 'content-type: application/json' \
  -d '{"id":"run1","status":"waiting","body":"Need approval"}'

curl -X POST http://localhost:8799/agent/approval \
  -H 'content-type: application/json' \
  -d '{"id":"run1","title":"Allow continue?","body":"Need your approval."}'

curl -X POST http://localhost:8799/agent/end \
  -H 'content-type: application/json' \
  -d '{"id":"run1","status":"done"}'
```

Python:

```python
from bridge import BuddyClient

buddy = BuddyClient(host="<buddy-ip>")
session = buddy.agent("run1", name="Codex", status="running", body="Working...")
session.log("Scanning repository...\n")
session.status_update("waiting", body="Need approval")
session.approval("Allow continue?", "Need your approval.")
session.end("done", exit_code=0)
```

## Local adapter

Use `bridge/adapter.py` when you want to mirror a local command or a host-side agent into Buddy without writing bridge calls by hand.

### Default execution rule

For open-source integrations, the recommended default is:

- commands worth showing on Buddy should run through the adapter
- existing stdout pipelines should go through the stdin wrapper
- direct `BuddyClient` calls are for richer integrations that also need status or approval events

That makes these the default entrypoints we expect third-party agents to adopt:

- `scripts/buddy-run.sh`: wrap a command and stream its stdout/stderr
- `scripts/buddy-stdin.sh`: mirror an existing stdout stream
- `bridge/adapter.py`: lower-level adapter for custom integrations

The wrappers support environment variables, so an agent installer can set them once:

```sh
export BUDDY_HOST=<buddy-ip>
export BUDDY_NAME=Codex
export BUDDY_STATUS=running
export BUDDY_BODY="Working..."
```

Wrap a command:

```sh
python3 bridge/adapter.py --host <buddy-ip> --id run1 --name Codex --status running \
  --body "Streaming wrapped command output" \
  run --exec zsh -lc 'printf "hello from adapter\n"; ls bridge'
```

Or use the default wrapper:

```sh
scripts/buddy-run.sh zsh -lc 'printf "hello from wrapper\n"; ls bridge'
```

Mirror stdin:

```sh
some-command 2>&1 | python3 bridge/adapter.py --host <buddy-ip> --id run1 --name Codex stdin
```

Or with the stdin wrapper:

```sh
some-command 2>&1 | scripts/buddy-stdin.sh
```

Drive Buddy with JSONL events:

```sh
printf '%s\n' \
  '{"type":"log","text":"Scanning repository...\n"}' \
  '{"type":"status","status":"waiting","body":"Need approval"}' \
  '{"type":"approval","title":"Allow continue?","body":"Need your approval."}' \
  '{"type":"end","status":"done","exitCode":0}' \
  | python3 bridge/adapter.py --host <buddy-ip> --id run1 --name Codex jsonl
```

## Practical note on "connecting Codex itself"

Buddy can already show:

- wrapped command output (`agent run`, `stream --exec`, or anything piped to stdin)
- explicit status updates from a host integration
- approval overlays on top of a running stream

What it cannot do by itself is tap the Codex desktop app's internal token stream unless the host app exposes that stream to a script or plugin. In practice, the easiest near-term integration is:

- mirror assistant work updates explicitly through the agent API
- wrap shell commands and CLI tools with `agent run` / `stream --exec`
- later add a small host-side adapter if you want true token-by-token chat mirroring

More details live in [docs/protocol.md](../docs/protocol.md) and the runnable examples under [examples/](../examples/).

## Compatibility Layers

The Buddy bridge is the stable core. Host-specific behavior should live in a
compatibility layer, not in the Android app protocol itself.

Built-in modules:

- [bridge/compat/claude_desktop_buddy.py](compat/claude_desktop_buddy.py)
- [bridge/compat/claude_code.py](compat/claude_code.py)
- [bridge/compat/codex_private.py](compat/codex_private.py)
- [bridge/compat/openclaw.py](compat/openclaw.py)
- [bridge/compat/qwenpaw.py](compat/qwenpaw.py)
- [bridge/compat/base.py](compat/base.py)

Use the compat layer that matches the host:

- **Claude Desktop Buddy**: translate Anthropic's documented hardware buddy
  heartbeat snapshots, turn events, and permission prompts through
  [bridge/compat/claude_desktop_buddy.py](compat/claude_desktop_buddy.py)
  or the stdin bridge at
  [bridge/claude_desktop_buddy_bridge.py](claude_desktop_buddy_bridge.py).
- **Claude Code**: translate host snapshots and turn events into Buddy protocol
  events before sending them to the device.
- **Codex Desktop**: use the private sidecar monitor under
  [integrations/codex/](../integrations/codex/).
  This is an experimental monitor over private local state, not a public host API.
- **openclaw**: translate structured lifecycle events such as `start`, `log`,
  `status`, `approval`, and `end`.
- **QwenPaw**: translate `/api/console/chat` SSE payloads and
  `/api/approval/list` records. In production, prefer the installer-based
  runtime patch; a ready-to-run manual bridge script lives at
  [bridge/qwenpaw_bridge.py](qwenpaw_bridge.py).
- **Other agents**: add another module under `bridge/compat/`.

This gives every host a clear integration entrypoint while keeping the Buddy
protocol stable.

### Claude Desktop Buddy entrypoints

If you already have Anthropic hardware buddy NDJSON payloads, the simplest
bridge is:

```sh
python3 bridge/claude_desktop_buddy_bridge.py \
  --buddy-host <buddy-ip> \
  --stream-id claude-desktop \
  < hardware-buddy.ndjson
```

That bridge expects the exact snapshot / turn payload families documented by
Anthropic in
[claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy)
and
[REFERENCE.md](https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md).

For a pure Python embedding path, use:

```python
from bridge import BuddyClient, ClaudeDesktopBuddyCompatAdapter

buddy = BuddyClient(host="<buddy-ip>")
adapter = ClaudeDesktopBuddyCompatAdapter(stream_id="claude-desktop")
for event in adapter.translate(native_payload):
    buddy.send_event(event)
```

If Buddy approvals need to go back into the Claude Desktop transport, convert
them into Anthropic permission commands with:

```python
ClaudeDesktopBuddyCompatAdapter.buddy_response_to_permission_command(
    {"action": "approve"},
    "req_abc123",
)
```

### Codex entrypoints

The preferred Codex entrypoint is now:

```sh
./integrations/codex/start.sh
```

Stop it with:

```sh
./integrations/codex/stop.sh
```

The legacy bridge path still works for backward compatibility:

```sh
python3 bridge/codex_private_bridge.py --buddy-host <buddy-ip>
```

### QwenPaw entrypoints

For installed QwenPaw hosts, the runtime patch is the intended default path:
normal `/api/console/chat` output and session-scoped channel output that flows
through QwenPaw's channel manager are mirrored automatically.

Installed hosts also get a local restore helper:

```sh
~/.qwenpaw/buddy/bin/qwenpaw-buddy-uninstall
```

The manual debug entrypoint is:

```sh
python3 bridge/qwenpaw_bridge.py \
  --qwenpaw-url http://127.0.0.1:8088 \
  --buddy-host <buddy-ip> \
  --name QwenPaw \
  chat \
  --session-id qwenpaw-demo \
  --user-id buddy-test \
  --text 'Hello from QwenPaw'
```

To relay approvals back from Buddy into QwenPaw:

```sh
python3 bridge/qwenpaw_bridge.py \
  --qwenpaw-url http://127.0.0.1:8088 \
  --buddy-host <buddy-ip> \
  watch-approvals
```

For a host-side install flow, see
[integrations/qwenpaw/install.sh](../integrations/qwenpaw/install.sh)
and
[integrations/qwenpaw/README.md](../integrations/qwenpaw/README.md).

Installed QwenPaw hosts use runtime hooks for normal output mirroring. The
`qwenpaw_bridge.py chat` command is primarily for manual debugging or hosts
where runtime patching is disabled.

See [docs/compatibility.md](../docs/compatibility.md)
for the structure and examples.
