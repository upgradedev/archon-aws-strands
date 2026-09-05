"""The books between one Sunday and the next.

What is stored is the post, not the position, so loading runs the same
validation as receiving. The tests that matter are the ones where the store is
wrong, because a store that opens with a subtly wrong ledger is worse than one
that will not open.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import date

import pytest

from archon.demo import TODAY, keep_the_books, the_post
from archon.domain.books import Books
from archon.domain.documents import Receipt
from archon.store.sqlite import StoreError, forget, load, save


@pytest.fixture
def path(tmp_path):
    return tmp_path / "books.db"


def test_a_month_survives_the_round_trip(path):
    books = keep_the_books(the_post())
    assert save(books, path) == 9

    back = load(path)
    assert len(back.ledger.entries) == len(books.ledger.entries)
    assert back.ledger.trial_balance() == 0
    assert back.worst_overdue(TODAY).outstanding == books.worst_overdue(TODAY).outstanding


def test_the_client_address_survives_because_the_chase_needs_it(path):
    save(keep_the_books(the_post()), path)
    assert load(path).sales_settlements()[0].contact == "accounts@cafe.example"


def test_an_absent_store_is_an_empty_month_not_an_error(tmp_path):
    assert load(tmp_path / "nothing.db").ledger.entries == []


def test_saving_twice_does_not_double_the_books(path):
    books = keep_the_books(the_post())
    save(books, path)
    save(books, path)
    assert len(load(path).ledger.entries) == len(books.ledger.entries)


def test_new_documents_are_added_to_what_was_there(path):
    books = keep_the_books(the_post())
    save(books, path)

    books.record(
        Receipt(
            doc_id="RC-later",
            settles="SI-001",
            received_on=date(2026, 9, 3),
            amount="100.00",
            source_ref="email:later",
        )
    )
    save(books, path)
    assert len(load(path).receipts) == 3


def test_forget_removes_it(path):
    save(keep_the_books(the_post()), path)
    forget(path)
    assert load(path).ledger.entries == []


# --- a store that is wrong ---------------------------------------------------


def _corrupt(path, doc_id: str, **changes):
    with contextlib.closing(sqlite3.connect(str(path))) as db, db:
        row = db.execute("SELECT kind, body FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
        fields = json.loads(row[1])
        fields.update(changes)
        db.execute(
            "UPDATE documents SET body = ? WHERE doc_id = ?", (json.dumps(fields), doc_id)
        )


def test_an_invoice_whose_vat_stopped_adding_up_will_not_open(path):
    """Loading runs the same arithmetic as receiving, so this cannot slip through."""
    save(keep_the_books(the_post()), path)
    _corrupt(path, "PI-001", gross="9999.00")

    with pytest.raises(StoreError, match="PI-001"):
        load(path)


def test_a_payment_against_a_missing_invoice_will_not_open(path):
    save(keep_the_books(the_post()), path)
    _corrupt(path, "PAY-001", settles="PI-999")

    with pytest.raises(StoreError, match="PAY-001"):
        load(path)


def test_an_overpayment_will_not_open(path):
    save(keep_the_books(the_post()), path)
    _corrupt(path, "RC-002", amount="99999.00")

    with pytest.raises(StoreError, match="RC-002"):
        load(path)


def test_a_kind_nothing_can_post_will_not_open(path):
    save(keep_the_books(the_post()), path)
    with contextlib.closing(sqlite3.connect(str(path))) as db, db:
        db.execute("UPDATE documents SET kind = 'ChristmasCard' WHERE doc_id = 'PI-001'")

    with pytest.raises(StoreError, match="nothing here can post"):
        load(path)


def test_the_error_names_the_row_so_it_can_be_found(path):
    save(keep_the_books(the_post()), path)
    _corrupt(path, "PI-002", gross="1.00")

    with pytest.raises(StoreError) as caught:
        load(path)
    assert "PI-002" in str(caught.value)
    assert "not opened rather than opened wrong" in str(caught.value)


def test_replay_order_puts_invoices_before_the_payments_that_settle_them(path):
    """Reversed, every payment would be refused for pointing at nothing."""
    save(keep_the_books(the_post()), path)
    with contextlib.closing(sqlite3.connect(str(path))) as db, db:
        db.execute("UPDATE documents SET received = -received")  # invert the order

    assert load(path).ledger.trial_balance() == 0


def test_an_empty_book_saves_and_loads(path):
    assert save(Books(), path) == 0
    assert load(path).ledger.entries == []


def test_the_screen_survives_a_restart(tmp_path):
    """The whole point: closing the laptop does not lose the month."""
    pytest.importorskip("fastapi")
    from archon.web.app import SAMPLE_EMAIL, Session

    store = tmp_path / "session.db"
    first = Session(store_path=str(store))
    before = len(first.books.ledger.entries)

    from archon.adapters.inbound import LocalReader, read_email

    reading = read_email(SAMPLE_EMAIL, "email:pasted", client=LocalReader())
    first.books.record(reading.document)
    first._remember()

    # a new process, same store
    second = Session(store_path=str(store))
    second.reopen()
    assert len(second.books.ledger.entries) == before + 1
    assert any(d.doc_id == "WA-9001" for d in second.books.purchases)


def test_without_a_store_nothing_is_written(tmp_path, monkeypatch):
    """A visitor pressing buttons must not leave the next visitor their books."""
    pytest.importorskip("fastapi")
    from archon.web.app import Session

    monkeypatch.delenv("ARCHON_STORE", raising=False)
    session = Session(store_path=None)
    assert session.store_path is None
    assert not list(tmp_path.glob("*.db"))
