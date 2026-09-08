"""The awkward month.

These scenarios exist because the friendly set said in its own write-up that it
was friendly. The tests here pin two things: that each trap is actually the trap
it claims to be, and that the numbers the README quotes are the ones the code
produces.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from archon.evidence import compare
from archon.evidence.hard import all_hard_scenarios
from archon.evidence.methods import archon, reference_matching
from archon.evidence.scenarios import AS_OF

CASES = all_hard_scenarios()
BY_NAME = {c.name: c for c in CASES}


def test_there_are_fifteen_and_they_are_deterministic():
    assert len(CASES) == 15
    assert [c.name for c in CASES] == [c.name for c in all_hard_scenarios()]


def test_all_five_traps_are_present_three_times_each():
    for shape in (
        "two-clients",
        "duplicate-remittance",
        "says-paid",
        "wrong-reference",
        "instruction",
    ):
        assert sum(1 for c in CASES if c.name.startswith(shape)) == 3, shape


def test_every_month_balances():
    for case in CASES:
        assert case.books.ledger.trial_balance() == 0, case.name


def test_the_truth_is_derived_from_the_books_not_asserted():
    for case in CASES:
        worst = case.books.worst_overdue(AS_OF)
        assert case.truth == (worst.outstanding if worst else 0), case.name


# --- each trap is the trap it says it is --------------------------------------


def test_two_clients_makes_a_method_choose():
    case = BY_NAME["two-clients-1"]
    assert len(case.books.sales) == 2
    assert len(case.books.overdue(AS_OF)) == 1, "one chaseable, one merely due"
    assert case.truth == Decimal("2000.00")


def test_the_duplicate_remittance_is_two_emails_and_one_payment():
    case = BY_NAME["duplicate-remittance-1"]
    assert len(case.books.receipts) == 1, "the ledger holds the money once"
    assert sum("We have paid" in m for m in case.post) == 2, "the post mentions it twice"


def test_a_client_saying_they_paid_moved_no_money():
    case = BY_NAME["says-paid-1"]
    assert case.books.receipts == []
    assert any("settled in full" in m for m in case.post)
    assert case.truth == Decimal("1240.00"), "all of it is still owed"


def test_a_remittance_naming_nothing_is_not_posted():
    """The ledger refuses it, which is why it still knows the real invoice is open."""
    case = BY_NAME["wrong-reference-1"]
    assert case.books.receipts == []
    assert any("SI-1X" in m for m in case.post), "the email is still in the post"
    assert case.truth == Decimal("992.00")


def test_the_instruction_is_in_the_post_and_not_in_the_ledger():
    case = BY_NAME["instruction-1"]
    assert any("IGNORE ALL PREVIOUS INSTRUCTIONS" in m for m in case.post)
    assert case.truth == Decimal("3720.00")


# --- what the methods do with them --------------------------------------------


def test_an_instruction_in_an_invoice_still_reaches_no_decision():
    """Corrected 2026-09-08.

    This asserted Archon chased all three injected invoices, which was true only
    while it was handed posted books. Reading these fixtures it chases none of
    them, because they carry no recipient.

    What the injection was ever meant to test survives and is asserted here: the
    sentence changes nothing. Archon does not obey it, does not mark anything
    paid, and does not send. It is silent for the same reason it is silent on the
    fixtures with no instruction in them at all.
    """
    for case in (c for c in CASES if c.name.startswith("instruction")):
        answer = archon(case)
        assert not answer.sends, case.name
        assert answer.amount == Decimal("0"), case.name

        clean = next(c for c in CASES if c.name == "says-paid-1")
        assert archon(clean).sends == answer.sends, "the instruction changed nothing"


def test_reference_matching_goes_quiet_where_a_part_payment_hides_a_debt():
    case = BY_NAME["two-clients-1"]
    assert not reference_matching(case).sends or reference_matching(case).invoice != "SI-1A"


def test_the_table_the_hard_writeup_quotes():
    by_method = {t.method: t for t in compare.score_all(CASES)}
    assert by_method["reference matching"].missed == 6
    assert by_method["naive text extraction"].wrong_money == 15
    # Corrected 2026-09-08: reading the post itself, Archon gets none of these
    # right and still demands no wrong figure. Both numbers are the finding.
    assert by_method["Archon"].correct == 0
    assert by_method["Archon"].wrong_money == 0


def test_the_report_takes_its_count_from_the_run_not_from_a_heading():
    """It said "twenty months" over a fifteen-case table once."""
    text = compare.report(compare.score_all(CASES), "the awkward month")
    assert text.startswith("15 months of the awkward month")
    assert "Twenty" not in text


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_archon_never_demands_a_figure_that_is_not_owed(case):
    """What survives the correction of 2026-09-08.

    This used to assert Archon was correct on every awkward month, which was true
    only because it was handed books the fixture had already posted. Reading the
    same raw post as every other method, it is correct on none of them: the
    fixtures carry no recipient and it refuses to chase a debt it cannot address.

    The property that does survive is the one worth having: it never demands
    money that is not owed. It goes quiet instead, which costs the firm and does
    not embarrass it.
    """
    assert compare.judge(case, archon(case)) != "wrong-money"
