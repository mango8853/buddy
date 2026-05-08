#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ARGS=(
  --host "${BUDDY_HOST:-10.214.75.86}"
  --port "${BUDDY_PORT:-8787}"
  --timeout "${BUDDY_TIMEOUT:-5}"
  --name "${BUDDY_NAME:-Agent}"
  --status "${BUDDY_STATUS:-running}"
  --body "${BUDDY_BODY:-Streaming stdin}"
  --flush-ms "${BUDDY_FLUSH_MS:-120}"
)

if [[ -n "${BUDDY_ID:-}" ]]; then
  ARGS+=(--id "${BUDDY_ID}")
fi

if [[ -n "${BUDDY_END_STATUS:-}" ]]; then
  ARGS+=(--end-status "${BUDDY_END_STATUS}")
fi

if [[ "${BUDDY_NO_END:-0}" == "1" ]]; then
  ARGS+=(--no-end)
fi

exec python3 "${ROOT_DIR}/bridge/adapter.py" "${ARGS[@]}" stdin
