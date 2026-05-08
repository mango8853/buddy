#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
PIDFILE="${HOME}/.codex/buddy-codex-private.pid"
STATUSFILE="${BUDDY_CODEX_STATUS:-${HOME}/.codex/buddy-codex-private.status.json}"
LOGFILE="${BUDDY_CODEX_LOG:-/tmp/buddy-codex-private.log}"
BUDDY_HOST="${BUDDY_HOST:-localhost}"
BUDDY_PORT="${BUDDY_PORT:-8787}"
export BUDDY_HOST BUDDY_PORT

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" 2>/dev/null || true)"
else
  PID=""
fi

RUNNING=0
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  RUNNING=1
fi

echo "Codex Buddy sidecar"
echo "pid_file: $PIDFILE"
echo "status_file: $STATUSFILE"
echo "log_file: $LOGFILE"
echo "buddy: http://$BUDDY_HOST:$BUDDY_PORT"
echo "running: $RUNNING"
if [ -n "$PID" ]; then
  echo "pid: $PID"
fi

echo
echo "status_json:"
if [ -f "$STATUSFILE" ]; then
  cat "$STATUSFILE"
else
  echo "{}"
fi

echo
echo "buddy_state:"
python3 - <<'PY'
import json
import os
import urllib.error
import urllib.request

host = os.environ["BUDDY_HOST"]
port = os.environ["BUDDY_PORT"]
url = f"http://{host}:{port}/api/state"
try:
    with urllib.request.urlopen(url, timeout=2.5) as response:
        body = response.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
            print(json.dumps(parsed, ensure_ascii=False, indent=2))
        except Exception:
            print(body)
except urllib.error.URLError as exc:
    print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
PY

echo
echo "log_tail:"
tail -n 30 "$LOGFILE" 2>/dev/null || true
