#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUDDY_HOST="${BUDDY_HOST:?set BUDDY_HOST}"
BUDDY_PET="${BUDDY_PET_ID:-rocky}"

# Kill existing
pkill -f "integrations/claude-code/monitor.py" 2>/dev/null || true
sleep 0.3

nohup python3 "${ROOT}/integrations/claude-code/monitor.py" \
  --buddy-host "$BUDDY_HOST" \
  --pet "$BUDDY_PET" \
  > /tmp/buddy-claude-code.log 2>&1 &

echo "Claude Code monitor started (PID $!)"
