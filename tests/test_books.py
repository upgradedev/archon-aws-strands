"""The six questions the owner asked, each with a test that answers it."""

from datetime import date
from decimal import Decimal

import pytest

from archon.domain.documents import DocumentError, PurchaseInvoice

TODAY = date(2026, 9, 3)


# 1. what invoices have my suppliers sent me
def test_supplier_invoices_are_all_there(books):
    assert {inv.doc_id for inv in books.purchases} == {"PI-001", "PI-002"}


# 2. which of them have I paid
def test_paid_and_unpaid_supplier_invoices_are_distinguished(books):
    by_id = {s.doc_id: s for s in books.purchase_settlements()}
    assert by_id["PI-001"].is_settled
    assert not by_id["PI-002"].is_settled
    assert by_id["PI-002"].outstanding == Decimal("496.00")
    assert [s.doc_id for s in books.owed_to_suppliers()] == ["PI-002"]


# 3. what sales have I made
def test_sales_are_all_there(books):
    assert {inv.doc_id for inv in books.sales} == {"SI-001", "SI-002", "SI-003"}


# 4. which of those have I collected
def test_collection_handles_full_partial_and_none(books):
    by_id = {s.doc_id: s for s in books.sales_settlements()}
    assert by_id["SI-002"].is_settled                       # paid in full
    assert by_id["SI-001"].outstanding == Decimal("2000.00")  # part paid, 480 of 2480
    assert by_id["SI-003"].outstanding == Decimal("1860.00")  # untouched


def test_a_part_paid_invoice_is_still_owed(books):
    # The trap this guards: treating any receipt as settlement. SI-001 received
    # 480 against 2480 and is the largest debt in the book, not a closed item.
    assert "SI-001" in {s.doc_id for s in books.uncollected()}


# 5. have I paid my staff
def test_unpaid_payroll_is_visible(books):
    assert not books.staff_are_paid()
    assert [run.doc_id for run in books.payroll_unpaid()] == ["PR-2026-08"]


# the hero: which receivable the chase is written about
def test_the_worst_overdue_is_the_oldest_open_debt(books):
    worst = books.worst_overdue(TODAY)
    assert worst is not None
    assert worst.doc_id == "SI-001"
    assert worst.counterparty == "Cafe on the corner"
    assert worst.outstanding == Decimal("2000.00")
    assert worst.days_overdue(TODAY) == 55


def test_an_invoice_not_yet_due_is_not_chased(books):
    # SI-003 falls due 2026-09-24. Chasing it today would cost a client.
    assert "SI-003" not in {s.doc_id for s in books.overdue(TODAY)}


def test_nothing_is_overdue_before_any_due_date(books):
    assert books.worst_overdue(date(2026, 6, 1)) is None


def test_a_document_with_no_posting_rule_is_refused_not_ignored(books):
    with pytest.raises(TypeError, match="no posting rule"):
        books.record("an invoice, honest")


def test_an_invoice_whose_vat_does_not_add_up_is_refused():
    with pytest.raises(DocumentError, match="does not|but the document says"):
        PurchaseInvoice(
            doc_id="PI-X",
            supplier="Wholesaler A",
            issued=date(2026, 9, 1),
            due=date(2026, 9, 30),
            net="100.00",
            vat="24.00",
            gross="125.00",
            source_ref="email:x",
        )


def test_recording_a_document_posts_a_balanced_ledger(books):
    assert books.ledger.trial_balance() == Decimal("0.00")
