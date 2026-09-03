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
from datetime import date, datetime
from decimal import Decimal

from archon.domain.books import Books
from archon.domain.money import ZERO

from .claims import ClaimRefuted
from .draft import ChaseDraft


@dataclass(frozen=True, slots=True)
class Approval:
    """A human's yes, bound to the exact bytes they read."""

    fingerprint: str
    approved_by: str
    approved_at: datetime

    def __post_init__(self) -> None:
        if not self.approved_by.strip():
            raise ValueError("an approval with no approver is not an approval")
        if len(self.fingerprint) != 64:
            raise ValueError(f"not a sha-256 fingerprint: {self.fingerprint!r}")


@dataclass(frozen=True, slots=True)
class Release:
    """The gate's verdict, with every reason it reached it."""

    allowed: bool
    reasons: tuple[str, ...]

    def __str__(self) -> str:
        verdict = "release" if self.allowed else "held"
        return f"{verdict}: " + "; ".join(self.reasons)


def assess(books: Books, draft: ChaseDraft, approval: Approval, as_of: date) -> Release:
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
