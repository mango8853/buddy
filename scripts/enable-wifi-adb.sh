#!/bin/sh
set -eu

DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

"$DIR/platform-tools/adb" shell 'setprop persist.adb.tcp.port 5555; setprop service.adb.tcp.port 5555'
"$DIR/platform-tools/adb" shell 'getprop persist.adb.tcp.port; getprop service.adb.tcp.port'
