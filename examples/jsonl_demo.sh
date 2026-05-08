#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '%s\n' \
  '{"type":"log","text":"Starting JSONL demo...\n"}' \
  '{"type":"log","text":"Streaming from a shell pipeline...\n"}' \
  '{"type":"status","status":"waiting","body":"Approval example follows"}' \
  '{"type":"approval","approvalId":"jsonl-demo-approval","title":"Allow continue?","body":"This approval came from JSONL."}' \
  '{"type":"log","text":"Back to stream output...\n"}' \
  '{"type":"end","status":"done","exitCode":0}' \
  | python3 "${ROOT_DIR}/bridge/adapter.py" \
      --host "${BUDDY_HOST:-10.214.75.86}" \
      --id "jsonl-demo" \
      --name "${BUDDY_NAME:-Codex}" \
      --status running \
      --body "JSONL adapter demo" \
      jsonl
