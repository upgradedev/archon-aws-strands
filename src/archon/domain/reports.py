"""P&L, cashflow and the metrics that sit on top of them.

Read-only over the ledger. Nothing here posts, and nothing here holds a number
that the ledger does not already imply, so a report can never drift from the
books it claims to describe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .accounts import Account
from .books import Books
from .money import ZERO, money


@dataclass(frozen=True, slots=True)
class ProfitAndLoss:
    """What the period earned, and what it cost to earn it."""

    frm: date
    to: date
    sales: Decimal
    purchases: Decimal
    wages: Decimal

    @property
    def costs(self) -> Decimal:
        return money(self.purchases + self.wages)

    @property
    def profit(self) -> Decimal:
        return money(self.sales - self.costs)

    @property
    def margin(self) -> Decimal | None:
        """Profit as a share of sales, or None when nothing was sold.

        None rather than zero: a month with no sales has no margin, and calling
        that 0% invites a chart to draw a line through a quantity that does not
        exist.
        """
        if self.sales == ZERO:
            return None
        return (self.profit / self.sales).quantize(Decimal("0.0001"))


@dataclass(frozen=True, slots=True)
class Cashflow:
    """What actually moved through the bank, which is not the same as profit."""

    frm: date
    to: date
    opening: Decimal
    inflow: Decimal
    outflow: Decimal

    @property
    def net(self) -> Decimal:
        return money(self.inflow - self.outflow)

    @property
    def closing(self) -> Decimal:
        return money(self.opening + self.net)


def _movement(books: Books, account: Account, frm: date, to: date) -> Decimal:
    return sum(
        (
            posting.amount
            for entry in books.ledger.entries
            if frm <= entry.on <= to
            for posting in entry.postings
            if posting.account is account
        ),
        ZERO,
    )


def profit_and_loss(books: Books, frm: date, to: date) -> ProfitAndLoss:
    return ProfitAndLoss(
        frm=frm,
        to=to,
        sales=money(-_movement(books, Account.SALES, frm, to)),
        purchases=money(_movement(books, Account.PURCHASES, frm, to)),
        wages=money(_movement(books, Account.WAGES, frm, to)),
    )


def cashflow(books: Books, frm: date, to: date) -> Cashflow:
    bank_before = sum(
        (
            posting.amount
            for entry in books.ledger.entries
            if entry.on < frm
            for posting in entry.postings
            if posting.account is Account.BANK
        ),
        ZERO,
    )
    inflow = sum(
        (
            posting.amount
            for entry in books.ledger.entries
            if frm <= entry.on <= to
            for posting in entry.postings
            if posting.account is Account.BANK and posting.amount > ZERO
        ),
        ZERO,
    )
    outflow = -sum(
        (
            posting.amount
            for entry in books.ledger.entries
            if frm <= entry.on <= to
            for posting in entry.postings
            if posting.account is Account.BANK and posting.amount < ZERO
        ),
        ZERO,
    )
    return Cashflow(
        frm=frm, to=to, opening=money(bank_before), inflow=money(inflow), outflow=money(outflow)
    )


@dataclass(frozen=True, slots=True)
class Metrics:
    """The handful of numbers the owner actually looks at."""

    as_of: date
    owed_to_suppliers: Decimal
    owed_by_clients: Decimal
    overdue_amount: Decimal
    overdue_count: int
    oldest_overdue_days: int
    staff_paid: bool
    owed_to_staff: Decimal
    bank: Decimal

    @property
    def working_capital(self) -> Decimal:
        """Bank plus what clients owe, less everything owed out.

        Wages owed count. Leaving payroll out of this flatters the number in
        exactly the month a small firm can least afford to be flattered, which
        is the month it has not yet paid its people.
        """
        return money(
            self.bank + self.owed_by_clients - self.owed_to_suppliers - self.owed_to_staff
        )


def metrics(books: Books, as_of: date) -> Metrics:
    overdue = books.overdue(as_of)
    return Metrics(
        as_of=as_of,
        owed_to_suppliers=money(sum((s.outstanding for s in books.owed_to_suppliers()), ZERO)),
        owed_by_clients=money(sum((s.outstanding for s in books.uncollected()), ZERO)),
        overdue_amount=money(sum((s.outstanding for s in overdue), ZERO)),
        overdue_count=len(overdue),
        oldest_overdue_days=max((s.days_overdue(as_of) for s in overdue), default=0),
        staff_paid=books.staff_are_paid(),
        owed_to_staff=money(sum((run.gross for run in books.payroll_unpaid()), ZERO)),
        bank=books.ledger.balance_as_read(Account.BANK, upto=as_of),
    )
