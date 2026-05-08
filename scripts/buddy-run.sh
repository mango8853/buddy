#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $# -eq 0 ]]; then
  echo "usage: $0 <command> [args...]" >&2
  echo "example: $0 zsh -lc 'git status'" >&2
  exit 2
fi

ARGS=(
  --host "${BUDDY_HOST:?set BUDDY_HOST}"
  --port "${BUDDY_PORT:-8787}"
  --timeout "${BUDDY_TIMEOUT:-5}"
  --name "${BUDDY_NAME:-Agent}"
  --status "${BUDDY_STATUS:-running}"
  --body "${BUDDY_BODY:-Running wrapped command}"
  --flush-ms "${BUDDY_FLUSH_MS:-120}"
)

if [[ -n "${BUDDY_ID:-}" ]]; then
  ARGS+=(--id "${BUDDY_ID}")
fi

if [[ -n "${BUDDY_END_STATUS:-}" ]]; then
  ARGS+=(--end-status "${BUDDY_END_STATUS}")
fi

exec python3 "${ROOT_DIR}/bridge/adapter.py" "${ARGS[@]}" run --exec "$@"
