#!/bin/sh
set -eu

REPO="${BUDDY_REPO:-mango8853/buddy}"
TAG="${BUDDY_RELEASE_TAG:-latest}"
WORKDIR="${BUDDY_DOWNLOAD_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/buddy-release.XXXXXX")}"

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  cat <<'EOF'
usage: ./install-buddy-release.sh

Downloads prebuilt Buddy APKs from GitHub Releases and installs them onto the
Android device currently visible to adb.

Inputs:
  ADB                 Optional path to adb. Defaults to ./platform-tools/adb, then adb from PATH.
  ADB_SERIAL          Optional adb serial when more than one device is connected.
  BUDDY_REPO          GitHub repo, default: mango8853/buddy.
  BUDDY_RELEASE_TAG   Release tag, default: latest.
  BUDDY_DOWNLOAD_DIR  Optional download/cache directory.

Before running:
  1. Connect the target Android speaker/device over USB.
  2. Enable USB debugging and accept the adb authorization prompt.
  3. Make sure `adb devices` shows the device as `device`.
EOF
  exit 0
fi

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

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

download() {
  url="$1"
  out="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$out"
  elif command -v python3 >/dev/null 2>&1; then
    python3 - "$url" "$out" <<'PY'
import sys
import urllib.request

url, out = sys.argv[1], sys.argv[2]
with urllib.request.urlopen(url, timeout=60) as response:
    data = response.read()
with open(out, "wb") as fh:
    fh.write(data)
PY
  else
    echo "[buddy] curl or python3 is required to download release APKs." >&2
    exit 1
  fi
}

if [ "$TAG" = "latest" ]; then
  BASE="https://github.com/$REPO/releases/latest/download"
else
  BASE="https://github.com/$REPO/releases/download/$TAG"
fi

mkdir -p "$WORKDIR"
BUDDY_APK="$WORKDIR/buddy.apk"
AUTOSTART_APK="$WORKDIR/buddy-autostart.apk"

LOCAL_BUDDY_APK="$ROOT/dist/buddy.apk"
LOCAL_AUTOSTART_APK="$ROOT/dist/buddy-autostart.apk"

echo "[buddy] downloading release APKs from $BASE ..."
if download "$BASE/buddy.apk" "$BUDDY_APK" && download "$BASE/buddy-autostart.apk" "$AUTOSTART_APK"; then
  echo "[buddy] using GitHub Release APKs"
elif [ -f "$LOCAL_BUDDY_APK" ] && [ -f "$LOCAL_AUTOSTART_APK" ]; then
  echo "[buddy] release APK download failed; using repo-local dist APKs"
  cp "$LOCAL_BUDDY_APK" "$BUDDY_APK"
  cp "$LOCAL_AUTOSTART_APK" "$AUTOSTART_APK"
else
  echo "[buddy] release APK download failed and dist APKs are missing." >&2
  echo "[buddy] Build from source with ./install-buddy-device.sh." >&2
  exit 1
fi

echo "[buddy] checking adb target..."
adb_cmd get-state >/dev/null

echo "[buddy] installing app..."
adb_cmd install -r "$BUDDY_APK" >/dev/null

echo "[buddy] installing autostart helper..."
adb_cmd install -r "$AUTOSTART_APK" >/dev/null

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
