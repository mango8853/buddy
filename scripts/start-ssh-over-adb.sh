#!/bin/sh
set -eu

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <buddy-ip>" >&2
  exit 2
fi
HOST="$1"
DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
SERIAL="$HOST:5555"

"$DIR/platform-tools/adb" connect "$SERIAL" >/dev/null
"$DIR/platform-tools/adb" -s "$SERIAL" shell /data/local/start-sshd.sh
"$DIR/platform-tools/adb" -s "$SERIAL" shell 'ss -ltnp 2>/dev/null | grep 2222 || true'
