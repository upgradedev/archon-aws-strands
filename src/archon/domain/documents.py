"""The six things that arrive, and the entries each one causes.

Every document knows how to become balanced journal entries and nothing else.
Keeping the posting rules next to the document they belong to is what stops the
rules being reinvented, slightly differently, at each call site.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .accounts import Account
from .ledger import JournalEntry, Posting
from .money import ZERO, money


class DocumentError(ValueError):
    """A document that cannot be posted as it stands."""


def _checked(
    net: Decimal, vat: Decimal, gross: Decimal, ref: str
) -> tuple[Decimal, Decimal, Decimal]:
    net, vat, gross = money(net), money(vat), money(gross)
    if net <= ZERO:
        raise DocumentError(f"{ref}: a net of {net} is not an invoice")
    if vat < ZERO:
        raise DocumentError(f"{ref}: negative VAT of {vat}")
    if net + vat != gross:
        raise DocumentError(
            f"{ref}: {net} plus VAT {vat} is {net + vat}, but the document says {gross}. "
            "Archon does not guess which of the three is wrong."
        )
    return net, vat, gross


@dataclass(frozen=True, slots=True)
class PurchaseInvoice:
    """What a supplier billed us."""

    doc_id: str
    supplier: str
    issued: date
    due: date
    net: Decimal
    vat: Decimal
    gross: Decimal
    source_ref: str

    def __post_init__(self) -> None:
        net, vat, gross = _checked(self.net, self.vat, self.gross, self.doc_id)
        object.__setattr__(self, "net", net)
        object.__setattr__(self, "vat", vat)
        object.__setattr__(self, "gross", gross)
        if self.due < self.issued:
            raise DocumentError(f"{self.doc_id}: due {self.due} precedes issue {self.issued}")

    def entries(self) -> tuple[JournalEntry, ...]:
        postings = [Posting(Account.PURCHASES, self.net)]
        if self.vat > ZERO:
            postings.append(Posting(Account.VAT_INPUT, self.vat))
        postings.append(Posting(Account.PAYABLES, -self.gross))
        return (
            JournalEntry(
                entry_id=f"{self.doc_id}:booked",
                on=self.issued,
                narrative=f"Invoice from {self.supplier}",
                postings=tuple(postings),
                source_ref=self.source_ref,
            ),
        )


@dataclass(frozen=True, slots=True)
class SalesInvoice:
    """What we billed a client."""

    doc_id: str
    client: str
    client_email: str
    issued: date
    due: date
    net: Decimal
    vat: Decimal
    gross: Decimal
    source_ref: str

    def __post_init__(self) -> None:
        net, vat, gross = _checked(self.net, self.vat, self.gross, self.doc_id)
        object.__setattr__(self, "net", net)
        object.__setattr__(self, "vat", vat)
        object.__setattr__(self, "gross", gross)
        if self.due < self.issued:
            raise DocumentError(f"{self.doc_id}: due {self.due} precedes issue {self.issued}")
        # The address lives on the invoice because that is where it can be checked.
        # An address carried on the draft instead is an address the agent chose,
        # and a correct chase sent to the wrong inbox is still a disclosure.
        if "@" not in self.client_email:
            raise DocumentError(f"{self.doc_id}: not a client address: {self.client_email!r}")

    def entries(self) -> tuple[JournalEntry, ...]:
        postings = [Posting(Account.RECEIVABLES, self.gross), Posting(Account.SALES, -self.net)]
        if self.vat > ZERO:
            postings.append(Posting(Account.VAT_OUTPUT, -self.vat))
        return (
            JournalEntry(
                entry_id=f"{self.doc_id}:booked",
                on=self.issued,
                narrative=f"Invoice to {self.client}",
                postings=tuple(postings),
                source_ref=self.source_ref,
            ),
        )


@dataclass(frozen=True, slots=True)
class Payment:
    """Money leaving the bank against a supplier invoice."""

    doc_id: str
    settles: str
    paid_on: date
    amount: Decimal
    source_ref: str

    def __post_init__(self) -> None:
        amount = money(self.amount)
        if amount <= ZERO:
            raise DocumentError(f"{self.doc_id}: a payment of {amount}")
        object.__setattr__(self, "amount", amount)

    def entries(self) -> tuple[JournalEntry, ...]:
        return (
            JournalEntry(
                entry_id=f"{self.doc_id}:paid",
                on=self.paid_on,
                narrative=f"Paid {self.settles}",
                postings=(
                    Posting(Account.PAYABLES, self.amount),
                    Posting(Account.BANK, -self.amount),
                ),
                source_ref=self.source_ref,
            ),
        )


@dataclass(frozen=True, slots=True)
class Receipt:
    """Money arriving in the bank against a sales invoice."""

    doc_id: str
    settles: str
    received_on: date
    amount: Decimal
    source_ref: str

    def __post_init__(self) -> None:
        amount = money(self.amount)
        if amount <= ZERO:
            raise DocumentError(f"{self.doc_id}: a receipt of {amount}")
        object.__setattr__(self, "amount", amount)

    def entries(self) -> tuple[JournalEntry, ...]:
        return (
            JournalEntry(
                entry_id=f"{self.doc_id}:received",
                on=self.received_on,
                narrative=f"Received against {self.settles}",
                postings=(
                    Posting(Account.BANK, self.amount),
                    Posting(Account.RECEIVABLES, -self.amount),
                ),
                source_ref=self.source_ref,
            ),
        )


@dataclass(frozen=True, slots=True)
class PayrollRun:
    """A pay period. Synthetic staff only, which S11 requires and the README says."""

    doc_id: str
    period: str
    run_on: date
    gross: Decimal
    paid_on: date | None
    source_ref: str

    def __post_init__(self) -> None:
        gross = money(self.gross)
        if gross <= ZERO:
            raise DocumentError(f"{self.doc_id}: a payroll of {gross}")
        object.__setattr__(self, "gross", gross)
        if self.paid_on is not None and self.paid_on < self.run_on:
            raise DocumentError(f"{self.doc_id}: paid {self.paid_on} before the run {self.run_on}")

    @property
    def is_paid(self) -> bool:
        return self.paid_on is not None

    def entries(self) -> tuple[JournalEntry, ...]:
        booked = JournalEntry(
            entry_id=f"{self.doc_id}:booked",
            on=self.run_on,
            narrative=f"Payroll {self.period}",
            postings=(
                Posting(Account.WAGES, self.gross),
                Posting(Account.PAYROLL_PAYABLE, -self.gross),
            ),
            source_ref=self.source_ref,
        )
        if self.paid_on is None:
            return (booked,)
        return (
            booked,
            JournalEntry(
                entry_id=f"{self.doc_id}:paid",
                on=self.paid_on,
                narrative=f"Staff paid for {self.period}",
                postings=(
                    Posting(Account.PAYROLL_PAYABLE, self.gross),
                    Posting(Account.BANK, -self.gross),
                ),
                source_ref=self.source_ref,
            ),
        )
