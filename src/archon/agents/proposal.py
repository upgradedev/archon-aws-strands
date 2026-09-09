"""Reading what a client proposed, without letting them decide what it means.

A client replies to a chase and says something like "I can do five hundred on
Friday and the rest at the end of the month." Turning that sentence into two
dated amounts is the kind of work a model is genuinely good at and a regular
expression is not.

Everything after that is arithmetic and belongs to `domain.arrangement`. The
split matters: a client who could talk the model into a smaller total would have
talked it into a smaller debt. So the model is asked for **structure only** —
dates and figures it can see in the text — and the books decide whether that
structure is acceptable.

Three answers send it to a person instead, and they are the answers a system
like this most wants to fudge:

* **the proposal is ambiguous.** "Next month sometime" is not a date.
* **the client disputes the debt.** That is not a payment proposal at all, and
  no amount of parsing makes it one.
* **the proposal does not add up.** Handled by the books, not here.

None of those is guessed at. A guess about when somebody will pay is a guess
that ends in a chase nobody expected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from archon.adapters.bedrock import MODEL_ID, REGION
from archon.domain.arrangement import Instalment
from archon.security.sanitizer import sanitize_payload

NEEDS_A_PERSON = "needs-a-person"
DISPUTED = "disputed"
PROPOSED = "proposed"

ASK = """A client owes an invoice and has replied to a request for payment. Read
their reply and report only its structure.

Return one JSON object and nothing else:

{{"outcome": "proposed" | "disputed" | "needs-a-person",
  "instalments": [{{"due": "YYYY-MM-DD", "amount": "0.00"}}],
  "why": "one short sentence"}}

Rules you do not get to relax:

- "proposed" only when every instalment has a date you can read off the text and
  an amount you can read off the text. Today is {today}, so "Friday" and "the
  end of the month" are datable; "soon", "next month sometime" and "when I can"
  are not.
- "disputed" when they are arguing about whether the money is owed, about the
  amount, or about the work. That is not a payment proposal and must not be
  turned into one.
- "needs-a-person" for anything else, including anything you are unsure about.
  You are never penalised for choosing this.
- Never invent a date or an amount. Never total anything up. Never decide whether
  the proposal is acceptable; somebody else checks the arithmetic.

The reply:

{body}
"""


@dataclass(frozen=True, slots=True)
class Proposal:
    """What the client's reply turned out to be."""

    outcome: str
    instalments: tuple[Instalment, ...] = ()
    why: str = ""
    redactions: int = 0

    @property
    def needs_a_person(self) -> bool:
        return self.outcome != PROPOSED


def _instalments(raw: object) -> tuple[Instalment, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[Instalment] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            out.append(
                Instalment(
                    due=date.fromisoformat(str(item["due"])),
                    amount=Decimal(str(item["amount"])),
                )
            )
        except (KeyError, ValueError, InvalidOperation):
            # A row the model wrote that will not parse is not a row to guess at.
            # One unreadable instalment sends the whole reply to a person.
            return ()
    return tuple(out)


def read_reply(
    raw: str,
    today: date,
    client=None,
    model_id: str = MODEL_ID,
) -> Proposal:
    """Read a client's reply. Redacted first, like everything else."""
    if client is None:  # pragma: no cover - needs credentials
        import boto3

        client = boto3.client("bedrock-runtime", region_name=REGION)

    safe = sanitize_payload(raw)
    response = client.converse(
        modelId=model_id,
        messages=[
            {
                "role": "user",
                "content": [{"text": ASK.format(today=today, body=safe.sanitized_text)}],
            }
        ],
        # Enough room to answer. At 400 a reasoning model spends the budget
        # before it reaches the JSON, comes back empty with stopReason
        # max_tokens, and the caller reports that the reply carried no JSON.
        # Every live read of a realistic invoice email failed that way on
        # 2026-09-09, and it read as a model that could not do the job rather
        # than one that was cut off mid-sentence.
        inferenceConfig={"maxTokens": 4000},
    )
    text = "".join(
        block.get("text", "")
        for block in response["output"]["message"]["content"]
        if "text" in block
    )

    try:
        start, end = text.index("{"), text.rindex("}") + 1
        parsed = json.loads(text[start:end])
    except (ValueError, KeyError):
        return Proposal(
            outcome=NEEDS_A_PERSON,
            why="the reply could not be read as a proposal",
            redactions=safe.redactions_count,
        )

    outcome = str(parsed.get("outcome", NEEDS_A_PERSON))
    if outcome not in {PROPOSED, DISPUTED, NEEDS_A_PERSON}:
        outcome = NEEDS_A_PERSON

    instalments = _instalments(parsed.get("instalments")) if outcome == PROPOSED else ()
    if outcome == PROPOSED and not instalments:
        # It said "proposed" and gave nothing usable. That is a person's problem.
        outcome = NEEDS_A_PERSON

    return Proposal(
        outcome=outcome,
        instalments=instalments,
        why=str(parsed.get("why", ""))[:200],
        redactions=safe.redactions_count,
    )
