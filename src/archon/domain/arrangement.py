"""A client says when they will pay. That is a promise, not a payment.

This is the whole discipline of this module, and it is one sentence long:
**an arrangement posts nothing.** No journal entry, no change to what is
outstanding, no reduction of the debt. A client who agrees to pay in three
instalments owes exactly what they owed before they agreed.

What it changes is *when the chase fires*, not *how much is owed*. An invoice
with a live arrangement whose next instalment is not due yet is not chaseable
today. A missed instalment makes it chaseable again, for the whole outstanding
balance, because the balance never moved.

Getting this wrong is the one thing in this area that would be genuinely bad. An
arrangement that touched the ledger would let a client reduce their own debt by
sending an email, and every figure downstream of it would be wrong while looking
right.

The model's job here is narrow: turn "five hundred now and the rest on the
fifteenth" into structured instalments. Whether those instalments are acceptable
is arithmetic, and arithmetic is done here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .money import ZERO, money


class ArrangementRefused(ValueError):
    """A proposal the books will not accept, with the reason a person can read."""


@dataclass(frozen=True, slots=True)
class Instalment:
    """One dated promise. Nothing has been received."""

    due: date
    amount: Decimal

    def is_missed(self, as_of: date, received: Decimal) -> bool:
        """Overdue, and the money that has arrived does not cover it."""
        return self.due < as_of and received < self.amount


@dataclass(frozen=True, slots=True)
class Arrangement:
    """What a client promised, and when. It settles nothing.

    `agreed_on` is when the owner accepted it, not when the client asked. An
    arrangement nobody approved does not exist: the client's email is a proposal
    and it stays one until a person says otherwise.
    """

    invoice_id: str
    agreed_on: date
    instalments: tuple[Instalment, ...]
    #: What had already been received against this invoice when the owner agreed.
    #: Without it, money paid *before* the arrangement counts towards the first
    #: instalment and a client who has paid nothing since looks like they are
    #: keeping to the plan. The baseline is why "received" and "received under
    #: this arrangement" are different numbers.
    baseline: Decimal = ZERO
    #: Who approved it and against which version of the terms. An arrangement
    #: nobody approved does not exist, and the record has to say who did.
    approved_by: str = ""
    version: int = 1
    note: str = ""

    @property
    def promised(self) -> Decimal:
        return money(sum((i.amount for i in self.instalments), ZERO))

    def next_due(self, as_of: date) -> Instalment | None:
        """The first instalment not yet reached. None when all dates have passed."""
        upcoming = [i for i in self.instalments if i.due >= as_of]
        return min(upcoming, key=lambda i: i.due) if upcoming else None

    def due_by(self, as_of: date) -> Decimal:
        """How much the client has promised to have paid by now."""
        return money(sum((i.amount for i in self.instalments if i.due < as_of), ZERO))

    def paid_under_this(self, received_in_total: Decimal) -> Decimal:
        """Of everything received, how much arrived after this was agreed.

        Never negative. A credit note or a correction that reduces total receipts
        below the baseline would otherwise produce a negative payment, which is
        not a thing, and the arrangement should be reviewed by a person rather
        than quietly re-scored.
        """
        return max(ZERO, money(received_in_total - self.baseline))

    def is_broken(self, as_of: date, received_in_total: Decimal) -> bool:
        """A promise that has come due and has not been kept.

        `received_in_total` comes from the books. This class never asks what was
        paid; it is told, because the only thing that knows is the ledger. What
        it does do is subtract the baseline, so money that arrived before the
        promise cannot be spent twice on keeping it.
        """
        return self.paid_under_this(received_in_total) < self.due_by(as_of)

    def is_finished(self, as_of: date) -> bool:
        return self.next_due(as_of) is None


def consider(
    *,
    invoice_id: str,
    outstanding: Decimal,
    instalments: tuple[Instalment, ...],
    as_of: date,
    agreed_on: date | None = None,
    baseline: Decimal = ZERO,
    approved_by: str = "",
) -> Arrangement:
    """Accept a proposal, or refuse it saying exactly why.

    Every check here is arithmetic or a date comparison. None of it is a
    judgement, and none of it is delegated to a model, because a client who can
    talk a model into a smaller total has talked it into a smaller debt.
    """
    if not instalments:
        raise ArrangementRefused(
            "this proposal names no instalments, so there is nothing to agree to"
        )
    if outstanding <= ZERO:
        raise ArrangementRefused(
            f"{invoice_id} has nothing outstanding, so there is nothing to arrange"
        )

    promised = money(sum((i.amount for i in instalments), ZERO))
    if promised != outstanding:
        short = "less" if promised < outstanding else "more"
        raise ArrangementRefused(
            f"the instalments come to {promised} EUR, which is {short} than the "
            f"{outstanding} EUR outstanding on {invoice_id}. A person has to decide "
            "whether to accept a different figure; this is not arithmetic any more."
        )
    if any(i.amount <= ZERO for i in instalments):
        raise ArrangementRefused("an instalment of nothing is not a payment plan")
    if any(i.due < as_of for i in instalments):
        raise ArrangementRefused(
            "one of these instalments is already in the past, which is a proposal "
            "to have paid rather than to pay"
        )

    dates = [i.due for i in instalments]
    if len(set(dates)) != len(dates):
        raise ArrangementRefused("two instalments fall on the same day; say which is which")

    return Arrangement(
        invoice_id=invoice_id,
        agreed_on=agreed_on or as_of,
        instalments=tuple(sorted(instalments, key=lambda i: i.due)),
        baseline=baseline,
        approved_by=approved_by,
    )
