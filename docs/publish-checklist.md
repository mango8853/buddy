# Publish Checklist

Use this before creating the first public GitHub repo or release.

## Repo hygiene

- Initialize git at the repo root if it is not already a repository.
- Check `.gitignore` before the first commit.
- Make sure local secrets and device-specific captures are not tracked:
  - SSH keys
  - `known_hosts`
  - extracted Android SDKs or platform tools
  - screenshots, videos, and temporary reverse-engineering artifacts
  - imported custom pets under `pets/custom/`

## Docs

- Read [README.md](../README.md) top to bottom once on GitHub preview.
- Read [bridge/README.md](../bridge/README.md) in GitHub preview.
- Read [docs/compatibility.md](compatibility.md) in GitHub preview.
- Confirm all links are relative and render correctly outside the local machine.

## Device build

- Run `./build-buddy-apk.sh`
- Run `./build-autostart-apk.sh`
- Optionally run `./install-buddy-device.sh` on a real device for a smoke test

## Integration smoke tests

- `python3 bridge/buddy.py --host <device-ip> health`
- `python3 bridge/buddy.py --host <device-ip> version`
- `python3 bridge/buddy.py --host <device-ip> message "hello" --title "Buddy"`
- `python3 bridge/buddy.py --host <device-ip> stream --title "Smoke" --exec zsh -lc 'printf "ok\n"'`
- `python3 bridge/buddy.py --host <device-ip> agent start --id smoke --name Buddy --status running`
- `python3 bridge/buddy.py --host <device-ip> agent end --id smoke --status done`

## Host integrations

- Codex sidecar:
  - `./integrations/codex/status.sh`
- QwenPaw:
  - re-read [integrations/qwenpaw/README.md](../integrations/qwenpaw/README.md)
- Claude Desktop Buddy:
  - re-read [examples/claude_desktop_buddy_demo.py](../examples/claude_desktop_buddy_demo.py)

## Release framing

- Decide whether to include generated APKs in a GitHub release or keep them out of git entirely.
- Decide on a license before making the repo public.
- Add a short release note with:
  - supported device assumptions
  - supported host integrations
  - what is experimental
