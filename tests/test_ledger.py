"""The one invariant everything else rests on."""

from datetime import date
from decimal import Decimal

import pytest

from archon.domain.accounts import Account, Side
from archon.domain.ledger import JournalEntry, Ledger, Posting, UnbalancedEntry


def _entry(*postings: Posting, entry_id: str = "E1") -> JournalEntry:
    return JournalEntry(
        entry_id=entry_id,
        on=date(2026, 9, 1),
        narrative="test",
        postings=postings,
        source_ref="email:test",
    )


def test_an_unbalanced_entry_never_reaches_the_ledger():
    with pytest.raises(UnbalancedEntry, match="differ by"):
        _entry(Posting(Account.BANK, "100.00"), Posting(Account.SALES, "-90.00"))


def test_an_entry_with_no_source_is_not_evidence():
    with pytest.raises(ValueError, match="no source"):
        JournalEntry(
            entry_id="E1",
            on=date(2026, 9, 1),
            narrative="test",
            postings=(Posting(Account.BANK, "10.00"), Posting(Account.SALES, "-10.00")),
            source_ref="",
        )


def test_a_posting_of_nothing_is_refused():
    with pytest.raises(ValueError, match="posting of nothing"):
        Posting(Account.BANK, "0.00")


def test_posting_side_follows_the_sign():
    assert Posting(Account.BANK, "1.00").side is Side.DEBIT
    assert Posting(Account.SALES, "-1.00").side is Side.CREDIT


def test_the_same_entry_cannot_be_posted_twice():
    ledger = Ledger()
    ledger.post(_entry(Posting(Account.BANK, "10.00"), Posting(Account.SALES, "-10.00")))
    with pytest.raises(ValueError, match="already posted"):
        ledger.post(_entry(Posting(Account.BANK, "10.00"), Posting(Account.SALES, "-10.00")))


def test_a_credit_balance_reads_positive_to_a_human(books):
    # Trade creditors of 496 is a debt of 496, not minus 496.
    raw = books.ledger.balance(Account.PAYABLES)
    assert raw == Decimal("-496.00")
    assert books.ledger.balance_as_read(Account.PAYABLES) == Decimal("496.00")


def test_the_whole_fixture_trial_balances(books):
    assert books.ledger.trial_balance() == Decimal("0.00")


def test_every_number_walks_back_to_a_document(books):
    entries = books.ledger.by_source("email:001")
    assert [e.entry_id for e in entries] == ["PI-001:booked"]
