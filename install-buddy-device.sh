#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  cat <<'EOF'
usage: ./install-buddy-device.sh

Installs Buddy onto the Android device currently visible to adb.

Inputs:
  ADB           Optional path to adb. Defaults to ./platform-tools/adb, then adb from PATH.
  ADB_SERIAL    Optional adb serial when more than one device is connected.
  JAVA_HOME     Optional JDK path. Defaults to ./.tools/jdk17.
  ANDROID_HOME  Optional Android SDK path. Defaults to ./.tools/android-sdk.

Before running:
  1. Connect the target Android speaker/device over USB.
  2. Enable USB debugging and accept the adb authorization prompt.
  3. Make sure `adb devices` shows the device as `device`.
EOF
  exit 0
fi

if [ -n "${ADB:-}" ]; then
  :
elif [ -x "$ROOT/platform-tools/adb" ]; then
  ADB="$ROOT/platform-tools/adb"
elif command -v adb >/dev/null 2>&1; then
  ADB="$(command -v adb)"
else
  echo "[buddy] adb not found. Install Android platform-tools or set ADB=/path/to/adb." >&2
  exit 1
fi
SERIAL="${ADB_SERIAL:-}"

adb_cmd() {
  if [ -n "$SERIAL" ]; then
    "$ADB" -s "$SERIAL" "$@"
  else
    "$ADB" "$@"
  fi
}

echo "[buddy] checking adb target..."
adb_cmd get-state >/dev/null

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
echo
echo "[buddy] Device IP candidates:"
adb_cmd shell "ip -f inet addr show wlan0 2>/dev/null | sed -n 's/.*inet \([0-9.]*\).*/\1/p' || true"
echo "[buddy] Next: python3 bridge/buddy.py --host <buddy-ip> health"
