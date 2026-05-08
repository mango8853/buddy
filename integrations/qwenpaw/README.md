# QwenPaw Installation

This integration installs a small Buddy bridge next to an existing QwenPaw
deployment, and can also patch the running QwenPaw host so Buddy mirroring
becomes automatic.

## What it installs

- `qwenpaw-buddy-chat`: send one QwenPaw console session to Buddy
- `qwenpaw-buddy-watch-approvals`: relay Buddy approval replies back into QwenPaw
- `qwenpaw-buddy-uninstall`: restore patched QwenPaw files and remove Buddy glue
- a local `bridge/` copy with:
  - `client.py`
  - `compat/base.py`
  - `compat/qwenpaw.py`
  - `qwenpaw_bridge.py`
- `install-manifest.json` with the patched file list and restore metadata
- an optional runtime patch inside QwenPaw itself:
  - auto-mirror `/api/console/chat` output to Buddy
  - auto-mirror session-scoped channel output that flows through the QwenPaw channel manager
  - auto-push approval requests to Buddy
  - auto-poll Buddy approval responses when `--responses-url` is set

Default install location:

```text
~/.qwenpaw/buddy
```

## Install

From the Buddy repo:

```sh
./integrations/qwenpaw/install.sh \
  --buddy-host 10.214.75.86 \
  --qwenpaw-url http://127.0.0.1:8088
```

If you also want approval relay from Buddy back into QwenPaw:

```sh
./integrations/qwenpaw/install.sh \
  --buddy-host 10.214.75.86 \
  --qwenpaw-url http://127.0.0.1:8088 \
  --responses-url http://YOUR_BRIDGE_HOST:8799/responses
```

`YOUR_BRIDGE_HOST` should be the host running `python3 bridge/buddy.py serve`.

By default, the installer also patches QwenPaw runtime and appends a short
Buddy note into `~/.qwenpaw/workspaces/default/AGENTS.md`.

## Use

After installation, normal QwenPaw console sessions and channel-manager
sessions are mirrored automatically. The agent does not need to call
`qwenpaw_bridge.py` for ordinary session output that flows through QwenPaw's
channel lifecycle.

Manual debug entrypoint:

```sh
~/.qwenpaw/buddy/bin/qwenpaw-buddy-chat \
  --session-id qwenpaw-demo \
  --user-id buddy-test \
  --text 'Hello from QwenPaw'
```

Relay approvals:

```sh
~/.qwenpaw/buddy/bin/qwenpaw-buddy-watch-approvals
```

Remove the integration and restore patched files:

```sh
~/.qwenpaw/buddy/bin/qwenpaw-buddy-uninstall
```

## Automatic mode

If runtime patching is enabled, normal QwenPaw console sessions and
channel-manager sessions will mirror to Buddy automatically. In that mode,
`qwenpaw-buddy-chat` becomes a manual debug or test entrypoint rather than the
main path.

The runtime patch adds:

- a small `qwenpaw.app.buddy_runtime` module
- hooks in `/api/console/chat` SSE streaming and the shared channel manager
- hooks for approval creation and resolution
- a short `Buddy Integration` note in `~/.qwenpaw/workspaces/default/AGENTS.md`

Backups are written next to patched QwenPaw files with a `.buddy.bak` suffix.

## Restore and cleanup

The installer records restore metadata in:

```text
~/.qwenpaw/buddy/install-manifest.json
```

The uninstall helper will:

- restore patched QwenPaw files from `.buddy.bak`
- remove `qwenpaw.app.buddy_runtime`
- remove the injected `Buddy Integration` note from `AGENTS.md`
- remove `~/.qwenpaw/buddy` unless you pass `--keep-install-dir`

Useful flags:

```sh
~/.qwenpaw/buddy/bin/qwenpaw-buddy-uninstall --keep-install-dir
~/.qwenpaw/buddy/bin/qwenpaw-buddy-uninstall --keep-agents-md
```
