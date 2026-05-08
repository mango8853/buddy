#!/bin/sh
set -eu

HOST="${1:-${BUDDY_HOST:-}}"
LISTEN="${BUDDY_LISTEN:-0.0.0.0}"
PORT="${BUDDY_PORT:-8799}"

if [ -z "$HOST" ]; then
  echo "usage: $0 <buddy-ip>" >&2
  echo "or set BUDDY_HOST=<buddy-ip>" >&2
  exit 1
fi

exec python3 bridge/buddy.py --host "$HOST" --timeout 1 serve --listen "$LISTEN" --listen-port "$PORT"
