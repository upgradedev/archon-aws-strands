"""The whole journey, in one command.

    python -m archon.demo

Post arrives, the books are kept, six Strands agents read one domain each, a
chase is drafted from claims the ledger confirmed, the gate decides, a human
approves, the email leaves, and the receipt is read back.

**It runs offline by default and says so.** No AWS account, no key, no network:
the model answers from a script and the send goes to an outbox held in memory.
That is what lets anyone verify the numbers, and it is the mode this file assumes
unless told otherwise.

    python -m archon.demo --live-model     # reason on Bedrock
    python -m archon.demo --live-send      # send through SES, needs verified addresses

Each flag is reported in the header, because a scripted run that reads like an
agentic one is the discrepancy this project's own standard calls out.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime

from archon.adapters.scripted import ScriptedModel
from archon.adapters.ses import Outbox, SendRefused
from archon.agents import tools, wiring
from archon.agents.claims import (
    Claim,
    Outstanding,
    Overdue,
    PartPaid,
    StatutoryInterest,
    WagesDue,
)
from archon.agents.draft import ChaseDraft, UnsafeDraft
from archon.agents.gate import Approval, assess
from archon.agents.graph import build
from archon.domain.books import Books
from archon.domain.completeness import statutory_interest
from archon.domain.documents import (
    Payment,
    PayrollRun,
    PurchaseInvoice,
    Receipt,
    SalesInvoice,
)
from archon.domain.money import ZERO, fmt
from archon.domain.reports import cashflow, metrics, profit_and_loss

TODAY = date(2026, 9, 3)
QUARTER_FROM = date(2026, 7, 1)
NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)

DEMO_SENDER = "books@archon.example"

#: What the composer is asked to write when no model is reasoning. Two lines, no
#: digits, which is the same rule a live model is held to.
SCRIPTED_REPLY = (
    "Hello, I hope the summer has been kind to you.\n"
    "Could you let me know when this will be settled? Many thanks."
)


class _Rule:
    def __init__(self, title: str) -> None:
        self.title = title

    def __enter__(self):
        print(f"\n\033[1m{self.title}\033[0m")
        print("-" * max(len(self.title), 60))
        return self

    def __exit__(self, *exc):
        return False


def the_post() -> list[object]:
    """One quarter of a one-person electrical firm, as documents.

    Invented, and every name in it is invented. Nothing customer-owned travels
    into this repository, which the submission rules require and the README says.
    """
    return [
        PurchaseInvoice(
            doc_id="PI-001", supplier="Wholesaler A", issued=date(2026, 7, 4),
            due=date(2026, 8, 3), net="1000.00", vat="240.00", gross="1240.00",
            source_ref="email:001",
        ),
        PurchaseInvoice(
            doc_id="PI-002", supplier="Van Leasing B", issued=date(2026, 8, 1),
            due=date(2026, 9, 30), net="400.00", vat="96.00", gross="496.00",
            source_ref="email:002",
        ),
        Payment(
            doc_id="PAY-001", settles="PI-001", paid_on=date(2026, 8, 2),
            amount="1240.00", source_ref="email:003",
        ),
        SalesInvoice(
            doc_id="SI-001", client="Cafe on the corner",
            client_email="accounts@cafe.example", issued=date(2026, 6, 10),
            due=date(2026, 7, 10), net="2000.00", vat="480.00", gross="2480.00",
            source_ref="email:010",
        ),
        SalesInvoice(
            doc_id="SI-002", client="Letting agent", client_email="pay@letting.example",
            issued=date(2026, 7, 20), due=date(2026, 8, 19), net="800.00",
            vat="192.00", gross="992.00", source_ref="email:011",
        ),
        SalesInvoice(
            doc_id="SI-003", client="New build site", client_email="ap@newbuild.example",
            issued=date(2026, 8, 25), due=date(2026, 9, 24), net="1500.00",
            vat="360.00", gross="1860.00", source_ref="email:012",
        ),
        Receipt(
            doc_id="RC-001", settles="SI-002", received_on=date(2026, 8, 20),
            amount="992.00", source_ref="email:013",
        ),
        Receipt(
            doc_id="RC-002", settles="SI-001", received_on=date(2026, 8, 1),
            amount="480.00", source_ref="email:014",
        ),
        PayrollRun(
            doc_id="PR-2026-08", period="August 2026", run_on=date(2026, 8, 31),
            gross="1100.00", paid_on=None, source_ref="email:020",
        ),
    ]


def keep_the_books(post: list[object]) -> Books:
    books = Books()
    for document in post:
        books.record(document)
    return books


def two_lines(reply: str) -> tuple[str, str]:
    """Take the composer's opening and closing out of whatever it wrote."""
    lines = [line.strip() for line in reply.splitlines() if line.strip()]
    if len(lines) >= 2:
        return lines[0], lines[-1]
    if lines:
        return lines[0], "Could you let me know when this will be settled? Many thanks."
    raise UnsafeDraft("the composer wrote nothing to send")


def run(live_model: bool = False, live_send: bool = False, sender: str = DEMO_SENDER) -> int:
    print("\033[1mArchon: the back office that lives in an inbox\033[0m")
    print(
        f"  reasoning: {'Bedrock' if live_model else 'scripted, offline'}"
        f"   |   sending: {'SES' if live_send else 'in-memory outbox'}"
        f"   |   as at {TODAY}"
    )
    if not live_model:
        print(
            "  The scripted model walks the graph; it does not judge. Tone and the "
            "decision to chase\n  are a model's work. Run with --live-model for that."
        )

    post = the_post()
    with _Rule(f"1. The post. {len(post)} documents arrive"):
        for document in post:
            print(f"  {getattr(document, 'doc_id', '?'):<12} {type(document).__name__}")

    books = keep_the_books(post)
    with _Rule("2. The books, kept. Every entry names the email it came from"):
        print(f"  {len(books.ledger.entries)} journal entries")
        print(
            f"  trial balance {books.ledger.trial_balance()}"
            "  (anything but zero is a broken ledger)"
        )

    with _Rule("3. The six domains the owner asked about"):
        print(tools.supplier_position(books))
        print(tools.sales_position(books, TODAY))
        print(tools.payroll_position(books))
        print(tools.trading_position(books, QUARTER_FROM, TODAY))
        print(tools.cash_position(books, QUARTER_FROM, TODAY))
        print(tools.headline_metrics(books, TODAY))

    with _Rule("4. Six Strands agents, one per domain, feeding one composer"):
        model = None if live_model else ScriptedModel(default=SCRIPTED_REPLY)
        graph = build(books, TODAY, QUARTER_FROM, TODAY, model=model)
        result = graph("Close the quarter and decide whether a chase is warranted.")
        order = [
            getattr(node, "node_id", str(node))
            for node in getattr(result, "execution_order", [])
        ]
        print(f"  ran in order: {', '.join(order) or 'unavailable'}")
        print(
            f"  the composer holds no tools, and every edge into it is conditioned on all "
            f"{len(wiring.REQUIRED_REPORTS)} reports"
        )
        reply = _composer_reply(result)
        print(f"\n  the composer wrote:\n    {reply.strip().replace(chr(10), chr(10) + '    ')}")

    worst = books.worst_overdue(TODAY)
    if worst is None:
        print("\nNothing is overdue. There is no chase to write, and that is the right answer.")
        return 0

    with _Rule("5. The draft. Every figure comes from a claim, never from the model"):
        claims = _claims_for(books, worst)
        opening, closing = two_lines(reply)
        try:
            draft = ChaseDraft(
                invoice_id=worst.doc_id, client=worst.counterparty,
                to_address=worst.contact, subject="Our outstanding invoice",
                opening=opening, claims=claims, closing=closing, as_of=TODAY,
            )
        except UnsafeDraft as refused:
            print(f"  the composer's own text was refused: {refused}")
            print("  falling back to the scripted wording; the guard is the point")
            opening, closing = two_lines(SCRIPTED_REPLY)
            draft = ChaseDraft(
                invoice_id=worst.doc_id, client=worst.counterparty,
                to_address=worst.contact, subject="Our outstanding invoice",
                opening=opening, claims=claims, closing=closing, as_of=TODAY,
            )
        print(draft.wire())
        print(f"  fingerprint {draft.fingerprint()[:16]}...")

    with _Rule("6. The gate. Everything re-derived from the books at send time"):
        approval = Approval(
            fingerprint=draft.fingerprint(), approved_by="the owner", approved_at=NOW
        )
        release = assess(books, draft, approval, TODAY, now=NOW)
        print(f"  {release}")

        # Show the refusal rather than assert it. One word is edited after the
        # approval was given, which is the shape a helpful last-minute tweak has.
        tweaked = ChaseDraft(
            invoice_id=draft.invoice_id, client=draft.client, to_address=draft.to_address,
            subject=draft.subject, opening=draft.opening, claims=draft.claims,
            closing=draft.closing.replace("Many thanks", "Thanks"), as_of=draft.as_of,
        )
        after_edit = assess(books, tweaked, approval, TODAY, now=NOW)
        print(f"  one word edited after approval -> {after_edit}")

        # And the client pays at lunchtime, after the draft was written.
        moved = keep_the_books(the_post())
        moved.record(
            Receipt(
                doc_id="RC-late", settles=draft.invoice_id, received_on=TODAY,
                amount=str(worst.outstanding), source_ref="email:late",
            )
        )
        print(f"  the client pays at lunchtime -> {assess(moved, draft, approval, TODAY, now=NOW)}")

    with _Rule("7. The one write"):
        outbox = _outbox(live_send, sender)
        try:
            receipt = outbox.send(draft, release)
        except SendRefused as refused:
            print(f"  held: {refused}")
            return 1
        print(f"  sent to {receipt.to_address}, message id {receipt.message_id}")
        again = outbox.send(draft, release)
        print(f"  asked to send the same email again: replayed={again.replayed}, "
              f"same id={again.message_id == receipt.message_id}")
        print(f"  read back from the outbox: {outbox.receipt_for(draft).message_id}")

    print(
        "\n\033[1mThe month is closed and one email left, "
        "after one human approved that exact text.\033[0m"
    )
    return 0


def _composer_reply(result: object) -> str:
    """Pull the composer's text out of the graph result, whatever shape it is."""
    results = getattr(result, "results", {}) or {}
    for key, value in results.items():
        if wiring.COMPOSER in str(key):
            return str(getattr(value, "result", value))
    return SCRIPTED_REPLY


def _claims_for(books: Books, worst) -> tuple[Claim, ...]:
    claims: list[Claim] = [
        Outstanding(worst.doc_id, worst.outstanding),
        Overdue(worst.doc_id, worst.days_overdue(TODAY)),
    ]
    if worst.settled > ZERO:
        claims.append(PartPaid(worst.doc_id, worst.settled))
    # Money the owner is owed by law and almost never asks for, because working it
    # out means knowing the reference rate and the day count. Offered only when it
    # has actually accrued; the claim refuses itself inside the statutory window.
    interest = statutory_interest(worst.outstanding, worst.days_overdue(TODAY))
    if interest > ZERO:
        claims.append(StatutoryInterest(worst.doc_id, interest))
    owed_to_staff = metrics(books, TODAY).owed_to_staff
    if owed_to_staff > ZERO:
        claims.append(WagesDue(owed_to_staff))
    return tuple(claims)


def _outbox(live_send: bool, sender: str) -> Outbox:
    if live_send:  # pragma: no cover - needs verified SES identities
        import os

        from archon.adapters.ses import live_outbox
        from archon.store.sqlite import SendLog

        path = os.environ.get("ARCHON_SEND_LEDGER")
        return live_outbox(
            sender=sender,
            log=SendLog(path) if path else None,
            controlled_recipient=os.environ.get("ARCHON_VERIFIED_RECIPIENT"),
            authorized=os.environ.get("ARCHON_OPERATOR_SEND_AUTHORIZATION")
            == "I_AUTHORIZE_CONTROLLED_SEND",
        )

    class InMemorySes:
        def __init__(self) -> None:
            self.n = 0

        def send_email(self, **kwargs):
            self.n += 1
            return {"MessageId": f"offline-{self.n:04d}"}

    return Outbox(client=InMemorySes(), sender=sender, clock=lambda: NOW)


def summary(books: Books) -> str:
    """The three lines a video needs on screen at once."""
    pnl = profit_and_loss(books, QUARTER_FROM, TODAY)
    cash = cashflow(books, QUARTER_FROM, TODAY)
    m = metrics(books, TODAY)
    return (
        f"profit {fmt(pnl.profit)} | cash {fmt(cash.closing)} | "
        f"owed to us {fmt(m.owed_by_clients)} | overdue {fmt(m.overdue_amount)}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walk the whole Archon journey.")
    parser.add_argument("--live-model", action="store_true", help="reason on Bedrock")
    parser.add_argument("--live-send", action="store_true", help="send through SES")
    parser.add_argument("--sender", default=DEMO_SENDER, help="verified SES sender address")
    args = parser.parse_args(argv)
    return run(live_model=args.live_model, live_send=args.live_send, sender=args.sender)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

