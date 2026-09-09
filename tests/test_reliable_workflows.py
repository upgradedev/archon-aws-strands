"""Fresh synthetic regression oracles; no retained benchmark inputs or live calls."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from archon.adapters import bedrock
from archon.adapters.inbound import LocalReader, UnreadablePost, read_email
from archon.adapters.ledger_script import LedgerScriptModel
from archon.agents.graph import build
from archon.domain.books import Books, SettlementError
from archon.domain.documents import Payment, PurchaseInvoice, Receipt, SalesInvoice
from archon.evidence.fair import CORRECT, WRONG_INVOICE, WRONG_MONEY, WRONG_RECIPIENT, Answer, judge
from archon.evidence.independent import Case
from archon.store.sqlite import load, save
from archon.web import workspace


def opened():
    state = workspace.fresh()
    workspace.intake(state, workspace.SAMPLES["invoice"])
    return state


@pytest.mark.parametrize("change", [
    lambda raw: raw.replace("Subject: Remittance", "Subject: Forwarded remittance"),
    lambda raw: "From: me@myjoinery.example\n\n----- Forwarded message -----\n" + raw,
    lambda raw: raw.replace("Transfer ID:", "Bank transaction reference:").replace(
        "DEMO-BANK-600-A", "demo-bank-600-a"),
])
def test_same_bank_event_never_credits_twice(change):
    state = opened()
    workspace.intake(state, workspace.SAMPLES["payment"])
    workspace.intake(state, change(workspace.SAMPLES["payment"]))
    assert workspace.books_for(state).sales_settlements()[0].outstanding == Decimal("1260")
    assert state["sources"][-1]["status"] == "refused"
    assert state["draft"] is None


def test_distinct_equal_instalments_are_not_collapsed():
    state = opened()
    workspace.intake(state, workspace.SAMPLES["payment"])
    workspace.intake(state, workspace.SAMPLES["payment"].replace("600-A", "600-B"))
    assert not workspace.holds(state)
    assert workspace.books_for(state).sales_settlements()[0].outstanding == Decimal("660")


def test_missing_identity_holds_then_corrects_with_original_retained():
    state = opened()
    raw = workspace.SAMPLES["payment"].split("\nTransfer ID:", 1)[0]
    workspace.intake(state, raw)
    held = state["sources"][-1]
    assert held["status"] == "refused"
    assert workspace.books_for(state).sales_settlements()[0].outstanding == Decimal("1860")
    workspace.intake(state, workspace.SAMPLES["payment"], replace_id=held["id"])
    assert held["body"] == raw and held["status"] == "corrected"
    assert not workspace.holds(state)
    assert workspace.books_for(state).sales_settlements()[0].outstanding == Decimal("1260")


def test_domain_identity_survives_replay_and_checks_direct_callers(tmp_path):
    state = opened()
    workspace.intake(state, workspace.SAMPLES["payment"])
    books = workspace.books_for(state)
    path = str(tmp_path / "books.db")
    save(books, path)
    recovered = load(path)
    original = recovered.receipts[0]
    assert original.transfer_id == "DEMO-BANK-600-A"
    for attempted in (
        replace(original, doc_id="new-document", source_ref="forward"),
        replace(original, doc_id="changed-amount", amount=Decimal("200")),
    ):
        with pytest.raises(SettlementError, match="already recorded"):
            recovered.record(attempted)
    assert recovered.sales_settlements()[0].outstanding == Decimal("1260")


def test_direct_ambiguous_equal_receipts_hold_but_different_references_pass():
    books = workspace.books_for(opened())
    receipt = Receipt("manual-a", "JN-4410", date(2026, 8, 20), Decimal("600"), "manual")
    books.record(receipt)
    with pytest.raises(SettlementError, match="Ambiguous"):
        books.record(replace(receipt, doc_id="manual-b", received_on=date(2026, 8, 21)))
    assert books.sales_settlements()[0].outstanding == Decimal("1260")


def test_payment_direction_does_not_bypass_transfer_identity():
    books = workspace.books_for(opened())
    books.record(PurchaseInvoice("PI-90", "Supplier", date(2026, 7, 1), date(2026, 8, 1),
                                 Decimal("600"), Decimal("0"), Decimal("600"), "purchase"))
    books.record(Payment("PAY-90", "PI-90", date(2026, 8, 1), Decimal("600"),
                         "outgoing", transfer_id="BANK-90"))
    with pytest.raises(SettlementError, match="already recorded"):
        books.record(Receipt("RC-90", "JN-4410", date(2026, 8, 1), Decimal("600"),
                             "incoming", transfer_id="bank-90"))


@pytest.mark.parametrize("label", ["Billed to", "Invoice to", "Customer:"])
def test_supplier_bill_to_configured_business_is_payable(label):
    raw = workspace.SAMPLES["supplier"].replace(
        "\nSubject:", "\nTo: me@myjoinery.example\nSubject:"
    ) + f"\n{label} My Joinery"
    result = read_email(raw, "source", client=LocalReader()).document
    assert isinstance(result, PurchaseInvoice)
    forwarded = "From: me@myjoinery.example\n\n----- Forwarded message -----\n" + raw
    assert isinstance(read_email(forwarded, "fwd", client=LocalReader()).document, PurchaseInvoice)


def test_legitimate_outbound_and_forward_keep_recipient_without_leaking_it():
    class Watching(LocalReader):
        def converse(self, **kwargs):
            self.prompt = kwargs["messages"][0]["content"][0]["text"]
            return super().converse(**kwargs)

    watcher = Watching()
    raw = "From: archive@myjoinery.example\n\n----- Forwarded message -----\n"
    raw += workspace.SAMPLES["invoice"]
    result = read_email(raw, "source", client=watcher).document
    assert isinstance(result, SalesInvoice)
    assert result.client_email == "accounts@buildco.example"
    assert result.client_email not in watcher.prompt
    assert "me@myjoinery.example" not in watcher.prompt


@pytest.mark.parametrize("raw", [
    workspace.SAMPLES["invoice"].replace("BuildCo Ltd.", "My Joinery."),
    workspace.SAMPLES["invoice"].replace("me@myjoinery.example", "stranger@elsewhere.example"),
    workspace.SAMPLES["invoice"] + "\nIssued by: Other Company",
])
def test_conflicting_or_unknown_direction_is_refused(raw):
    with pytest.raises(UnreadablePost, match="direction"):
        read_email(raw, "source", client=LocalReader())


def test_human_duplicate_resolution_preserves_money_and_invalidates_draft():
    state = opened()
    workspace.intake(state, workspace.SAMPLES["payment"])
    workspace.reason(state)
    old_draft = state["draft"]["fingerprint"]
    workspace.intake(state, workspace.SAMPLES["payment"] + "\nForwarded for reference.")
    source = state["sources"][-1]
    workspace.resolve(state, source["id"], "duplicate-payment",
                      "Reviewed bank reference and original remittance.", "email:002")
    assert source["status"] == "resolved" and source["body"].endswith("reference.")
    assert workspace.books_for(state).sales_settlements()[0].outstanding == Decimal("1260")
    with pytest.raises(ValueError):
        workspace.approve(state, old_draft)
    assert state["sends"] == {}


def test_dispute_human_resolution_never_changes_debt():
    state = opened()
    workspace.propose(state, "JN-4410", "I dispute this debt.")
    source = state["sources"][-1]
    workspace.resolve(state, source["id"], "resume-collection",
                      "Client confirmed the invoice after reviewing the work.")
    assert source["resolution"]["approved_by"] == "demo visitor"
    assert workspace.books_for(state).sales_settlements()[0].outstanding == Decimal("1860")
    assert state["draft"] is None
    workspace.reason(state)
    assert state["draft"] is not None


def test_factory_arguments_reach_real_graph_without_live_inference(monkeypatch):
    called = []
    model = LedgerScriptModel(default="Hello.\nMany thanks.")
    def factory(**kwargs):
        called.append(kwargs)
        return model
    monkeypatch.setattr("strands.models.BedrockModel", factory)
    monkeypatch.setattr(bedrock, "MODEL_ID", "configured-test-model")
    monkeypatch.setattr(bedrock, "REGION", "eu-central-1")
    monkeypatch.setattr(bedrock, "MAX_TOKENS", 777)
    result = build(Books(), workspace.AS_OF, date(2026, 7, 1), workspace.AS_OF)("Review.")
    assert result.results
    assert called == [{"region_name": "eu-central-1", "model_id": "configured-test-model",
                       "max_tokens": 777, "streaming": True}]


@pytest.fixture
def oracle():
    return Case("new-contract-oracle", "synthetic", (), "OR-987", Decimal("734.28"),
                "EUR", "receivables@customer.example", False, "Fixed contract, no benchmark reuse")


@pytest.mark.parametrize(("answer", "expected"), [
    (Answer("OTHER-987", Decimal("734.28"), "receivables@customer.example"), WRONG_INVOICE),
    (Answer("OR-987", Decimal("734.28"), ""), WRONG_RECIPIENT),
    (Answer("OR-987", Decimal("734.28"), " "), WRONG_RECIPIENT),
    (Answer("OR-987", Decimal("734.28"), "other@customer.example"), WRONG_RECIPIENT),
    (Answer("OR-987", Decimal("734.27"), "receivables@customer.example"), WRONG_MONEY),
    (Answer("OR-987", Decimal("734.28"), "receivables@customer.example"), CORRECT),
])
def test_fresh_evaluator_oracles(oracle, answer, expected):
    assert judge(oracle, answer) == expected
