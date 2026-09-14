"""Native credit notes reverse invoices without inventing cash or repayment."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from archon.agents.claims import Outstanding, PartPaid
from archon.agents.draft import ChaseDraft
from archon.agents.gate import Approval, assess
from archon.agents.tools import chase_candidate, sales_position, supplier_position
from archon.domain.accounts import Account
from archon.domain.arrangement import Instalment, consider
from archon.domain.books import Books, Settlement, SettlementError
from archon.domain.documents import (
    DocumentError,
    Payment,
    PurchaseCreditNote,
    PurchaseInvoice,
    Receipt,
    SalesCreditNote,
    SalesInvoice,
)
from archon.domain.ledger import Ledger
from archon.domain.money import ZERO, MoneyError
from archon.domain.queue import build
from archon.domain.reports import cashflow, metrics, profit_and_loss

ISSUED = date(2026, 8, 1)
DUE = date(2026, 8, 15)
TODAY = date(2026, 9, 14)
CREDIT_TYPES = (SalesCreditNote, PurchaseCreditNote)


@pytest.fixture(params=("sales", "purchase"))
def lane(request):
    if request.param == "sales":
        invoice = SalesInvoice(
            "INV", "Client", "client@example.test", ISSUED, DUE,
            "100.00", "20.00", "120.00", "email:invoice",
        )
        credit_type, cash_type = SalesCreditNote, Receipt
        accounts = (Account.RECEIVABLES, Account.SALES, Account.VAT_OUTPUT)
    else:
        invoice = PurchaseInvoice(
            "INV", "Supplier", ISSUED, DUE, "100.00", "20.00", "120.00", "email:invoice",
        )
        credit_type, cash_type = PurchaseCreditNote, Payment
        accounts = (Account.PAYABLES, Account.PURCHASES, Account.VAT_INPUT)
    books = Books()
    books.record(invoice)
    return books, invoice, credit_type, cash_type, accounts


def _settlement(books, credit_type):
    settlements = (
        books.sales_settlements() if credit_type is SalesCreditNote
        else books.purchase_settlements()
    )
    return settlements[0]


@pytest.mark.parametrize("credit_type", CREDIT_TYPES)
def test_credit_is_immutable_exact_and_has_provenance(credit_type):
    credit = credit_type("CN", "INV", TODAY, "0.10", "0.02", "0.12", "email:credit")
    assert (credit.net, credit.vat, credit.gross) == (
        Decimal("0.10"), Decimal("0.02"), Decimal("0.12"),
    )
    assert all(isinstance(value, Decimal) for value in (credit.net, credit.vat, credit.gross))
    with pytest.raises(FrozenInstanceError):
        credit.gross = Decimal("99.00")
    entry, = credit.entries()
    assert entry.on == TODAY
    assert entry.source_ref == "email:credit"
    assert "INV" in entry.narrative
    assert sum((posting.amount for posting in entry.postings), ZERO) == ZERO
    assert all(posting.account is not Account.BANK for posting in entry.postings)


@pytest.mark.parametrize("credit_type", CREDIT_TYPES)
@pytest.mark.parametrize("changes", (
    {"net": "0", "vat": "1", "gross": "1"},
    {"net": "-1", "vat": "1", "gross": "0"},
    {"vat": "-1", "gross": "19"},
    {"gross": "0"},
    {"gross": "-24"},
    {"gross": "25"},
    {"net": 20.0},
    {"vat": 4.0},
    {"gross": 24.0},
    {"net": "NaN"},
    {"vat": "Infinity"},
    {"gross": "NaN"},
    {"net": "20.001"},
    {"vat": "4.001"},
    {"gross": "24.001"},
    {"doc_id": " "},
    {"settles": ""},
    {"source_ref": " "},
))
def test_invalid_credit_amounts_and_references_are_refused(credit_type, changes):
    fields = dict(
        doc_id="CN", settles="INV", issued=TODAY, net="20", vat="4", gross="24",
        source_ref="email:credit",
    )
    fields.update(changes)
    with pytest.raises((DocumentError, MoneyError)):
        credit_type(**fields)


def test_credit_reverses_original_accounts_and_reports_without_cash(lane):
    books, invoice, credit_type, _, accounts = lane
    before_cash = cashflow(books, ISSUED, TODAY)
    books.record(credit_type("CN", "INV", TODAY, "20", "4", "24", "email:credit"))
    assert books.ledger.trial_balance() == ZERO
    assert cashflow(books, ISSUED, TODAY) == before_cash
    assert books.ledger.balance(Account.BANK) == ZERO
    assert tuple(books.ledger.balance_as_read(account) for account in accounts) == (
        Decimal("96.00"), Decimal("80.00"), Decimal("16.00"),
    )
    assert books.ledger.balance_as_read(accounts[0], upto=DUE) == invoice.gross
    pnl = profit_and_loss(books, ISSUED, TODAY)
    assert (pnl.sales if credit_type is SalesCreditNote else pnl.purchases) == Decimal("80.00")
    position = metrics(books, TODAY)
    assert (
        position.owed_by_clients if credit_type is SalesCreditNote else position.owed_to_suppliers
    ) == Decimal("96.00")
    settlement = _settlement(books, credit_type)
    assert settlement.settled == ZERO
    assert settlement.credited == Decimal("24.00")
    assert settlement.outstanding == Decimal("96.00")
    assert not settlement.is_paid and not settlement.is_settled


def test_full_credit_closes_invoice_without_marking_it_paid(lane):
    books, _, credit_type, _, _ = lane
    books.record(credit_type("CN", "INV", ISSUED, "100", "20", "120", "email:credit"))
    settlement = _settlement(books, credit_type)
    assert settlement.is_settled and not settlement.is_paid
    assert settlement.outstanding == settlement.settled == ZERO
    assert settlement.credited == Decimal("120.00")
    assert not settlement.is_overdue(TODAY)
    assert settlement.days_overdue(TODAY) == 0
    assert books.uncollected() == books.owed_to_suppliers() == []
    assert build(books, TODAY).ready == ()
    assert not PartPaid("INV", Decimal("120")).holds(books, TODAY)
    copy = (
        sales_position(books, TODAY) if credit_type is SalesCreditNote
        else supplier_position(books)
    )
    assert "credit notes" in copy
    assert "been paid" not in copy and "been collected" not in copy


def test_zero_vat_invoice_accepts_zero_vat_credit(lane):
    _, invoice, credit_type, _, _ = lane
    books = Books()
    books.record(replace(invoice, vat="0", gross="100"))
    books.record(credit_type("CN", "INV", TODAY, "100", "0", "100", "email:credit"))
    assert _settlement(books, credit_type).is_settled
    assert len(books.ledger.entries[-1].postings) == 2


@pytest.mark.parametrize("target", ("missing", "opposite", "CN-first", "cash"))
def test_credit_requires_original_invoice_in_same_direction_atomically(lane, target):
    books, _, credit_type, cash_type, _ = lane
    opposite = (
        PurchaseInvoice("opposite", "Supplier", ISSUED, DUE, "100", "20", "120", "email:pi")
        if credit_type is SalesCreditNote else
        SalesInvoice(
            "opposite", "Client", "client@example.test", ISSUED, DUE,
            "100", "20", "120", "email:si",
        )
    )
    books.record(opposite)
    books.record(credit_type("CN-first", "INV", TODAY, "1", "0", "1", "email:cn1"))
    books.record(cash_type("cash", "INV", TODAY, "2", "email:cash"))
    before = deepcopy(books)
    with pytest.raises(SettlementError, match="not a .* invoice"):
        books.record(credit_type("CN", target, TODAY, "20", "4", "24", "email:credit"))
    assert books == before


def test_credit_cannot_precede_invoice_atomically(lane):
    books, _, credit_type, _, _ = lane
    before = deepcopy(books)
    with pytest.raises(SettlementError, match="precedes"):
        books.record(
            credit_type("CN", "INV", date(2026, 7, 31), "20", "4", "24", "email:credit")
        )
    assert books == before


@pytest.mark.parametrize("first,second,component", (
    (("90", "1", "91"), ("11", "1", "12"), "net"),
    (("1", "19", "20"), ("1", "2", "3"), "vat"),
    (("1", "0", "1"), ("101", "0", "101"), "net"),
    (("1", "0", "1"), ("1", "21", "22"), "vat"),
))
def test_credit_bounds_each_original_component_atomically(lane, first, second, component):
    books, _, credit_type, _, _ = lane
    books.record(credit_type("CN-first", "INV", TODAY, *first, "email:first"))
    before = deepcopy(books)
    with pytest.raises(SettlementError, match=f"cumulative {component}"):
        books.record(credit_type("CN-second", "INV", TODAY, *second, "email:second"))
    assert books == before


@pytest.mark.parametrize("cash_first", (True, False))
def test_cash_and_credit_cannot_together_exceed_balance_in_either_order(lane, cash_first):
    books, _, credit_type, cash_type, _ = lane
    cash = cash_type("cash", "INV", TODAY, "70", "email:cash")
    credit = credit_type("CN", "INV", TODAY, "50", "10", "60", "email:credit")
    first, second = (cash, credit) if cash_first else (credit, cash)
    books.record(first)
    before = deepcopy(books)
    with pytest.raises(SettlementError, match="outstanding"):
        books.record(second)
    assert books == before


def test_credit_on_fully_paid_invoice_is_refused(lane):
    books, _, credit_type, cash_type, _ = lane
    books.record(cash_type("cash", "INV", TODAY, "120", "email:cash"))
    before = deepcopy(books)
    with pytest.raises(SettlementError, match="only 0.00 outstanding"):
        books.record(credit_type("CN", "INV", TODAY, "1", "0", "1", "email:credit"))
    assert books == before
    assert _settlement(books, credit_type).is_paid


@pytest.mark.parametrize("cash_first", (True, False))
def test_multiple_credits_and_cash_can_exactly_clear_an_invoice(lane, cash_first):
    books, _, credit_type, cash_type, _ = lane
    cash = cash_type("cash", "INV", TODAY, "48", "email:cash")
    if cash_first:
        books.record(cash)
    books.record(credit_type("CN-1", "INV", TODAY, "20", "4", "24", "email:credit1"))
    books.record(credit_type("CN-2", "INV", TODAY, "40", "8", "48", "email:credit2"))
    if not cash_first:
        books.record(cash)
    settlement = _settlement(books, credit_type)
    assert (settlement.settled, settlement.credited, settlement.outstanding) == (
        Decimal("48.00"), Decimal("72.00"), ZERO,
    )
    assert settlement.is_settled and not settlement.is_paid
    assert abs(books.ledger.balance(Account.BANK)) == Decimal("48.00")


def test_duplicate_credit_does_not_post_twice(lane):
    books, _, credit_type, _, _ = lane
    credit = credit_type("CN", "INV", TODAY, "20", "4", "24", "email:credit")
    books.record(credit)
    before = deepcopy(books)
    with pytest.raises(ValueError, match="already posted"):
        books.record(credit)
    assert books == before


def test_posting_failure_does_not_file_a_credit(lane, monkeypatch):
    books, _, credit_type, _, _ = lane
    before = deepcopy(books)

    def fail(_ledger, _entry):
        _ledger.entries.append(_entry)
        raise RuntimeError("posting unavailable")

    monkeypatch.setattr(Ledger, "post", fail)
    with pytest.raises(RuntimeError, match="posting unavailable"):
        books.record(credit_type("CN", "INV", TODAY, "20", "4", "24", "email:credit"))
    assert books == before


def test_failed_legacy_cash_replay_after_credit_does_not_leave_a_hold(lane):
    books, _, credit_type, cash_type, _ = lane
    books.record(cash_type("cash", "INV", TODAY, "40", "email:cash"))
    books.record(credit_type("CN", "INV", TODAY, "50", "10", "60", "email:credit"))
    before = deepcopy(books)
    with pytest.raises(SettlementError, match="outstanding"):
        books.record(
            cash_type("cash-again", "INV", TODAY, "40", "email:again"), replay_legacy=True,
        )
    assert books == before


def test_legacy_settlement_constructor_keeps_cash_semantics():
    settlement = Settlement("INV", "Client", "client@example.test", Decimal("120"), ZERO, DUE)
    assert settlement.credited == ZERO
    assert settlement.outstanding == Decimal("120")
    assert replace(settlement, settled=Decimal("120")).is_paid


def _sales_books():
    books = Books()
    books.record(SalesInvoice(
        "INV", "Client", "client@example.test", ISSUED, DUE,
        "100", "20", "120", "email:invoice",
    ))
    return books


def test_part_paid_and_agent_copy_only_describe_cash_as_received():
    books = _sales_books()
    books.record(Receipt("cash", "INV", TODAY, "30", "email:cash"))
    books.record(SalesCreditNote("CN", "INV", TODAY, "20", "4", "24", "email:credit"))
    claim = PartPaid("INV", Decimal("30"))
    assert claim.holds(books, TODAY)
    assert claim.sentence() == "We have received 30.00 EUR against it, with thanks."
    assert not PartPaid("INV", Decimal("54")).holds(books, TODAY)
    assert Outstanding("INV", Decimal("66")).holds(books, TODAY)
    for copy in (sales_position(books, TODAY), chase_candidate(books, TODAY)):
        assert "30.00 EUR received" in copy
        assert "24.00 EUR credited" in copy
        assert "66.00 EUR outstanding" in copy
        assert "54.00 EUR received" not in copy


def test_credit_does_not_count_towards_keeping_an_arrangement():
    books = _sales_books()
    books.record(Receipt("before", "INV", DUE, "12", "email:before"))
    plan = consider(
        invoice_id="INV", outstanding=Decimal("108"), as_of=DUE,
        baseline=Decimal("12"), approved_by="owner",
        instalments=(
            Instalment(date(2026, 9, 1), Decimal("24")),
            Instalment(date(2026, 10, 1), Decimal("84")),
        ),
    )
    books.agree(plan)
    books.record(SalesCreditNote("CN", "INV", TODAY, "20", "4", "24", "email:credit"))
    settlement = books.sales_settlements()[0]
    assert settlement.outstanding == Decimal("84")
    assert not books.is_held_by_arrangement(settlement, TODAY)
    assert build(books, TODAY).at_stake == Decimal("84")
    books.record(Receipt("after", "INV", TODAY, "24", "email:after"))
    assert books.is_held_by_arrangement(books.sales_settlements()[0], TODAY)
    assert build(books, TODAY).at_stake == ZERO
    assert books.arrangement_for("INV") == plan


@pytest.mark.parametrize("full_credit", (False, True))
def test_credit_invalidates_previously_approved_outstanding_claim(full_credit):
    books = _sales_books()
    draft = ChaseDraft(
        invoice_id="INV", client="Client", to_address="client@example.test",
        subject="Our outstanding invoice", opening="Hello,",
        claims=(Outstanding("INV", Decimal("120")),), closing="Thank you.", as_of=TODAY,
    )
    approval = Approval(
        fingerprint=draft.fingerprint(), approved_by="owner",
        approved_at=datetime(2026, 9, 14, 9, tzinfo=UTC),
    )
    assert assess(books, draft, approval, TODAY).allowed
    amounts = ("100", "20", "120") if full_credit else ("20", "4", "24")
    books.record(SalesCreditNote("CN", "INV", TODAY, *amounts, "email:credit"))
    verdict = assess(books, draft, approval, TODAY)
    assert not verdict.allowed
    assert any("draft says 120.00" in reason for reason in verdict.reasons)
    if full_credit:
        assert any("credit notes" in reason for reason in verdict.reasons)
        assert not any("client who has paid" in reason for reason in verdict.reasons)
