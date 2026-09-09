"""A benchmark whose inputs were written by somebody who had not seen the reader.

ALL-01 asks for the same raw inputs on both sides, a declared baseline, expected
answers fixed before the run, and held-out cases. The two earlier sets failed
that in different ways and both are withdrawn:

* the friendly and awkward sets were written by the same hand as the parser, and
  the emails were one-line summaries shaped like the thing that would read them;
* Archon's own column was scored from books the fixture had already posted
  correctly, while the method it was measured against started from raw text.

These emails were written by twenty-four independent agents, each told only the
business situation — an overdue invoice, a part payment, a dispute — and nothing
whatever about how anything here reads an email. They came back as real post:
line items, VAT at the local rate, IBANs, a note about a condenser fan that is
starting to rattle. Then each was audited by a different agent for realism and
for whether its stated answer follows from its own emails.

The truth travels with the fixture and was fixed before any method ran. It is
checked again here, deterministically, because an author's arithmetic is a claim
like any other.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

FIXTURES = pathlib.Path(__file__).resolve().parents[3] / "tests" / "fixtures"
SOURCE = FIXTURES / "independent_emails.json"

#: The day the fixtures were written for, so ageing is stable.
AS_OF = date(2026, 9, 9)

#: Fixtures held back from every published figure. They exist so that a change
#: made to move a number can be checked against cases it was not tuned on.
HELD_OUT = frozenset({"independent-04", "independent-11", "independent-18", "independent-23"})


@dataclass(frozen=True, slots=True)
class Case:
    """One month of somebody else's post, and the answer fixed before the run."""

    name: str
    shape: str
    emails: tuple[str, ...]
    chase_invoice: str
    outstanding: Decimal
    currency: str
    recipient: str
    needs_a_person: bool
    why: str

    @property
    def held_out(self) -> bool:
        return self.name in HELD_OUT

    @property
    def expects_a_chase(self) -> bool:
        return bool(self.chase_invoice) and self.outstanding > 0 and not self.needs_a_person


def _as_email(raw: dict) -> str:
    """Back into the shape a mail client would hand over."""
    return (
        f"From: {raw.get('from', '')}\n"
        f"To: {raw.get('to', '')}\n"
        f"Subject: {raw.get('subject', '')}\n\n"
        f"{raw.get('body', '')}"
    )


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def load() -> tuple[Case, ...]:
    """Read the fixtures, keeping only those whose own answer holds up.

    An author's arithmetic is a claim. A fixture whose outstanding amount will
    not parse, or which expects a chase with nowhere to send it, is dropped here
    rather than quietly scored, because a benchmark that cannot state its own
    answer cannot judge anybody else's.
    """
    if not SOURCE.exists():  # pragma: no cover - the file is committed
        return ()

    cases: list[Case] = []
    for raw in json.loads(SOURCE.read_text(encoding="utf-8")):
        truth = raw.get("truth", {})
        outstanding = _decimal(truth.get("amount_outstanding"))
        if outstanding is None:
            continue
        chase = str(truth.get("chase_invoice", "")).strip()
        recipient = str(truth.get("recipient", "")).strip()
        needs_person = bool(truth.get("should_stop_and_ask_a_person"))
        if chase and outstanding > 0 and not needs_person and "@" not in recipient:
            # It says to chase and does not say where. That is not an answer.
            continue
        cases.append(
            Case(
                name=str(raw.get("name", "")),
                shape=str(raw.get("shape", "")),
                emails=tuple(_as_email(e) for e in raw.get("emails", [])),
                chase_invoice=chase,
                outstanding=outstanding,
                currency=str(truth.get("currency", "EUR")),
                recipient=recipient,
                needs_a_person=needs_person,
                why=str(truth.get("why", ""))[:400],
            )
        )
    return tuple(cases)


def scored() -> tuple[Case, ...]:
    """The cases a published figure may be computed from."""
    return tuple(case for case in load() if not case.held_out)


def held_out() -> tuple[Case, ...]:
    """The cases kept back, reported separately and never tuned against."""
    return tuple(case for case in load() if case.held_out)
