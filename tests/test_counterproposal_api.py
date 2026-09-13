"""Real HTTP counterproposal contract, with synthetic ledger and no provider calls."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from archon.store.sessions import SQLiteSessions
from archon.web import api, workspace
from test_workspace_api import change, create, posted, read
from test_workspace_api import client as client

ORIGINAL = "2026-09-20: 1260.00 EUR"
COUNTER = "2026-09-25: 600.00 EUR\n2026-10-10: 660.00 EUR"


def proposed(client, session):
    posted(client, session)
    response = change(client, session, "arrangements/propose", invoice_id="JN-4410", body=ORIGINAL)
    assert response.status_code == 200, response.text
    return response.json()["proposal"]


def test_counterproposal_is_durable_replay_safe_and_never_client_acceptance(client):
    session = create(client)
    original = proposed(client, session)
    before = read(client, session)
    request = dict(fingerprint=original["fingerprint"], body=COUNTER,
                   request_id=uuid.uuid4().hex, revision=before["revision"])
    response = change(client, session, "arrangements/counter", **request)
    assert response.status_code == 200, response.text
    assert change(client, session, "arrangements/counter", **request).json() == response.json()
    state, _ = SQLiteSessions(api.store().path).get(session)
    view = workspace.snapshot(state)
    assert view["sales"] == before["sales"] and view["queue"] == before["queue"]
    assert view["arrangements"] == [] and view["receipts"] == [] and view["proposal"] is None
    record = view["terms_history"][-1]
    assert record["original"] == original and record["body"] == COUNTER
    assert record["status"] == "pending-client-acceptance"
    assert change(client, session, "arrangements/approve",
                  fingerprint=record["fingerprint"]).status_code == 409
    bundle = client.get("/api/evidence", headers={"X-Archon-Session": session}).json()["text"]
    assert "PAYMENT TERMS HISTORY" in bundle and "2026-10-10" in bundle
    assert "2026-09-20" in bundle and "pending-client-acceptance" in bundle
    accepted = change(client, session, "arrangements/propose", invoice_id="JN-4410",
                      body=COUNTER).json()["proposal"]
    result = change(client, session, "arrangements/approve", fingerprint=accepted["fingerprint"])
    assert result.status_code == 200 and len(result.json()["arrangements"]) == 1
    assert result.json()["sales"] == before["sales"]
    assert result.json()["terms_history"][1]["original"] == original


@pytest.mark.parametrize("body", [ORIGINAL, "soon", "I dispute this debt", "2026-09-25: 1.00 EUR",
                                "2026-08-01: 1260.00 EUR"])
def test_invalid_counterproposal_leaves_every_record_unchanged(client, body):
    session = create(client)
    original = proposed(client, session)
    before = read(client, session)
    response = change(client, session, "arrangements/counter",
                      fingerprint=original["fingerprint"], body=body)
    assert response.status_code == 422
    assert read(client, session) == before


@pytest.mark.parametrize("cause", ["fingerprint", "revision", "expired", "changed-books", "hold"])
def test_counterproposal_cannot_bypass_existing_authority_guards(client, cause):
    session = create(client)
    original = proposed(client, session)
    args = dict(fingerprint=original["fingerprint"], body=COUNTER)
    if cause == "fingerprint":
        args["fingerprint"] = "e" * 64
    elif cause == "revision":
        args["revision"] = 0
    elif cause == "changed-books":
        change(client, session, "intake", body=workspace.SAMPLES["supplier"])
    else:
        state, version = api.store().get(session)
        if cause == "expired":
            state["proposal"]["at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        else:
            state["sources"].append({"id": "email:held", "kind": "ClientReply",
                                     "status": "refused", "error": "Dispute", "body": "dispute"})
        api.store().put(session, state, version)
    response = change(client, session, "arrangements/counter", **args)
    assert response.status_code in {409, 422}, response.text
    assert read(client, session)["arrangements"] == []
    assert all(r["decision"] != "owner-counterproposal"
               for r in read(client, session)["terms_history"])
