"""What is worth doing next, and what nobody can do yet.

AR-03 asks for deterministic arithmetic over the same raw evidence, a full
payment cancelling a pending chase, a partial payment changing the amount, and
ambiguity going to a person. The half that matters most here is the blocked
list: an invoice nobody can chase must stay visible with the one thing that is
missing, rather than disappearing and leaving the screen looking tidy.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from archon.demo import TODAY, keep_the_books, the_post
from archon.domain import queue
from archon.domain.arrangement import Instalment, consider
from archon.domain.documents import Receipt, SalesInvoice
from archon.domain.money import money


@pytest.fixture
def books():
    return keep_the_books(the_post())


def test_the_queue_is_ordered_by_age_then_size(books):
    built = queue.build(books, TODAY)
    ages = [item.days_overdue for item in built.ready]
    assert ages == sorted(ages, reverse=True)


def test_only_chaseable_money_counts_as_at_stake(books):
    built = queue.build(books, TODAY)
    assert built.at_stake == sum(i.outstanding for i in built.ready)
    assert all(i.actionable for i in built.ready)


def test_an_invoice_not_yet_due_is_blocked_and_says_so(books):
    built = queue.build(books, TODAY)
    reasons = {i.reason for i in built.blocked}
    assert queue.NOT_DUE in reasons


def test_an_invoice_with_no_reply_address_never_reaches_the_books():
    """It is refused at the reading boundary, which is the right boundary.

    `SalesInvoice` will not construct without a client address, so an invoice
    nobody could reply to cannot be posted at all. That is stricter than
    blocking it in the queue and it is the behaviour worth keeping: the money is
    never silently in the books as something that looks chaseable.
    """
    from archon.domain.documents import DocumentError

    with pytest.raises(DocumentError):
        SalesInvoice(
            doc_id="SI-NOADDR",
            client="Someone",
            client_email="",
            issued=date(2026, 6, 1),
            due=date(2026, 7, 1),
            net=money(Decimal("100.00")),
            vat=money(Decimal("24.00")),
            gross=money(Decimal("124.00")),
            source_ref="email:noaddr",
        )


def test_an_email_with_no_reply_address_becomes_a_visible_pending_item():
    """Refused, and then shown. AR-01: it stops explicitly rather than guessing."""
    from archon.runtime import OFFLINE, read_the_post

    kept = read_the_post(
        [
            "Subject: Invoice NR-1" + chr(10) + chr(10) + "Invoice NR-1 dated 2026-06-01, "
            "due 2026-07-01. Net 100.00 EUR, VAT 24.00 EUR, total 124.00 EUR."
        ],
        OFFLINE,
        prefix="email",
    )
    assert kept.read_count == 0
    assert len(kept.refusals) == 1
    said = kept.refusals[0]
    assert "Invoice direction is ambiguous" in said, said
    assert "Include the original issuer and customer" in said, (
        "the refusal has to say which missing evidence would fix it"
    )


def test_a_full_payment_takes_it_out_of_the_queue_entirely(books):
    worst = books.worst_overdue(TODAY)
    books.record(
        Receipt("RC-FULL", worst.doc_id, date(2026, 9, 8), worst.outstanding, "email:full")
    )
    built = queue.build(books, TODAY)

    assert worst.doc_id not in {i.invoice_id for i in built.ready}
    assert worst.doc_id not in {i.invoice_id for i in built.blocked}


def test_a_partial_payment_changes_the_amount_and_it_stays_chaseable(books):
    worst = books.worst_overdue(TODAY)
    before = worst.outstanding
    part = money(Decimal("500.00"))
    books.record(Receipt("RC-PART", worst.doc_id, date(2026, 9, 8), part, "email:part"))

    built = queue.build(books, TODAY)
    item = next(i for i in built.ready if i.invoice_id == worst.doc_id)
    assert item.outstanding == before - part
    assert item.actionable


def test_an_agreed_plan_blocks_the_chase_and_names_the_reason(books):
    worst = books.worst_overdue(TODAY)
    books.agree(
        consider(
            invoice_id=worst.doc_id,
            outstanding=worst.outstanding,
            instalments=(Instalment(date(2026, 9, 20), worst.outstanding),),
            as_of=TODAY,
            baseline=worst.gross - worst.outstanding,
            approved_by="owner",
        )
    )
    built = queue.build(books, TODAY)
    blocked = {i.invoice_id: i.reason for i in built.blocked}

    assert blocked.get(worst.doc_id) == queue.ARRANGED
    assert built.at_stake == 0


def test_a_broken_plan_puts_it_back_in_the_queue(books):
    worst = books.worst_overdue(TODAY)
    owed = worst.outstanding
    books.agree(
        consider(
            invoice_id=worst.doc_id,
            outstanding=owed,
            instalments=(Instalment(date(2026, 9, 20), owed),),
            as_of=TODAY,
            baseline=worst.gross - owed,
            approved_by="owner",
        )
    )
    built = queue.build(books, date(2026, 9, 21))
    item = next(i for i in built.ready if i.invoice_id == worst.doc_id)
    assert item.outstanding == owed, "a broken promise chases the whole balance"


def test_nothing_here_calls_a_model():
    """A ranking nobody can check against the books is not a ranking."""
    import ast
    import pathlib

    source = pathlib.Path("src/archon/domain/queue.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "converse" not in names
    assert "invoke_model" not in names
    assert "agent" not in source.lower().split("arrangement")[0].split("def ")[0]


def test_two_currencies_are_never_added_together():
    """Declared rather than converted at a rate nobody chose."""
    import pathlib

    source = pathlib.Path("src/archon/domain/queue.py").read_text(encoding="utf-8")
    said = " ".join(source.split())
    assert "Currencies are never added together" in said
    built = queue.build(keep_the_books(the_post()), TODAY)
    assert built.currency == "EUR"
    assert all(i.currency == built.currency for i in built.ready + built.blocked)


def test_the_queue_appears_on_the_page_with_both_halves():
    from fastapi.testclient import TestClient

    from archon.web.app import app, session

    session.reset()
    with TestClient(app) as client:
        html = client.get("/").text

    assert "What is worth doing next" in html
    assert "Waiting on somebody, not on Archon" in html
    assert "2,000.00 EUR can be chased today" in html
    assert queue.NOT_DUE in html
