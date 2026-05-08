#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ADB="${ADB:-$ROOT/platform-tools/adb}"
SERIAL="${ADB_SERIAL:-}"

adb_cmd() {
  if [ -n "$SERIAL" ]; then
    "$ADB" -s "$SERIAL" "$@"
  else
    "$ADB" "$@"
  fi
}

echo "[buddy] building APKs..."
"$ROOT/build-buddy-apk.sh" >/dev/null
"$ROOT/build-autostart-apk.sh" >/dev/null

echo "[buddy] installing app..."
adb_cmd install -r "$ROOT/buddy-android/build/manual/buddy.apk" >/dev/null

echo "[buddy] installing autostart helper..."
adb_cmd install -r "$ROOT/buddy-autostart/build/manual/buddy-autostart.apk" >/dev/null

echo "[buddy] enabling autostart helper..."
adb_cmd shell pm enable com.codex.buddyautostart >/dev/null || true

echo "[buddy] priming autostart helper..."
adb_cmd shell am broadcast -n com.codex.buddyautostart/.BootReceiver -a com.codex.buddyautostart.TEST >/dev/null || true

echo "[buddy] launching Buddy..."
adb_cmd shell am start -n com.codex.buddy/.MainActivity >/dev/null || true

echo "[buddy] done"
echo "serial: ${SERIAL:-default}"
