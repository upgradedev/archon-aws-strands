"""Fresh synthetic regression oracles; no retained benchmark inputs or live calls."""

import copy
import json
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


@pytest.mark.parametrize("label", ["Billed to", "Invoice to", "Customer:",
                                 "Billed to:", "Invoice to:"])
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


def historical_state():
    state = opened()
    for number in (1, 2):
        document = {"doc_id": f"OLD-{number}", "settles": "JN-4410",
                    "received_on": "2026-08-20", "amount": "600.00",
                    "source_ref": f"email:old-{number}"}
        state["sources"].append({"id": f"email:old-{number}", "kind": "Receipt",
                                 "document": document, "status": "posted", "error": "",
                                 "body": f"Original historical payment {number}",
                                 "hash": workspace.digest(document), "redactions": 0,
                                 "at": workspace.now()})
    return state


def test_historical_equal_receipts_view_attest_and_progress_without_rewriting(tmp_path):
    state = historical_state()
    original = json.dumps(state["sources"], sort_keys=True)
    snapshot = workspace.snapshot(state)
    assert snapshot["sales"][0]["outstanding"] == "660.00"
    assert snapshot["holds"][0]["kind"] == "LegacyPaymentReview"
    assert len(snapshot["holds"][0]["legacy_documents"]) == 2
    assert not snapshot["queue"]["ready"]
    with pytest.raises(ValueError, match="refused"):
        workspace.reason(state)
    # An unrelated payable can still be recorded and durable replay still works.
    workspace.intake(state, workspace.SAMPLES["supplier"])
    assert state["sources"][-1]["status"] == "posted"
    db = str(tmp_path / "legacy.db")
    save(workspace.books_for(state), db)
    recovered = load(db)
    assert recovered.legacy_payment_holds and len(recovered.purchases) == 1
    assert not recovered.overdue(workspace.AS_OF)
    workspace.resolve(state, "email:old-2", "attest-legacy-payments",
                      "Reviewed two distinct historical bank events with the operator.",
                      identities={"OLD-1": "BANK-LEGACY-A", "OLD-2": "BANK-LEGACY-B"})
    assert json.dumps(state["sources"][:-1], sort_keys=True) == original
    assert state["resolutions"][0]["verification"] == "Human supplied; not bank verified"
    reloaded = json.loads(json.dumps(state))
    assert not workspace.holds(reloaded)
    assert workspace.books_for(reloaded).sales_settlements()[0].outstanding == Decimal("660")
    workspace.reason(reloaded)
    assert reloaded["draft"] is not None
    workspace.approve(reloaded, reloaded["draft"]["fingerprint"])
    assert len(reloaded["sends"]) == 1


@pytest.mark.parametrize("identities", [
    {}, {"OLD-1": "ONLY-ONE"},
    {"OLD-1": "BANK-A", "OLD-2": "BANK-A"},
    {"OLD-1": "BANK-A", "OLD-2": "bank-a"},
    {"OLD-1": "BANK-A", "OTHER": "BANK-B"},
    {"OLD-1": "BANK-A", "OLD-2": "  "},
])
def test_legacy_attestation_refuses_missing_conflicting_and_unknown_references(identities):
    state = historical_state()
    before = copy.deepcopy(state)
    with pytest.raises(ValueError):
        workspace.resolve(state, "email:old-2", "attest-legacy-payments",
                          "Human checked the original bank statements.", identities=identities)
    assert state == before and workspace.holds(state)


def test_final_gate_also_holds_legacy_books_even_for_direct_callers():
    from datetime import UTC, datetime

    from archon.agents.claims import Outstanding
    from archon.agents.draft import ChaseDraft
    from archon.agents.gate import Approval, assess
    books = workspace.books_for(historical_state())
    draft = ChaseDraft("JN-4410", "BuildCo Ltd", "accounts@buildco.example",
                       "Outstanding invoice", "Hello.",
                       (Outstanding("JN-4410", Decimal("660")),), "Thank you.", workspace.AS_OF)
    moment = datetime.now(UTC)
    result = assess(books, draft, Approval(draft.fingerprint(), "reviewer", moment),
                    workspace.AS_OF, now=moment)
    assert not result.allowed
    assert any("historical payment identities" in reason for reason in result.reasons)


@pytest.mark.parametrize("decision", ["duplicate-payment", "resume-collection"])
def test_generated_legacy_hold_cannot_be_cleared_as_a_refused_source(decision):
    state = historical_state()
    with pytest.raises(ValueError):
        workspace.resolve(state, "email:old-2", decision,
                          "Reviewed this source in the retained books.", "email:old-1")
    assert workspace.holds(state)


@pytest.mark.parametrize("separator", [
    "-----Original Message-----", "----- Forwarded message -----", "Begin forwarded message:",
])
@pytest.mark.parametrize("quoted", [False, True])
@pytest.mark.parametrize("reader_kind", ["local", "bedrock-proposal"])
def test_common_forward_formats_never_turn_supplier_debt_into_a_sale(
    separator, quoted, reader_kind,
):
    class FakeBedrock:
        def converse(self, **kwargs):
            self.prompt = kwargs["messages"][0]["content"][0]["text"]
            return {"output": {"message": {"content": [{"text": json.dumps({
                "kind": "sales_invoice", "doc_id": "WS-77", "counterparty": "Wrong guess",
                "issued": "2026-08-02", "due": "2026-10-01", "net": "100.00",
                "vat": "24.00", "gross": "124.00", "counterparty_email": "wrong@example.com",
            })}]}}}
    inner = workspace.SAMPLES["supplier"].replace(
        "\nSubject:", "\nTo: me@myjoinery.example\nSubject:") + "\nBilled to: My Joinery"
    if quoted:
        inner = "\n".join("> " + line for line in inner.splitlines())
    raw = ("From: me@myjoinery.example\nTo: accountant@example.com\n"
           "Subject: Please file this\n\n" + separator + "\n" + inner)
    reader = LocalReader() if reader_kind == "local" else FakeBedrock()
    result = read_email(raw, "supplier-forward", client=reader).document
    assert isinstance(result, PurchaseInvoice)
    if reader_kind == "bedrock-proposal":
        assert "accountant@example.com" not in reader.prompt
        assert "billing@wholesaler.example" not in reader.prompt
    outbound = ("From: archive@example.com\nTo: accountant@example.com\n\n"
                + separator + "\n" + workspace.SAMPLES["invoice"].replace(
                    "Our invoice to BuildCo Ltd.", "Invoice to: BuildCo Ltd."))
    result = read_email(outbound, "sales-forward", client=reader).document
    assert isinstance(result, SalesInvoice)
    assert result.client_email == "accounts@buildco.example"


def test_unseparated_quoted_thread_is_refused_not_reinterpreted():
    inner = "\n".join("> " + line for line in workspace.SAMPLES["supplier"].splitlines())
    raw = "From: me@myjoinery.example\nTo: accountant@example.com\n\n" + inner
    with pytest.raises(UnreadablePost, match="conflicting original headers"):
        read_email(raw, "ambiguous-thread", client=LocalReader())


@pytest.mark.parametrize("extra", ["Transfer ID: OTHER-EVENT", "Transfer ID: ???", "Transfer ID:"])
def test_conflicting_or_malformed_second_reference_cannot_hide_behind_a_valid_one(extra):
    state = opened()
    workspace.intake(state, workspace.SAMPLES["payment"] + "\n" + extra)
    assert state["sources"][-1]["status"] == "refused"
    assert workspace.books_for(state).sales_settlements()[0].outstanding == Decimal("1860")


def test_business_configuration_changes_classification_not_just_recipient_address():
    supplier = workspace.SAMPLES["supplier"].replace("wholesaler.example", "parts.example")
    supplier += "\nInvoice to: Custom Workshop"
    received = read_email(supplier, "custom", ours="owner@custom.example",
                          business_name="Custom Workshop", client=LocalReader())
    assert isinstance(received.document, PurchaseInvoice)
    with pytest.raises(UnreadablePost, match="direction conflicts"):
        read_email(supplier, "wrong-owner", client=LocalReader())


def test_one_historical_instalment_can_be_attested_before_distinct_equal_correction():
    state = historical_state()
    state["sources"].pop()
    original = copy.deepcopy(state["sources"])
    assert not workspace.holds(state)
    workspace.intake(state, workspace.SAMPLES["payment"])
    refused = state["sources"][-1]
    assert refused["status"] == "refused" and "Ambiguous payment identity" in refused["error"]
    legacy_hold = next(s for s in workspace.holds(state) if s["kind"] == "LegacyPaymentReview")
    workspace.resolve(state, legacy_hold["id"], "attest-legacy-payments",
                      "Checked the original historical event in supplied bank records.",
                      identities={"OLD-1": "BANK-ORIGINAL-LEGACY"})
    assert state["sources"][:2] == original
    assert [s["id"] for s in workspace.holds(state)] == [refused["id"]]
    workspace.intake(state, workspace.SAMPLES["payment"], replace_id=refused["id"])
    assert refused["status"] == "corrected" and not workspace.holds(state)
    assert workspace.books_for(state).sales_settlements()[0].outstanding == Decimal("660")
    workspace.reason(state)
    assert state["draft"] is not None


def test_attested_same_event_cannot_be_reposted_as_distinct_equal_correction():
    state = historical_state()
    state["sources"].pop()
    workspace.intake(state, workspace.SAMPLES["payment"])
    refused = state["sources"][-1]
    workspace.resolve(state, "email:old-1", "attest-legacy-payments",
                      "Matched the supplied reference to the historical bank event.",
                      identities={"OLD-1": "DEMO-BANK-600-A"})
    workspace.intake(state, workspace.SAMPLES["payment"], replace_id=refused["id"])
    assert state["sources"][-1]["status"] == "refused"
    assert workspace.books_for(state).sales_settlements()[0].outstanding == Decimal("1260")
    assert workspace.holds(state)
