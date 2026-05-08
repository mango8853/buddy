#!/bin/sh
set -eu

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <buddy-ip>" >&2
  exit 2
fi
HOST="$1"
DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

"$DIR/platform-tools/adb" connect "$HOST:5555"
"$DIR/platform-tools/adb" -s "$HOST:5555" shell 'id; ip addr show wlan0 | grep "inet " || true'
