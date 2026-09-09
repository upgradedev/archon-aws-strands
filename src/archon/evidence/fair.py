"""Run every method over the same post and score it against the same answer.

    python -m archon.evidence.fair

The protocol is fixed here before any figure is quoted, which is the part the
two earlier comparisons got wrong:

* **the same raw inputs.** Every method receives `case.emails`, the strings, and
  nothing else. No method is handed books somebody else posted for it.
* **the same allowed context.** Every method may read every email in the case
  and may know today's date. None of them is told the answer or the shape.
* **a declared baseline.** `reference matching` is what small-business software
  actually does: match a payment to an invoice by its reference, and chase what
  is left. It is the thing to beat, and it is stated before the run rather than
  chosen afterwards.
* **the answers fixed first.** They came with the fixtures, written by authors
  who had not seen any of this code.
* **held-out cases.** Four are never used for a published figure.

Outcomes are counted apart because they cost differently, and both are always
shown. A method that never sends scores zero wrong money and is useless.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from archon.domain.money import ZERO

from .compare import wilson
from .independent import AS_OF, Case, held_out, scored

WRONG_MONEY = "wrong-money"
WRONG_RECIPIENT = "wrong-recipient"
MISSED = "missed"
CORRECT = "correct"
ASKED = "asked-a-person"


@dataclass(frozen=True, slots=True)
class Answer:
    """What a method decided. Empty invoice means it is sending nothing."""

    invoice: str = ""
    amount: Decimal = ZERO
    recipient: str = ""
    asked: bool = False

    @property
    def sends(self) -> bool:
        return bool(self.invoice) and self.amount > ZERO and not self.asked


def judge(case: Case, answer: Answer) -> str:
    """One of five outcomes, decided the same way for every method."""
    if answer.asked:
        # Asking is right when the case needs it and a missed chase otherwise.
        return CORRECT if case.needs_a_person else MISSED
    if not answer.sends:
        return MISSED if case.expects_a_chase else CORRECT
    if not case.expects_a_chase:
        return WRONG_MONEY
    if answer.amount != case.outstanding:
        return WRONG_MONEY
    if case.recipient and answer.recipient and answer.recipient != case.recipient:
        return WRONG_RECIPIENT
    return CORRECT


# --- the methods --------------------------------------------------------------


def archon(case: Case) -> Answer:
    """Read the post, keep books, decide from the books."""
    from archon.domain.queue import build as build_queue
    from archon.runtime import OFFLINE, read_the_post

    kept = read_the_post(list(case.emails), OFFLINE, prefix=case.name)
    if kept.refusals:
        # An email in this month could not be read, so the balance is not known.
        # Chasing from what did post is how this demanded 2,029.50 where
        # 1,429.50 was owed: it had the invoice and not the payment. Partial
        # books look exactly like complete ones.
        return Answer(asked=True)
    queue = build_queue(kept.books, AS_OF)
    top = queue.next_up
    if top is None:
        return Answer()
    return Answer(invoice=top.invoice_id, amount=top.outstanding, recipient=top.recipient)


_REFERENCE = re.compile(r"\b((?:INV|SI|PI|JN|RC)[-\s]?\d{2,8}|\d{4}-\d{4})\b", re.I)
_TOTAL = re.compile(r"\b(?:total|comes to|amounts? to)\b[^\d]{0,20}([\d.,]+\.\d{2})", re.I)
_PAID = re.compile(r"\b(?:paid|sent|transferred|put)\b[^\d]{0,30}([\d.,]+\.\d{2})", re.I)
_ADDRESS = re.compile(r"^From:\s*([^\s<>@]+@[^\s<>,;]+)", re.M)


def _money(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", ""))
    except Exception:  # noqa: BLE001 - any unparseable figure is simply not one
        return None


def reference_matching(case: Case) -> Answer:
    """The declared baseline: match payments to invoices by reference.

    This is what small-business accounting software does. It is not a straw man
    and it is not weakened on purpose: it reads the same emails, finds the
    invoice reference, takes the largest stated total as the invoice and every
    stated payment carrying the same reference as a payment against it.
    """
    totals: dict[str, Decimal] = {}
    payments: dict[str, Decimal] = {}
    address = ""

    for email in case.emails:
        references = {r.replace(" ", "").upper() for r in _REFERENCE.findall(email)}
        if not references:
            continue
        reference = sorted(references)[0]
        total = _TOTAL.search(email)
        paid = _PAID.search(email)
        if total and (amount := _money(total.group(1))) is not None:
            totals[reference] = max(totals.get(reference, ZERO), amount)
            found = _ADDRESS.search(email)
            if found:
                address = found.group(1)
        if paid and (amount := _money(paid.group(1))) is not None:
            payments[reference] = payments.get(reference, ZERO) + amount

    open_items = {
        reference: total - payments.get(reference, ZERO) for reference, total in totals.items()
    }
    owing = {r: a for r, a in open_items.items() if a > ZERO}
    if not owing:
        return Answer()
    reference = max(owing, key=lambda r: owing[r])
    return Answer(invoice=reference, amount=owing[reference], recipient=address)


def one_pass_reading(case: Case) -> Answer:
    """Read the text, take the first total, chase it. No ledger of any kind."""
    for email in case.emails:
        total = _TOTAL.search(email)
        reference = _REFERENCE.search(email)
        if total and reference and (amount := _money(total.group(1))) is not None:
            found = _ADDRESS.search(email)
            return Answer(
                invoice=reference.group(1).replace(" ", "").upper(),
                amount=amount,
                recipient=found.group(1) if found else "",
            )
    return Answer()


METHODS = {
    "reference matching (baseline)": reference_matching,
    "naive text extraction": one_pass_reading,
    "Archon": archon,
}


# --- scoring ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Tally:
    method: str
    n: int
    counts: dict


def score(method: str, run, cases: tuple[Case, ...]) -> Tally:
    counts = {WRONG_MONEY: 0, WRONG_RECIPIENT: 0, MISSED: 0, CORRECT: 0}
    for case in cases:
        try:
            answer = run(case)
        except Exception:  # noqa: BLE001 - a method that crashes has missed
            answer = Answer()
        counts[judge(case, answer)] += 1
    return Tally(method=method, n=len(cases), counts=counts)


def report(cases: tuple[Case, ...] | None = None, title: str = "independently written post") -> str:
    cases = cases if cases is not None else scored()
    rows = [score(name, run, cases) for name, run in METHODS.items()]
    header = (
        f"{'method':<32}{'wrong money':>13}{'wrong to':>10}{'missed':>9}"
        f"{'correct':>9}   95% CI, wrong money"
    )
    lines = [
        f"{len(cases)} cases of {title}. The emails and the answers were written",
        "by agents that had never seen this code. Same inputs, same context, same",
        "scoring, for every method.",
        "",
        header,
        "-" * len(header),
    ]
    for row in rows:
        # A zero without an interval reads as certainty, and twenty cases do not
        # earn certainty. Wilson because the textbook interval collapses to
        # zero-to-zero at the edge, which would publish a confidence nothing here
        # has bought.
        low, high = wilson(row.counts[WRONG_MONEY], row.n)
        lines.append(
            f"{row.method:<32}{row.counts[WRONG_MONEY]:>8} /{row.n:<3}"
            f"{row.counts[WRONG_RECIPIENT]:>10}{row.counts[MISSED]:>9}{row.counts[CORRECT]:>9}"
            f"   {low:.1%} to {high:.1%}"
        )
    lines += [
        "",
        "Wrong money is a demand for a figure that is not owed; it reaches a client and cannot be",
        "recalled. Wrong to is the right figure sent to the wrong address. A missed",
        "chase is silence",
        "where money was owed, which costs the firm without embarrassing it. All are",
        "shown, because a",
        "method that never sends scores zero on the first two and is useless.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    import sys

    print(report())
    if "--held-out" in sys.argv:
        print()
        print(report(held_out(), "held-out post, never used to tune anything"))
