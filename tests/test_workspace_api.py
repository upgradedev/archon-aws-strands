"""Real HTTP API/domain/Strands/session contract; no live model or mail calls."""

from __future__ import annotations

import base64
import io
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from archon.adapters.ses import Outbox, SendRefused, live_outbox
from archon.store.sessions import Conflict, MissingSession, S3Sessions, SQLiteSessions
from archon.web import api, workspace
from archon.web.lambda_handler import handler


@pytest.fixture
def client(tmp_path, monkeypatch):
    sessions = SQLiteSessions(str(tmp_path / "sessions.sqlite3"))
    monkeypatch.setattr(api, "store", lambda: sessions)
    with TestClient(api.app) as connected:
        yield connected


def create(client):
    response = client.post("/api/sessions", json={"mode": "synthetic"})
    assert response.status_code == 201, response.text
    return response.json()["session"]


def read(client, session):
    return client.get("/api/workspace", headers={"X-Archon-Session": session}).json()


def change(client, session, path, *, revision=None, request_id=None, **payload):
    revision = read(client, session)["revision"] if revision is None else revision
    return client.post(
        f"/api/{path}",
        headers={"X-Archon-Session": session},
        json={
            "revision": revision,
            "request_id": request_id or uuid.uuid4().hex,
            **payload,
        },
    )


def posted(client, session):
    for name in ("invoice", "payment"):
        result = change(client, session, "intake", body=workspace.SAMPLES[name])
        assert result.status_code == 200, result.text
    return result.json()


def drafted(client, session):
    posted(client, session)
    response = change(client, session, "reason")
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_session_is_isolated_and_has_no_seeded_outcome(client):
    first, second = create(client), create(client)
    assert first != second and len(first) == 64
    posted(client, first)
    assert read(client, second)["sales"] == []
    assert read(client, second)["metrics"]["owed_by_clients"] == "0.00"


def test_evidence_is_session_scoped_redacted_and_tracks_corrections(client):
    session = create(client)
    change(client, session, "intake", body=workspace.SAMPLES["invoice"])
    raw = workspace.SAMPLES["payment"].split("\nTransfer ID:", 1)[0]
    refused = change(client, session, "intake", body=raw).json()
    original = refused["sources"][-1]
    assert original["kind"] == "Receipt" and original["body"] == raw
    corrected = change(client, session, "intake", body=workspace.SAMPLES["payment"],
                       replace_id=original["id"]).json()
    assert corrected["sources"][-2]["status"] == "corrected"
    response = client.get("/api/evidence", headers={"X-Archon-Session": session})
    assert response.status_code == 200
    bundle = response.json()
    assert bundle["revision"] == corrected["revision"]
    assert "Correction:" in bundle["text"] and "FAILURE AND RECOVERY" in bundle["text"]
    assert "accounts@buildco.example" not in bundle["text"]
    assert "not truth" in bundle["text"] and "scripted" in bundle["text"].lower()
    assert client.get("/api/evidence").status_code == 422
    assert client.get("/api/evidence", headers={"X-Archon-Session": "absent"}).status_code == 401
    other = create(client)
    empty = client.get("/api/evidence", headers={"X-Archon-Session": other}).json()
    assert "JN-4410" not in empty["text"]


def test_legacy_resolution_is_revision_bound_durable_and_does_not_rewrite(client):
    from test_reliable_workflows import historical_state
    session = create(client)
    state, version = api.store().get(session)
    state["sources"] = historical_state()["sources"]
    api.store().put(session, state, version)
    shown = read(client, session)
    assert shown["holds"][0]["kind"] == "LegacyPaymentReview"
    payload = dict(source_id="email:old-2", decision="attest-legacy-payments",
                   note="Operator reviewed two distinct supplied bank references.",
                   identities={"OLD-1": "BANK-A", "OLD-2": "BANK-B"})
    bad = change(client, session, "resolve", **{**payload, "identities": {"OLD-1": "BANK-A"}})
    assert bad.status_code == 422 and read(client, session)["holds"]
    assert change(client, session, "resolve", revision=99, **payload).status_code == 409
    resolved = change(client, session, "resolve", **payload)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["sources"] == shown["sources"]
    assert not read(client, session)["holds"]
    assert read(client, session)["resolutions"][0]["decision"] == "attest-legacy-payments"
    assert change(client, session, "resolve", **payload).status_code == 409
    assert change(client, session, "reason").json()["draft"] is not None


def test_single_legacy_instalment_attestation_recovers_new_equal_payment_over_http(client):
    from test_reliable_workflows import historical_state
    session = create(client)
    state, version = api.store().get(session)
    state["sources"] = historical_state()["sources"][:-1]
    original = json.loads(json.dumps(state["sources"]))
    api.store().put(session, state, version)
    refused = change(client, session, "intake", body=workspace.SAMPLES["payment"]).json()
    old = next(s for s in refused["holds"] if s["kind"] == "LegacyPaymentReview")
    result = change(client, session, "resolve", source_id=old["id"],
                    decision="attest-legacy-payments", identities={"OLD-1": "BANK-OLD-EVENT"},
                    note="Reviewed distinct historical bank event with the owner.")
    assert result.status_code == 200, result.text
    assert result.json()["sources"][:2] == original
    result = change(client, session, "intake", body=workspace.SAMPLES["payment"],
                    replace_id=refused["sources"][-1]["id"])
    assert result.status_code == 200 and not result.json()["holds"]
    assert result.json()["sales"][0]["outstanding"] == "660.00"


def test_raw_post_real_strands_exact_approval_and_durable_receipt(client):
    session = create(client)
    state = drafted(client, session)
    assert state["sales"][0]["outstanding"] == "1260.00"
    assert state["metrics"]["bank"] == "600.00"
    assert state["pnl"]["profit"] == "1500.00"
    assert state["trial_balance"] == "0.00"
    assert len(state["graph"]["reports"]) == 6
    assert "1,260.00" in state["graph"]["reports"]["sales"]
    draft = state["draft"]
    assert "1,260.00 EUR" in draft["body"]
    assert draft["recipient"] == "accounts@buildco.example"
    approved = change(client, session, "approve", fingerprint=draft["fingerprint"])
    assert approved.status_code == 200, approved.text
    receipt = read(client, session)["receipts"][0]
    assert receipt["state"] == "provider-accepted"
    assert receipt["message_id"].startswith("simulated-")
    assert receipt["fingerprint"] == draft["fingerprint"]
    assert set(read(client, session)["receipt_states"]) == {
        "queued",
        "unknown",
        "provider-accepted",
        "delivered",
        "failed",
    }


def test_retry_after_lost_response_is_one_post_and_rejects_key_reuse(client):
    session, key = create(client), uuid.uuid4().hex
    first = change(
        client, session, "intake", revision=0, request_id=key, body=workspace.SAMPLES["invoice"]
    )
    replay = change(
        client, session, "intake", revision=0, request_id=key, body=workspace.SAMPLES["invoice"]
    )
    assert first.json() == replay.json()
    assert len(read(client, session)["sources"]) == 1
    refused = change(client, session, "intake", request_id=key, body=workspace.SAMPLES["payment"])
    assert refused.status_code == 409


def test_retry_approval_across_new_api_client_retains_one_receipt(client):
    session = create(client)
    draft = drafted(client, session)["draft"]
    key = uuid.uuid4().hex
    approved = change(client, session, "approve", fingerprint=draft["fingerprint"], request_id=key)
    with TestClient(api.app) as restarted:
        replayed = change(
            restarted,
            session,
            "approve",
            fingerprint=draft["fingerprint"],
            request_id=key,
            revision=0,
        )
    assert approved.json() == replayed.json()
    assert len(read(client, session)["receipts"]) == 1


def test_late_payment_invalidates_exact_approval(client):
    session = create(client)
    old = drafted(client, session)
    extra = (workspace.SAMPLES["payment"].replace("600.00", "200.00")
             .replace("08-20", "09-09").replace("DEMO-BANK-600-A", "TEST-BANK-LATE-200"))
    assert change(client, session, "intake", body=extra).status_code == 200
    assert (
        change(
            client,
            session,
            "approve",
            revision=old["revision"],
            fingerprint=old["draft"]["fingerprint"],
        ).status_code
        == 409
    )
    assert read(client, session)["receipts"] == []
    current = change(client, session, "reason").json()
    assert "1,060.00 EUR" in current["draft"]["body"]


def test_refused_input_holds_every_chase_until_corrected(client):
    session = create(client)
    drafted(client, session)
    state = change(client, session, "intake", body=workspace.SAMPLES["refusal"]).json()
    assert state["draft"] is None and len(state["holds"]) == 1
    assert change(client, session, "reason").status_code == 422
    corrected = change(
        client,
        session,
        "intake",
        body=workspace.SAMPLES["supplier"],
        replace_id=state["holds"][0]["id"],
    ).json()
    assert corrected["holds"] == []
    assert corrected["sources"][2]["status"] == "corrected"
    assert change(client, session, "reason").json()["draft"]


def test_arrangement_exact_approval_survives_store_reopen_without_changing_debt(client):
    session = create(client)
    posted(client, session)
    proposed = change(
        client,
        session,
        "arrangements/propose",
        invoice_id="JN-4410",
        body="2026-09-20: 600.00 EUR\n2026-10-05: 660.00 EUR",
    ).json()
    assert proposed["proposal"]["plan"]["baseline"] == "600.00"
    approved = change(
        client, session, "arrangements/approve", fingerprint=proposed["proposal"]["fingerprint"]
    )
    assert approved.status_code == 200, approved.text
    state, _ = SQLiteSessions(api.store().path).get(session)
    books = workspace.books_for(state)
    assert books.worst_overdue(workspace.AS_OF) is None
    assert books.uncollected()[0].outstanding == 1260
    assert (
        workspace.snapshot(state)["queue"]["blocked"][0]["reason"] == "a payment plan is being kept"
    )


@pytest.mark.parametrize("body", ["soon", "I dispute this debt"])
def test_ambiguous_or_disputed_reply_holds_collection(client, body):
    session = create(client)
    posted(client, session)
    response = change(client, session, "arrangements/propose", invoice_id="JN-4410", body=body)
    assert response.status_code == 200
    assert response.json()["proposal"]["plan"] is None
    assert response.json()["holds"]
    assert change(client, session, "reason").status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        "2026-09-20: 1.00 EUR",
        "2026-01-01: 1260.00 EUR",
        "2026-09-20: 600.00 EUR\n2026-09-20: 660.00 EUR",
    ],
)
def test_invalid_arrangement_never_changes_books(client, body):
    session = create(client)
    posted(client, session)
    assert (
        change(client, session, "arrangements/propose", invoice_id="JN-4410", body=body).status_code
        == 422
    )
    assert read(client, session)["arrangements"] == []


@pytest.mark.parametrize(
    "body",
    [
        workspace.SAMPLES["invoice"].replace("1860.00", "1859.99"),
        workspace.SAMPLES["invoice"].replace("EUR", "USD"),
        workspace.SAMPLES["invoice"].replace("To: accounts@buildco.example\n", ""),
        workspace.SAMPLES["payment"],
    ],
)
def test_unsupported_or_contradictory_input_is_visible_refusal(client, body):
    session = create(client)
    response = change(client, session, "intake", body=body)
    assert response.status_code == 200
    assert response.json()["holds"] and response.json()["sales"] == []


def test_no_public_live_provider_or_foreign_session_selection(client):
    session = create(client)
    assert client.get("/api/workspace").status_code == 422
    assert (
        client.get("/api/workspace", headers={"X-Archon-Session": "../elsewhere"}).status_code
        == 401
    )
    assert client.get("/api/workspace", headers={"X-Archon-Session": "f" * 64}).status_code == 401
    assert client.post("/api/sessions", json={"mode": "live"}).status_code == 422
    assert change(client, session, "reason", provider="ses").status_code == 422
    assert client.post("/api/intake", content=b"x" * 40001).status_code == 413
    assert client.get("/api/health").headers["cache-control"] == "no-store"


def test_expired_session_and_expired_draft_are_refused(client):
    session = create(client)
    current = drafted(client, session)
    state, version = api.store().get(session)
    state["draft"]["at"] = (datetime.now(UTC) - timedelta(minutes=31)).isoformat()
    api.store().put(session, state, version)
    assert (
        change(client, session, "approve", fingerprint=current["draft"]["fingerprint"]).status_code
        == 409
    )
    state, version = api.store().get(session)
    state["created_at"] = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    api.store().put(session, state, version)
    assert client.get("/api/workspace", headers={"X-Archon-Session": session}).status_code == 401


def test_sqlite_concurrent_compare_and_swap_loses_no_writes(tmp_path):
    store = SQLiteSessions(str(tmp_path / "concurrent.db"))
    handle = "a" * 64
    store.put(handle, workspace.fresh(), None)

    def attempt(_):
        state = workspace.fresh()
        state["revision"] = 1
        try:
            store.put(handle, state, "0")
            return True
        except Conflict:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(8))) == 1
    with pytest.raises(Conflict):
        store.put(handle, workspace.fresh(), None)


class S3Error(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


class ObjectClient:
    def __init__(self):
        self.objects = {}

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise S3Error("NoSuchKey")
        body, etag = self.objects[Key]
        return {"Body": io.BytesIO(body), "ETag": etag}

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        if "IfNoneMatch" in kwargs and key in self.objects:
            raise S3Error("PreconditionFailed")
        if "IfMatch" in kwargs and self.objects[key][1] != kwargs["IfMatch"]:
            raise S3Error("PreconditionFailed")
        assert kwargs["ServerSideEncryption"] == "AES256"
        self.objects[key] = kwargs["Body"], uuid.uuid4().hex


def test_s3_private_prefix_and_conditional_writes():
    client = ObjectClient()
    store = S3Sessions("private-bucket", client=client)
    handle = "b" * 64
    with pytest.raises(MissingSession):
        store.get(handle)
    store.put(handle, workspace.fresh(), None)
    state, etag = store.get(handle)
    assert list(client.objects) == [f"sessions/{handle}.json"]
    state["revision"] += 1
    store.put(handle, state, etag)
    with pytest.raises(Conflict):
        store.put(handle, state, etag)
    with pytest.raises(Conflict):
        store.put(handle, state, None)


def test_s3_no_list_bucket_denial_is_unavailable_not_claimed_missing(client, monkeypatch, caplog):
    class Denied:
        def get_object(self, **kwargs):
            raise S3Error("AccessDenied")

    denied_store = S3Sessions("private-bucket", client=Denied())
    with pytest.raises(MissingSession, match="unavailable or expired"):
        denied_store.get("a" * 64)
    monkeypatch.setattr(api, "store", lambda: denied_store)
    response = client.get("/api/workspace", headers={"X-Archon-Session": "a" * 64})
    assert response.status_code == 401
    assert "unavailable or expired" in response.json()["detail"]
    assert "AccessDenied" not in response.text and "private-bucket" not in response.text
    assert "AccessDenied" in caplog.text
    assert "private-bucket" not in caplog.text


def gateway_event(path, body=None, session=None):
    return {
        "version": "2.0",
        "requestContext": {
            "http": {
                "method": "POST" if body is not None else "GET",
                "path": path,
            }
        },
        "headers": {
            "content-type": "application/json",
            **({"x-archon-session": session} if session else {}),
        },
        "rawQueryString": "",
        "body": json.dumps(body) if body is not None else "",
        "isBase64Encoded": False,
    }


def test_real_lambda_handler_http_api_v2_health_commit_and_session_journey(client, monkeypatch):
    monkeypatch.setenv("ARCHON_COMMIT_SHA", "test-immutable-commit")
    response = handler(gateway_event("/api/health"), None)
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["commit"] == "test-immutable-commit"
    assert json.loads(response["body"])["model"] == "LedgerScriptModel"
    event = gateway_event("/api/sessions", {"mode": "synthetic"})
    event.update(body=base64.b64encode(event["body"].encode()).decode(), isBase64Encoded=True)
    event["cookies"] = ["unrelated=value"]
    session = json.loads(handler(event, None)["body"])["session"]
    response = handler(
        gateway_event(
            "/api/intake",
            {
                "revision": 0,
                "request_id": uuid.uuid4().hex,
                "body": workspace.SAMPLES["invoice"],
            },
            session,
        ),
        None,
    )
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["sales"][0]["outstanding"] == "1860.00"
    assert handler(gateway_event("/api/workspace", session=session), None)["statusCode"] == 200


def test_live_adapter_requires_operator_authorization_and_durable_log():
    with pytest.raises(SendRefused, match="explicit operator"):
        live_outbox("sender@example.com")
    state = workspace.fresh()
    workspace.intake(state, workspace.SAMPLES["invoice"])
    workspace.reason(state)
    draft = workspace.draft_for(state)
    outbox = Outbox(
        workspace.SimulatedProvider(draft.fingerprint()),
        "sender@example.com",
        controlled_recipient="somebody-else@example.com",
    )
    with pytest.raises(SendRefused, match="verified recipient"):
        outbox.send(draft, None)


def test_unexpected_storage_error_does_not_leak_details(client, monkeypatch):
    def broken():
        raise RuntimeError("private-bucket-internal-detail")

    monkeypatch.setattr(api, "store", broken)
    response = client.post("/api/sessions", json={"mode": "synthetic"})
    assert response.status_code == 503
    assert "private-bucket" not in response.text
