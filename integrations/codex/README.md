# Codex Integration

This integration is a **private sidecar monitor** for Codex Desktop.

It is not a formal Codex plugin API. Instead, it watches local Codex state and
session files, infers thread lifecycle changes, and mirrors them into Buddy.

Today it can mirror:

- `thinking`
- `waiting / needs input`
- `done / failed`
- recent assistant text blocks for the followed thread

## Session model

Buddy is best at showing **one foreground Codex session at a time**.

So there are two practical modes:

- **Pinned thread**: follow one specific Codex thread id
- **Follow latest**: automatically switch to whichever Codex thread was updated most recently

`Follow latest` is the recommended default if you want Buddy to react when you
move between Codex sessions.

## What This Is

Use this integration when you want Buddy to follow the Codex Desktop thread
running on the same machine.

The implementation lives here:

- monitor: [monitor.py](monitor.py)
- compat adapter: [bridge/compat/codex_private.py](../../bridge/compat/codex_private.py)

The legacy entrypoint still exists for backward compatibility:

- [bridge/codex_private_bridge.py](../../bridge/codex_private_bridge.py)

## Start

```sh
./integrations/codex/start.sh
```

By default, `start.sh` also sends a light Buddy-side confirmation card such as
`Codex linked`, so the screen does not stay on an older demo scene while you
wait for the next real Codex event.

Useful environment variables:

```sh
export BUDDY_HOST=<buddy-ip>
export BUDDY_CODEX_THREAD_ID=019dafba-5428-7352-b77f-95c3a4db344a
export BUDDY_CODEX_QUIET_DONE_SECONDS=20
./integrations/codex/start.sh
```

To follow the latest active session instead of pinning one thread:

```sh
unset BUDDY_CODEX_THREAD_ID
./integrations/codex/start.sh
```

or equivalently:

```sh
export BUDDY_CODEX_THREAD_ID=latest
./integrations/codex/start.sh
```

To disable that startup confirmation:

```sh
export BUDDY_CODEX_BOOTSTRAP=0
./integrations/codex/start.sh
```

## Stop

```sh
./integrations/codex/stop.sh
```

## Restart

```sh
./integrations/codex/restart.sh
```

## Status

```sh
./integrations/codex/status.sh
```

`status.sh` shows:

- whether the sidecar pid is alive
- the local runtime status json
- the current Buddy `/api/state`
- the recent sidecar log tail

## Notes

- This integration depends on Codex private local storage under `~/.codex/`.
- It is intentionally labeled experimental because the host format is not a
  public stable API.
- The `waiting` state is currently inferred conservatively from recent assistant
  output and quiet-time behavior, not from a documented official host event.
