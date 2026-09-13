"""CI-only provider doubles behind the real API, durable worker and Strands graph."""
from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from tempfile import TemporaryDirectory

from archon.adapters.inbound import LocalReader
from archon.adapters.metered import MODEL_ID
from archon.adapters.ses import Outbox
from archon.store.execution import Journal
from archon.store.sessions import SQLiteSessions
from archon.web import api, live
from test_live_providers import Provider

if (os.environ.get("ARCHON_FAKE_PROVIDERS") != "true"
        or os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")):
    raise RuntimeError("Provider doubles are available only in the CI contract lane.")

directory = TemporaryDirectory(prefix="archon-live-contract-")
sessions = SQLiteSessions(directory.name + "/sessions.sqlite3")
journal = Journal(SQLiteSessions(directory.name + "/journal.sqlite3"))
journal.create("operating-grant", {
    "enabled": True, "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    "model_id": MODEL_ID, "pricing_basis": "INERT CI DOUBLES; no paid provider",
    "budget_usd": "100", "reserved_usd": "0", "max_calls": 1000, "max_mail": 20,
    "max_input_tokens": 10000, "max_output_tokens": 4000,
    "input_usd_per_million_ceiling": "5", "output_usd_per_million_ceiling": "25",
    "mail_usd_ceiling": "0.01",
})
for name, value in {"ENABLED": "true", "WORKER_ARN": "ci-only-worker",
                    "SENDER": "sender@example.test", "RECIPIENT": "controlled@example.test"}.items():
    os.environ["ARCHON_LIVE_" + name] = value


class ContractProvider(Provider):
    def converse(self, **request):
        prompt = request["messages"][0]["content"][0].get("text", "")
        if "Answer with JSON only" not in prompt:
            return super().converse(**request)
        self.calls.append(request)
        fields = LocalReader()._fields(prompt)
        return {"output": {"message": {"role": "assistant", "content": [
            {"text": json.dumps(fields)}]}}, "stopReason": "end_turn",
            "usage": {"inputTokens": 100, "outputTokens": 20, "totalTokens": 120}}


class ContractSES:
    def send_email(self, **request):
        return {"MessageId": "ci-" + hashlib.sha256(
            json.dumps(request, sort_keys=True).encode()).hexdigest()}


def outbox(**kwargs):
    return Outbox(ContractSES(), kwargs["sender"], log=kwargs["log"],
                  controlled_recipient=kwargs["controlled_recipient"])


workers = ThreadPoolExecutor(max_workers=2)


def enqueue(handle, job_id):
    workers.submit(live.run, sessions, journal, handle, job_id,
                   client_factory=ContractProvider, outbox_factory=outbox)


api.store = lambda: sessions
live.enqueue = enqueue
app = api.app
