#!/bin/sh
set -eu

HOST="${1:-10.214.75.86}"
DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

"$DIR/platform-tools/adb" connect "$HOST:5555"
"$DIR/platform-tools/adb" -s "$HOST:5555" shell 'id; ip addr show wlan0 | grep "inet " || true'
