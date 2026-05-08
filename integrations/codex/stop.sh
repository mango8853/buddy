#!/bin/sh
set -eu

PIDFILE="${HOME}/.codex/buddy-codex-private.pid"
STATUSFILE="${BUDDY_CODEX_STATUS:-${HOME}/.codex/buddy-codex-private.status.json}"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "${PID}" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    echo "Stopped Codex Buddy monitor (pid $PID)"
  fi
  rm -f "$PIDFILE"
  rm -f "$STATUSFILE"
else
  pkill -f '/integrations/codex/monitor.py' 2>/dev/null || true
  rm -f "$STATUSFILE"
  echo "Stopped any matching Codex Buddy monitor processes"
fi
