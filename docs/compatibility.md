# Buddy Compatibility Layers

Buddy has one stable device protocol and many possible host integrations.

That split is intentional:

- the **Buddy protocol** is the common wire format
- a **compatibility layer** translates one host or agent family into that format

This lets the Android app stay generic while each agent keeps a host-specific
entrypoint.

## Core Idea

Think of Buddy in two layers:

1. **Protocol layer**
   - `stream_start`
   - `stream_chunk`
   - `stream_meta`
   - `approval`
   - `stream_end`

2. **Compatibility layer**
   - Claude Code host snapshots
   - openclaw lifecycle events
   - custom agents
   - future host plugins

The protocol is documented in [protocol.md](protocol.md).

## Built-in Compatibility Modules

Buddy now ships a small compatibility package:

- [bridge/compat/base.py](../bridge/compat/base.py)
- [bridge/compat/claude_desktop_buddy.py](../bridge/compat/claude_desktop_buddy.py)
- [bridge/compat/claude_code.py](../bridge/compat/claude_code.py)
- [bridge/compat/codex_private.py](../bridge/compat/codex_private.py)
- [bridge/compat/openclaw.py](../bridge/compat/openclaw.py)
- [bridge/compat/qwenpaw.py](../bridge/compat/qwenpaw.py)

These modules do **not** scrape or hook desktop apps by themselves. They define
how a host integration should translate its native payloads into Buddy events.

## Claude Desktop Buddy

Use the Claude Desktop Buddy compatibility layer when you already have access
to the newline-delimited JSON payloads described by Anthropic's Hardware Buddy
bridge. The native protocol sends:

- heartbeat snapshots with `total`, `running`, `waiting`, `msg`, `entries`,
  `tokens`, `tokens_today`, and optional `prompt`
- one-shot completed turn events with `evt:"turn"`
- permission decisions that must be echoed back with
  `{"cmd":"permission","id":"...","decision":"once|deny"}`

Recommended entrypoint:

```python
from bridge.compat import ClaudeDesktopBuddyCompatAdapter

adapter = ClaudeDesktopBuddyCompatAdapter(stream_id="claude-desktop-1")
events = adapter.translate({
    "total": 3,
    "running": 1,
    "waiting": 0,
    "msg": "reading file...",
    "entries": ["10:42 reading file...", "10:41 planning next step..."],
})
```

For a runnable stdin bridge, use:

```sh
python3 bridge/claude_desktop_buddy_bridge.py \
  --buddy-host 10.214.75.86 \
  --stream-id claude-desktop \
  < hardware-buddy.ndjson
```

When Buddy returns an approval response, translate it back with:

```python
ClaudeDesktopBuddyCompatAdapter.buddy_response_to_permission_command(
    {"action": "approve"},
    "req_abc123",
)
```

This maps directly onto Anthropic's documented hardware buddy protocol in
[claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy) and
its [REFERENCE.md](https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md).

## Claude Code

Use the Claude Code compatibility layer when the host can provide Claude-style:

- snapshot updates
- thinking or running status changes
- recent transcript entries
- approval prompts
- turn-complete events

Recommended entrypoint:

```python
from bridge.compat import ClaudeCodeCompatAdapter

adapter = ClaudeCodeCompatAdapter(stream_id="claude-run-1")
events = adapter.translate({
    "type": "snapshot",
    "status": "running",
    "msg": "Checking environment...",
    "entries": ["Preparing command...", "Checking environment..."],
})
```

The adapter returns Buddy protocol events, which the host can forward through
`BuddyClient.send_event(...)` or the HTTP bridge.

If the host can emit a distinct `thinking` status, Buddy preserves it as
`thinking`; it does not have to be flattened into `running`.

This is conceptually aligned with Anthropic's host-specific bridge model in
[claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy) and
its [REFERENCE.md](https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md),
but our transport stays HTTP/WebSocket and our payload surface stays Buddy-native.

## Codex Desktop (private, experimental)

Codex Desktop does appear to maintain real internal thread lifecycle state,
including concepts equivalent to:

- thinking / running
- waiting on user input
- failed
- ready / unread output

At the moment we have **not** found a public, stable external host API for that
state. What we *have* found is:

- a private renderer-host message bus
- private `thread-stream-state-changed` events
- private shared-object subscriptions
- local sqlite logs that reveal active turn sampling

Buddy therefore ships an **experimental private bridge**:

- [bridge/compat/codex_private.py](../bridge/compat/codex_private.py)
- [integrations/codex/monitor.py](../integrations/codex/monitor.py)
- [integrations/codex/start.sh](../integrations/codex/start.sh)
- [integrations/codex/stop.sh](../integrations/codex/stop.sh)
- legacy entrypoint: [bridge/codex_private_bridge.py](../bridge/codex_private_bridge.py)

The current bridge follows local Codex sqlite state and log files and mirrors
the most reliable lifecycle we can infer today:

- `thinking` while Codex is actively sampling
- `waiting / needs input` after recent assistant output settles and the thread
  appears to be waiting on the user
- `done / failed` when the activity clearly completes
- recent assistant text blocks for the followed thread

Recommended entrypoint:

```sh
./integrations/codex/start.sh
```

Or pin it to a specific Codex thread:

```sh
export BUDDY_HOST=10.214.75.86
export BUDDY_CODEX_THREAD_ID=019dafba-5428-7352-b77f-95c3a4db344a
./integrations/codex/start.sh
```

Important caveats:

- this relies on **private Codex internals**
- it may break after Codex updates
- `thinking/running` is still the most reliable state today
- `waiting` is currently inferred heuristically rather than read from a public host flag

Stop the monitor with:

```sh
./integrations/codex/stop.sh
```

Operational helpers:

```sh
./integrations/codex/restart.sh
./integrations/codex/status.sh
```

## openclaw

Use the openclaw compatibility layer when you control the agent launcher or
source code and can emit structured lifecycle events.

Recommended entrypoint:

```python
from bridge.compat import OpenClawCompatAdapter

adapter = OpenClawCompatAdapter(stream_id="openclaw-run-1")
events = adapter.translate({
    "type": "approval",
    "id": "approval-1",
    "title": "Allow continue?",
    "body": "Need your approval before the next step.",
})
```

For openclaw-style agents, the most practical default is:

- wrap shell execution with `scripts/buddy-run.sh`
- stream raw output with `scripts/buddy-stdin.sh`
- send richer status and approval events through the compat layer

## QwenPaw

Use the QwenPaw compatibility layer when the host exposes QwenPaw's HTTP API
or when you want to mirror channel-scoped output from an installed QwenPaw
host.

Today the most useful endpoints are:

- `/api/console/chat` for SSE response streaming
- `/api/approval/list` for pending approvals
- `/api/approval/approve` and `/api/approval/deny` for replying

Recommended entrypoint:

```python
from bridge.compat import QwenPawCompatAdapter

adapter = QwenPawCompatAdapter(stream_id="qwenpaw-run-1")
events = adapter.translate({
    "object": "response",
    "status": "created",
    "session_id": "qwenpaw-run-1",
})
```

For a real runnable manual bridge, use
[bridge/qwenpaw_bridge.py](../bridge/qwenpaw_bridge.py).
It can:

- send a prompt to QwenPaw
- mirror the live SSE stream into Buddy
- watch QwenPaw approvals and relay Buddy responses back

For the recommended automatic mode, use the installer in
[integrations/qwenpaw/install.sh](../integrations/qwenpaw/install.sh),
which patches QwenPaw runtime so normal console sessions and channel-manager
sessions mirror to Buddy without the agent explicitly calling
`qwenpaw_bridge.py`.

Installed QwenPaw hosts also get a local restore path:

```sh
~/.qwenpaw/buddy/bin/qwenpaw-buddy-uninstall
```

Example commands:

```sh
python3 bridge/qwenpaw_bridge.py \
  --qwenpaw-url http://127.0.0.1:8088 \
  --buddy-host 10.214.75.86 \
  --name QwenPaw \
  chat \
  --session-id qwenpaw-demo \
  --user-id buddy-test \
  --text 'Hello from QwenPaw'
```

```sh
python3 bridge/qwenpaw_bridge.py \
  --qwenpaw-url http://127.0.0.1:8088 \
  --buddy-host 10.214.75.86 \
  watch-approvals
```

## Adding Another Host

When you add a new agent family, do not change the Android app first.

Instead:

1. add a new module under `bridge/compat/`
2. translate the host's native events into Buddy protocol events
3. document the expected entrypoint in the README

That keeps the app generic and makes integrations easy to reason about.

Suggested file pattern:

```text
bridge/compat/<host_name>.py
examples/<host_name>_demo.py
```

Example entrypoints already included:

- [examples/claude_code_compat_demo.py](../examples/claude_code_compat_demo.py)
- [examples/claude_desktop_buddy_demo.py](../examples/claude_desktop_buddy_demo.py)
- [examples/openclaw_compat_demo.py](../examples/openclaw_compat_demo.py)
- [examples/qwenpaw_compat_demo.py](../examples/qwenpaw_compat_demo.py)

## Rule of Thumb

- If the host only has stdout: use the wrapper scripts.
- If the host has structured lifecycle events: add a compat adapter.
- If the host exposes snapshots, prompts, or turn events: map them through a
  compat adapter instead of bypassing the protocol.
