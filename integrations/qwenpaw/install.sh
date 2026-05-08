#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

INSTALL_DIR="${HOME}/.qwenpaw/buddy"
BUDDY_HOST=""
BUDDY_PORT="8787"
QWENPAW_URL="http://127.0.0.1:8088"
BUDDY_NAME="QwenPaw"
BUDDY_TIMEOUT="5"
BUDDY_RESPONSES_URL=""
BUDDY_IDLE_TIMEOUT_MS="30000"
PATCH_RUNTIME="1"
PATCH_AGENTS_MD="1"
QWENPAW_PYTHON=""
QWENPAW_PACKAGE_DIR=""
AGENTS_MD_BEGIN_MARKER="<!-- BUDDY_QWENPAW_BEGIN -->"
AGENTS_MD_END_MARKER="<!-- BUDDY_QWENPAW_END -->"

usage() {
  cat <<EOF
usage: $0 --buddy-host <host> [options]

options:
  --buddy-host <host>          Buddy device host or IP (required)
  --buddy-port <port>          Buddy device port (default: 8787)
  --qwenpaw-url <url>          Local QwenPaw base URL (default: http://127.0.0.1:8088)
  --install-dir <path>         Install directory (default: ~/.qwenpaw/buddy)
  --name <name>                Left-panel title in Buddy (default: QwenPaw)
  --buddy-timeout <seconds>    Buddy HTTP timeout (default: 5)
  --responses-url <url>        Buddy bridge /responses URL for approval relay
  --idle-timeout-ms <ms>       Buddy idle return timeout for QwenPaw streams
  --qwenpaw-python <path>      Python that can import qwenpaw (default: ~/.qwenpaw/venv/bin/python or python3)
  --no-patch-runtime           Do not patch QwenPaw runtime for auto mirroring
  --no-patch-agents-md         Do not append Buddy note to workspace AGENTS.md
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --buddy-host) BUDDY_HOST="${2:-}"; shift 2 ;;
    --buddy-port) BUDDY_PORT="${2:-}"; shift 2 ;;
    --qwenpaw-url) QWENPAW_URL="${2:-}"; shift 2 ;;
    --install-dir) INSTALL_DIR="${2:-}"; shift 2 ;;
    --name) BUDDY_NAME="${2:-}"; shift 2 ;;
    --buddy-timeout) BUDDY_TIMEOUT="${2:-}"; shift 2 ;;
    --responses-url) BUDDY_RESPONSES_URL="${2:-}"; shift 2 ;;
    --idle-timeout-ms) BUDDY_IDLE_TIMEOUT_MS="${2:-}"; shift 2 ;;
    --qwenpaw-python) QWENPAW_PYTHON="${2:-}"; shift 2 ;;
    --no-patch-runtime) PATCH_RUNTIME="0"; shift 1 ;;
    --no-patch-agents-md) PATCH_AGENTS_MD="0"; shift 1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "${BUDDY_HOST}" ]]; then
  echo "--buddy-host is required" >&2
  usage
  exit 2
fi

if [[ -z "${QWENPAW_PYTHON}" ]]; then
  if [[ -x "${HOME}/.qwenpaw/venv/bin/python" ]]; then
    QWENPAW_PYTHON="${HOME}/.qwenpaw/venv/bin/python"
  else
    QWENPAW_PYTHON="python3"
  fi
fi

mkdir -p "${INSTALL_DIR}/bridge/compat" "${INSTALL_DIR}/bin"

cp "${ROOT_DIR}/bridge/client.py" "${INSTALL_DIR}/bridge/client.py"
cp "${ROOT_DIR}/bridge/qwenpaw_bridge.py" "${INSTALL_DIR}/bridge/qwenpaw_bridge.py"
cp "${ROOT_DIR}/bridge/compat/base.py" "${INSTALL_DIR}/bridge/compat/base.py"
cp "${ROOT_DIR}/bridge/compat/qwenpaw.py" "${INSTALL_DIR}/bridge/compat/qwenpaw.py"
cp "${ROOT_DIR}/integrations/qwenpaw/uninstall.sh" "${INSTALL_DIR}/uninstall.sh"
chmod +x "${INSTALL_DIR}/uninstall.sh"

cat > "${INSTALL_DIR}/bridge/__init__.py" <<'PY'
from .client import BuddyClient
from .compat.qwenpaw import QwenPawCompatAdapter

__all__ = ["BuddyClient", "QwenPawCompatAdapter"]
PY

cat > "${INSTALL_DIR}/bridge/compat/__init__.py" <<'PY'
from .base import BuddyCompatAdapter
from .qwenpaw import QwenPawCompatAdapter

__all__ = ["BuddyCompatAdapter", "QwenPawCompatAdapter"]
PY

cat > "${INSTALL_DIR}/buddy.env" <<EOF
BUDDY_HOST=${BUDDY_HOST}
BUDDY_PORT=${BUDDY_PORT}
BUDDY_TIMEOUT=${BUDDY_TIMEOUT}
BUDDY_NAME=${BUDDY_NAME}
QWENPAW_URL=${QWENPAW_URL}
BUDDY_RESPONSES_URL=${BUDDY_RESPONSES_URL}
BUDDY_IDLE_TIMEOUT_MS=${BUDDY_IDLE_TIMEOUT_MS}
EOF

cat > "${INSTALL_DIR}/bin/qwenpaw-buddy-chat" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${DIR}/buddy.env"

exec python3 "${DIR}/bridge/qwenpaw_bridge.py" \
  --qwenpaw-url "${QWENPAW_URL}" \
  --buddy-host "${BUDDY_HOST}" \
  --buddy-port "${BUDDY_PORT}" \
  --buddy-timeout "${BUDDY_TIMEOUT}" \
  --name "${BUDDY_NAME}" \
  chat "$@"
EOF
chmod +x "${INSTALL_DIR}/bin/qwenpaw-buddy-chat"

cat > "${INSTALL_DIR}/bin/qwenpaw-buddy-watch-approvals" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${DIR}/buddy.env"

if [[ -z "${BUDDY_RESPONSES_URL:-}" ]]; then
  echo "BUDDY_RESPONSES_URL is empty in ${DIR}/buddy.env" >&2
  exit 2
fi

exec python3 "${DIR}/bridge/qwenpaw_bridge.py" \
  --qwenpaw-url "${QWENPAW_URL}" \
  --buddy-host "${BUDDY_HOST}" \
  --buddy-port "${BUDDY_PORT}" \
  --buddy-timeout "${BUDDY_TIMEOUT}" \
  --name "${BUDDY_NAME}" \
  watch-approvals \
  --responses-url "${BUDDY_RESPONSES_URL}"
EOF
chmod +x "${INSTALL_DIR}/bin/qwenpaw-buddy-watch-approvals"

cat > "${INSTALL_DIR}/bin/qwenpaw-buddy-uninstall" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

exec "${DIR}/uninstall.sh" --install-dir "${DIR}" "$@"
EOF
chmod +x "${INSTALL_DIR}/bin/qwenpaw-buddy-uninstall"

if [[ "${PATCH_RUNTIME}" == "1" ]]; then
  QWENPAW_PACKAGE_DIR="$(
    "${QWENPAW_PYTHON}" - <<'PY'
import inspect
import os
import qwenpaw
print(os.path.dirname(inspect.getfile(qwenpaw)))
PY
  )"

python3 - <<PY
from pathlib import Path

install_dir = Path(${INSTALL_DIR@Q})
package_dir = Path(${QWENPAW_PACKAGE_DIR@Q})
backup_suffix = ".buddy.bak"


def backup_once(path):
    backup = path.with_name(path.name + backup_suffix)
    if path.exists() and not backup.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


runtime_template = (Path(${ROOT_DIR@Q}) / "integrations/qwenpaw/runtime/buddy_runtime.py").read_text(encoding="utf-8")
runtime_text = runtime_template.replace("__INSTALL_DIR__", str(install_dir))
(package_dir / "app" / "buddy_runtime.py").write_text(runtime_text, encoding="utf-8")

console_path = package_dir / "app" / "routers" / "console.py"
backup_once(console_path)
console_text = console_path.read_text(encoding="utf-8")
console_import = "from ..buddy_runtime import relay_console_sse\\n"
if console_import not in console_text:
    anchor = "from ..agent_context import get_agent_for_request\\n"
    console_text = console_text.replace(anchor, anchor + console_import)
needle = "                async for event_data in stream_it:\\n                    yield event_data\\n"
replacement = "                async for event_data in stream_it:\\n                    relay_console_sse(event_data, session_id)\\n                    yield event_data\\n"
if needle in console_text and replacement not in console_text:
    console_text = console_text.replace(needle, replacement)
console_path.write_text(console_text, encoding="utf-8")

service_path = package_dir / "app" / "approvals" / "service.py"
backup_once(service_path)
service_text = service_path.read_text(encoding="utf-8")
service_import = "from ..buddy_runtime import relay_approval_created, relay_approval_resolved\\n"
if service_import not in service_text:
    anchor = "from ...security.tool_guard.approval import ApprovalDecision\\n"
    service_text = service_text.replace(anchor, anchor + service_import)
needle = "        logger.info(\\n            \\"Approval pending created: request_id=%s agent_id=%s tool=%s \\"\\n            \\"severity=%s session=%s root=%s\\",\\n            request_id[:8],\\n            agent_id,\\n            tool_name,\\n            pending.severity,\\n            session_id[:8],\\n            root_session_id[:8],\\n        )\\n\\n        return pending\\n"
replacement = "        logger.info(\\n            \\"Approval pending created: request_id=%s agent_id=%s tool=%s \\"\\n            \\"severity=%s session=%s root=%s\\",\\n            request_id[:8],\\n            agent_id,\\n            tool_name,\\n            pending.severity,\\n            session_id[:8],\\n            root_session_id[:8],\\n        )\\n        relay_approval_created(pending)\\n\\n        return pending\\n"
if needle in service_text and "relay_approval_created(pending)" not in service_text:
    service_text = service_text.replace(needle, replacement)
needle = "        logger.info(\\n            \\"Approval request %s resolved: decision=%s tool=%s\\",\\n            request_id[:8],\\n            decision.value,\\n            pending.tool_name,\\n        )\\n\\n        return pending\\n"
replacement = "        logger.info(\\n            \\"Approval request %s resolved: decision=%s tool=%s\\",\\n            request_id[:8],\\n            decision.value,\\n            pending.tool_name,\\n        )\\n        relay_approval_resolved(pending, decision.value)\\n\\n        return pending\\n"
if needle in service_text and "relay_approval_resolved(pending, decision.value)" not in service_text:
    service_text = service_text.replace(needle, replacement)
service_path.write_text(service_text, encoding="utf-8")

manager_path = package_dir / "app" / "channels" / "manager.py"
backup_once(manager_path)
manager_text = manager_path.read_text(encoding="utf-8")
manager_import = "from ..buddy_runtime import install_channel_relay\\n"
if manager_import not in manager_text:
    anchor = "from ...config import get_available_channels\\n"
    manager_text = manager_text.replace(anchor, anchor + manager_import)
if "install_channel_relay()" not in manager_text:
    anchor = "logger = logging.getLogger(__name__)\\n"
    manager_text = manager_text.replace(anchor, anchor + "\\ninstall_channel_relay()\\n")
manager_path.write_text(manager_text, encoding="utf-8")

if ${PATCH_AGENTS_MD@Q} == "1":
    agents_md = Path.home() / ".qwenpaw" / "workspaces" / "default" / "AGENTS.md"
    marker = "## Buddy Integration"
    if agents_md.exists():
        text = agents_md.read_text(encoding="utf-8")
        if ${AGENTS_MD_BEGIN_MARKER@Q} not in text:
            addition = "\\n\\n${AGENTS_MD_BEGIN_MARKER}\\n## Buddy Integration\\n\\n- Buddy 输出镜像已由宿主自动接入。\\n- 控制台输出与审批请求会自动同步到 Buddy 小屏。\\n- 不需要手动调用 Buddy 脚本来显示普通会话输出。\\n${AGENTS_MD_END_MARKER}\\n"
            agents_md.write_text(text.rstrip() + addition + "\\n", encoding="utf-8")
PY
fi

python3 - <<PY
import json
from pathlib import Path

install_dir = Path(${INSTALL_DIR@Q}).expanduser()
package_dir = Path(${QWENPAW_PACKAGE_DIR@Q}).expanduser() if ${QWENPAW_PACKAGE_DIR@Q} else None
manifest = {
    "install_dir": str(install_dir),
    "qwenpaw_python": ${QWENPAW_PYTHON@Q},
    "qwenpaw_package_dir": str(package_dir) if package_dir else "",
    "patched_files": [],
    "buddy_runtime_path": str(package_dir / "app" / "buddy_runtime.py") if package_dir else "",
    "backup_suffix": ".buddy.bak",
    "agents_md_path": str((Path.home() / ".qwenpaw" / "workspaces" / "default" / "AGENTS.md").expanduser()),
    "agents_md_begin_marker": ${AGENTS_MD_BEGIN_MARKER@Q},
    "agents_md_end_marker": ${AGENTS_MD_END_MARKER@Q},
}
if package_dir:
    manifest["patched_files"] = [
        str(package_dir / "app" / "routers" / "console.py"),
        str(package_dir / "app" / "approvals" / "service.py"),
        str(package_dir / "app" / "channels" / "manager.py"),
    ]
(install_dir / "install-manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

cat <<EOF
Installed QwenPaw Buddy integration to:
  ${INSTALL_DIR}

Commands:
  ${INSTALL_DIR}/bin/qwenpaw-buddy-chat --session-id demo --user-id buddy --text 'Hello from QwenPaw'
  ${INSTALL_DIR}/bin/qwenpaw-buddy-watch-approvals
  ${INSTALL_DIR}/bin/qwenpaw-buddy-uninstall

Environment:
  ${INSTALL_DIR}/buddy.env

Manifest:
  ${INSTALL_DIR}/install-manifest.json

Runtime patch:
  ${PATCH_RUNTIME}
EOF
