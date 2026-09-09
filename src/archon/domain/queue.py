"""What is worth doing next, and what cannot be done until somebody says.

Two lists, deliberately separate.

**The queue** is money that can be chased today, ordered by what it is worth
chasing: the amount at stake and how late it is. The arithmetic is ordinary and
deterministic — no model ranks anything, because a ranking a model produced
would be a ranking nobody could check against the books.

**The blocked list** is money that cannot be chased and the exact reason. This
is the half that gets left out of tools like this, and leaving it out is what
makes them untrustworthy: an invoice with no reply address silently disappears,
the owner never learns it exists, and the software looks tidy while the money
sits there. Nothing here is guessed at. If the recipient is unknown it says the
recipient is unknown, and it stays on the screen until a person fixes it.

Currencies are never added together. This project trades in one, and a second
one appearing is a reason to stop rather than a reason to convert at a rate
nobody chose.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .money import ZERO

#: Why an invoice cannot be chased. Each is a specific thing a person can fix,
#: never a general "needs review".
NO_RECIPIENT = "no reply address on the invoice"
NO_AMOUNT = "no amount that adds up"
DISPUTED = "the client disputes it"
ARRANGED = "a payment plan is being kept"
NOT_DUE = "not due yet"


@dataclass(frozen=True, slots=True)
class Item:
    """One line of work, with the figure that justifies it."""

    invoice_id: str
    client: str
    recipient: str
    outstanding: Decimal
    currency: str
    days_overdue: int
    reason: str = ""

    @property
    def actionable(self) -> bool:
        return not self.reason

    @property
    def weight(self) -> tuple:
        """Order: most overdue first, then largest.

        Age before size on purpose. Age is the thing a client cannot argue with,
        and a small debt that has been ignored for ninety days is a worse sign
        than a large one that is a week late.
        """
        return (-self.days_overdue, -self.outstanding)


@dataclass(frozen=True, slots=True)
class Queue:
    """What to do, and what nobody can do yet."""

    ready: tuple[Item, ...]
    blocked: tuple[Item, ...]
    currency: str

    @property
    def at_stake(self) -> Decimal:
        """Only what is actually chaseable. Blocked money is not a pipeline."""
        return sum((item.outstanding for item in self.ready), ZERO)

    @property
    def next_up(self) -> Item | None:
        return self.ready[0] if self.ready else None


def build(books, as_of: date, currency: str = "EUR") -> Queue:
    """Work out the queue from the books, with no model anywhere near it."""
    ready: list[Item] = []
    blocked: list[Item] = []

    for settlement in books.uncollected():
        overdue_days = max(0, (as_of - settlement.due).days)
        item = Item(
            invoice_id=settlement.doc_id,
            client=settlement.counterparty,
            recipient=settlement.contact,
            outstanding=settlement.outstanding,
            currency=currency,
            days_overdue=overdue_days,
        )

        if settlement.outstanding <= ZERO:
            continue
        if not settlement.contact:
            # The case that quietly disappears in most tools. It stays visible.
            blocked.append(_with(item, NO_RECIPIENT))
            continue
        if books.arrangement_for(settlement.doc_id) is not None and books.is_held_by_arrangement(
            settlement, as_of
        ):
            blocked.append(_with(item, ARRANGED))
            continue
        if not settlement.is_overdue(as_of):
            blocked.append(_with(item, NOT_DUE))
            continue
        ready.append(item)

    return Queue(
        ready=tuple(sorted(ready, key=lambda i: i.weight)),
        blocked=tuple(sorted(blocked, key=lambda i: i.weight)),
        currency=currency,
    )


def _with(item: Item, reason: str) -> Item:
    return Item(
        invoice_id=item.invoice_id,
        client=item.client,
        recipient=item.recipient,
        outstanding=item.outstanding,
        currency=item.currency,
        days_overdue=item.days_overdue,
        reason=reason,
    )
