#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
PIDFILE="${HOME}/.codex/buddy-codex-private.pid"
LOGFILE="${BUDDY_CODEX_LOG:-/tmp/buddy-codex-private.log}"
STATUSFILE="${BUDDY_CODEX_STATUS:-${HOME}/.codex/buddy-codex-private.status.json}"

: "${BUDDY_HOST:?set BUDDY_HOST}"
THREAD_ID="${BUDDY_CODEX_THREAD_ID:-}"
POLL_INTERVAL="${BUDDY_CODEX_POLL_INTERVAL:-1.0}"
QUIET_DONE_SECONDS="${BUDDY_CODEX_QUIET_DONE_SECONDS:-20}"
BUDDY_CODEX_BOOTSTRAP="${BUDDY_CODEX_BOOTSTRAP:-1}"

case "${THREAD_ID}" in
  latest|LATEST|auto|AUTO)
    THREAD_ID=""
    ;;
esac

mkdir -p "$(dirname "$PIDFILE")"

send_bootstrap() {
  if [ "$BUDDY_CODEX_BOOTSTRAP" = "0" ]; then
    return 0
  fi
  BODY="Watching latest Codex thread"
  if [ -n "$THREAD_ID" ]; then
    BODY="Watching Codex thread ${THREAD_ID}"
  fi
  python3 "$ROOT/bridge/buddy.py" --host "$BUDDY_HOST" message "$BODY" --title "Codex linked" --mood linked >/dev/null 2>&1 || true
}

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "${PID}" ] && kill -0 "$PID" 2>/dev/null; then
    echo "Codex Buddy monitor already running (pid $PID)"
    send_bootstrap
    exit 0
  fi
  rm -f "$PIDFILE"
fi

PID="$(
ROOT="$ROOT" \
LOGFILE="$LOGFILE" \
BUDDY_CODEX_STATUS="$STATUSFILE" \
BUDDY_HOST="$BUDDY_HOST" \
THREAD_ID="$THREAD_ID" \
POLL_INTERVAL="$POLL_INTERVAL" \
QUIET_DONE_SECONDS="$QUIET_DONE_SECONDS" \
python3 - <<'PY'
import os
import subprocess
from pathlib import Path

root = os.environ["ROOT"]
logfile = Path(os.environ["LOGFILE"])
statusfile = os.environ["BUDDY_CODEX_STATUS"]
buddy_host = os.environ["BUDDY_HOST"]
thread_id = os.environ.get("THREAD_ID", "")
poll_interval = os.environ["POLL_INTERVAL"]
quiet_done_seconds = os.environ["QUIET_DONE_SECONDS"]

cmd = [
    "python3",
    f"{root}/integrations/codex/monitor.py",
    "--buddy-host",
    buddy_host,
    "--poll-interval",
    poll_interval,
    "--quiet-done-seconds",
    quiet_done_seconds,
    "--status-file",
    statusfile,
]
if thread_id:
    cmd.extend(["--thread-id", thread_id])

logfile.parent.mkdir(parents=True, exist_ok=True)
with logfile.open("ab") as log:
    proc = subprocess.Popen(
        cmd,
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        cwd=root,
    )
print(proc.pid)
PY
)"

echo "$PID" >"$PIDFILE"
echo "Started Codex Buddy monitor (pid $PID)"
echo "log: $LOGFILE"
send_bootstrap
