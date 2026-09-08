"""A client says when they will pay. That is a promise, not a payment.

The one thing this area must never do is let an arrangement touch the ledger. A
client who could reduce their own debt by sending an email would make every
figure downstream wrong while it still looked right, so most of this file is
about what does **not** change.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from archon.agents.proposal import DISPUTED, NEEDS_A_PERSON, PROPOSED, Proposal, read_reply
from archon.demo import TODAY, keep_the_books, the_post
from archon.domain.arrangement import ArrangementRefused, Instalment, consider


@pytest.fixture
def books():
    return keep_the_books(the_post())


@pytest.fixture
def worst(books):
    return books.worst_overdue(TODAY)


def halves(worst):
    half = worst.outstanding / 2
    return (
        Instalment(date(2026, 9, 20), half),
        Instalment(date(2026, 10, 5), worst.outstanding - half),
    )


def agreed(books, worst):
    plan = consider(
        invoice_id=worst.doc_id,
        outstanding=worst.outstanding,
        instalments=halves(worst),
        as_of=TODAY,
    )
    books.agree(plan)
    return plan


# --- what an arrangement must never do ----------------------------------------


def test_agreeing_posts_no_journal_entry(books, worst):
    before = len(books.ledger.entries)
    agreed(books, worst)
    assert len(books.ledger.entries) == before
    assert books.ledger.trial_balance() == 0


def test_agreeing_does_not_reduce_what_is_owed(books, worst):
    owed = worst.outstanding
    agreed(books, worst)
    still = next(s for s in books.uncollected() if s.doc_id == worst.doc_id)
    assert still.outstanding == owed, "a promise moved the balance"


def test_an_arrangement_is_not_reachable_through_the_door_that_posts(books, worst):
    """`record` posts documents. An arrangement must not be one."""
    plan = consider(
        invoice_id=worst.doc_id,
        outstanding=worst.outstanding,
        instalments=halves(worst),
        as_of=TODAY,
    )
    with pytest.raises(TypeError, match="no posting rule for Arrangement"):
        books.record(plan)


# --- what it does change ------------------------------------------------------


def test_a_live_promise_holds_the_chase(books, worst):
    assert books.worst_overdue(TODAY) is not None
    agreed(books, worst)
    assert books.worst_overdue(TODAY) is None


def test_a_missed_instalment_makes_it_chaseable_again_for_the_whole_balance(books, worst):
    owed = worst.outstanding
    agreed(books, worst)
    again = books.worst_overdue(date(2026, 9, 21))
    assert again is not None
    assert again.outstanding == owed, "a broken promise chases the whole debt, not the instalment"


def test_a_promise_being_kept_keeps_holding_it(books, worst):
    """Paid on time means the arrangement is still good."""
    from archon.domain.documents import Receipt
    from archon.domain.money import money

    half = worst.outstanding / 2
    agreed(books, worst)
    books.record(Receipt("RC-PLAN", worst.doc_id, date(2026, 9, 20), money(half), "email:plan"))
    assert books.worst_overdue(date(2026, 9, 21)) is None


# --- what the books refuse ----------------------------------------------------


def test_instalments_that_do_not_add_up_are_refused(worst):
    with pytest.raises(ArrangementRefused, match="is less than"):
        consider(
            invoice_id=worst.doc_id,
            outstanding=worst.outstanding,
            instalments=(Instalment(date(2026, 9, 20), Decimal("500.00")),),
            as_of=TODAY,
        )


def test_the_refusal_says_a_person_has_to_decide(worst):
    with pytest.raises(ArrangementRefused) as caught:
        consider(
            invoice_id=worst.doc_id,
            outstanding=worst.outstanding,
            instalments=(Instalment(date(2026, 9, 20), Decimal("500.00")),),
            as_of=TODAY,
        )
    assert "A person has to decide" in str(caught.value)


def test_a_date_in_the_past_is_refused(worst):
    with pytest.raises(ArrangementRefused, match="already in the past"):
        consider(
            invoice_id=worst.doc_id,
            outstanding=worst.outstanding,
            instalments=(Instalment(date(2026, 1, 1), worst.outstanding),),
            as_of=TODAY,
        )


def test_an_instalment_of_nothing_is_refused(worst):
    with pytest.raises(ArrangementRefused, match="instalment of nothing"):
        consider(
            invoice_id=worst.doc_id,
            outstanding=worst.outstanding,
            instalments=(
                Instalment(date(2026, 9, 20), worst.outstanding),
                Instalment(date(2026, 10, 1), Decimal("0.00")),
            ),
            as_of=TODAY,
        )


def test_nothing_can_be_arranged_on_a_settled_invoice():
    with pytest.raises(ArrangementRefused, match="nothing outstanding"):
        consider(
            invoice_id="SI-999",
            outstanding=Decimal("0.00"),
            instalments=(Instalment(date(2026, 9, 20), Decimal("10.00")),),
            as_of=TODAY,
        )


# --- reading the reply, which decides structure and never acceptability -------


class Replying:
    def __init__(self, text: str) -> None:
        self.text = text
        self.shown: list[str] = []

    def converse(self, **kwargs):
        self.shown.append(kwargs["messages"][0]["content"][0]["text"])
        return {"output": {"message": {"content": [{"text": self.text}]}}}


def test_a_clear_proposal_becomes_dated_instalments():
    client = Replying(
        '{"outcome": "proposed", "instalments": ['
        '{"due": "2026-09-20", "amount": "1000.00"},'
        '{"due": "2026-10-05", "amount": "1000.00"}], "why": "two halves"}'
    )
    proposal = read_reply("I can pay half on the 20th and half on the 5th.", TODAY, client=client)
    assert proposal.outcome == PROPOSED
    assert not proposal.needs_a_person
    assert [i.amount for i in proposal.instalments] == [Decimal("1000.00")] * 2


def test_a_dispute_is_never_turned_into_a_proposal():
    client = Replying('{"outcome": "disputed", "instalments": [], "why": "cancelled, they say"}')
    proposal = read_reply("We never agreed to this work.", TODAY, client=client)
    assert proposal.outcome == DISPUTED
    assert proposal.needs_a_person
    assert proposal.instalments == ()


def test_something_vague_goes_to_a_person():
    client = Replying('{"outcome": "needs-a-person", "instalments": [], "why": "no date"}')
    assert read_reply("I will sort it soon.", TODAY, client=client).needs_a_person


def test_a_reply_that_will_not_parse_goes_to_a_person():
    assert read_reply("x", TODAY, client=Replying("not json at all")).needs_a_person


def test_proposed_with_nothing_usable_goes_to_a_person():
    """It said proposed and gave a date nobody can read."""
    client = Replying('{"outcome": "proposed", "instalments": [{"due": "soon", "amount": "10"}]}')
    assert read_reply("x", TODAY, client=client).outcome == NEEDS_A_PERSON


def test_an_unknown_outcome_goes_to_a_person():
    client = Replying('{"outcome": "write-it-off", "instalments": []}')
    assert read_reply("x", TODAY, client=client).outcome == NEEDS_A_PERSON


def test_the_reply_is_redacted_before_the_model_sees_it():
    client = Replying('{"outcome": "needs-a-person", "instalments": []}')
    read_reply(
        "Pay from IBAN GR16 0110 1250 0000 0001 2300 695, call +30 210 1234567.",
        TODAY,
        client=client,
    )
    shown = client.shown[0]
    assert "GR16 0110 1250 0000 0001 2300 695" not in shown
    assert "+30 210 1234567" not in shown


def test_the_model_is_told_it_may_not_decide_acceptability():
    client = Replying('{"outcome": "needs-a-person", "instalments": []}')
    read_reply("anything", TODAY, client=client)
    # The prompt is wrapped to a column, so read it the way the model does.
    ask = " ".join(client.shown[0].split())
    assert "Never invent a date or an amount" in ask
    assert "Never decide whether the proposal is acceptable" in ask
    assert "never penalised for choosing this" in ask


def test_a_proposal_still_has_to_pass_the_books():
    """The model's structure is not an agreement. The arithmetic is separate."""
    proposal = Proposal(
        outcome=PROPOSED,
        instalments=(Instalment(date(2026, 9, 20), Decimal("1.00")),),
    )
    with pytest.raises(ArrangementRefused):
        consider(
            invoice_id="SI-001",
            outstanding=Decimal("2000.00"),
            instalments=proposal.instalments,
            as_of=TODAY,
        )
