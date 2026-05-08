#!/usr/bin/env python3
import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bridge import BuddyClient


def main():
    buddy = BuddyClient(
        host=os.environ.get("BUDDY_HOST", "10.214.75.86"),
        port=int(os.environ.get("BUDDY_PORT", "8787")),
    )
    session = buddy.agent(
        "python-demo",
        name=os.environ.get("BUDDY_NAME", "Codex"),
        status="running",
        body="Python client demo",
    )
    session.log("Scanning repository...\n")
    time.sleep(0.6)
    session.log("Checking bridge integration...\n")
    time.sleep(0.6)
    session.status_update("waiting", body="Approval example next")
    time.sleep(0.6)
    session.approval("Allow continue?", "This is a host-side approval demo.", approval_id="python-demo-approval")
    time.sleep(0.6)
    session.log("If approved, host can keep going.\n")
    session.end("done", exit_code=0)


if __name__ == "__main__":
    main()
