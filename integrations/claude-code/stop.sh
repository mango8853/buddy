#!/usr/bin/env bash
pkill -f "integrations/claude-code/monitor.py" 2>/dev/null || true
echo "Claude Code monitor stopped"
