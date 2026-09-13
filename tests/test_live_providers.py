"""Real-provider boundary contract on durable local stores; all executions run in CI."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from archon.adapters.grounded_post import validate_reading
from archon.adapters.inbound import UnreadablePost, read_email
from archon.adapters.metered import (
    MODEL_ID,
    Admission,
    LiveRefused,
    MeteredConverse,
    model_for,
)
from archon.adapters.ses import Outbox, SendRefused
from archon.store.execution import DurableSendLog, Journal
from archon.store.sessions import Conflict, SQLiteSessions
from archon.web import api, live, workspace

HANDLE = "a" * 64
RECIPIENT = "controlled@example.test"
SENDER = "sender@example.test"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for name, value in {"ENABLED": "true", "WORKER_ARN": "worker",
                        "SENDER": SENDER, "RECIPIENT": RECIPIENT}.items():
        monkeypatch.setenv("ARCHON_LIVE_" + name, value)
    sessions = SQLiteSessions(str(tmp_path / "sessions.db"))
    journal = Journal(SQLiteSessions(str(tmp_path / "journal.db")))
    journal.create("operating-grant", {
        "enabled": True, "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "model_id": MODEL_ID, "pricing_basis": "INERT CI TEST RATES; not production pricing",
        "budget_usd": "20", "reserved_usd": "0", "max_calls": 100, "max_mail": 3,
        "max_input_tokens": 10000, "max_output_tokens": 4000,
        "input_usd_per_million_ceiling": "5", "output_usd_per_million_ceiling": "25",
        "mail_usd_ceiling": "0.01",
    })
    state = workspace.fresh()
    state.update(provider_mode="live", test_recipient=RECIPIENT)
    sessions.put(HANDLE, state, None)
    monkeypatch.setattr(api, "store", lambda: sessions)
    monkeypatch.setattr(live, "enqueue", lambda *args: None)
    return sessions, journal


class Provider:
    def __init__(self):
        self.meta = SimpleNamespace(region_name="eu-west-1")
        self.calls = []
        self.counts = []

    def count_tokens(self, **request):
        self.counts.append(request)
        return {"inputTokens": 100}

    def converse(self, **request):
        self.calls.append(request)
        tools = request.get("toolConfig", {}).get("tools", [])
        prior_tool = any("toolResult" in c for m in request["messages"] for c in m["content"])
        if tools and not prior_tool:
            content = [{"toolUse": {"toolUseId": "call-1",
                                   "name": tools[0]["toolSpec"]["name"], "input": {}}}]
            stop = "tool_use"
        else:
            content = [{"text": workspace.OPENING + "\n" + workspace.CLOSING}]
            stop = "end_turn"
        return {"output": {"message": {"role": "assistant", "content": content}},
                "stopReason": stop,
                "usage": {"inputTokens": 100, "outputTokens": 20, "totalTokens": 120},
                "metrics": {"latencyMs": 1}}


class Reader(Provider):
    def converse(self, **request):
        self.calls.append(request)
        response = {
            "kind": "sales_invoice", "doc_id": "JN-4410", "counterparty": "BuildCo Ltd.",
            "issued": "2026-07-02", "due": "2026-08-01",
            "net": "1500.00", "vat": "360.00", "gross": "1860.00",
        }
        return {"output": {"message": {"content": [{"text": json.dumps(response)}]}},
                "usage": {"inputTokens": 100, "outputTokens": 20, "totalTokens": 120}}


def request():
    return {"modelId": MODEL_ID, "messages": [{"role": "user", "content": [{"text": "Hi"}]}],
            "inferenceConfig": {"maxTokens": 1024}}


def change(sessions, operation, payload=None, request_id="request-0000000001", dispatch=None):
    state, version = sessions.get(HANDLE)
    return live.submit(sessions, HANDLE, state, version, operation, payload or {},
                       request_id, state["revision"], dispatch=dispatch)


def seed(sessions):
    state, version = sessions.get(HANDLE)
    for name in ("invoice", "payment"):
        workspace.intake(state, workspace.SAMPLES[name].replace(
            "accounts@buildco.example", RECIPIENT))
    workspace.reason(state)
    state["revision"] += 1
    sessions.put(HANDLE, state, version)


def test_attempt_and_budget_are_durable_before_inference_and_usage_survives_restart(setup):
    _, journal = setup

    class Inspect(Provider):
        def converse(self, **kwargs):
            row, _ = journal.read("call:job:1")
            assert row["status"] == "pending"
            grant, _ = journal.read("operating-grant")
            assert "job:1" in grant["reservations"]
            return super().converse(**kwargs)

    provider = Inspect()
    model = MeteredConverse(provider, Admission(journal), journal, "job")
    model.converse(**request())
    assert len(provider.calls) == 1
    assert journal.read("call:job:1")[0]["usage"]["outputTokens"] == 20
    restarted = MeteredConverse(provider, Admission(journal), journal, "job")
    with pytest.raises(LiveRefused, match="already reserved"):
        restarted.converse(**request())
    assert len(provider.calls) == 1


@pytest.mark.parametrize("override", [
    {"enabled": False}, {"expires_at": "2020-01-01T00:00:00+00:00"},
    {"budget_usd": "0.000001"}, {"max_calls": 0}, {"max_input_tokens": 1},
    {"max_output_tokens": 1}, {"model_id": "different"}, {"pricing_basis": ""},
])
def test_no_inference_when_any_admission_gate_fails(setup, override):
    _, journal = setup
    grant, version = journal.read("operating-grant")
    journal.update("operating-grant", {**grant, **override}, version)
    provider = Provider()
    with pytest.raises(LiveRefused):
        MeteredConverse(provider, Admission(journal), journal, "job").converse(**request())
    assert provider.calls == []


def test_parallel_budget_reservations_do_not_overspend(setup):
    _, journal = setup
    grant, version = journal.read("operating-grant")
    journal.update("operating-grant", {**grant, "budget_usd": "0.0261"}, version)

    def reserve(index):
        try:
            Admission(journal).reserve(str(index), input_tokens=100, output_tokens=1024)
            return True
        except LiveRefused:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(reserve, range(8))) == 1
    assert Decimal(journal.read("operating-grant")[0]["reserved_usd"]) <= Decimal("0.0261")


def test_unknown_model_call_is_not_refunded_or_retried(setup):
    _, journal = setup

    class Timeout(Provider):
        def converse(self, **kwargs):
            self.calls.append(kwargs)
            raise TimeoutError()

    provider = Timeout()
    with pytest.raises(LiveRefused, match="uncertain"):
        MeteredConverse(provider, Admission(journal), journal, "job").converse(**request())
    assert len(provider.calls) == 1
    assert journal.read("call:job:1")[0]["status"] == "unknown"
    assert Decimal(journal.read("operating-grant")[0]["reserved_usd"]) > 0


@pytest.mark.parametrize("usage", [None, {"inputTokens": 101, "outputTokens": 20},
                                 {"inputTokens": 100, "outputTokens": 1025}])
def test_unpriced_usage_pauses_admission_and_retains_the_received_response(setup, usage):
    _, journal = setup

    class Unexpected(Provider):
        def converse(self, **kwargs):
            result = super().converse(**kwargs)
            result["usage"] = usage
            return result

    provider = Unexpected()
    with pytest.raises(LiveRefused):
        MeteredConverse(provider, Admission(journal), journal, "job").converse(**request())
    grant, _ = journal.read("operating-grant")
    assert grant["enabled"] is False
    assert Decimal(grant["reserved_usd"]) > 0
    row, _ = journal.read("call:job:1")
    assert row["status"] == "unknown" and row["usage"] == usage
    assert row["response"]["usage"] == usage
    with pytest.raises(LiveRefused, match="paused"):
        MeteredConverse(provider, Admission(journal), journal, "next").converse(**request())
    assert len(provider.calls) == 1


def test_admission_handles_two_workers_with_six_parallel_readers_each(setup):
    _, journal = setup

    def reserve(index):
        return Admission(journal).reserve(str(index), input_tokens=100, output_tokens=1024)

    with ThreadPoolExecutor(max_workers=12) as pool:
        assert len(list(pool.map(reserve, range(12)))) == 12
    grant, _ = journal.read("operating-grant")
    assert len(grant["reservations"]) == 12


def test_unsupported_native_token_count_stops_before_inference_or_budget_reservation(setup):
    _, journal = setup

    class UnsupportedCounter(Provider):
        def count_tokens(self, **kwargs):
            raise RuntimeError("The provided model does not support counting tokens")

    provider = UnsupportedCounter()
    with pytest.raises(LiveRefused, match="No inference was started"):
        MeteredConverse(provider, Admission(journal), journal, "job").converse(**request())
    assert provider.calls == []
    assert journal.read("operating-grant")[0]["reserved_usd"] == "0"


def test_source_validation_refuses_balanced_but_invented_values():
    reading = read_email(workspace.SAMPLES["invoice"], "source", client=Reader())
    validate_reading(workspace.SAMPLES["invoice"], reading)
    with pytest.raises(ValueError, match="numeric evidence"):
        validate_reading(workspace.SAMPLES["invoice"], replace(
            reading, document=replace(reading.document, net=Decimal("1000.00"),
                                      vat=Decimal("240.00"), gross=Decimal("1240.00"))))


@pytest.mark.parametrize("issued", ["2026-08-20", None])
def test_receipt_prompt_defines_payment_date_without_filling_missing_model_fields(issued):
    class ReceiptReader(Provider):
        def converse(self, **kwargs):
            prompt = kwargs["messages"][0]["content"][0]["text"]
            assert "For a receipt, issued is the explicitly stated payment date" in prompt
            assert "Never substitute today's date" in prompt
            response = {"kind": "receipt", "issued": issued, "amount": "600.00",
                        "settles": "JN-4410"}
            return {"output": {"message": {"content": [{"text": json.dumps(response)}]}}}

    if issued is None:
        with pytest.raises(UnreadablePost, match="does not state a date"):
            read_email(workspace.SAMPLES["payment"], "source", client=ReceiptReader())
    else:
        reading = read_email(workspace.SAMPLES["payment"], "source", client=ReceiptReader())
        assert reading.document.received_on.isoformat() == issued
        validate_reading(workspace.SAMPLES["payment"], reading)


def test_actual_strands_bedrock_adapter_routes_every_graph_turn_through_metered_client(setup):
    sessions, journal = setup
    seed(sessions)
    state, _ = sessions.get(HANDLE)
    provider = Provider()
    metered = MeteredConverse(provider, Admission(journal), journal, "graph")
    workspace.reason(state, model=model_for(metered), model_label="Actual provider adapter")
    assert len(provider.calls) == 13  # Six tool requests + six tool responses + composer.
    assert state["graph"]["mode"] == "Actual provider adapter"
    assert len(state["graph"]["reports"]) == 6
    assert state["draft"]["fingerprint"] == workspace.draft_for(state).fingerprint()


def test_pending_job_is_committed_before_dispatch_and_replay_does_not_create_new_job(setup):
    sessions, _ = setup
    calls = []

    def dispatch(handle, job_id):
        state, _ = sessions.get(handle)
        assert state["provider_job"]["id"] == job_id
        assert state["provider_job"]["status"] == "queued"
        calls.append(job_id)

    first = change(sessions, "reason", dispatch=dispatch)
    second = change(sessions, "reason", dispatch=dispatch)
    assert first["live"]["job"]["id"] == second["live"]["job"]["id"]
    assert len(set(calls)) == 1
    with pytest.raises(Conflict, match="different content"):
        change(sessions, "intake", {"body": "different"}, dispatch=dispatch)


def test_worker_semantic_intake_result_and_usage_survive_reload(setup):
    sessions, journal = setup
    result = change(sessions, "intake", {"body": workspace.SAMPLES["invoice"]})
    job_id = result["live"]["job"]["id"]
    provider = Reader()
    live.run(sessions, journal, HANDLE, job_id, client_factory=lambda: provider)
    saved, _ = sessions.get(HANDLE)
    assert saved["sources"][0]["status"] == "posted"
    assert saved["provider_job"]["status"] == "completed"
    assert saved["provider_job"]["calls"][0]["usage"]["inputTokens"] == 100
    live.run(sessions, journal, HANDLE, job_id, client_factory=lambda: provider)
    assert len(provider.calls) == 1


def test_a_second_tab_cannot_change_books_while_a_job_is_pending(setup):
    sessions, _ = setup
    change(sessions, "reason")
    with TestClient(api.app) as client:
        response = client.post("/api/arrangements/propose", headers={"X-Archon-Session": HANDLE},
                               json={"revision": 1, "request_id": "request-2222222222",
                                     "invoice_id": "JN-4410", "body": "2026-10-01: 1260.00 EUR"})
    assert response.status_code == 409


def test_running_worker_is_never_reentered_after_a_process_restart(setup):
    sessions, journal = setup
    result = change(sessions, "reason")
    state, version = sessions.get(HANDLE)
    state["provider_job"].update(status="running", started_at=datetime.now(UTC).isoformat())
    state["revision"] += 1
    sessions.put(HANDLE, state, version)
    provider = Provider()
    live.run(sessions, journal, HANDLE, result["live"]["job"]["id"],
             client_factory=lambda: provider)
    assert provider.calls == []


def test_real_send_path_reserves_separately_before_transport_and_never_repeats(setup):
    sessions, journal = setup
    seed(sessions)
    state, _ = sessions.get(HANDLE)
    fingerprint = state["draft"]["fingerprint"]
    change(sessions, "approve", {"fingerprint": fingerprint})
    state, _ = sessions.get(HANDLE)
    sends = []

    class Ses:
        def send_email(self, **kwargs):
            assert DurableSendLog(journal).find(fingerprint).in_flight
            sends.append(kwargs)
            return {"MessageId": "provider-id-not-delivery-proof"}

    def outbox_factory(**kwargs):
        assert kwargs["authorized"] and kwargs["controlled_recipient"] == RECIPIENT
        return Outbox(Ses(), kwargs["sender"], clock=lambda: datetime.now(UTC),
                      log=kwargs["log"], controlled_recipient=kwargs["controlled_recipient"])

    live.run(sessions, journal, HANDLE, state["provider_job"]["id"],
             outbox_factory=outbox_factory)
    saved, _ = sessions.get(HANDLE)
    assert saved["sends"][fingerprint]["state"] == "provider-accepted"
    assert saved["provider_job"]["status"] == "completed"
    live.run(sessions, journal, HANDLE, state["provider_job"]["id"],
             outbox_factory=outbox_factory)
    workspace.approve(saved, fingerprint, outbox=outbox_factory(
        sender=SENDER, authorized=True, controlled_recipient=RECIPIENT,
        log=DurableSendLog(journal)))
    assert len(sends) == 1


def test_ses_timeout_persists_unknown_outside_session_even_if_session_write_fails(setup):
    sessions, journal = setup
    seed(sessions)
    state, _ = sessions.get(HANDLE)
    fingerprint = state["draft"]["fingerprint"]

    class Timeout:
        def send_email(self, **kwargs):
            raise TimeoutError()

    def attempt():
        return workspace.approve(state, fingerprint, outbox=Outbox(
            Timeout(), SENDER, clock=lambda: datetime.now(UTC),
            log=DurableSendLog(journal), controlled_recipient=RECIPIENT))

    with pytest.raises(SendRefused):
        attempt()
    assert DurableSendLog(journal).find(fingerprint).state == "unknown"
    with pytest.raises(SendRefused, match="not sent again"):
        attempt()


def test_live_session_selection_is_server_gated(setup, monkeypatch):
    with TestClient(api.app) as client:
        assert client.post("/api/sessions", json={}).json()["workspace"]["live"]["model"]
        synthetic = client.post("/api/sessions", json={"mode": "synthetic"}).json()["workspace"]
        assert "live" not in synthetic
        monkeypatch.setenv("ARCHON_LIVE_ENABLED", "false")
        assert client.post("/api/sessions", json={"mode": "live"}).status_code == 422
        assert "live" not in client.post("/api/sessions", json={}).json()["workspace"]
