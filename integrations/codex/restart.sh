#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

"$ROOT/stop.sh" >/dev/null 2>&1 || true
sleep 1
"$ROOT/start.sh"
