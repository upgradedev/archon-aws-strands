"""Payments that point nowhere, payments that overpay, and half-posted documents.

All three failures are the quiet kind: the books still balance afterwards, so
nothing downstream notices. That is what makes them worth their own file.
"""

from __future__ import annotations

from datetime import date

import pytest

from archon.domain.books import Books, SettlementError
from archon.domain.documents import Payment, PayrollRun, Receipt


def test_a_receipt_against_a_typo_is_refused(books):
    # Posts happily if unchecked: the bank moves, the invoice stays open forever,
    # and the owner chases a client who has already paid.
    with pytest.raises(SettlementError, match="not a sales invoice"):
        books.record(
            Receipt(
                doc_id="RC-typo",
                settles="SI-O01",
                received_on=date(2026, 9, 3),
                amount="100.00",
                source_ref="email:typo",
            )
        )


def test_a_payment_against_an_unknown_supplier_invoice_is_refused(books):
    with pytest.raises(SettlementError, match="not a purchase invoice"):
        books.record(
            Payment(
                doc_id="PAY-ghost",
                settles="PI-999",
                paid_on=date(2026, 9, 3),
                amount="10.00",
                source_ref="email:ghost",
            )
        )


def test_a_receipt_cannot_settle_a_sales_invoice_as_though_it_were_a_purchase(books):
    # PI-001 is a real doc_id, just the wrong kind. The reference resolves and
    # the posting would still be wrong.
    with pytest.raises(SettlementError, match="not a sales invoice"):
        books.record(
            Receipt(
                doc_id="RC-crossed",
                settles="PI-001",
                received_on=date(2026, 9, 3),
                amount="10.00",
                source_ref="email:crossed",
            )
        )


def test_overpaying_an_invoice_is_refused(books):
    # SI-001 has 2000.00 outstanding of 2480.00.
    with pytest.raises(SettlementError, match="only 2000.00 outstanding"):
        books.record(
            Receipt(
                doc_id="RC-over",
                settles="SI-001",
                received_on=date(2026, 9, 3),
                amount="2480.00",
                source_ref="email:over",
            )
        )


def test_paying_exactly_what_is_outstanding_is_allowed(books):
    books.record(
        Receipt(
            doc_id="RC-exact",
            settles="SI-001",
            received_on=date(2026, 9, 3),
            amount="2000.00",
            source_ref="email:exact",
        )
    )
    assert {s.doc_id for s in books.uncollected()} == {"SI-003"}


def test_a_second_receipt_may_not_exceed_what_is_left(books):
    books.record(
        Receipt(
            doc_id="RC-part",
            settles="SI-001",
            received_on=date(2026, 9, 3),
            amount="1500.00",
            source_ref="email:part",
        )
    )
    with pytest.raises(SettlementError, match="only 500.00 outstanding"):
        books.record(
            Receipt(
                doc_id="RC-rest",
                settles="SI-001",
                received_on=date(2026, 9, 3),
                amount="600.00",
                source_ref="email:rest",
            )
        )


def test_a_refused_document_leaves_no_trace(books):
    before = len(books.ledger.entries)
    with pytest.raises(SettlementError):
        books.record(
            Receipt(
                doc_id="RC-over",
                settles="SI-001",
                received_on=date(2026, 9, 3),
                amount="9999.00",
                source_ref="email:over",
            )
        )
    assert len(books.ledger.entries) == before
    assert "RC-over" not in {r.doc_id for r in books.receipts}


def test_a_document_that_fails_halfway_posts_neither_entry(books):
    """A payroll run posts two entries. The second one collides here."""
    run = PayrollRun(
        doc_id="PR-2026-09",
        period="September 2026",
        run_on=date(2026, 9, 1),
        gross="900.00",
        paid_on=date(2026, 9, 2),
        source_ref="email:pr9",
    )
    # Occupy the id the second entry will want, so posting it raises partway.
    books.ledger.post(run.entries()[1])
    before = len(books.ledger.entries)

    with pytest.raises(ValueError, match="already posted"):
        books.record(run)

    assert len(books.ledger.entries) == before, "the first entry was left behind"
    assert "PR-2026-09" not in {r.doc_id for r in books.payroll}
    assert books.ledger.trial_balance() == 0


def test_the_books_still_balance_after_every_refusal(books):
    for bad in (
        Receipt("RC-a", "NOPE", date(2026, 9, 3), "1.00", "email:a"),
        Receipt("RC-b", "SI-001", date(2026, 9, 3), "99999.00", "email:b"),
    ):
        with pytest.raises(SettlementError):
            books.record(bad)
    assert books.ledger.trial_balance() == 0


def test_an_empty_book_refuses_everything_rather_than_inventing_a_reference():
    with pytest.raises(SettlementError):
        Books().record(Receipt("RC-x", "SI-001", date(2026, 9, 3), "1.00", "email:x"))
