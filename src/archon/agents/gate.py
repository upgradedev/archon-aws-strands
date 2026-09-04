"""The one governed write, and what has to be true before it happens.

Nothing leaves on an agent's say-so. The gate re-derives every fact from the
books at the moment of sending, re-checks that the human approved this exact
text, and returns a decision with its reasons. It never sends anything itself:
the caller sends only on ``allowed``, which keeps the deciding and the doing in
different places.

Re-checking at send time is the part that matters. A draft written this morning
against a client who paid at lunchtime is a draft that must not go out, and the
only way to know that is to ask the books again rather than to trust the draft.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from archon.domain.books import Books
from archon.domain.money import ZERO

from .claims import ClaimRefuted
from .draft import ChaseDraft

#: How long a human's yes stays good for. Short on purpose: an approval is a
#: statement about the books as they stood when it was given, and the books move.
APPROVAL_LIFETIME = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class Approval:
    """A human's yes, bound to the exact bytes they read and to a moment.

    The expiry is not ceremony. An approval left open overnight is a signature on
    a statement about a client's balance that stopped being true, and the person
    who gave it has gone home. Thirty minutes is long enough to read an email and
    short enough that the books cannot have moved far underneath it.
    """

    fingerprint: str
    approved_by: str
    approved_at: datetime
    lifetime: timedelta = APPROVAL_LIFETIME

    def __post_init__(self) -> None:
        if not self.approved_by.strip():
            raise ValueError("an approval with no approver is not an approval")
        if len(self.fingerprint) != 64:
            raise ValueError(f"not a sha-256 fingerprint: {self.fingerprint!r}")
        if self.approved_at.tzinfo is None:
            raise ValueError("an approval needs a timezone-aware moment, not a local guess")
        if self.lifetime <= timedelta(0):
            raise ValueError("an approval that expires before it is given is not an approval")

    @property
    def expires_at(self) -> datetime:
        return self.approved_at + self.lifetime

    def is_live(self, now: datetime) -> bool:
        return self.approved_at <= now <= self.expires_at


@dataclass(frozen=True, slots=True)
class Release:
    """The gate's verdict, with every reason it reached it."""

    allowed: bool
    reasons: tuple[str, ...]

    def __str__(self) -> str:
        verdict = "release" if self.allowed else "held"
        return f"{verdict}: " + "; ".join(self.reasons)


def assess(
    books: Books,
    draft: ChaseDraft,
    approval: Approval,
    as_of: date,
    now: datetime | None = None,
) -> Release:
    """Decide whether this exact email may leave, right now.

    Every reason is collected rather than returning on the first failure, because
    a person fixing a held draft should see all of what is wrong, not the first
    thing the loop happened to hit.
    """
    refusals: list[str] = []

    if books.ledger.trial_balance() != ZERO:
        refusals.append(
            "the books do not balance, so no figure in this email can be trusted"
        )

    settlements = {s.doc_id: s for s in books.sales_settlements()}
    invoice = settlements.get(draft.invoice_id)
    if invoice is None:
        refusals.append(f"{draft.invoice_id} is not a sales invoice in these books")
    else:
        if invoice.counterparty != draft.client:
            refusals.append(
                f"{draft.invoice_id} belongs to {invoice.counterparty}, "
                f"but the draft addresses {draft.client}"
            )
        if invoice.contact != draft.to_address:
            # The name matching is not enough. A correct chase delivered to the
            # wrong inbox is still a disclosure of one client's balance to
            # someone else, and the address is the part an agent could invent.
            refusals.append(
                f"{draft.invoice_id} is billed to {invoice.contact or 'no address on file'}, "
                f"but the draft would send to {draft.to_address}"
            )
        if invoice.is_settled:
            refusals.append(
                f"{draft.invoice_id} has been settled since the draft was written. "
                "Chasing a client who has paid is the expensive mistake here."
            )
        elif not invoice.is_overdue(as_of):
            refusals.append(f"{draft.invoice_id} is not overdue on {as_of}")

    for claim in draft.claims:
        try:
            claim.check(books, as_of)
        except ClaimRefuted as refuted:
            refusals.append(str(refuted))

    moment = now or approval.approved_at
    if not approval.is_live(moment):
        refusals.append(
            f"the approval was given at {approval.approved_at:%Y-%m-%d %H:%M} and lapsed at "
            f"{approval.expires_at:%Y-%m-%d %H:%M}. It describes books that have since moved."
        )

    if approval.fingerprint != draft.fingerprint():
        refusals.append(
            "the approval does not match this text. A human approved different bytes, "
            "so this send is not the one they agreed to."
        )

    if refusals:
        return Release(allowed=False, reasons=tuple(refusals))
    return Release(
        allowed=True,
        reasons=(
            f"{draft.invoice_id} is open, overdue on {as_of}, and every stated fact was "
            f"re-derived from the books; {approval.approved_by} approved this exact text",
        ),
    )


def outstanding_on(books: Books, invoice_id: str) -> Decimal:
    """What is genuinely still owed on one invoice, recomputed."""
    found = {s.doc_id: s for s in books.sales_settlements()}.get(invoice_id)
    if found is None:
        raise KeyError(invoice_id)
    return found.outstanding
