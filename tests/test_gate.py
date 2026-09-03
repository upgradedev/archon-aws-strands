"""The gate is the product. These tests are the ones that matter most.

Each test below is a way the send could go wrong in front of a client, and the
assertion is that it does not happen.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from archon.agents.claims import (
    CashPosition,
    ClaimRefuted,
    Outstanding,
    Overdue,
    PartPaid,
    WagesDue,
)
from archon.agents.draft import ChaseDraft, UnsafeDraft
from archon.agents.gate import Approval, assess
from archon.domain.documents import Receipt

TODAY = date(2026, 9, 3)
NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)


def _draft(**overrides) -> ChaseDraft:
    base = dict(
        invoice_id="SI-001",
        client="Cafe on the corner",
        to_address="accounts@cafe.example",
        subject="Our outstanding invoice",
        opening="Hello, I hope the summer has been kind to you.",
        claims=(
            Outstanding("SI-001", Decimal("2000.00")),
            Overdue("SI-001", 55),
            PartPaid("SI-001", Decimal("480.00")),
        ),
        closing="Could you let me know when this will be settled? Many thanks.",
        as_of=TODAY,
    )
    base.update(overrides)
    return ChaseDraft(**base)


def _approved(draft: ChaseDraft) -> Approval:
    return Approval(fingerprint=draft.fingerprint(), approved_by="the owner", approved_at=NOW)


def test_a_correct_chase_is_released(books):
    draft = _draft()
    verdict = assess(books, draft, _approved(draft), TODAY)
    assert verdict.allowed, verdict.reasons


def test_the_body_carries_only_figures_the_ledger_confirmed(books):
    body = _draft().body()
    assert "2,000.00 EUR" in body
    assert "480.00 EUR" in body
    assert "55 days" in body


# --- the ways it could go wrong in front of a client ------------------------


def test_free_text_may_not_contain_a_number():
    # An agent that writes "you owe us about 2000" has bypassed every check.
    with pytest.raises(UnsafeDraft, match="contains a digit"):
        _draft(closing="Please settle the 2000 within 7 days.")


def test_a_chase_that_states_nothing_is_refused():
    with pytest.raises(UnsafeDraft, match="states no verified fact"):
        _draft(claims=())


def test_a_wrong_amount_is_caught_even_though_it_looks_plausible(books):
    # 2,480 is the invoice total. It is the wrong number: 480 was received.
    draft = _draft(claims=(Outstanding("SI-001", Decimal("2480.00")),))
    verdict = assess(books, draft, _approved(draft), TODAY)
    assert not verdict.allowed
    assert any("outstanding 2000.00" in r for r in verdict.reasons)


def test_a_wrong_day_count_is_caught(books):
    draft = _draft(claims=(Outstanding("SI-001", Decimal("2000.00")), Overdue("SI-001", 30)))
    verdict = assess(books, draft, _approved(draft), TODAY)
    assert not verdict.allowed
    assert any("55 days overdue" in r for r in verdict.reasons)


def test_a_client_who_paid_at_lunchtime_is_not_chased(books):
    # The draft was correct when written. The gate re-asks the books at send
    # time, which is the only way to know it stopped being correct.
    draft = _draft()
    approval = _approved(draft)
    books.record(
        Receipt(
            doc_id="RC-003",
            settles="SI-001",
            received_on=TODAY,
            amount="2000.00",
            source_ref="email:late",
        )
    )
    verdict = assess(books, draft, approval, TODAY)
    assert not verdict.allowed
    assert any("settled since the draft was written" in r for r in verdict.reasons)


def test_an_invoice_not_yet_due_is_not_chased(books):
    draft = _draft(
        invoice_id="SI-003",
        client="New build site",
        claims=(Outstanding("SI-003", Decimal("1860.00")),),
    )
    verdict = assess(books, draft, _approved(draft), TODAY)
    assert not verdict.allowed
    assert any("not overdue" in r for r in verdict.reasons)


def test_the_email_cannot_be_addressed_to_the_wrong_client(books):
    draft = _draft(client="Letting agent")
    verdict = assess(books, draft, _approved(draft), TODAY)
    assert not verdict.allowed
    assert any("belongs to Cafe on the corner" in r for r in verdict.reasons)


def test_a_plea_about_wages_must_itself_be_true(books):
    # Pleading unpaid wages is persuasive, so it is exactly the sentence an
    # agent would invent. It has to be checked like any other figure.
    good = _draft(claims=(Outstanding("SI-001", Decimal("2000.00")), WagesDue(Decimal("1100.00"))))
    assert assess(books, good, _approved(good), TODAY).allowed

    invented = _draft(
        claims=(Outstanding("SI-001", Decimal("2000.00")), WagesDue(Decimal("5000.00")))
    )
    verdict = assess(books, invented, _approved(invented), TODAY)
    assert not verdict.allowed
    assert any("wages outstanding are 1100.00" in r for r in verdict.reasons)


def test_a_cash_position_claim_is_checked_against_the_bank(books):
    wrong = _draft(
        claims=(Outstanding("SI-001", Decimal("2000.00")), CashPosition(Decimal("50.00"), TODAY))
    )
    verdict = assess(books, wrong, _approved(wrong), TODAY)
    assert not verdict.allowed
    assert any("the bank stands at 232.00" in r for r in verdict.reasons)


# --- the approval is bound to the bytes -------------------------------------


def test_one_edited_character_invalidates_the_approval(books):
    read_by_human = _draft()
    approval = _approved(read_by_human)
    edited = _draft(closing="Could you let me know when this will be settled? Thanks.")
    verdict = assess(books, edited, approval, TODAY)
    assert not verdict.allowed
    assert any("approved different bytes" in r for r in verdict.reasons)


def test_an_approval_needs_a_named_human():
    draft = _draft()
    with pytest.raises(ValueError, match="no approver"):
        Approval(fingerprint=draft.fingerprint(), approved_by="  ", approved_at=NOW)


def test_a_fingerprint_that_is_not_a_hash_is_refused():
    with pytest.raises(ValueError, match="not a sha-256"):
        Approval(fingerprint="yes", approved_by="the owner", approved_at=NOW)


def test_every_reason_is_reported_not_just_the_first(books):
    draft = _draft(client="Letting agent", claims=(Outstanding("SI-001", Decimal("1.00")),))
    verdict = assess(books, draft, _approved(draft), TODAY)
    assert not verdict.allowed
    assert len(verdict.reasons) >= 2


def test_a_claim_can_be_asked_without_raising(books):
    assert Outstanding("SI-001", Decimal("2000.00")).holds(books, TODAY)
    assert not Outstanding("SI-001", Decimal("1.00")).holds(books, TODAY)


def test_a_claim_about_an_unknown_invoice_is_refuted(books):
    with pytest.raises(ClaimRefuted, match="not a sales invoice"):
        Outstanding("SI-999", Decimal("1.00")).check(books, TODAY)
