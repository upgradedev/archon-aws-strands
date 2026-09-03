"""Facts an outgoing email is allowed to state.

The usual way an agent embarrasses its owner is by writing a sentence that is
merely plausible: the right shape, the wrong number. Checking the prose
afterwards does not fix it, because prose can say anything and a checker has to
guess what was meant.

So the direction is reversed. A claim is a typed fact that knows how to verify
itself against the books and how to render itself as one sentence. The email
body is built **from** verified claims, which means an unverifiable sentence has
no way to exist. The agent's judgment is which claims to make and in what order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from archon.domain.books import Books
from archon.domain.money import ZERO, fmt, money
from archon.domain.reports import cashflow, metrics


class ClaimRefuted(ValueError):
    """A claim the books do not support."""


@dataclass(frozen=True, slots=True)
class Claim:
    """Base class. Subclasses implement ``check`` and ``sentence``."""

    def check(self, books: Books, as_of: date) -> None:
        raise NotImplementedError

    def sentence(self) -> str:
        raise NotImplementedError

    def holds(self, books: Books, as_of: date) -> bool:
        try:
            self.check(books, as_of)
        except ClaimRefuted:
            return False
        return True


@dataclass(frozen=True, slots=True)
class Outstanding(Claim):
    """"You still owe 2,000.00 EUR on invoice SI-001." """

    invoice_id: str
    amount: Decimal

    def check(self, books: Books, as_of: date) -> None:
        found = {s.doc_id: s for s in books.sales_settlements()}.get(self.invoice_id)
        if found is None:
            raise ClaimRefuted(f"{self.invoice_id} is not a sales invoice in these books")
        if found.outstanding != money(self.amount):
            raise ClaimRefuted(
                f"{self.invoice_id} is outstanding {found.outstanding}, "
                f"but the draft says {money(self.amount)}"
            )

    def sentence(self) -> str:
        return f"Invoice {self.invoice_id} is still outstanding at {fmt(money(self.amount))}."


@dataclass(frozen=True, slots=True)
class Overdue(Claim):
    """"It fell due 55 days ago." """

    invoice_id: str
    days: int

    def check(self, books: Books, as_of: date) -> None:
        found = {s.doc_id: s for s in books.sales_settlements()}.get(self.invoice_id)
        if found is None:
            raise ClaimRefuted(f"{self.invoice_id} is not a sales invoice in these books")
        if not found.is_overdue(as_of):
            raise ClaimRefuted(f"{self.invoice_id} is not overdue on {as_of}")
        actual = found.days_overdue(as_of)
        if actual != self.days:
            raise ClaimRefuted(
                f"{self.invoice_id} is {actual} days overdue, but the draft says {self.days}"
            )

    def sentence(self) -> str:
        return f"It fell due {self.days} days ago."


@dataclass(frozen=True, slots=True)
class PartPaid(Claim):
    """"We received 480.00 EUR against it, with thanks." """

    invoice_id: str
    received: Decimal

    def check(self, books: Books, as_of: date) -> None:
        found = {s.doc_id: s for s in books.sales_settlements()}.get(self.invoice_id)
        if found is None:
            raise ClaimRefuted(f"{self.invoice_id} is not a sales invoice in these books")
        if found.settled == ZERO:
            raise ClaimRefuted(f"nothing has been received against {self.invoice_id}")
        if found.settled != money(self.received):
            raise ClaimRefuted(
                f"{found.settled} was received against {self.invoice_id}, "
                f"but the draft says {money(self.received)}"
            )

    def sentence(self) -> str:
        return f"We have received {fmt(money(self.received))} against it, with thanks."


@dataclass(frozen=True, slots=True)
class WagesDue(Claim):
    """"We have wages to pay this month." The urgency has to be true too."""

    amount: Decimal

    def check(self, books: Books, as_of: date) -> None:
        owed = money(sum((run.gross for run in books.payroll_unpaid()), ZERO))
        if owed == ZERO:
            raise ClaimRefuted("staff are paid; this firm has no wages outstanding to plead")
        if owed != money(self.amount):
            raise ClaimRefuted(f"wages outstanding are {owed}, but the draft says {money(self.amount)}")

    def sentence(self) -> str:
        return f"We have {fmt(money(self.amount))} of wages to settle this month."


@dataclass(frozen=True, slots=True)
class CashPosition(Claim):
    """"Our bank stands at 232.00 EUR." Rarely sent, never guessed."""

    amount: Decimal
    upto: date

    def check(self, books: Books, as_of: date) -> None:
        actual = metrics(books, as_of).bank
        if actual != money(self.amount):
            raise ClaimRefuted(f"the bank stands at {actual}, but the draft says {money(self.amount)}")

    def sentence(self) -> str:
        return f"Our own bank balance stands at {fmt(money(self.amount))}."


def cash_in_window(books: Books, frm: date, to: date) -> Decimal:
    """Helper for an agent deciding how hard to push. Not itself a claim."""
    return cashflow(books, frm, to).net
