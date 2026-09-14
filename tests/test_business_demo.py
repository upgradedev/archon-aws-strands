"""Large fictional books stay source-backed, isolated and bounded; CI only."""

from __future__ import annotations

import copy
import json
from collections import Counter
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from archon.store.sessions import SQLiteSessions
from archon.web import api, business_demo, workspace


@pytest.fixture
def client(tmp_path, monkeypatch):
    sessions = SQLiteSessions(str(tmp_path / "business-sessions.sqlite3"))
    monkeypatch.setattr(api, "store", lambda: sessions)
    with TestClient(api.app) as connected:
        yield connected


def new_state(**options):
    state = workspace.fresh()
    state.update(options)
    business_demo.seed(state)
    return state


def test_fixed_bundle_has_six_document_types_and_balanced_real_projection():
    state = new_state()
    assert len(state["sources"]) == 240
    assert Counter(s["kind"] for s in state["sources"]) == {
        "SalesInvoice": 80, "PurchaseInvoice": 50, "Receipt": 50,
        "Payment": 30, "SalesCreditNote": 20, "PurchaseCreditNote": 10,
    }
    books = workspace.books_for(state)
    data = workspace.snapshot(state)
    assert data["trial_balance"] == "0.00"
    assert len(books.ledger.entries) == 240
    assert len({s["document"]["doc_id"] for s in state["sources"]}) == 240
    assert len({s["hash"] for s in state["sources"]}) == 240
    assert len({s["counterparty"] for s in data["sales"]}) == 16
    assert len({s["counterparty"] for s in data["purchases"]}) == 10
    assert data["holds"] == []
    assert data["graph"] is None and data["draft"] is None and data["receipts"] == []
    assert len(data["activity"]) == 1
    assert "provider_job" not in state and "provider_history" not in state
    # Bound the response rather than asserting only row counts. No huge blob per source.
    assert len(json.dumps(data).encode()) < 1_000_000
    for source in state["sources"]:
        assert source["document"]["source_ref"] == source["id"]
        assert source["hash"] == workspace.digest(source["body"])
        assert "not an imported email or bank feed" in source["body"]


def test_cash_is_not_inferred_from_invoice_or_credit_totals():
    data = workspace.snapshot(new_state())
    incoming = sum((Decimal(s["document"]["amount"]) for s in data["sources"]
                    if s["kind"] == "Receipt"), Decimal(0))
    outgoing = sum((Decimal(s["document"]["amount"]) for s in data["sources"]
                    if s["kind"] == "Payment"), Decimal(0))
    assert Decimal(data["cashflow"]["inflow"]) == incoming
    assert Decimal(data["cashflow"]["outflow"]) == outgoing
    assert Decimal(data["metrics"]["bank"]) == incoming - outgoing
    # First sale has a partial cash receipt; sale 51 is fully credited, not paid.
    part = next(s for s in data["sales"] if s["doc_id"] == "SV-0001")
    credit = next(s for s in data["sales"] if s["doc_id"] == "SV-0051")
    assert part["gross"] == "223.20" and part["settled"] == "111.60"
    assert part["outstanding"] == "111.60" and part["credited"] == "0.00"
    assert credit["settled"] == "0.00" and credit["outstanding"] == "0.00"
    assert credit["credited"] == credit["gross"]
    for row in [*data["sales"], *data["purchases"]]:
        assert Decimal(row["gross"]) == sum(Decimal(row[k]) for k in
                                            ("settled", "credited", "outstanding"))
    assert any(s["due"] < data["as_of"] and Decimal(s["outstanding"]) > 0
               for s in data["sales"])
    assert any(s["due"] > data["as_of"] for s in data["sales"])


def test_seed_api_preserves_existing_books_and_survives_reload(client):
    previous = client.post("/api/sessions", json={"mode": "synthetic", "seed": "joinery"})
    first = previous.json()
    response = client.post("/api/sessions", json={"mode": "synthetic", "seed": "business"})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["session"] != first["session"]
    assert result["workspace"]["demo_seed"] == "business-v1"
    for saved in (first, result):
        current = client.get("/api/workspace", headers={"X-Archon-Session": saved["session"]})
        assert current.json() == saved["workspace"]
    assert len(first["workspace"]["sources"]) == 5
    assert client.post("/api/sessions", json={"seed": "business", "sources": []}).status_code == 422


def test_live_seed_does_not_invoke_any_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Seed loading must not call intake, AI, or send")

    monkeypatch.setattr(workspace, "intake", forbidden)
    monkeypatch.setattr(workspace, "reason", forbidden)
    monkeypatch.setattr(workspace, "approve", forbidden)
    state = new_state(provider_mode="live", test_recipient="owner@controlled.example")
    assert all(s["document"]["client_email"] == "owner@controlled.example"
               for s in state["sources"] if s["kind"] == "SalesInvoice")
    assert state["sends"] == {} and state["requests"] == {}


def test_operator_can_pause_new_bundles_without_losing_existing_books(client, monkeypatch):
    saved = client.post("/api/sessions", json={"mode": "synthetic", "seed": "business"}).json()
    monkeypatch.setenv("ARCHON_BUSINESS_DEMO_DISABLED", "true")
    stopped = client.post("/api/sessions", json={"mode": "synthetic", "seed": "business"})
    assert stopped.status_code == 422 and "paused" in stopped.text
    assert client.get("/api/workspace", headers={"X-Archon-Session": saved["session"]}).json() == (
        saved["workspace"]
    )
    small = client.post("/api/sessions", json={"mode": "synthetic", "seed": "joinery"})
    assert small.status_code == 201


def test_seed_is_atomic_and_cannot_replace_user_records(monkeypatch):
    state = new_state()
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="new workspace"):
        business_demo.seed(state)
    assert state == before
    original = business_demo.documents
    monkeypatch.setattr(business_demo, "documents", lambda recipient: original(recipient)[:-1])
    blank = workspace.fresh()
    before = copy.deepcopy(blank)
    with pytest.raises(ValueError, match="failed validation"):
        business_demo.seed(blank)
    assert blank == before


def test_fixed_bundle_does_not_consume_or_expand_interactive_allowance():
    state = new_state()
    assert business_demo.interactive_count(state) == 0
    for index in range(50):
        # Invalid inputs still consume the same bounded evidence slots.
        workspace.intake(state, f"Unclear synthetic document {index}")
    assert len(state["sources"]) == 290
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="at most 50"):
        workspace.intake(state, "one too many")
    assert state == before
    ordinary = workspace.fresh()
    ordinary["sources"] = copy.deepcopy(state["sources"][-50:])
    assert business_demo.interactive_count(ordinary) == 50
    ordinary["demo_seed"] = "business-v1"
    assert business_demo.interactive_count(ordinary) == 50
    broken = new_state()
    broken["sources"][0]["origin"] = "caller-supplied"
    assert business_demo.interactive_count(broken) == 240


def test_source_documents_are_reproducible_independent_of_session_timestamp():
    first, second = new_state(), new_state()
    assert [(s["body"], s["hash"]) for s in first["sources"]] == [
        (s["body"], s["hash"]) for s in second["sources"]]


def test_resolved_sources_still_count_and_refused_reply_cannot_overflow():
    state = new_state()
    for index in range(50):
        state["sources"].append({"id": f"held:{index}", "status": "resolved",
                                 "document": None, "kind": "ClientReply"})
    assert business_demo.interactive_count(state) == 50
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="at most 50"):
        workspace.propose(state, "SV-0001", "I dispute this invoice")
    assert state == before


def test_evidence_export_discloses_fixture_origin_and_retains_every_source():
    from archon.web.export import evidence_bundle

    state = new_state()
    result = evidence_bundle(state, "test-source")
    assert "240 fictional typed fixtures, not model-extracted mail" in result["text"]
    assert "demo:001" in result["text"] and "demo:240" in result["text"]


@pytest.mark.parametrize("label", ["Credit note", "credit-note", "CREDIT MEMO", "Refund"])
def test_invoice_shaped_credit_mail_is_held_before_reader(label):
    class MustNotRead:
        def converse(self, **kwargs):
            raise AssertionError("Unsupported credit mail must not reach a model")

    state = new_state()
    books = workspace.books_for(state)
    balance = books.ledger.trial_balance()
    workspace.intake(state, workspace.SAMPLES["invoice"] + "\n" + label, reader=MustNotRead())
    assert state["sources"][-1]["status"] == "refused"
    assert "not supported by mail intake" in state["sources"][-1]["error"]
    assert len(workspace.books_for(state).sales) == 80
    assert workspace.books_for(state).ledger.trial_balance() == balance
