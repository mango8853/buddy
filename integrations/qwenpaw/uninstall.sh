#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${HOME}/.qwenpaw/buddy"
QWENPAW_PYTHON=""
KEEP_INSTALL_DIR="0"
KEEP_AGENTS_MD="0"

usage() {
  cat <<EOF
usage: $0 [options]

options:
  --install-dir <path>         Install directory (default: ~/.qwenpaw/buddy)
  --qwenpaw-python <path>      Python that can import qwenpaw
  --keep-install-dir           Keep the installed Buddy bridge directory
  --keep-agents-md             Keep the Buddy Integration note in AGENTS.md
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir) INSTALL_DIR="${2:-}"; shift 2 ;;
    --qwenpaw-python) QWENPAW_PYTHON="${2:-}"; shift 2 ;;
    --keep-install-dir) KEEP_INSTALL_DIR="1"; shift 1 ;;
    --keep-agents-md) KEEP_AGENTS_MD="1"; shift 1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "${QWENPAW_PYTHON}" ]]; then
  if [[ -x "${HOME}/.qwenpaw/venv/bin/python" ]]; then
    QWENPAW_PYTHON="${HOME}/.qwenpaw/venv/bin/python"
  else
    QWENPAW_PYTHON="python3"
  fi
fi

python3 - <<PY
import json
import shutil
from pathlib import Path

install_dir = Path(${INSTALL_DIR@Q}).expanduser()
manifest_path = install_dir / "install-manifest.json"
keep_install_dir = ${KEEP_INSTALL_DIR@Q} == "1"
keep_agents_md = ${KEEP_AGENTS_MD@Q} == "1"
fallback_python = ${QWENPAW_PYTHON@Q}


def detect_package_dir() -> str:
    import inspect
    import os
    import subprocess
    import textwrap

    script = textwrap.dedent(
        """
        import inspect
        import os
        import qwenpaw
        print(os.path.dirname(inspect.getfile(qwenpaw)))
        """
    ).strip()
    result = subprocess.run(
        [fallback_python, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


manifest = {}
if manifest_path.exists():
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

package_dir = Path(
    manifest.get("qwenpaw_package_dir") or detect_package_dir()
).expanduser()
patched_files = [
    Path(path).expanduser()
    for path in manifest.get(
        "patched_files",
        [
            str(package_dir / "app" / "routers" / "console.py"),
            str(package_dir / "app" / "approvals" / "service.py"),
            str(package_dir / "app" / "channels" / "manager.py"),
        ],
    )
]
backup_suffix = manifest.get("backup_suffix", ".buddy.bak")
restored = []
for path in patched_files:
    backup = path.with_name(path.name + backup_suffix)
    if backup.exists():
        path.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        restored.append(str(path))

runtime_path = Path(
    manifest.get("buddy_runtime_path") or str(package_dir / "app" / "buddy_runtime.py")
).expanduser()
if runtime_path.exists():
    runtime_path.unlink()

agents_md = Path(
    manifest.get("agents_md_path") or str(Path.home() / ".qwenpaw" / "workspaces" / "default" / "AGENTS.md")
).expanduser()
begin_marker = manifest.get("agents_md_begin_marker", "<!-- BUDDY_QWENPAW_BEGIN -->")
end_marker = manifest.get("agents_md_end_marker", "<!-- BUDDY_QWENPAW_END -->")
removed_agents_md = False
if not keep_agents_md and agents_md.exists():
    text = agents_md.read_text(encoding="utf-8")
    if begin_marker in text and end_marker in text:
        start = text.index(begin_marker)
        end = text.index(end_marker) + len(end_marker)
        prefix = text[:start].rstrip()
        suffix = text[end:].lstrip()
        new_text = prefix
        if prefix and suffix:
            new_text += "\n\n"
        new_text += suffix
        if new_text != text:
            agents_md.write_text((new_text.rstrip() + "\n") if new_text.strip() else "", encoding="utf-8")
            removed_agents_md = True

if install_dir.exists() and not keep_install_dir:
    shutil.rmtree(install_dir)

print("Restored files:")
for path in restored:
    print(f"  {path}")
print(f"Removed runtime: {runtime_path}")
print(f"Removed AGENTS note: {removed_agents_md}")
print(f"Removed install dir: {install_dir if not keep_install_dir else 'kept'}")
PY
