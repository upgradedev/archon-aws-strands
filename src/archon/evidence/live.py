"""The baseline that is not ours: a real model reading the same post.

**Why this file exists, stated plainly because it is the weakness in the offline
comparison.** In `compare.py`, Archon's answer and the scenario's truth are
computed the same way, from the same postings. Archon is correct there by
construction, and a judge is right to discount it. What that table honestly
measures is whether a method's *data model* can represent the answer at all:
reference matching cannot represent a part payment, and one pass over the post
cannot see across messages.

This is the comparison that does not share our arithmetic. A real Claude model
on Bedrock is given exactly the post the firm received, with no ledger and no
tools, and asked what to chase. Its answer is scored against the same known
truth. It is a strong baseline: the same model Archon itself reasons with,
reading the same evidence, differing only in that nothing checks it.

Not part of the offline suite, because it costs money and needs credentials.
Run it, record the number and the date, and quote that.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from archon.adapters.bedrock import MODEL_ID, REGION
from archon.domain.money import ZERO, money

from .compare import Tally, judge, wilson
from .methods import Answer
from .scenarios import AS_OF, Scenario, all_scenarios

ASK = (
    "You are the back office of a one-person firm. Today is {today}.\n\n"
    "Below is every message the firm received about one client. Decide whether to "
    "chase an unpaid invoice, and if so, for exactly how much.\n\n"
    "{post}\n\n"
    'Answer with JSON only: {{"chase": true or false, "invoice": "SI-nnn" or null, '
    '"amount": "0.00"}}'
)


@dataclass(frozen=True, slots=True)
class LiveAnswer:
    """What the model said, and what it said it in."""

    answer: Answer
    raw: str


def _parse(raw: str) -> Answer:
    """Read the model's JSON, forgiving the wrapping but not the numbers."""
    block = re.search(r"\{.*\}", raw, re.S)
    if not block:
        return Answer(invoice=None, amount=ZERO, note="no JSON in the reply")
    try:
        data = json.loads(block.group(0))
    except json.JSONDecodeError:
        return Answer(invoice=None, amount=ZERO, note="unparseable JSON")
    if not data.get("chase"):
        return Answer(invoice=None, amount=ZERO, note="declined to chase")
    try:
        amount = money(Decimal(str(data.get("amount", "0")).replace(",", "")))
    except (InvalidOperation, TypeError):
        return Answer(invoice=None, amount=ZERO, note="unreadable amount")
    return Answer(invoice=data.get("invoice"), amount=amount)


def ask_model(scenario: Scenario, client=None, model_id: str = MODEL_ID) -> LiveAnswer:
    """One call, no tools, no ledger. Exactly the post and the question."""
    if client is None:  # pragma: no cover - needs credentials
        import boto3

        client = boto3.client("bedrock-runtime", region_name=REGION)

    prompt = ASK.format(today=AS_OF, post="\n\n---\n\n".join(scenario.post))
    response = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        # No temperature. Sampling parameters were removed on this model family
        # and Bedrock rejects them: "`temperature` is deprecated for this model".
        # Determinism here would have been comfortable; the baseline is honest without it.
        inferenceConfig={"maxTokens": 200},
    )
    raw = _text_of(response)
    return LiveAnswer(answer=_parse(raw), raw=raw)


def _text_of(response: dict) -> str:
    """Pull the answer out, whatever else came with it.

    Indexing content[0] was wrong: thinking is on by default on this model
    family, so the first block is reasoning and the reply is further down. A
    fixed index would have worked on a model without thinking and broken here.
    """
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    for block in blocks:
        if "text" in block:
            return block["text"]
    return ""


def run(client=None, scenarios: tuple[Scenario, ...] | None = None) -> tuple[Tally, list[str]]:
    """Score the live model and hand back every reply for inspection."""
    cases = scenarios or all_scenarios()
    counts = {"wrong-money": 0, "missed": 0, "refused": 0, "correct": 0}
    transcript: list[str] = []
    for case in cases:
        live = ask_model(case, client=client)
        verdict = judge(case, live.answer)
        counts[verdict] += 1
        transcript.append(
            f"{case.name}: truth={case.truth} said={live.answer.amount} "
            f"invoice={live.answer.invoice} -> {verdict}"
        )
    tally = Tally(
        method=f"one live model pass ({MODEL_ID})",
        n=len(cases),
        wrong_money=counts["wrong-money"],
        missed=counts["missed"],
        refused=counts["refused"],
        correct=counts["correct"],
    )
    return tally, transcript


if __name__ == "__main__":  # pragma: no cover
    import sys

    if "--hard" in sys.argv:
        from .hard import all_hard_scenarios

        tally, transcript = run(scenarios=all_hard_scenarios())
    else:
        tally, transcript = run()
    low, high = wilson(tally.wrong_money, tally.n)
    print("\n".join(transcript))
    print()
    print(
        f"{tally.method}: wrong money {tally.wrong_money}/{tally.n} "
        f"(95% CI {low:.1%} to {high:.1%}), missed {tally.missed}, correct {tally.correct}"
    )
