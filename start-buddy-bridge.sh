#!/bin/sh
set -eu

HOST="${1:-10.214.75.86}"
LISTEN="${BUDDY_LISTEN:-0.0.0.0}"
PORT="${BUDDY_PORT:-8799}"

exec python3 bridge/buddy.py --host "$HOST" --timeout 1 serve --listen "$LISTEN" --listen-port "$PORT"
