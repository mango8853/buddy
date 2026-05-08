# Buddy Protocol

This document describes the stable host-to-device protocol for Buddy.

## Transport

Buddy accepts JSON events over:

- `POST /api/event` on the Android device
- WebSocket text frames on the device's WebSocket endpoint
- the local host bridge started with `python3 bridge/buddy.py serve`

The recommended host lifecycle is:

```text
stream_start -> stream_chunk* -> stream_meta* -> approval? -> stream_end
```

Pet selection is orthogonal to scene type. Any event may include:

- `petId`: built-in or imported custom pet id
- `petSpritesheetUrl`: Codex-format animated spritesheet override
- `petUrl`: static image override

## Device Endpoints

The Android app listens on port `8787`.

- `GET /health` or `GET /api/health`
- `GET /state` or `GET /api/state`
- `GET /version` or `GET /api/version`
- `POST /api/event`
- `POST /api/upload`
- `POST /api/clear`
- `GET /media/<name>`

### Health

```json
{"ok": true, "name": "buddy"}
```

### Version

```json
{"ok": true, "name": "buddy", "version": "0.1.0", "package": "com.codex.buddy"}
```

## Core Events

### `message`

Shows a simple idle-state message on the left panel.

```json
{
  "type": "message",
  "title": "Agent",
  "body": "Task finished",
  "mood": "noted"
}
```

### `approval`

Temporarily shows approval controls. If the current scene is a stream, Buddy overlays approval on top of it and then resumes the stream afterwards.

```json
{
  "type": "approval",
  "id": "approval-123",
  "streamId": "run-1",
  "title": "Allow continue?",
  "body": "Need your approval before the next step.",
  "approveLabel": "确认",
  "denyLabel": "拒绝"
}
```

When the user acts, Buddy emits a `response` event back to the configured bridge:

```json
{
  "type": "response",
  "id": "approval-123",
  "action": "approve",
  "side": "left",
  "ts": 1710000000000
}
```

### `stream_start`

Opens the left-status / right-output stream scene.

```json
{
  "type": "stream_start",
  "streamId": "run-1",
  "title": "Codex",
  "body": "Working...",
  "mood": "running",
  "petId": "rocky",
  "maxLines": 160,
  "maxChars": 12000
}
```

### `stream_chunk`

Appends output to an existing stream.

```json
{
  "type": "stream_chunk",
  "streamId": "run-1",
  "text": "Scanning repository...\n"
}
```

### `stream_meta`

Updates left-side status text without resetting the stream.

```json
{
  "type": "stream_meta",
  "streamId": "run-1",
  "status": "waiting",
  "title": "Codex",
  "body": "Waiting for approval"
}
```

### `stream_end`

Marks the stream complete.

```json
{
  "type": "stream_end",
  "streamId": "run-1",
  "status": "done",
  "exitCode": 0
}
```

### Media Events

Supported `type` values:

- `image`
- `video`
- `audio`
- `html`

Common fields:

- `title`
- `body`
- `fullscreen`
- `fit`: `contain`, `cover`, `fill`
- `petId`
- `petSpritesheetUrl`
- `petUrl`

Video fields:

- `loop`
- `controls`
- `muted`
- `autoplay`

Audio fields:

- `loop`

## Local Host Bridge

The local bridge started with `python3 bridge/buddy.py serve` adds convenience endpoints for other host tools:

- `GET /health`
- `GET /state`
- `GET /version`
- `GET /next`
- `GET /responses`
- `POST /message`
- `POST /approval`
- `POST /image`
- `POST /video`
- `POST /audio`
- `POST /html`
- `POST /pet`
- `POST /scene`
- `POST /stream/start`
- `POST /stream/chunk`
- `POST /stream/end`
- `POST /agent/start`
- `POST /agent/log`
- `POST /agent/status`
- `POST /agent/approval`
- `POST /agent/end`
- `POST /response`

### Polling approval results

`GET /responses` returns all captured `response` events from the device.

Query options:

- `id=<approval-id>`: filter to one approval id
- `consume=1`: remove returned entries from the queue

Example:

```sh
curl 'http://127.0.0.1:8799/responses?id=approval-123&consume=1'
```

## Compatibility Notes

- The Android device is the source of truth for scene state.
- Buddy persists the last non-response state and restores it after app restart.
- The stream scene currently prioritizes stable auto-follow over manual touch scrolling.
