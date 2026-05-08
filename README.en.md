# Buddy

Chinese README: [README.md](README.md)

Buddy turns a rooted touch-screen speaker into a small local agent display.

Buddy is built around three pieces:

- an Android display app for a small always-on screen
- a host bridge for streams, approvals, media, and pets
- host-specific integrations for Codex, QwenPaw, Claude Desktop Buddy, and wrapper-based agents

The Android app itself is intentionally generic:

- full-screen WebView UI
- small animated buddy
- HTTP API on port `8787`
- WebSocket endpoint
- approval buttons that return responses

## Current Status

Buddy is already usable as an alpha-stage open-source project.

Stable enough to build on:

- Android app, media scenes, stream scene, approval overlay
- autostart helper on the target device
- CLI / HTTP / Python bridge surfaces
- QwenPaw integration
- Codex private sidecar integration
- Claude Desktop Buddy compatibility bridge

Still intentionally experimental:

- host-specific state inference where no public host API exists
- exact behavior of private desktop integrations after upstream app updates

Device-specific root tasks, such as SSH or Wi-Fi ADB setup, live in `scripts/` and are not part of the APK.

## Fresh Install

In this section, "device" means the Android touch-screen device that will run the Buddy display app. For example, a USB-debuggable smart speaker or a small Android panel.

For a fresh install, give your local agent this task:

```text
Install Buddy onto my Android device over USB.

GitHub repository: https://github.com/mango8853/buddy.git

Known inputs:
- I have an Android touch device with USB debugging enabled.
- The device is connected to this computer over USB.
- If adb asks for authorization, tell me to approve it on the device.

Please do:
1. Clone the repository.
2. Check or prepare runtime dependencies: git, python3, adb, and curl or python3 for downloads.
3. Find the target device with adb. If more than one device is connected, ask me to choose one or use ADB_SERIAL.
4. Run install-buddy-release.sh. It prefers prebuilt APKs from GitHub Releases; if release assets are not available yet, it uses the APKs shipped in the repository under dist/.
5. If both release assets and dist APKs are unavailable, use source build as a fallback: prepare JDK 17, Android SDK platform 35, Android build-tools 35.0.0, then run install-buddy-device.sh.
6. Enable the autostart helper and launch Buddy once.
7. Find the device wlan0 IP address and store it as BUDDY_HOST.
8. Verify the device with: python3 bridge/buddy.py --host $BUDDY_HOST health
9. Send one test message to the Buddy screen.
10. Tell me the detected BUDDY_HOST and whether installation succeeded.
```

The command flow usually looks like this:

```sh
git clone https://github.com/mango8853/buddy.git
cd buddy

# If adb is not in PATH:
# export ADB=/path/to/adb
#
# If more than one adb device is connected:
# export ADB_SERIAL=<adb-serial>

./install-buddy-release.sh
```

This script:

- prefers prebuilt `buddy.apk` from GitHub Releases
- prefers prebuilt `buddy-autostart.apk` from GitHub Releases
- falls back to `dist/buddy.apk` and `dist/buddy-autostart.apk` from the cloned repository
- installs both packages onto the adb-connected Android device
- explicitly runs `pm enable com.codex.buddyautostart`
- launches Buddy once

So the boot helper is not only present in the manifest, but also left enabled on
the target device by default.

The script prints the detected `wlan0` IP candidates at the end. Use that address as `<buddy-ip>`:

```sh
export BUDDY_HOST=<buddy-ip>
python3 bridge/buddy.py --host "$BUDDY_HOST" health
```

If you want to build from source, or if the release APKs are not available yet, use the developer install script:

```sh
# Requires JDK 17, Android SDK platform 35, and Android build-tools 35.0.0.
./install-buddy-device.sh
```

## Send Events

```sh
python3 bridge/buddy.py --host <buddy-ip> message "hello" --title "Agent"
python3 bridge/buddy.py --host <buddy-ip> approval "Allow?" "Continue running this task?"
python3 bridge/buddy.py --host <buddy-ip> image ./photo.png --title "Snapshot"
python3 bridge/buddy.py --host <buddy-ip> video ./clip.mp4 --title "Preview" --loop --fullscreen --fit cover
python3 bridge/buddy.py --host <buddy-ip> audio ./ding.wav --title "Done" --loop
python3 bridge/buddy.py --host <buddy-ip> html '<b style="font-size:32px">OK</b>' --title "HTML" --fullscreen
python3 bridge/buddy.py --host <buddy-ip> stop-audio
python3 bridge/buddy.py --host <buddy-ip> pet list
python3 bridge/buddy.py --host <buddy-ip> pet import --id moss ./my-pet-spritesheet.webp
python3 bridge/buddy.py --host <buddy-ip> pet set --pet-id dewey
python3 bridge/buddy.py --host <buddy-ip> pet set --pet-id moss
```

For local tools that prefer HTTP:

```sh
python3 bridge/buddy.py --host <buddy-ip> serve
curl -X POST http://localhost:8799/message \
  -H 'content-type: application/json' \
  -d '{"title":"Agent","body":"hello"}'
curl -X POST http://localhost:8799/html \
  -H 'content-type: application/json' \
  -d '{"title":"Card","html":"<div style=\"font-size:28px\">hello</div>"}'
curl -X POST http://localhost:8799/video \
  -H 'content-type: application/json' \
  -d '{"url":"http://example.local/clip.mp4","title":"Clip","loop":true,"fullscreen":true,"fit":"cover"}'
```

The direct CLI can upload local images, videos, and audio files to the Android app before sending the event. The lightweight HTTP bridge accepts JSON events and is useful for agent integrations; for binary file upload, call the CLI or POST directly to the Android app's `/api/upload`.

Media events support `fullscreen`, `fit` (`contain`, `cover`, `fill`), and text fields. Video also supports `loop`, `controls`, `muted`, and `autoplay`; audio supports `loop`.

## Pets

Buddy now mirrors the Codex desktop pet model:

- built-in Codex pets by `petId`
- custom animated pets via `petSpritesheetUrl`
- legacy static pet images via `petUrl`

Built-in pets:

```text
claw, codex, dewey, fireball, rocky, seedy, stacky, bsod, null-signal
```

Examples:

```sh
python3 bridge/buddy.py --host <buddy-ip> pet set --pet-id codex
python3 bridge/buddy.py --host <buddy-ip> stream --pet-id rocky --title "Build" --exec zsh -lc 'make'
python3 bridge/buddy.py --host <buddy-ip> pet import --id moss ./my-codex-format-spritesheet.webp
python3 bridge/buddy.py --host <buddy-ip> pet set --pet-id moss
python3 bridge/buddy.py --host <buddy-ip> pet remove --id moss
```

Custom pets are stored under [pets/custom/README.md](pets/custom/README.md). Importing one copies the spritesheet into the repo-local custom pet directory, so later `stream`, `scene`, and `agent` commands can reuse it by `petId`.

Custom pets should use the same Codex-style spritesheet layout as the desktop app: 8 columns by 9 rows, with the same state rows used by Buddy (`idle`, `running`, `running-left`, `running-right`, `waiting`, `review`, `failed`, `jumping`, `waving`).

## Agent Integration

Buddy now has a stable agent-oriented surface:

- CLI lifecycle commands under `agent`
- matching local HTTP endpoints under `/agent/*`
- a small importable Python client in `bridge/client.py`
- a local adapter in `bridge/adapter.py` for wrapping commands or stdin streams

The intended lifecycle is:

```text
start -> log/chunk -> status/meta -> approval (optional) -> end
```

Examples:

```sh
python3 bridge/buddy.py --host <buddy-ip> agent start --id run1 --name Codex --status running --body "Working..."
python3 bridge/buddy.py --host <buddy-ip> agent log --id run1 "Scanning repository...\n"
python3 bridge/buddy.py --host <buddy-ip> agent approval --id run1 "Allow continue?" "Need your approval."
python3 bridge/buddy.py --host <buddy-ip> agent end --id run1 --status done
```

```python
from bridge import BuddyClient

buddy = BuddyClient(host="<buddy-ip>")
session = buddy.agent("run1", name="Codex", status="running", body="Working...")
session.log("Scanning repository...\n")
session.approval("Allow continue?", "Need your approval.")
session.end("done")
```

This is enough for:

- mirroring shell command output
- streaming agent logs
- pausing for approval without losing the stream underneath

### Default rule for host agents

If an agent is installed against this project, the default rule should be:

- anything worth showing on Buddy runs through `scripts/buddy-run.sh`
- existing stdout pipelines go through `scripts/buddy-stdin.sh`
- richer host integrations can call `bridge/client.py` directly for status and approval events

Minimal setup:

```sh
export BUDDY_HOST=<buddy-ip>
export BUDDY_NAME=Codex
export BUDDY_STATUS=running
```

Examples:

```sh
scripts/buddy-run.sh zsh -lc 'git status'
```

```sh
some-command 2>&1 | scripts/buddy-stdin.sh
```

True token-by-token mirroring of a desktop chat UI still needs host-side support from that app; the Buddy bridge can consume such a stream once the host exposes it.

## Compatibility Layers

Buddy should expose one stable device protocol and many host-specific adapters.

That means:

- the Android app and Buddy protocol stay generic
- each agent family gets its own compatibility layer
- the README can tell integrators exactly which entrypoint to use

Today the built-in compatibility package lives under [bridge/compat/](bridge/compat/):

- [bridge/compat/claude_desktop_buddy.py](bridge/compat/claude_desktop_buddy.py)
- [bridge/compat/claude_code.py](bridge/compat/claude_code.py)
- [bridge/compat/codex_private.py](bridge/compat/codex_private.py)
- [bridge/compat/openclaw.py](bridge/compat/openclaw.py)
- [bridge/compat/qwenpaw.py](bridge/compat/qwenpaw.py)
- shared base helpers in [bridge/compat/base.py](bridge/compat/base.py)

Use them like this:

- **Claude Desktop Buddy**: route Anthropic hardware buddy heartbeat snapshots,
  recent transcript entries, permission prompts, and `evt:"turn"` events
  through the Claude Desktop Buddy compat layer or stdin bridge.
- **Claude Code**: route host snapshots, transcript entries, approval prompts, and turn-complete events through the Claude Code compat layer.
- **Codex Desktop**: use the private sidecar monitor under [integrations/codex/](integrations/codex/). It mirrors thread-local `thinking`, `waiting`, `done/failed`, and recent assistant text into Buddy.
- **openclaw**: route structured lifecycle events through the openclaw compat layer.
- **QwenPaw**: prefer the installer-based runtime patch for automatic Buddy mirroring; use [bridge/qwenpaw_bridge.py](bridge/qwenpaw_bridge.py) as the manual/debug bridge entrypoint.
- **other agents**: add another module under `bridge/compat/` instead of changing the Android app protocol.

This keeps Buddy's wire format stable while letting each host integration feel native.

### Claude Desktop Buddy Quick Start

If you already have newline-delimited JSON payloads from Anthropic's hardware
buddy bridge, pipe them into:

```sh
python3 bridge/claude_desktop_buddy_bridge.py \
  --buddy-host <buddy-ip> \
  --stream-id claude-desktop \
  < hardware-buddy.ndjson
```

This path is designed around Anthropic's documented protocol in
[claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy) and
[REFERENCE.md](https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md):
heartbeat snapshots with `total/running/waiting/msg/entries/prompt`, plus
completed `evt:"turn"` messages.

If you need to translate Buddy approval results back into Anthropic permission
commands, use:

```python
from bridge import ClaudeDesktopBuddyCompatAdapter

ClaudeDesktopBuddyCompatAdapter.buddy_response_to_permission_command(
    {"action": "approve"},
    "req_abc123",
)
```

### Codex Quick Start

The Codex integration is a private sidecar monitor, not an official plugin API.

Use the new integration directory:

```sh
./integrations/codex/start.sh
```

Useful variables:

```sh
export BUDDY_HOST=<buddy-ip>
export BUDDY_CODEX_THREAD_ID=019dafba-5428-7352-b77f-95c3a4db344a
./integrations/codex/start.sh
```

If you want Buddy to react as you switch between Codex sessions, do **not** pin
one thread id:

```sh
unset BUDDY_CODEX_THREAD_ID
./integrations/codex/start.sh
```

Stop it with:

```sh
./integrations/codex/stop.sh
```

Restart or inspect it with:

```sh
./integrations/codex/restart.sh
./integrations/codex/status.sh
```

Details live in
[integrations/codex/README.md](integrations/codex/README.md).

### QwenPaw Quick Start

For a manual or debug bridge, if QwenPaw is already running and reachable over
HTTP, use:

```sh
python3 bridge/qwenpaw_bridge.py \
  --qwenpaw-url http://127.0.0.1:8088 \
  --buddy-host <buddy-ip> \
  --name QwenPaw \
  chat \
  --session-id qwenpaw-demo \
  --user-id buddy-test \
  --text 'Please reply in exactly three short lines: QWENPAW, BUDDY, OK.'
```

If you also want Buddy approvals to reply back into QwenPaw:

```sh
python3 bridge/qwenpaw_bridge.py \
  --qwenpaw-url http://127.0.0.1:8088 \
  --buddy-host <buddy-ip> \
  watch-approvals
```

For the recommended automatic mode, install the QwenPaw integration onto the
QwenPaw host:

```sh
./integrations/qwenpaw/install.sh \
  --buddy-host <buddy-ip> \
  --qwenpaw-url http://127.0.0.1:8088
```

Installer details live in
[integrations/qwenpaw/README.md](integrations/qwenpaw/README.md).

After installation, QwenPaw's normal `/api/console/chat` stream is mirrored to
Buddy automatically, and the broader channel lifecycle is patched so session-
scoped outputs that flow through QwenPaw's channel manager also mirror into
Buddy. `bridge/qwenpaw_bridge.py` remains available as a manual debug
entrypoint, but it is no longer the main path for installed QwenPaw hosts.

To restore patched files and remove the integration:

```sh
~/.qwenpaw/buddy/bin/qwenpaw-buddy-uninstall
```

## Protocol and Examples

- Protocol: [docs/protocol.md](docs/protocol.md)
- Compatibility layers: [docs/compatibility.md](docs/compatibility.md)
- Publish checklist: [docs/publish-checklist.md](docs/publish-checklist.md)
- Python agent demo: [examples/python_agent_demo.py](examples/python_agent_demo.py)
- Claude Code compat demo: [examples/claude_code_compat_demo.py](examples/claude_code_compat_demo.py)
- Claude Desktop Buddy compat demo: [examples/claude_desktop_buddy_demo.py](examples/claude_desktop_buddy_demo.py)
- openclaw compat demo: [examples/openclaw_compat_demo.py](examples/openclaw_compat_demo.py)
- QwenPaw compat demo: [examples/qwenpaw_compat_demo.py](examples/qwenpaw_compat_demo.py)
- JSONL adapter demo: [examples/jsonl_demo.sh](examples/jsonl_demo.sh)
- Wrapped command demo: [examples/wrapped_command_demo.sh](examples/wrapped_command_demo.sh)
- Approval polling demo: [examples/approval_poll_demo.py](examples/approval_poll_demo.py)

## Build APK

```sh
./build-buddy-apk.sh
```

The built APK is written to:

```text
buddy-android/build/manual/buddy.apk
```

## Device Scripts

Enable Wi-Fi ADB once over USB:

```sh
scripts/enable-wifi-adb.sh
```

Connect later over Wi-Fi:

```sh
scripts/connect-wifi-adb.sh <buddy-ip>
```

Start the optional OpenSSH service over Wi-Fi ADB:

```sh
scripts/start-ssh-over-adb.sh <buddy-ip>
```
