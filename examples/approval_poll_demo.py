#!/usr/bin/env python3
import json
import os
import time
import urllib.request


BRIDGE_BASE = os.environ.get("BUDDY_BRIDGE_BASE", "http://127.0.0.1:8799")
APPROVAL_ID = "approval-poll-demo"


def post(path, payload):
    req = urllib.request.Request(
        BRIDGE_BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.read().decode("utf-8", "replace")


def get_json(path):
    with urllib.request.urlopen(BRIDGE_BASE + path, timeout=5) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def main():
    post("/agent/start", {"id": "approval-poll-demo", "name": "Codex", "status": "waiting", "body": "Polling for approval response"})
    post("/agent/approval", {
        "id": "approval-poll-demo",
        "approvalId": APPROVAL_ID,
        "title": "Allow continue?",
        "body": "Click approve or deny on Buddy.",
    })
    print("waiting for approval response...")
    while True:
        payload = get_json(f"/responses?id={APPROVAL_ID}&consume=1")
        responses = payload.get("responses", [])
        if responses:
            print(json.dumps(responses[0], ensure_ascii=False))
            break
        time.sleep(0.8)


if __name__ == "__main__":
    main()
