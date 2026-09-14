"""Credit persistence replays native documents and rolls failed saves back."""

import contextlib
import json
import sqlite3
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from archon.agents.claims import PartPaid
from archon.domain.accounts import Account
from archon.domain.arrangement import Instalment, consider
from archon.domain.books import Books
from archon.domain.documents import (
    Payment,
    PurchaseCreditNote,
    PurchaseInvoice,
    Receipt,
    SalesCreditNote,
    SalesInvoice,
)
from archon.domain.money import ZERO
from archon.domain.reports import cashflow, metrics, profit_and_loss
from archon.store.sqlite import StoreError, _decode, _encode, load, save

ISSUED = date(2026, 8, 1)
DUE = date(2026, 8, 15)
TODAY = date(2026, 9, 14)


def _sales(doc_id="SI"):
    return SalesInvoice(
        doc_id, "Client", "client@example.test", ISSUED, DUE,
        "100", "20", "120", f"email:{doc_id}",
    )


def _purchase(doc_id="PI"):
    return PurchaseInvoice(doc_id, "Supplier", ISSUED, DUE, "100", "20", "120", f"email:{doc_id}")


def _books():
    books = Books()
    for document in (
        _sales(), _purchase(),
        SalesCreditNote("SCN", "SI", TODAY, "20", "4", "24", "email:scn"),
        PurchaseCreditNote("PCN", "PI", TODAY, "30", "6", "36", "email:pcn"),
        Receipt("RC", "SI", TODAY, "30", "email:receipt", "bank:receipt"),
        Payment("PAY", "PI", TODAY, "48", "email:payment", "bank:payment"),
    ):
        books.record(document)
    return books


def _rows(path):
    with contextlib.closing(sqlite3.connect(path)) as db:
        return (
            db.execute("SELECT * FROM documents ORDER BY kind, doc_id").fetchall(),
            db.execute("SELECT * FROM arrangements ORDER BY invoice_id").fetchall(),
            db.execute("SELECT * FROM sends ORDER BY fingerprint").fetchall(),
        )


@pytest.mark.parametrize("credit_type", (SalesCreditNote, PurchaseCreditNote))
def test_credit_codec_preserves_native_type_and_exact_fields(credit_type):
    credit = credit_type("CN", "INV", TODAY, "0.10", "0.02", "0.12", "email:credit")
    body = _encode(credit)
    assert json.loads(body) == {
        "doc_id": "CN", "settles": "INV", "issued": "2026-09-14",
        "net": "0.10", "vat": "0.02", "gross": "0.12", "source_ref": "email:credit",
    }
    decoded = _decode(credit_type.__name__, body)
    assert type(decoded) is credit_type
    assert decoded == credit


def test_native_credits_cash_and_reports_survive_idempotent_reopen(tmp_path):
    path = tmp_path / "credits.db"
    books = _books()
    for _ in range(2):
        assert save(books, path) == 6
        back = load(path)
        assert back.sales_credits == books.sales_credits
        assert back.purchase_credits == books.purchase_credits
        assert back.sales_settlements() == books.sales_settlements()
        assert back.purchase_settlements() == books.purchase_settlements()
        assert len(back.ledger.entries) == 6
        assert back.ledger.trial_balance() == ZERO
        for account in Account:
            assert back.ledger.balance(account) == books.ledger.balance(account)
        assert profit_and_loss(back, ISSUED, TODAY) == profit_and_loss(books, ISSUED, TODAY)
        assert cashflow(back, ISSUED, TODAY) == cashflow(books, ISSUED, TODAY)
        assert metrics(back, TODAY) == metrics(books, TODAY)
        assert PartPaid("SI", Decimal("30")).holds(back, TODAY)
        assert not PartPaid("SI", Decimal("54")).holds(back, TODAY)
    kinds = {row[1] for row in _rows(path)[0]}
    assert kinds == {
        "SalesInvoice", "PurchaseInvoice", "Receipt", "Payment",
        "SalesCreditNote", "PurchaseCreditNote",
    }


def test_replay_resolves_invoices_before_credits_regardless_of_stored_order(tmp_path):
    path = tmp_path / "credits.db"
    books = _books()
    save(books, path)
    with contextlib.closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE documents SET received = -received")
    back = load(path)
    assert back.sales_settlements() == books.sales_settlements()
    assert back.purchase_settlements() == books.purchase_settlements()


@pytest.mark.parametrize("counts", (
    (0, 0, 0, 0, 0, 0),
    (73, 11, 61, 7, 43, 3),
    (5, 53, 2, 47, 1, 29),
))
def test_store_supports_unequal_type_counts_without_fixed_replay_offsets(tmp_path, counts):
    sales, purchases, sales_credits, purchase_credits, receipts, payments = counts
    books = Books()
    for i in range(sales):
        books.record(_sales(f"SI-{i}"))
    for i in range(purchases):
        books.record(_purchase(f"PI-{i}"))
    for i in range(sales_credits):
        books.record(SalesCreditNote(
            f"SCN-{i}", f"SI-{i}", TODAY, "10", "2", "12", f"email:scn:{i}",
        ))
    for i in range(purchase_credits):
        books.record(PurchaseCreditNote(
            f"PCN-{i}", f"PI-{i}", TODAY, "10", "2", "12", f"email:pcn:{i}",
        ))
    for i in range(receipts):
        books.record(Receipt(
            f"RC-{i}", f"SI-{i}", TODAY, "24", f"email:rc:{i}", f"bank:rc:{i}",
        ))
    for i in range(payments):
        books.record(Payment(
            f"PAY-{i}", f"PI-{i}", TODAY, "36", f"email:pay:{i}", f"bank:pay:{i}",
        ))
    path = tmp_path / "volume.db"
    assert save(books, path) == sum(counts)
    back = load(path)
    assert tuple(len(bucket) for bucket in (
        back.sales, back.purchases, back.sales_credits, back.purchase_credits,
        back.receipts, back.payments,
    )) == counts
    assert len(back.ledger.entries) == sum(counts)
    assert back.ledger.trial_balance() == ZERO
    assert metrics(back, TODAY) == metrics(books, TODAY)


@pytest.mark.parametrize("credit_id,changes", (
    ("SCN", {"settles": "absent"}),
    ("SCN", {"settles": "PI"}),
    ("PCN", {"settles": "SI"}),
    ("SCN", {"settles": "PCN"}),
    ("SCN", {"issued": "2026-07-31"}),
    ("PCN", {"issued": "not-a-date"}),
    ("SCN", {"net": "101", "vat": "0", "gross": "101"}),
    ("PCN", {"net": "1", "vat": "21", "gross": "22"}),
    ("SCN", {"net": "80", "vat": "20", "gross": "100"}),
    ("PCN", {"net": "70", "vat": "10", "gross": "80"}),
    ("SCN", {"gross": "24.001"}),
    ("SCN", {"net": 20.0}),
    ("SCN", {"doc_id": "another-id"}),
    ("PCN", {"source_ref": ""}),
))
def test_invalid_stored_credit_fails_replay_without_rewriting_rows(tmp_path, credit_id, changes):
    path = tmp_path / "credits.db"
    save(_books(), path)
    with contextlib.closing(sqlite3.connect(path)) as db, db:
        body, = db.execute("SELECT body FROM documents WHERE doc_id = ?", (credit_id,)).fetchone()
        fields = json.loads(body)
        fields.update(changes)
        db.execute(
            "UPDATE documents SET body = ? WHERE doc_id = ?", (json.dumps(fields), credit_id),
        )
    before = _rows(path)
    with pytest.raises(StoreError, match=credit_id):
        load(path)
    assert _rows(path) == before


def test_invalid_credit_save_rolls_back_new_rows_and_invoice_overwrite(tmp_path):
    path = tmp_path / "credits.db"
    books = _books()
    save(books, path)
    before = _rows(path)
    books.sales[0] = replace(books.sales[0], net="40", vat="8", gross="48")
    books.record(_sales("SI-new"))
    with pytest.raises(StoreError, match="SCN"):
        save(books, path)
    assert _rows(path) == before
    assert load(path).sales_settlements()[0].outstanding == Decimal("66")


@pytest.mark.parametrize("net,vat,gross,match", (
    ("90", "1", "91", "cumulative net"),
    ("1", "19", "20", "cumulative vat"),
    ("60", "10", "70", "outstanding"),
))
def test_credit_save_revalidates_mutated_lists_atomically(tmp_path, net, vat, gross, match):
    path = tmp_path / "credits.db"
    books = _books()
    save(books, path)
    before = _rows(path)
    books.sales_credits.append(SalesCreditNote("bad", "SI", TODAY, net, vat, gross, "email:bad"))
    with pytest.raises(StoreError, match=match):
        save(books, path)
    assert _rows(path) == before


def test_existing_persisted_credits_bound_a_save_from_a_stale_book(tmp_path):
    path = tmp_path / "credits.db"
    save(_books(), path)
    before = _rows(path)
    stale = Books()
    stale.record(_sales())
    stale.record(Receipt("new-cash", "SI", TODAY, "80", "email:new", "bank:new"))
    with pytest.raises(StoreError, match="outstanding"):
        save(stale, path)
    assert _rows(path) == before


def test_credit_and_arrangement_save_roll_back_together_on_sql_failure(tmp_path):
    path = tmp_path / "credits.db"
    books = _books()
    plan = consider(
        invoice_id="SI", outstanding=Decimal("66"), as_of=TODAY,
        baseline=Decimal("30"), approved_by="owner",
        instalments=(Instalment(date(2026, 10, 1), Decimal("66")),),
    )
    books.agree(plan)
    save(books, path)
    before = _rows(path)
    books.record(SalesCreditNote("SCN-new", "SI", TODAY, "10", "2", "12", "email:new"))
    books.agree(replace(plan, approved_by=object()))
    with pytest.raises(sqlite3.Error):
        save(books, path)
    assert _rows(path) == before
    back = load(path)
    assert back.arrangement_for("SI") == plan
    assert back.sales_settlements()[0].credited == Decimal("24")


def test_arrangement_baseline_remains_cash_only_after_credit_replay(tmp_path):
    path = tmp_path / "credits.db"
    books = Books()
    books.record(_sales())
    books.record(Receipt("before", "SI", DUE, "12", "email:before"))
    plan = consider(
        invoice_id="SI", outstanding=Decimal("108"), as_of=DUE,
        baseline=Decimal("12"), approved_by="owner",
        instalments=(
            Instalment(date(2026, 9, 1), Decimal("24")),
            Instalment(date(2026, 10, 1), Decimal("84")),
        ),
    )
    books.agree(plan)
    books.record(SalesCreditNote("SCN", "SI", TODAY, "20", "4", "24", "email:credit"))
    save(books, path)
    back = load(path)
    assert back.arrangement_for("SI") == plan
    assert back.sales_settlements()[0].settled == Decimal("12")
    assert not back.is_held_by_arrangement(back.sales_settlements()[0], TODAY)
    assert back.worst_overdue(TODAY).outstanding == Decimal("84")
