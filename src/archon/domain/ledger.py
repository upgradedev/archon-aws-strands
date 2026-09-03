"""Double entry, enforced rather than assumed.

A journal entry that does not balance is refused at construction. That single
invariant is what makes every report downstream trustworthy: a P&L computed
from entries that each sum to zero cannot silently lose money, and a cashflow
that disagrees with the bank balance is then a bug in one place, not anywhere.

Provenance is not optional. Every entry carries the source it came from, so a
number on screen can always be walked back to the email that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .accounts import Account, Side
from .money import ZERO, money


class UnbalancedEntry(ValueError):
    """Debits and credits do not agree."""


@dataclass(frozen=True, slots=True)
class Posting:
    """One line of a journal entry.

    ``amount`` is signed: positive is a debit, negative is a credit. One signed
    number beats a side flag plus a magnitude, because balance is then a sum and
    not a comparison of two running totals that can drift apart.
    """

    account: Account
    amount: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", money(self.amount))
        if self.amount == ZERO:
            raise ValueError(f"a posting of nothing to {self.account.value}")

    @property
    def side(self) -> Side:
        return Side.DEBIT if self.amount > ZERO else Side.CREDIT


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """A balanced set of postings, with the document that caused it."""

    entry_id: str
    on: date
    narrative: str
    postings: tuple[Posting, ...]
    source_ref: str

    def __post_init__(self) -> None:
        if not self.postings:
            raise UnbalancedEntry(f"{self.entry_id}: an entry with no postings")
        if not self.source_ref:
            raise ValueError(f"{self.entry_id}: an entry with no source is not evidence")
        residual = sum((p.amount for p in self.postings), ZERO)
        if residual != ZERO:
            raise UnbalancedEntry(
                f"{self.entry_id}: debits and credits differ by {residual}. "
                "Nothing is posted until they agree."
            )


@dataclass
class Ledger:
    """Every entry ever posted, and the balances that fall out of them."""

    entries: list[JournalEntry] = field(default_factory=list)

    def post(self, entry: JournalEntry) -> JournalEntry:
        """Append an entry. Construction already proved it balances."""
        if any(e.entry_id == entry.entry_id for e in self.entries):
            raise ValueError(f"{entry.entry_id}: already posted")
        self.entries.append(entry)
        return entry

    def balance(self, account: Account, *, upto: date | None = None) -> Decimal:
        """Signed balance of one account: positive debit, negative credit."""
        return sum(
            (
                posting.amount
                for entry in self.entries
                if upto is None or entry.on <= upto
                for posting in entry.postings
                if posting.account is account
            ),
            ZERO,
        )

    def balance_as_read(self, account: Account, *, upto: date | None = None) -> Decimal:
        """Balance signed the way a human reads that account.

        Trade creditors of 1,200 is a debt of 1,200, not minus 1,200. This flips
        credit-natural accounts so a report never has to remember to.
        """
        raw = self.balance(account, upto=upto)
        return raw if account.natural is Side.DEBIT else -raw

    def trial_balance(self, *, upto: date | None = None) -> Decimal:
        """Sum of every posting. Any answer but zero is a broken ledger."""
        return sum(
            (
                posting.amount
                for entry in self.entries
                if upto is None or entry.on <= upto
                for posting in entry.postings
            ),
            ZERO,
        )

    def by_source(self, source_ref: str) -> list[JournalEntry]:
        """Every entry that came from one document. This is the audit trail."""
        return [e for e in self.entries if e.source_ref == source_ref]
