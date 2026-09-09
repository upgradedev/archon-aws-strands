"""A month of a small firm's post, generated so the answer is known.

Every scenario carries its own truth: what is genuinely owed on the invoice a
chase would be about, computed from how the scenario was constructed rather than
from any method under test. That is what makes this a comparison and not a
demonstration.

The traps are not invented for effect. Each is a shape that arrives in a real
inbox and that at least one obvious method reads wrongly:

* a part payment, which bank-style matching closes as settled
* several part payments, where the arithmetic is easy and the reading is not
* an invoice paid in full, where the right answer is to say nothing
* an invoice not yet due, where chasing costs a client
* nothing owed at all, where the right answer is again to say nothing

Deterministic by construction. No randomness, so the number is reproducible and
a judge re-running this gets the figure the README claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from archon.domain.books import Books
from archon.domain.documents import Receipt, SalesInvoice
from archon.domain.money import ZERO, money

AS_OF = date(2026, 9, 3)


@dataclass(frozen=True, slots=True)
class Scenario:
    """One month of post, and the answer it is hiding."""

    name: str
    trap: str
    books: Books
    #: The invoice a correct method chases, or None when the right answer is silence.
    chase_invoice: str | None
    #: What is genuinely outstanding on it. ZERO when nothing should be chased.
    truth: Decimal
    #: Every document as it arrived, for the methods that read post rather than books.
    post: tuple[str, ...]


def _invoice(n: int, gross: Decimal, days_ago: int, due_in: int = 30) -> SalesInvoice:
    net = money(gross / Decimal("1.24"))
    vat = money(gross - net)
    issued = AS_OF - timedelta(days=days_ago)
    return SalesInvoice(
        doc_id=f"SI-{n:03d}",
        client=f"Client {n}",
        client_email=f"accounts@client{n}.example",
        issued=issued,
        due=issued + timedelta(days=due_in),
        net=net,
        vat=vat,
        gross=money(gross),
        source_ref=f"email:inv-{n}",
    )


def _describe(inv: SalesInvoice) -> str:
    return (
        f"From: {inv.client_email}\n"
        f"Subject: Invoice {inv.doc_id}\n\n"
        f"Invoice {inv.doc_id} issued {inv.issued} to {inv.client}, due {inv.due}. "
        f"Net {inv.net}, VAT {inv.vat}, total due {inv.gross} EUR."
    )


def _remittance(inv: SalesInvoice, amount: Decimal, when: date) -> str:
    return (
        f"From: {inv.client_email}\n"
        f"Subject: Remittance advice\n\n"
        f"We have paid {money(amount)} EUR on {when} against invoice {inv.doc_id}."
    )


def _build(
    name: str, trap: str, invoice: SalesInvoice, payments: list[tuple[Decimal, int]]
) -> Scenario:
    books = Books()
    books.record(invoice)
    post = [_describe(invoice)]
    settled = ZERO
    for i, (amount, days_ago) in enumerate(payments, start=1):
        when = AS_OF - timedelta(days=days_ago)
        books.record(
            Receipt(
                doc_id=f"{invoice.doc_id}-RC{i}",
                settles=invoice.doc_id,
                received_on=when,
                amount=money(amount),
                source_ref=f"email:rc-{invoice.doc_id}-{i}",
                # A distinct event in this constructed ledger, not an inferred email identity.
                transfer_id=f"SYNTHETIC-EVENT-{invoice.doc_id}-{i}",
            )
        )
        post.append(_remittance(invoice, money(amount), when))
        settled += money(amount)

    outstanding = money(invoice.gross - settled)
    overdue = invoice.due < AS_OF
    chase = invoice.doc_id if (outstanding > ZERO and overdue) else None
    return Scenario(
        name=name,
        trap=trap,
        books=books,
        chase_invoice=chase,
        truth=outstanding if chase else ZERO,
        post=tuple(post),
    )


def all_scenarios() -> tuple[Scenario, ...]:
    """Twenty months of post. Fixed, so the published number can be re-derived."""
    cases: list[Scenario] = []

    # 1-8: a single part payment. Bank-style matching closes these as settled.
    for i, (gross, paid) in enumerate(
        [
            ("2480.00", "480.00"),
            ("1200.00", "200.00"),
            ("960.00", "860.00"),
            ("3100.00", "1550.00"),
            ("744.00", "24.00"),
            ("5000.00", "4999.00"),
            ("620.00", "310.00"),
            ("1860.00", "1000.00"),
        ],
        start=1,
    ):
        cases.append(
            _build(
                f"part-paid-{i}",
                "one part payment, which reference matching reads as settled",
                _invoice(i, Decimal(gross), days_ago=80),
                [(Decimal(paid), 40)],
            )
        )

    # 9-13: several part payments. The arithmetic is easy; the reading is not.
    for i, (gross, parts) in enumerate(
        [
            ("2480.00", ["480.00", "500.00"]),
            ("1240.00", ["100.00", "100.00", "100.00"]),
            ("3720.00", ["1000.00", "1000.00", "1000.00"]),
            ("930.00", ["310.00", "310.00"]),
            ("1500.00", ["250.00", "125.00", "125.00"]),
        ],
        start=9,
    ):
        cases.append(
            _build(
                f"instalments-{i}",
                "several part payments, so the balance is in no single message",
                _invoice(i, Decimal(gross), days_ago=90),
                [(Decimal(p), 60 - n * 5) for n, p in enumerate(parts)],
            )
        )

    # 14-17: settled in full. The right answer is to say nothing at all.
    for i, gross in enumerate(["1240.00", "620.00", "2480.00", "310.00"], start=14):
        cases.append(
            _build(
                f"settled-{i}",
                "paid in full, where any chase at all is the error",
                _invoice(i, Decimal(gross), days_ago=70),
                [(Decimal(gross), 30)],
            )
        )

    # 18-19: not yet due. Chasing early costs a client.
    for i, gross in enumerate(["1860.00", "744.00"], start=18):
        cases.append(
            _build(
                f"not-due-{i}",
                "issued recently and not yet due, where chasing costs a client",
                _invoice(i, Decimal(gross), days_ago=5),
                [],
            )
        )

    # 20: overdue and untouched. The easy case every method should get right.
    cases.append(
        _build(
            "plain-overdue-20",
            "overdue with no payment against it, the case nothing should miss",
            _invoice(20, Decimal("1240.00"), days_ago=75),
            [],
        )
    )
    return tuple(cases)
