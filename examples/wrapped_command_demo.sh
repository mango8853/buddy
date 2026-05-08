#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export BUDDY_HOST="${BUDDY_HOST:-10.214.75.86}"
export BUDDY_NAME="${BUDDY_NAME:-Codex}"
export BUDDY_STATUS="${BUDDY_STATUS:-running}"
export BUDDY_BODY="${BUDDY_BODY:-Wrapped command demo}"

"${ROOT_DIR}/scripts/buddy-run.sh" zsh -lc '
  printf "wrapped demo start\n"
  printf "pwd: %s\n" "$PWD"
  printf "listing bridge files...\n"
  ls bridge
  printf "wrapped demo end\n"
'
