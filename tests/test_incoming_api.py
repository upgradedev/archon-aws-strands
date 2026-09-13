"""Incoming capability contracts through FastAPI and SQLite; CI-only provider doubles."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import boto3
import pytest
from fastapi.testclient import TestClient

from archon.adapters.metered import MODEL_ID
from archon.store.execution import Journal
from archon.store.sessions import MissingSession, SQLiteSessions
from archon.web import api, incoming, live, workspace
from test_live_providers import Reader

OWNER = "a" * 64
OTHER = "b" * 64
RECIPIENT = "controlled@example.test"
BODY = workspace.SAMPLES["invoice"].replace("accounts@buildco.example", RECIPIENT)
EVENT = "incoming-event-0001"


@pytest.fixture
def harness(tmp_path, monkeypatch):
    for name, value in {"ENABLED": "true", "WORKER_ARN": "ci-only-worker",
                        "SENDER": "sender@example.test", "RECIPIENT": RECIPIENT}.items():
        monkeypatch.setenv("ARCHON_LIVE_" + name, value)

    def forbidden(*args, **kwargs):
        pytest.fail("Incoming tests must never create an AWS client")

    monkeypatch.setattr(boto3, "client", forbidden)
    monkeypatch.setattr(boto3, "Session", forbidden)
    sessions = SQLiteSessions(str(tmp_path / "sessions.db"))
    journal = Journal(SQLiteSessions(str(tmp_path / "journal.db")))
    instant = datetime.now(UTC)
    monkeypatch.setattr(incoming, "now", lambda: instant)
    journal.create("operating-grant", {
        "enabled": True, "expires_at": (instant + timedelta(hours=1)).isoformat(),
        "model_id": MODEL_ID, "pricing_basis": "INERT CI TEST RATES; not production pricing",
        "budget_usd": "20", "reserved_usd": "0", "max_calls": 100, "max_mail": 3,
        "max_input_tokens": 10000, "max_output_tokens": 4000,
        "input_usd_per_million_ceiling": "5", "output_usd_per_million_ceiling": "25",
        "mail_usd_ceiling": "0.01",
    })
    for handle in (OWNER, OTHER):
        state = workspace.fresh()
        state.update(provider_mode="live", test_recipient=RECIPIENT,
                     created_at=instant.isoformat())
        sessions.put(handle, state, None)
    dispatch = Mock()
    monkeypatch.setattr(api, "store", lambda: sessions)
    monkeypatch.setattr(live, "enqueue", dispatch)
    with TestClient(api.app) as client:
        yield SimpleNamespace(client=client, sessions=sessions, journal=journal,
                              dispatch=dispatch, now=instant)


def configure(harness, action="enable", request_id="connection-request-0001", handle=OWNER):
    payload = {"action": action, "request_id": request_id}
    if action == "enable":
        payload["consent"] = "fictional-intake"
    return harness.client.post("/api/incoming/connection",
                               headers={"X-Archon-Session": handle}, json=payload)


def enable(harness, **kwargs):
    response = configure(harness, **kwargs)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["enabled"] is True
    assert re.fullmatch(r"[a-f0-9]{64}\.[a-f0-9]{64}", result["token"])
    return result["token"]


def receive(harness, token, event_id=EVENT, body=BODY, **headers):
    return harness.client.post("/api/incoming",
                               headers={"Authorization": "Bearer " + token, **headers},
                               json={"event_id": event_id, "body": body})


def run_job(harness, job_id, provider=None):
    provider = provider if provider is not None else Reader()
    live.run(harness.sessions, harness.journal, OWNER, job_id,
             client_factory=lambda: provider)
    state, _ = harness.sessions.get(OWNER)
    assert state["provider_job"]["status"] == "completed"
    assert state["sends"] == {} and state["draft"] is None
    return provider


def test_owner_must_explicitly_consent_before_issuing_an_intake_key(harness):
    before = harness.sessions.get(OWNER)
    headers = {"X-Archon-Session": OWNER}
    status = harness.client.get("/api/incoming/connection", headers=headers)
    assert status.status_code == 200
    assert status.json() == {"enabled": False, "expires_at": None, "path": "/api/incoming",
                             "scope": "fictional-intake-only", "events": []}
    for consent in ({}, {"consent": None}, {"consent": "real-email"}):
        response = harness.client.post("/api/incoming/connection", headers=headers,
                                       json={"action": "enable",
                                             "request_id": "connection-no-consent", **consent})
        assert response.status_code == 422, response.text
        with pytest.raises(MissingSession):
            harness.sessions.get(incoming.connection_key(OWNER))
    token = enable(harness)
    assert OWNER not in token
    assert harness.sessions.get(OWNER) == before
    harness.dispatch.assert_not_called()
    assert harness.journal.read("operating-grant")[0]["reserved_usd"] == "0"


def test_synthetic_workspace_cannot_enable_incoming_when_live_is_available(harness):
    opened = harness.client.post("/api/sessions", json={"mode": "synthetic"})
    assert opened.status_code == 201
    handle = opened.json()["session"]
    before = harness.sessions.get(handle)
    response = configure(harness, handle=handle)
    assert response.status_code == 422
    assert "controlled-live workspace" in response.json()["detail"]
    assert harness.sessions.get(handle) == before
    harness.dispatch.assert_not_called()


def test_enable_replay_is_stable_and_different_action_with_same_id_conflicts(harness):
    token = enable(harness)
    before = harness.sessions.get(incoming.connection_key(OWNER))
    assert enable(harness) == token
    assert harness.sessions.get(incoming.connection_key(OWNER)) == before
    response = configure(harness, action="disable")
    assert response.status_code == 409
    assert harness.sessions.get(incoming.connection_key(OWNER)) == before


@pytest.mark.parametrize("credential", ["token", "record-key", "secret"])
def test_intake_capability_cannot_read_books_evidence_or_approve(harness, credential):
    token = enable(harness)
    key, secret = token.split(".")
    value = {"token": token, "record-key": key, "secret": secret}[credential]
    before = harness.sessions.get(OWNER)
    connection = harness.sessions.get(key)
    headers = {"X-Archon-Session": value, "Authorization": "Bearer " + token}
    for path in ("/api/workspace", "/api/evidence", "/api/incoming/connection"):
        response = harness.client.get(path, headers=headers)
        assert response.status_code == 401, response.text
    response = harness.client.post("/api/approve", headers=headers, json={
        "revision": before[0]["revision"], "request_id": "forbidden-approval-0001",
        "fingerprint": "c" * 64, "live_send_consent": "real-email",
    })
    assert response.status_code == 401, response.text
    response = harness.client.post("/api/incoming/connection", headers=headers,
                                   json={"action": "disable",
                                         "request_id": "forbidden-disable-0001"})
    assert response.status_code == 401
    assert harness.sessions.get(OWNER) == before
    assert harness.sessions.get(key) == connection
    harness.dispatch.assert_not_called()


def test_bearer_alone_does_not_replace_the_owner_session_header(harness):
    token = enable(harness)
    before = harness.sessions.get(OWNER)
    headers = {"Authorization": "Bearer " + token}
    for path in ("/api/workspace", "/api/evidence", "/api/incoming/connection"):
        assert harness.client.get(path, headers=headers).status_code == 422
    response = harness.client.post("/api/approve", headers=headers, json={
        "revision": 0, "request_id": "bearer-approval-0001", "fingerprint": "c" * 64,
        "live_send_consent": "real-email",
    })
    assert response.status_code == 422
    assert harness.sessions.get(OWNER) == before
    harness.dispatch.assert_not_called()


@pytest.mark.parametrize("kind", ["missing", "basic", "owner", "wrong-secret", "wrong-record"])
def test_missing_or_forged_bearer_has_no_effect(harness, kind):
    token = enable(harness)
    key, secret = token.split(".")
    wrong = ("0" if secret[0] != "0" else "1") + secret[1:]
    authorization = {"missing": None, "basic": "Basic " + token, "owner": "Bearer " + OWNER,
                     "wrong-secret": "Bearer " + key + "." + wrong,
                     "wrong-record": "Bearer " + OTHER + "." + secret}[kind]
    before = harness.sessions.get(OWNER)
    headers = {"Authorization": authorization} if authorization else {}
    response = harness.client.post("/api/incoming", headers=headers,
                                   json={"event_id": EVENT, "body": BODY})
    assert response.status_code == 401
    assert harness.sessions.get(OWNER) == before
    harness.dispatch.assert_not_called()


def test_capability_target_cannot_be_changed_by_another_session_header(harness):
    token = enable(harness)
    other_token = enable(harness, handle=OTHER)
    other_before = harness.sessions.get(OTHER)
    response = receive(harness, token, **{"X-Archon-Session": OTHER})
    assert response.status_code == 202, response.text
    assert set(response.json()) == {"event_id", "job_id", "status"}
    first_job = response.json()["job_id"]
    assert harness.sessions.get(OTHER) == other_before
    state, _ = harness.sessions.get(OWNER)
    assert state["provider_job"]["id"] == first_job
    assert state["provider_job"]["payload"] == {"body": BODY}
    assert state["provider_job"]["operation"] == "intake"
    owner_before = harness.sessions.get(OWNER)
    second = receive(harness, other_token)
    assert second.status_code == 202
    assert second.json()["job_id"] != first_job
    assert harness.sessions.get(OWNER) == owner_before
    assert harness.dispatch.call_args_list[0].args == (OWNER, first_job)
    assert harness.dispatch.call_args_list[1].args == (OTHER, second.json()["job_id"])


def test_duplicate_body_reuses_durable_job_and_repeated_worker_dispatch_is_inert(harness):
    token = enable(harness)
    first = receive(harness, token)
    assert first.status_code == 202
    before = harness.sessions.get(OWNER)
    repeated = receive(harness, token)
    assert repeated.status_code == 202 and repeated.json() == first.json()
    assert harness.sessions.get(OWNER) == before
    assert before[0]["provider_job_count"] == 1
    assert len(before[0]["requests"]) == 1
    assert len({call.args for call in harness.dispatch.call_args_list}) == 1
    provider = run_job(harness, first.json()["job_id"])
    completed = harness.sessions.get(OWNER)
    run_job(harness, first.json()["job_id"], provider)
    assert harness.sessions.get(OWNER) == completed
    assert len(provider.calls) == 1
    assert len(completed[0]["sources"]) == 1


@pytest.mark.parametrize("completed", [False, True])
def test_same_event_with_different_body_is_409_without_mutation(harness, completed):
    token = enable(harness)
    accepted = receive(harness, token)
    assert accepted.status_code == 202
    if completed:
        run_job(harness, accepted.json()["job_id"])
    before = harness.sessions.get(OWNER)
    dispatches = harness.dispatch.call_count
    refused = receive(harness, token, body=BODY + "\nDifferent content")
    assert refused.status_code == 409
    assert harness.sessions.get(OWNER) == before
    assert harness.dispatch.call_count == dispatches


@pytest.mark.parametrize("running", [False, True])
def test_busy_409_does_not_accept_or_reserve_a_new_event(harness, running):
    token = enable(harness)
    assert receive(harness, token).status_code == 202
    if running:
        state, version = harness.sessions.get(OWNER)
        state["provider_job"].update(status="running", started_at=harness.now.isoformat())
        state["revision"] += 1
        harness.sessions.put(OWNER, state, version)
    before = harness.sessions.get(OWNER)
    refused = receive(harness, token, event_id="incoming-event-0002")
    assert refused.status_code == 409
    assert harness.sessions.get(OWNER) == before
    harness.dispatch.assert_called_once()
    result = harness.client.get("/api/incoming/connection", headers={"X-Archon-Session": OWNER})
    assert [event["event_id"] for event in result.json()["events"]] == [EVENT]


def test_enqueue_failure_is_503_and_identical_retry_schedules_the_same_durable_job(harness):
    token = enable(harness)
    harness.dispatch.side_effect = [RuntimeError("private scheduling detail"), None]
    failed = receive(harness, token)
    assert failed.status_code == 503
    assert "private scheduling detail" not in failed.text
    saved = harness.sessions.get(OWNER)
    job = saved[0]["provider_job"]
    assert job["status"] == "queued" and job["incoming_event"] == EVENT
    assert saved[0]["provider_job_count"] == 1
    assert saved[0]["sources"] == []
    repeated = receive(harness, token)
    assert repeated.status_code == 202
    assert repeated.json() == {"event_id": EVENT, "job_id": job["id"], "status": "queued"}
    assert harness.sessions.get(OWNER) == saved
    assert [call.args for call in harness.dispatch.call_args_list] == [(OWNER, job["id"])] * 2
    provider = run_job(harness, job["id"])
    assert len(provider.calls) == 1


def test_completed_replay_uses_history_while_a_newer_incoming_job_is_pending(harness):
    token = enable(harness)
    first = receive(harness, token)
    assert first.status_code == 202
    provider = run_job(harness, first.json()["job_id"])
    second = receive(harness, token, event_id="incoming-event-0002")
    assert second.status_code == 202
    before = harness.sessions.get(OWNER)
    dispatches = harness.dispatch.call_count
    # Reload via a new client; the old job is no longer the current provider_job.
    with TestClient(api.app) as restarted:
        response = restarted.post("/api/incoming", headers={"Authorization": "Bearer " + token},
                                  json={"event_id": EVENT, "body": BODY})
    assert response.status_code == 202
    assert response.json() == {**first.json(), "status": "completed"}
    assert harness.sessions.get(OWNER) == before
    assert harness.dispatch.call_count == dispatches and len(provider.calls) == 1
    status = harness.client.get("/api/incoming/connection", headers={"X-Archon-Session": OWNER})
    events = status.json()["events"]
    assert [(row["event_id"], row["job_id"], row["status"]) for row in events] == [
        ("incoming-event-0002", second.json()["job_id"], "queued"),
        (EVENT, first.json()["job_id"], "completed"),
    ]


def test_rotation_revokes_old_key_without_reviving_prior_enable_request(harness):
    old = enable(harness)
    rotated = enable(harness, request_id="connection-rotate-0002")
    assert rotated != old
    before = harness.sessions.get(OWNER)
    assert receive(harness, old).status_code == 401
    assert configure(harness).status_code == 409
    assert harness.sessions.get(OWNER) == before
    assert enable(harness, request_id="connection-rotate-0002") == rotated
    assert receive(harness, rotated).status_code == 202


def test_revocation_is_idempotent_and_stays_available_when_live_is_disabled(harness, monkeypatch):
    token = enable(harness)
    before = harness.sessions.get(OWNER)
    monkeypatch.setenv("ARCHON_LIVE_ENABLED", "false")
    disabled = configure(harness, "disable", "connection-disable-0002")
    assert disabled.status_code == 200 and disabled.json()["enabled"] is False
    assert "token" not in disabled.json()
    record = harness.sessions.get(incoming.connection_key(OWNER))
    repeated = configure(harness, "disable", "connection-disable-0002")
    assert repeated.status_code == 200 and repeated.json() == disabled.json()
    assert harness.sessions.get(incoming.connection_key(OWNER)) == record
    assert receive(harness, token).status_code == 401
    assert harness.sessions.get(OWNER) == before
    harness.dispatch.assert_not_called()


def test_connection_change_limit_must_not_prevent_owner_revocation(harness):
    # Reach the public limit using owner requests, not a fixture derived from a limit constant.
    for index in range(50):
        token = enable(harness, request_id=f"connection-rotation-{index:04d}")
    before = harness.sessions.get(OWNER)
    refused = configure(harness, request_id="connection-over-limit-0050")
    assert refused.status_code == 422
    disabled = configure(harness, "disable", "connection-emergency-disable")
    assert disabled.status_code == 200, "The change limit must not prevent owner revocation"
    assert disabled.json()["enabled"] is False
    assert receive(harness, token).status_code == 401
    assert harness.sessions.get(OWNER) == before
    harness.dispatch.assert_not_called()


@pytest.mark.parametrize("age,remaining", [(timedelta(0), timedelta(hours=24)),
                                         (timedelta(days=6, hours=23), timedelta(hours=1))])
def test_key_ttl_is_capped_by_both_one_day_and_owner_session_expiry(
        harness, monkeypatch, age, remaining):
    state, version = harness.sessions.get(OWNER)
    state["created_at"] = (harness.now - age).isoformat()
    harness.sessions.put(OWNER, state, version)
    token = enable(harness)
    status = harness.client.get("/api/incoming/connection", headers={"X-Archon-Session": OWNER})
    expiry = datetime.fromisoformat(status.json()["expires_at"])
    assert expiry == harness.now + remaining
    before = harness.sessions.get(OWNER)
    monkeypatch.setattr(incoming, "now", lambda: expiry)
    assert receive(harness, token).status_code == 401
    status = harness.client.get("/api/incoming/connection", headers={"X-Archon-Session": OWNER})
    assert status.json()["enabled"] is False
    assert harness.sessions.get(OWNER) == before
    harness.dispatch.assert_not_called()


def test_expired_owner_session_rejects_an_independently_unexpired_capability(harness):
    token = enable(harness)
    state, version = harness.sessions.get(OWNER)
    state["created_at"] = (harness.now - timedelta(days=7, seconds=1)).isoformat()
    harness.sessions.put(OWNER, state, version)
    record, _ = harness.sessions.get(incoming.connection_key(OWNER))
    assert datetime.fromisoformat(record["expires_at"]) > harness.now
    before = harness.sessions.get(OWNER)
    for path in ("/api/workspace", "/api/evidence", "/api/incoming/connection"):
        response = harness.client.get(path, headers={"X-Archon-Session": OWNER})
        assert response.status_code == 401 and "expired" in response.json()["detail"]
    assert configure(harness, request_id="expired-owner-enable").status_code == 401
    assert receive(harness, token).status_code == 401
    assert harness.sessions.get(OWNER) == before
    harness.dispatch.assert_not_called()


def test_disabling_during_worker_call_does_not_change_revision_or_lose_the_result(harness):
    token = enable(harness)
    accepted = receive(harness, token)
    assert accepted.status_code == 202

    class RevokeDuringRead(Reader):
        def converse(self, **request):
            running = harness.sessions.get(OWNER)
            assert running[0]["provider_job"]["status"] == "running"
            response = configure(harness, "disable", "disable-during-worker")
            assert response.status_code == 200 and response.json()["enabled"] is False
            assert harness.sessions.get(OWNER) == running
            assert receive(harness, token, event_id="revoked-new-event").status_code == 401
            return super().converse(**request)

    provider = run_job(harness, accepted.json()["job_id"], RevokeDuringRead())
    saved, _ = harness.sessions.get(OWNER)
    assert saved["revision"] == 3  # enqueue, worker claim, final worker result
    assert len(provider.calls) == 1 and len(saved["sources"]) == 1
    assert saved["sources"][0]["status"] == "posted"
    assert saved["provider_history"][0]["incoming_event"] == EVENT
    assert saved["provider_history"][0]["status"] == "completed"
    status = harness.client.get("/api/incoming/connection", headers={"X-Archon-Session": OWNER})
    assert status.json()["enabled"] is False
    assert status.json()["events"][0]["status"] == "completed"


@pytest.mark.parametrize("patch", [
    {"action": "rotate"}, {"action": True}, {"request_id": "short"},
    {"request_id": "x" * 81}, {"request_id": "bad-request-id!!!"}, {"request_id": 1234567890123456},
    {"consent": True}, {"consent": "real-email"}, {"session": OTHER}, {"revision": 0},
])
def test_connection_payload_is_strict_and_does_not_create_a_key(harness, patch):
    before = harness.sessions.get(OWNER)
    response = harness.client.post("/api/incoming/connection",
                                   headers={"X-Archon-Session": OWNER}, json={
                                       "action": "enable", "request_id": "strict-enable-0001",
                                       "consent": "fictional-intake", **patch,
                                   })
    assert response.status_code == 422
    with pytest.raises(MissingSession):
        harness.sessions.get(incoming.connection_key(OWNER))
    assert harness.sessions.get(OWNER) == before
    harness.dispatch.assert_not_called()


@pytest.mark.parametrize("patch", [
    {"event_id": "short"}, {"event_id": "x" * 101}, {"event_id": "invalid/event"},
    {"event_id": 12345678}, {"body": ""}, {"body": "x" * 32001}, {"body": True},
    {"body": None}, {"body": {"text": BODY}}, {"session": OTHER}, {"target": OTHER},
    {"operation": "approve"}, {"replace_id": "email:001"}, {"live_send_consent": "real-email"},
])
def test_event_payload_is_strict_and_never_accepts_outbound_or_target_fields(harness, patch):
    token = enable(harness)
    before = harness.sessions.get(OWNER)
    response = harness.client.post("/api/incoming", headers={"Authorization": "Bearer " + token},
                                   json={"event_id": EVENT, "body": BODY, **patch})
    assert response.status_code == 422, response.text
    assert harness.sessions.get(OWNER) == before
    harness.dispatch.assert_not_called()


@pytest.mark.parametrize("event_id,body", [("event001", "x"), ("e" * 100, "x" * 32000)])
def test_valid_event_size_boundaries_queue_only_the_exact_intake(harness, event_id, body):
    token = enable(harness)
    response = receive(harness, token, event_id=event_id, body=body)
    assert response.status_code == 202, response.text
    saved, _ = harness.sessions.get(OWNER)
    assert saved["provider_job"]["payload"] == {"body": body}
    assert saved["provider_job"]["incoming_event"] == event_id
    assert saved["sources"] == [] and saved["sends"] == {}
    harness.dispatch.assert_called_once_with(OWNER, response.json()["job_id"])


@pytest.mark.parametrize("chunked", [False, True])
def test_oversized_utf8_body_is_rejected_before_json_decoding(harness, chunked):
    token = enable(harness)
    before = harness.sessions.get(OWNER)
    payload = json.dumps({"event_id": EVENT, "body": "é" * 20001}, ensure_ascii=False).encode()
    assert len(payload) > 40000
    content = iter([payload[:19000], payload[19000:]]) if chunked else payload
    response = harness.client.post("/api/incoming", content=content, headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json",
    })
    assert response.status_code == 413
    assert harness.sessions.get(OWNER) == before
    harness.dispatch.assert_not_called()


def test_token_is_absent_from_ordinary_reads_and_export_before_and_after_execution(harness):
    token = enable(harness)
    key, secret = token.split(".")

    def inspect_reads():
        for path in ("/api/workspace", "/api/evidence", "/api/incoming/connection"):
            response = harness.client.get(path, headers={"X-Archon-Session": OWNER})
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            for value in (token, key, secret, '"token"', '"secret_digest"', '"nonce"'):
                assert value not in response.text, path
        state, _ = harness.sessions.get(OWNER)
        for value in (token, key, secret):
            assert value not in json.dumps(state)

    inspect_reads()
    accepted = receive(harness, token)
    assert accepted.status_code == 202
    inspect_reads()
    run_job(harness, accepted.json()["job_id"])
    inspect_reads()
    record, _ = harness.sessions.get(key)
    assert token not in json.dumps(record) and secret not in json.dumps(record)


@pytest.mark.parametrize("previously_enabled", [False, True], ids=["no-record", "already-revoked"])
def test_noop_disable_replay_cannot_revoke_a_subsequently_enabled_key(harness, previously_enabled):
    key = incoming.connection_key(OWNER)
    if previously_enabled:
        enable(harness, request_id="initial-enable-0001")
        initial = configure(harness, "disable", "initial-disable-0002")
        assert initial.status_code == 200 and initial.json()["enabled"] is False
    else:
        with pytest.raises(MissingSession):
            harness.sessions.get(key)
    owner_before = harness.sessions.get(OWNER)
    disabled = configure(harness, "disable", "noop-disable-request-D")
    assert disabled.status_code == 200 and disabled.json()["enabled"] is False
    assert "token" not in disabled.json()
    disabled_record = harness.sessions.get(key)
    repeated = configure(harness, "disable", "noop-disable-request-D")
    assert repeated.status_code == 200 and repeated.json() == disabled.json()
    assert harness.sessions.get(key) == disabled_record

    token = enable(harness, request_id="subsequent-enable-E")
    enabled_record = harness.sessions.get(key)
    stale = configure(harness, "disable", "noop-disable-request-D")
    assert stale.status_code == 409
    assert "Connection changed" in stale.json()["detail"]
    assert harness.sessions.get(key) == enabled_record
    assert harness.sessions.get(OWNER) == owner_before
    assert enable(harness, request_id="subsequent-enable-E") == token
    assert harness.sessions.get(key) == enabled_record
    status = harness.client.get("/api/incoming/connection", headers={"X-Archon-Session": OWNER})
    assert status.status_code == 200 and status.json()["enabled"] is True
    assert "token" not in status.json()
    harness.dispatch.assert_not_called()

    accepted = receive(harness, token)
    assert accepted.status_code == 202, "The newer key must remain usable after stale disable"
    harness.dispatch.assert_called_once_with(OWNER, accepted.json()["job_id"])
    saved, _ = harness.sessions.get(OWNER)
    assert saved["provider_job_count"] == 1 and len(saved["requests"]) == 1


@pytest.mark.parametrize("completed", [False, True], ids=["queued-replay", "completed-replay"])
def test_job_cap_rejects_new_event_but_preserves_same_event_replay(harness, completed):
    token = enable(harness)
    state, version = harness.sessions.get(OWNER)
    # Seed prior usage, then exercise the twentieth admission through the public API.
    state["provider_job_count"] = 19
    harness.sessions.put(OWNER, state, version)
    accepted = receive(harness, token)
    assert accepted.status_code == 202
    job_id = accepted.json()["job_id"]
    provider = Reader()
    if completed:
        run_job(harness, job_id, provider)
    before = harness.sessions.get(OWNER)
    assert before[0]["provider_job_count"] == 20
    connection = harness.sessions.get(incoming.connection_key(OWNER))
    grant = harness.journal.read("operating-grant")
    calls = len(provider.calls)
    harness.dispatch.assert_called_once_with(OWNER, job_id)

    refused = receive(harness, token, event_id="incoming-event-over-cap")
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"].lower()
    assert "twenty-job limit" in detail and "new workspace" in detail
    assert harness.sessions.get(OWNER) == before
    assert harness.sessions.get(incoming.connection_key(OWNER)) == connection
    assert harness.journal.read("operating-grant") == grant
    assert len(provider.calls) == calls
    harness.dispatch.assert_called_once_with(OWNER, job_id)

    replay = receive(harness, token)
    assert replay.status_code == 202
    assert replay.json() == {**accepted.json(), "status": "completed" if completed else "queued"}
    assert harness.sessions.get(OWNER) == before
    assert harness.sessions.get(incoming.connection_key(OWNER)) == connection
    assert harness.journal.read("operating-grant") == grant
    assert len(provider.calls) == calls
    # A queued retry may reschedule only the same durable job, never a new execution.
    assert harness.dispatch.call_count == (1 if completed else 2)
    assert all(call.args == (OWNER, job_id) for call in harness.dispatch.call_args_list)
    status = harness.client.get("/api/incoming/connection", headers={"X-Archon-Session": OWNER})
    assert status.status_code == 200
    assert [event["event_id"] for event in status.json()["events"]] == [EVENT]

    run_job(harness, job_id, provider)
    finished = harness.sessions.get(OWNER)
    spent = harness.journal.read("operating-grant")
    run_job(harness, job_id, provider)
    assert harness.sessions.get(OWNER) == finished
    assert harness.journal.read("operating-grant") == spent
    assert len(provider.calls) == 1
    assert finished[0]["provider_job_count"] == 20
    assert len(finished[0]["requests"]) == len(finished[0]["provider_history"]) == 1
    assert len(finished[0]["sources"]) == 1
