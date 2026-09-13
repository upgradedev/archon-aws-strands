"""The graph, actually run.

Everything up to here proved wiring. This proves behaviour: the six domains are
consulted, the composer runs after them and not before, and none of it needs an
AWS account.

The guard stays because the SDK is a real dependency and a machine may not have
it, but it is not doing any skipping today: `strands-agents 1.53.0` is present
locally and 1.54.0 in CI, so these run in both places. Two versions passing is
better evidence than one.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip(
    "strands",
    reason="the graph needs the real SDK; a fake would only prove the fake behaves",
)

from archon.adapters.scripted import ScriptedModel  # noqa: E402
from archon.agents import wiring  # noqa: E402
from archon.agents.graph import build  # noqa: E402

TODAY = date(2026, 9, 3)
FRM = date(2026, 7, 1)


def _run(books):
    model = ScriptedModel(default="Reported.")
    graph = build(books, TODAY, FRM, TODAY, model=model)
    return model, graph("Close the month and decide whether a chase is warranted.")


def test_the_graph_completes_with_no_aws_account(books):
    _, result = _run(books)
    assert str(getattr(result, "status", "")).upper().endswith("COMPLETED"), result


def test_every_one_of_the_six_domains_was_consulted(books):
    _, result = _run(books)
    order = [str(node) for node in getattr(result, "execution_order", [])]
    joined = " ".join(order)
    for reader in wiring.READERS:
        assert reader.name in joined, f"{reader.name} never ran: {order}"


def test_the_composer_runs_last_not_first(books):
    """The failure this pins: under OR semantics it used to be able to run first."""
    _, result = _run(books)
    order = [str(node) for node in getattr(result, "execution_order", [])]
    positions = {
        reader.name: next(i for i, n in enumerate(order) if reader.name in n)
        for reader in wiring.READERS
    }
    composer_at = next(i for i, n in enumerate(order) if wiring.COMPOSER in n)
    assert composer_at > max(positions.values()), (
        f"the composer ran at {composer_at} before some reader finished: {order}"
    )


def test_the_model_saw_all_seven_agents(books):
    model, _ = _run(books)
    assert len(model.asks) >= len(wiring.READERS) + 1


def test_the_readers_were_given_their_own_duties(books):
    model, _ = _run(books)
    prompts = " ".join(model.prompts_seen)
    for reader in wiring.READERS:
        assert reader.duty in prompts, f"{reader.name} was not told what it reports on"
        assert reader.system_prompt in model.prompts_seen  # Default prompts stay byte-for-byte.


def test_the_composer_was_told_the_debt_and_the_no_numbers_rule(books):
    model, _ = _run(books)
    composer_prompts = [p for p in model.prompts_seen if "The debt in question" in p]
    assert composer_prompts, "the composer never received the deterministic candidate"
    brief = composer_prompts[0]
    assert "SI-001" in brief and "Cafe on the corner" in brief
    assert "never write a number" in brief
    assert "hold no tools" in brief


def test_a_clean_book_tells_the_composer_there_is_nothing_to_chase():
    from archon.domain.books import Books

    model = ScriptedModel(default="Nothing to do.")
    graph = build(Books(), TODAY, FRM, TODAY, model=model)
    graph("Close the month.")
    brief = next(p for p in model.prompts_seen if "The debt in question" in p)
    assert "no chase to write" in brief
