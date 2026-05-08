#!/usr/bin/env python3
import os
import json
import time
import urllib.error
import urllib.request


DEFAULT_HOST = os.environ.get("BUDDY_HOST", "localhost")
DEFAULT_PORT = 8787


class BuddyClient:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=5, retries=8, retry_delay=0.35):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay

    def post(self, path, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_error = None
        for attempt in range(self.retries):
            request = urllib.request.Request(
                f"http://{self.host}:{self.port}{path}",
                data=data,
                headers={"content-type": "application/json; charset=utf-8"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    return response.status, body
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt >= self.retries - 1:
                    raise
                time.sleep(self.retry_delay)
        raise last_error

    def send_event(self, payload):
        return self.post("/api/event", payload)

    def agent(self, stream_id, name="Agent", status="thinking", body="", agent_kind=""):
        session = BuddyAgentSession(self, stream_id, name=name, status=status, body=body, agent_kind=agent_kind)
        session.start()
        return session

    def agent_start(self, stream_id, name="Agent", status="thinking", body="", pet_url="", max_lines=160, max_chars=12000, agent_kind=""):
        payload = {
            "type": "stream_start",
            "streamId": stream_id,
            "title": name,
            "body": body,
            "mood": status,
            "maxLines": int(max_lines),
            "maxChars": int(max_chars),
        }
        if agent_kind:
            payload["agentKind"] = agent_kind
        if pet_url:
            payload["petUrl"] = pet_url
        return self.send_event(payload)

    def agent_log(self, stream_id, text):
        return self.send_event({
            "type": "stream_chunk",
            "streamId": stream_id,
            "text": text,
        })

    def agent_status(self, stream_id, status, name="", body="", agent_kind=""):
        payload = {
            "type": "stream_meta",
            "streamId": stream_id,
            "status": status,
            "title": name,
            "body": body,
        }
        if agent_kind:
            payload["agentKind"] = agent_kind
        return self.send_event(payload)

    def agent_approval(self, stream_id, title, body, approval_id=None, approve_label="确认", deny_label="拒绝", agent_kind=""):
        payload = {
            "type": "approval",
            "id": approval_id or f"{stream_id}-approval-{int(time.time())}",
            "streamId": stream_id,
            "mood": "waiting",
            "title": title,
            "body": body,
            "approveLabel": approve_label,
            "denyLabel": deny_label,
        }
        if agent_kind:
            payload["agentKind"] = agent_kind
        return self.send_event(payload)

    def agent_end(self, stream_id, status="done", exit_code=0, agent_kind=""):
        payload = {
            "type": "stream_end",
            "streamId": stream_id,
            "status": status,
            "exitCode": int(exit_code),
        }
        if agent_kind:
            payload["agentKind"] = agent_kind
        return self.send_event(payload)


class BuddyAgentSession:
    def __init__(self, client, stream_id, name="Agent", status="thinking", body="", pet_url="", max_lines=160, max_chars=12000, agent_kind=""):
        self.client = client
        self.stream_id = stream_id
        self.name = name
        self.status = status
        self.body = body
        self.pet_url = pet_url
        self.max_lines = max_lines
        self.max_chars = max_chars
        self.agent_kind = agent_kind

    def start(self):
        return self.client.agent_start(
            self.stream_id,
            name=self.name,
            status=self.status,
            body=self.body,
            pet_url=self.pet_url,
            max_lines=self.max_lines,
            max_chars=self.max_chars,
            agent_kind=self.agent_kind,
        )

    def log(self, text):
        return self.client.agent_log(self.stream_id, text)

    def status_update(self, status, name="", body=""):
        return self.client.agent_status(self.stream_id, status, name=name, body=body, agent_kind=self.agent_kind)

    def approval(self, title, body, approval_id=None, approve_label="确认", deny_label="拒绝"):
        return self.client.agent_approval(
            self.stream_id,
            title,
            body,
            approval_id=approval_id,
            approve_label=approve_label,
            deny_label=deny_label,
            agent_kind=self.agent_kind,
        )

    def end(self, status="done", exit_code=0):
        return self.client.agent_end(self.stream_id, status=status, exit_code=exit_code, agent_kind=self.agent_kind)
