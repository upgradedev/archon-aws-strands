"""Observe the public ASGI API with private temporary SQLite and simulated mail."""

from __future__ import annotations

import copy
import re
import socket
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from archon.store.sessions import SQLiteSessions
from archon.web import api, workspace


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 9, 9, 12, tzinfo=UTC).astimezone(tz)


@contextmanager
def offline_only():
    """Deny network/cloud access even if the surrounding runner has credentials."""
    def denied(*args, **kwargs):
        raise RuntimeError("AR2 forbids network and cloud clients")

    with ExitStack() as stack:
        stack.enter_context(patch.object(socket.socket, "connect", denied))
        stack.enter_context(patch.object(socket.socket, "connect_ex", denied))
        stack.enter_context(patch("socket.create_connection", denied))
        stack.enter_context(patch("boto3.session.Session.client", denied))
        stack.enter_context(patch.object(workspace, "datetime", FixedClock))
        stack.enter_context(patch.object(api, "datetime", FixedClock))
        yield


def sent_action(payload: dict) -> dict:
    """Read actual simulated provider bytes, not a desired draft or ledger row."""
    body = payload["Content"]["Simple"]["Body"]["Text"]["Data"]
    matches = re.findall(r"Invoice (\S+) is still outstanding at ([\d,]+\.\d{2}) EUR\.", body)
    recipients = payload["Destination"]["ToAddresses"]
    if len(matches) != 1 or len(recipients) != 1:
        raise ValueError("Unscorable simulated message; expected one invoice claim and recipient")
    invoice, amount = matches[0]
    return {"invoice": invoice, "recipient": recipients[0], "amount": amount.replace(",", "")}


def run_public(steps: list[dict], context: dict) -> list[dict]:
    if (str(workspace.AS_OF), workspace.BUSINESS_EMAIL, workspace.BUSINESS_NAME) != (
        context["as_of"], context["business_email"], context["business_name"],
    ):
        raise ValueError("Public business/date changed; this frozen protocol requires review")
    observations, trace, sent = [], [], []
    original_send = workspace.SimulatedProvider.send_email

    def observe_send(provider, **kwargs):
        sent.append(copy.deepcopy(kwargs))
        return original_send(provider, **kwargs)

    with TemporaryDirectory(prefix="archon-ar2-") as directory, offline_only():
        path = str(Path(directory) / "sessions.sqlite3")
        sessions = SQLiteSessions(path)
        # The API and actual domain functions are unchanged; only storage and clock are isolated.
        with patch.object(api, "store", lambda: sessions), patch.object(
            workspace.SimulatedProvider, "send_email", observe_send,
        ):
            client = TestClient(api.app)
            try:
                created = client.post("/api/sessions", json={"mode": "synthetic"})
                if created.status_code != 201:
                    raise RuntimeError(f"Session creation failed: {created.status_code}")
                headers = {"X-Archon-Session": created.json()["session"]}

                def read():
                    response = client.get("/api/workspace", headers=headers)
                    if response.status_code != 200:
                        raise RuntimeError(f"Workspace read failed: {response.status_code}")
                    return response.json()

                saved_fingerprint = "0" * 64
                accounted_for = 0
                for index, step in enumerate(steps):
                    op = step["op"]
                    if op == "reload":
                        client.close()
                        sessions = SQLiteSessions(path)
                        client = TestClient(api.app)
                        state = read()
                        trace.append({"step": index, "op": op, "status": 200})
                        continue
                    state = read()
                    payload = {"revision": state["revision"],
                               "request_id": f"ar2-request-{index:08}"}
                    if op == "intake":
                        payload["body"] = step["body"]
                    elif op == "approve":
                        payload["fingerprint"] = saved_fingerprint
                    path_name = "reason" if op == "draft" else op
                    before = len(sent)
                    response = client.post(f"/api/{path_name}", headers=headers, json=payload)
                    after = len(sent)
                    if response.status_code not in (200, 409, 422):
                        raise RuntimeError(f"{op} failed: HTTP {response.status_code}")
                    trace.append({"step": index, "op": op, "status": response.status_code,
                                  "detail": response.json().get("detail", "")})
                    state = read()
                    if op == "draft":
                        draft = state["draft"]
                        saved_fingerprint = draft["fingerprint"] if draft else "0" * 64
                    if op == "approve":
                        calls = sent[before:after]
                        unexpected = sent[accounted_for:before] + sent[after:]
                        observations.append({
                            "step": index,
                            "calls": [sent_action(call) for call in calls],
                            "provider_payloads": calls,
                            "unexpected_calls": [sent_action(call) for call in unexpected],
                            "unexpected_provider_payloads": unexpected,
                            "balances": {s["doc_id"]: s["outstanding"] for s in state["sales"]},
                            "hold": bool(state["holds"]),
                            "sources": [{"id": s["id"], "status": s["status"],
                                         "kind": s["kind"], "error": s["error"]}
                                        for s in state["sources"]],
                            "graph_reports": sorted((state["graph"] or {}).get("reports", {})),
                            "receipt_count": len(state["receipts"]),
                            "trace": copy.deepcopy(trace),
                        })
                        accounted_for = len(sent)
                if len(sent) != accounted_for:
                    raise RuntimeError("Provider calls remain outside a measured decision")
            finally:
                client.close()
    return observations
