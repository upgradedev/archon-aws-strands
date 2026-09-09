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

import os
from datetime import date, datetime

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from archon.adapters.inbound import (
    LocalReader,
    Reading,
    UnreadablePost,
    read_attachment,
    read_email,
)
from archon.adapters.ses import Outbox, Receipt, SendRefused
from archon.agents.draft import ChaseDraft
from archon.agents.gate import Approval, Release, assess
from archon.agents.views import CAPTURED_ON, captured
from archon.demo import (
    NOW,
    QUARTER_FROM,
    TODAY,
    _composer_reply,
    keep_the_books,
    the_post,
    two_lines,
)
from archon.demo import _claims_for as claims_for
from archon.demo import _outbox as build_outbox
from archon.domain.books import Books
from archon.domain.money import fmt
from archon.domain.queue import build as build_queue
from archon.domain.reports import cashflow, metrics, profit_and_loss
from archon.evidence.compare import score_all, wilson
from archon.runtime import Reasoning
from archon.store.sqlite import forget, load, save

from .render import broke, page

app = FastAPI(title="Archon", docs_url=None, redoc_url=None)


@app.exception_handler(Exception)
async def anything_unexpected(request: Request, failure: Exception) -> HTMLResponse:
    """Say what went wrong, in the page's own voice, and admit it plainly.

    The default is a bare "Internal Server Error", which on a demonstration
    someone is watching says nothing and looks like the product simply stopped.
    This is a project whose whole argument is that a system should say what it
    knows and refuse rather than guess, so its own failure page should do the
    same thing: name the fault, say what was not done, and offer the way back.

    The exception type and message go on the page. That is a deliberate choice
    for a demonstration running against an invented firm with no customer data
    in it; a deployment holding real books would log this and show the visitor
    only that something failed.
    """
    detail = f"{type(failure).__name__}: {failure}"
    return HTMLResponse(
        broke(detail),
        status_code=500,
        headers={"Cache-Control": "no-store"},
    )


class Session:
    """One firm's books, kept between restarts when a store is configured.

    Still one firm and still not a tenancy: this is a demonstration surface and
    pretending otherwise would say something untrue about what exists. What it
    does now is survive the process. Set `ARCHON_STORE` to a path and the post is
    written down, so closing the laptop does not lose the month.

    Without it everything is in memory, which is what the tests and the public
    walkthrough want: a visitor pressing buttons should not be able to leave the
    next visitor somebody else's books.
    """

    def __init__(self, store_path: str | None = None) -> None:
        self.store_path = store_path if store_path is not None else os.environ.get("ARCHON_STORE")
        # Constructing must not destroy. An earlier version called reset() here,
        # which forgot the store before reopen() could read it, so starting the
        # process was indistinguishable from throwing the month away.
        self._fresh()

    def reset(self) -> None:
        """The visitor's start-again button, which is the only thing that forgets."""
        if self.store_path:
            forget(self.store_path)
        self._fresh()
        self._remember()

    def _fresh(self) -> None:
        self.books: Books = keep_the_books(the_post())
        self.outbox: Outbox = build_outbox(False, "books@archon.example")
        # The send ledger goes on disk whenever the books do. Without a store
        # everything is in memory anyway and a restart loses the books too, so
        # there is nothing for a durable send record to be consistent with.
        if self.store_path:
            from archon.store.sqlite import SendLog

            self.outbox.log = SendLog(self.store_path)
        self.receipt: Receipt | None = None
        self.last_refusal: str | None = None
        self.last_reading: Reading | None = None
        self.reading_error: str | None = None
        #: Which reader produced the last reading, so the page can say.
        self.read_by: str = "rules"
        # What actually produced the tone on screen. Until somebody asks for a
        # live run this is a constant, and the page says so rather than letting a
        # visitor assume six agents reasoned about their books.
        self.reasoning: Reasoning = Reasoning.scripted()

    def run_the_agents(self) -> None:
        """Run the real graph on Bedrock, or fail saying so.

        The screen used to return `SCRIPTED_REPLY`, a constant, and never built
        the graph at all: the six agents this project is about were exercised
        only by the command line. A judge pressing buttons saw none of it.

        There is no fallback. If Bedrock cannot be reached the page says that and
        keeps the scripted tone it already had, clearly labelled. Quietly serving
        a script while claiming a live run is the one thing this must not do.
        """
        from archon.agents.graph import build
        from archon.agents.views import from_graph_result

        try:
            graph = build(self.books, TODAY, QUARTER_FROM, TODAY, model=None)
            result = graph("Close the quarter and decide whether a chase is warranted.")
        except Exception as failure:  # noqa: BLE001 - reported, never swallowed
            self.reasoning = Reasoning.unreachable(f"{type(failure).__name__}: {failure}")
            return
        self.reasoning = Reasoning.live(
            reply=_composer_reply(result),
            views=tuple(from_graph_result(result)),
        )

    def draft(self) -> ChaseDraft | None:
        worst = self.books.worst_overdue(TODAY)
        if worst is None:
            return None
        opening, closing = two_lines(self.reasoning.reply)
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

    def _remember(self) -> None:
        """Write the post down. Cheap, and it means a crash costs nothing."""
        if self.store_path:
            save(self.books, self.store_path)

    def reopen(self) -> None:
        """Load what was written, or start fresh if nothing was.

        A store that will not open stops the process rather than starting with
        half a month, because half a month is the shape of a wrong figure in an
        email to a client.
        """
        if not self.store_path:
            return
        self.books = load(self.store_path) or self.books
        if not self.books.ledger.entries:
            self.books = keep_the_books(the_post())
            self._remember()

    def verdict(self, draft: ChaseDraft, now: datetime | None = None) -> Release:
        approval = Approval(
            fingerprint=draft.fingerprint(), approved_by="the owner", approved_at=NOW
        )
        return assess(self.books, draft, approval, TODAY, now=now or NOW)


session = Session()
session.reopen()


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
def home() -> HTMLResponse:
    """The page, and never a cached copy of it.

    Every figure here changes when a document arrives or a client pays, and the
    page is reached by redirect after each of those. A browser holding the
    previous copy shows a balance that was true a moment ago, which is precisely
    the failure this project spends its effort refusing everywhere else.
    """
    return HTMLResponse(
        _render_home(),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


def _render_home() -> str:
    return page(
        reasoning=session.reasoning,
        queue=build_queue(session.books, TODAY),
        books=session.books,
        stats=_stats(session.books),
        draft=session.draft(),
        verdict_for=session.verdict,
        receipt=session.receipt,
        refusal=session.last_refusal,
        views=captured(),
        captured_on=CAPTURED_ON,
        reading=session.last_reading,
        reading_error=session.reading_error,
        sample=SAMPLE_EMAIL,
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


#: The most an attachment or a pasted body may be. An invoice is a page; nothing
#: legitimate here is megabytes. The cap exists because the alternative is
#: reading whatever arrives into memory and finding out afterwards, and "afterwards"
#: for a large enough upload is after the process has died.
MAX_UPLOAD = 4 * 1024 * 1024
MAX_PASTED = 256 * 1024


SAMPLE_EMAIL = """From: accounts@wholesaler.example
Subject: Invoice WA-9001

Invoice WA-9001 dated 2026-09-02, due 2026-10-02.
Net 500.00 EUR, VAT 120.00 EUR, total 620.00 EUR.
Please pay to IBAN GR16 0110 1250 0000 0001 2300 695, VAT EL123456789.
Any queries call +30 210 1234567."""


@app.post("/post")
def post_an_email(body: str = Form(...), reader: str = Form("rules")) -> RedirectResponse:
    """Read a pasted email and put it in the books, or say why not.

    Which reader runs is chosen on the page and never guessed. `rules` is the
    offline extractor and `bedrock` is the real model; the page says which ran
    and neither stands in for the other. If a live read is asked for and cannot
    be done, that is reported. **It must never fall back to the rules and call
    the result a success**, because a screen that quietly downgrades is a screen
    that lies at the moment somebody is watching it.

    The redaction, the typed proposal and the ledger's arithmetic check are the
    same either way, because those are the parts that must not depend on which
    reader ran.
    """
    session.reading_error = None
    session.last_reading = None
    if len(body) > MAX_PASTED:
        session.reading_error = (
            f"That is longer than {MAX_PASTED // 1024} KB of text, which no email is. "
            "Nothing was read."
        )
        return RedirectResponse("/", status_code=303)
    try:
        reading = read_email(
            body,
            f"email:pasted-{len(session.books.ledger.entries)}",
            client=_reader_for(reader),
        )
        session.books.record(reading.document)
        session.last_reading = reading
        session.read_by = reader
        session._remember()
    except (UnreadablePost, ValueError) as refused:
        session.reading_error = str(refused)
        session.read_by = reader
    return RedirectResponse("/", status_code=303)


@app.post("/upload")
async def upload_an_invoice(attachment: UploadFile = File(...)) -> RedirectResponse:
    """Read an attached invoice. The file is opened here and stays here.

    The text is extracted on this machine, redacted on this machine, and only the
    redacted text is sent. Handing the PDF to Bedrock would read it perfectly well
    and would also hand over the IBAN printed on it.
    """
    session.reading_error = None
    session.last_reading = None

    # Read a bounded amount rather than everything and then measuring. One byte
    # over the cap is enough to know, and it is the only amount worth reading.
    data = await attachment.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        session.reading_error = (
            f"That file is larger than {MAX_UPLOAD // (1024 * 1024)} MB, which no invoice is. "
            "Nothing was read."
        )
        return RedirectResponse("/", status_code=303)

    try:
        reading = read_attachment(
            data,
            attachment.filename or "attachment",
            f"email:attached-{len(session.books.ledger.entries)}",
            client=LocalReader(),
        )
        session.books.record(reading.document)
        session.last_reading = reading
        session._remember()
    except (UnreadablePost, ValueError) as refused:
        session.reading_error = str(refused)
    return RedirectResponse("/", status_code=303)


def _reader_for(choice: str):
    """The client `read_email` should use, chosen rather than defaulted.

    `None` means the real Bedrock client. Returning `LocalReader()` for an
    unrecognised value would be a silent downgrade, so an unrecognised value is
    an error instead.
    """
    if choice == "bedrock":
        return None
    if choice == "rules":
        return LocalReader()
    raise ValueError(
        f"{choice!r} is not a reader. It is 'rules' for the offline extractor or "
        "'bedrock' for the model, and there is no third thing that quietly means one of them."
    )


@app.post("/reason")
def run_the_agents() -> RedirectResponse:
    """Ask the six agents, for real, on Bedrock.

    Deliberately a button rather than something the page does on load: the graph
    takes about thirteen seconds and costs money, and a screen that spent both on
    every refresh would be a screen nobody leaves open.
    """
    session.run_the_agents()
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
        session._remember()
    return RedirectResponse("/", status_code=303)
