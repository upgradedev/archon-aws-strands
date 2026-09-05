"""The screen. What the owner opens on a Sunday night, and what a judge opens.

Server-rendered, no build step, no CDN, no external asset of any kind. That is a
constraint with a reason: the page has to work for someone with no account, no
network beyond this host, and no patience, and every one of those is a person
this project has to convince.

Nothing here computes a figure. Every number on the page comes from the ledger
through `archon.domain.reports`, and every sentence in the draft comes from a
claim the books confirmed. The page is a window, and a window that did arithmetic
would be another place for the arithmetic to be wrong.
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from archon.adapters.ses import Outbox, Receipt, SendRefused
from archon.agents.draft import ChaseDraft
from archon.agents.gate import Approval, Release, assess
from archon.demo import (
    NOW,
    QUARTER_FROM,
    SCRIPTED_REPLY,
    TODAY,
    keep_the_books,
    the_post,
    two_lines,
)
from archon.demo import _claims_for as claims_for
from archon.demo import _outbox as build_outbox
from archon.domain.books import Books
from archon.domain.money import fmt
from archon.domain.reports import cashflow, metrics, profit_and_loss
from archon.evidence.compare import score_all, wilson

from .render import page

app = FastAPI(title="Archon", docs_url=None, redoc_url=None)


class Session:
    """One firm's books for the life of the process.

    Deliberately in memory and deliberately one. This is a demonstration surface
    for a single invented firm, not a tenancy, and pretending otherwise with a
    database would be scaffolding that says something untrue about what exists.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.books: Books = keep_the_books(the_post())
        self.outbox: Outbox = build_outbox(False, "books@archon.example")
        self.receipt: Receipt | None = None
        self.last_refusal: str | None = None

    def draft(self) -> ChaseDraft | None:
        worst = self.books.worst_overdue(TODAY)
        if worst is None:
            return None
        opening, closing = two_lines(SCRIPTED_REPLY)
        return ChaseDraft(
            invoice_id=worst.doc_id,
            client=worst.counterparty,
            to_address=worst.contact,
            subject="Our outstanding invoice",
            opening=opening,
            claims=claims_for(self.books, worst),
            closing=closing,
            as_of=TODAY,
        )

    def verdict(self, draft: ChaseDraft, now: datetime | None = None) -> Release:
        approval = Approval(
            fingerprint=draft.fingerprint(), approved_by="the owner", approved_at=NOW
        )
        return assess(self.books, draft, approval, TODAY, now=now or NOW)


session = Session()


def _stats(books: Books, as_of: date = TODAY) -> list[tuple[str, str, str]]:
    m = metrics(books, as_of)
    pnl = profit_and_loss(books, QUARTER_FROM, as_of)
    cash = cashflow(books, QUARTER_FROM, as_of)
    return [
        ("in the bank", fmt(m.bank), "cash in, cash out, this quarter"),
        (
            "owed to you",
            fmt(m.owed_by_clients),
            f"{m.overdue_count} overdue, {fmt(m.overdue_amount)}",
        ),
        ("you owe", fmt(m.owed_to_suppliers), "suppliers, still open"),
        (
            "wages",
            "paid" if m.staff_paid else fmt(m.owed_to_staff),
            "August payroll" if not m.staff_paid else "up to date",
        ),
        ("profit this quarter", fmt(pnl.profit), f"on sales of {fmt(pnl.sales)}"),
        ("cash moved", fmt(cash.net), f"in {fmt(cash.inflow)}, out {fmt(cash.outflow)}"),
    ]


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return page(
        books=session.books,
        stats=_stats(session.books),
        draft=session.draft(),
        verdict_for=session.verdict,
        receipt=session.receipt,
        refusal=session.last_refusal,
        evidence=[(t, wilson(t.wrong_money, t.n)) for t in score_all()],
    )


@app.post("/approve")
def approve(fingerprint: str = Form(...)) -> RedirectResponse:
    """Send, but only the exact text the person was looking at.

    The fingerprint comes back from the form rather than being recomputed here.
    If the books moved while the page was open, the draft this rebuilds differs,
    the fingerprints disagree, and the gate refuses. That is the whole point of
    binding approval to bytes, and it has to survive the round trip through a
    browser to mean anything.
    """
    draft = session.draft()
    session.last_refusal = None
    if draft is None:
        session.last_refusal = "There is nothing overdue any more."
        return RedirectResponse("/", status_code=303)
    if draft.fingerprint() != fingerprint:
        session.last_refusal = (
            "The books moved while this page was open, so the text you approved is not "
            "the text that would be sent. Nothing was sent. Reload and read it again."
        )
        return RedirectResponse("/", status_code=303)
    try:
        session.receipt = session.outbox.send(draft, session.verdict(draft))
    except SendRefused as refused:
        session.last_refusal = str(refused)
    return RedirectResponse("/", status_code=303)


@app.post("/reset")
def reset() -> RedirectResponse:
    session.reset()
    return RedirectResponse("/", status_code=303)


@app.post("/pay")
def client_pays() -> RedirectResponse:
    """The client pays at lunchtime, after the draft was written.

    On the page so a visitor can do it themselves rather than take our word for
    what the gate would do. It is the single most convincing thing here.
    """
    from archon.domain.documents import Receipt as ReceiptDoc
    from archon.domain.money import money

    worst = session.books.worst_overdue(TODAY)
    if worst is not None:
        # Half, not all. Paying in full would leave nothing overdue and the page
        # would simply go quiet, which is correct but says less. A part payment
        # keeps the chase alive with different numbers in it, so the approval the
        # visitor is holding becomes an approval of text that no longer exists.
        # Halving never reaches zero, so repeated presses would never let a
        # visitor see the quiet answer. Under a euro, settle the remainder.
        half = money(worst.outstanding / 2)
        part = worst.outstanding if half < money("1.00") else half
        session.books.record(
            ReceiptDoc(
                doc_id=f"RC-live-{len(session.books.receipts)}",
                settles=worst.doc_id,
                received_on=TODAY,
                amount=str(part),
                source_ref="email:paid-at-lunchtime",
            )
        )
    return RedirectResponse("/", status_code=303)
