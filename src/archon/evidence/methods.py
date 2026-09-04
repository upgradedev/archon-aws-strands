"""Three ways to decide what to chase, scored against the same known answers.

The two baselines are not straw men. Reference matching is how small-business
software actually reconciles, and a single pass over the inbox is what an agent
built in an afternoon does. Both are given exactly the same post Archon gets,
and both are allowed to be right.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from archon.agents.claims import ClaimRefuted, Outstanding
from archon.domain.money import ZERO, money

from .scenarios import AS_OF, Scenario


@dataclass(frozen=True, slots=True)
class Answer:
    """What a method decided to do about one month."""

    invoice: str | None
    amount: Decimal
    refused: bool = False
    note: str = ""

    @property
    def sends(self) -> bool:
        return self.invoice is not None and not self.refused


def reference_matching(scenario: Scenario) -> Answer:
    """Bank-feed style: a receipt naming an invoice closes it.

    The failure is not carelessness, it is the data model. A credit that names an
    invoice looks like settlement, and nothing in the feed says how much of the
    invoice it settled.
    """
    for inv in scenario.books.sales:
        if any(r.settles == inv.doc_id for r in scenario.books.receipts):
            continue
        if inv.due < AS_OF:
            return Answer(invoice=inv.doc_id, amount=inv.gross)
    return Answer(invoice=None, amount=ZERO, note="every invoice looks settled")


_AMOUNT = re.compile(r"(\d[\d,]*\.\d{2})")


def one_pass_reading(scenario: Scenario) -> Answer:
    """Pull the total off the invoice message and chase that.

    **This is not a model and it must never be labelled as one.** It was written
    as a stand-in for "what one pass over the post concludes", and then the live
    run on 2026-09-04 showed a real Claude model scoring 0 wrong money over the
    same twenty months. Reporting this regex under that name would have been a
    straw man wearing a strong baseline's label.

    It stays because it is still a real method: it is what naive extraction does,
    and it shows what happens when the balance is in no single message. It is
    named for what it is.
    """
    invoice_line = scenario.post[0]
    found = _AMOUNT.findall(invoice_line)
    if not found:
        return Answer(invoice=None, amount=ZERO, note="no total found")
    try:
        total = money(Decimal(found[-1].replace(",", "")))
    except InvalidOperation:
        return Answer(invoice=None, amount=ZERO, note="unreadable total")
    doc = re.search(r"(SI-\d+)", invoice_line)
    return Answer(invoice=doc.group(1) if doc else None, amount=total)


def archon(scenario: Scenario) -> Answer:
    """Pick deterministically, then let the claim be checked.

    The Outstanding claim is built and verified exactly as the gate verifies it
    before a send, so a claim the books refute becomes a refusal here too. That
    is reported as a refusal rather than as a silent pass, because refusing is a
    real cost and hiding it would flatter this column.
    """
    worst = scenario.books.worst_overdue(AS_OF)
    if worst is None:
        return Answer(invoice=None, amount=ZERO, note="nothing overdue")
    claim = Outstanding(worst.doc_id, worst.outstanding)
    try:
        claim.check(scenario.books, AS_OF)
    except ClaimRefuted as refuted:
        return Answer(invoice=worst.doc_id, amount=ZERO, refused=True, note=str(refuted))
    return Answer(invoice=worst.doc_id, amount=worst.outstanding)


METHODS = {
    "reference matching": reference_matching,
    "naive text extraction": one_pass_reading,
    "Archon": archon,
}
