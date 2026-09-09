"""The description and the script are claims too, so they are tested like claims.

The submission standard this project works to has one row about the README, the
code, the video and the description all agreeing. Two of those four are prose a
person will paste into a form and read aloud on camera, which makes them the two
most likely to drift and the two nobody re-checks. They are checked here.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DESCRIPTION = (ROOT / "docs" / "SUBMISSION-DESCRIPTION.md").read_text(encoding="utf-8")
SCRIPT = (ROOT / "docs" / "VIDEO-SCRIPT.md").read_text(encoding="utf-8")


def said(text: str) -> str:
    """The prose as a person reads it, not as the file wraps it.

    Both of these are written to a column width, so a sentence a reader takes in
    at a glance is split across two lines in the bytes. Asserting on the bytes
    fails for the wrong reason, which it did twice here before this existed.

    The blockquote markers go too. A script is read aloud, and a ">" that lands
    mid-sentence when the lines are joined is markup, not speech.
    """
    spoken = re.sub(r"^\s*>\s?", " ", text, flags=re.M)
    return " ".join(spoken.split()).lower()


# --- the figures ---------------------------------------------------------------


def test_the_description_quotes_the_fair_table_and_the_cost_with_it():
    """It carried both withdrawn tables until 2026-09-09."""
    from archon.evidence.fair import METHODS, score
    from archon.evidence.independent import scored

    rows = {name: score(name, run, scored()).counts for name, run in METHODS.items()}
    assert rows["reference matching (baseline)"]["wrong-money"] == 10
    assert rows["Archon"]["wrong-money"] == 0

    assert "| 10 / 20 | 10 | **0** |" in DESCRIPTION
    assert "| **0 / 20** | **0** | **0** |" in DESCRIPTION
    said = said_plain(DESCRIPTION)
    assert "archon sends nothing at all" in said
    assert "safe and not yet useful" in said


def said_plain(text: str) -> str:
    return " ".join(text.split()).lower()


def test_the_statutory_interest_figure_is_the_one_the_ledger_produces():
    from decimal import Decimal

    from archon.demo import TODAY, keep_the_books, the_post
    from archon.domain.completeness import statutory_interest

    books = keep_the_books(the_post())
    worst = books.worst_overdue(TODAY)
    due = statutory_interest(worst.outstanding, worst.days_overdue(TODAY))
    assert due == Decimal("37.67")
    assert "37.67 EUR" in DESCRIPTION


def test_the_injection_claim_is_not_in_the_description_at_all():
    """It was measured on a withdrawn set. The README says so where it stands.

    The description is what gets pasted into a form, and a finding that needs a
    paragraph of provenance to be honest does not survive that trip.
    """
    said = " ".join(DESCRIPTION.split()).lower()
    assert "three times out of three" not in said
    assert "measured on one of the withdrawn sets" in said


def test_the_hero_line_on_the_page_is_the_one_the_script_reads_out():
    from archon.web.app import Session

    session = Session(store_path=None)
    worst = session.books.worst_overdue(__import__("archon.demo", fromlist=["TODAY"]).TODAY)
    assert worst.counterparty in SCRIPT
    assert f"{worst.outstanding:,.2f} EUR" in SCRIPT


# --- the admissions ------------------------------------------------------------


@pytest.mark.parametrize(
    "admission",
    [
        "earned by not acting",
        "SES sandbox",
        "No mailbox is connected",
        "no OCR",
        "invented",
        "a better line than the one I wrote",
    ],
)
def test_the_description_keeps_its_admissions(admission):
    # Read the way a person does: the file is wrapped to a column.
    assert admission in " ".join(DESCRIPTION.split()), admission


def test_the_script_forbids_the_things_that_would_overclaim():
    forbidden = said(SCRIPT[SCRIPT.index("What must not be said") :])
    for rule in (
        "do not call the offline run agentic",
        "do not claim a live mailbox",
        "do not claim ocr",
    ):
        assert rule in forbidden, rule
    assert "circular" in forbidden, "the weakest row must be named as weak on camera too"


def test_the_script_has_a_fallback_for_the_shot_that_needs_ses():
    """The one shot that can fail on the day, so it has an alternative in writing."""
    assert "if they are not" in said(SCRIPT)
    assert "do not imply otherwise" in said(SCRIPT)


# --- the commands --------------------------------------------------------------


def test_every_command_the_script_tells_someone_to_run_exists():
    for module in ("archon.demo", "archon.web.app", "archon.evidence.compare"):
        assert module in SCRIPT
        __import__(module)


def test_the_files_the_script_puts_on_screen_are_in_the_repository():
    for named in re.findall(r"`(evidence/[\w.\-]+)`", SCRIPT):
        assert (ROOT / named).exists(), named


def test_the_script_fits_in_five_minutes():
    """The rules cap it at five. The section targets have to add up."""
    seconds = [int(s) for s in re.findall(r"— (\d+) seconds", SCRIPT)]
    assert len(seconds) >= 6, "every section needs a target"
    assert sum(seconds) <= 300, f"{sum(seconds)}s of script for a 300s limit"


def test_the_description_names_the_sdk_and_the_model_actually_used():
    from archon.adapters.bedrock import MODEL_ID

    assert "Strands Agents SDK" in DESCRIPTION
    assert MODEL_ID in DESCRIPTION


def test_the_disclosure_travels_with_the_description():
    assert "Ten earlier Archon repositories" in DESCRIPTION
    assert "No code from any of them is in this repository" in DESCRIPTION


def test_the_description_says_plainly_what_this_is_that_lasttake_is_not():
    """Uniqueness is the Sponsor's sole discretion, so it is stated rather than left."""
    section = DESCRIPTION[DESCRIPTION.index("What Archon is that our other entry is not") :]
    assert "script supervisor" in section, "the other buyer is named"
    assert "sole trader" in section, "this buyer is named"
    assert "one shoot day" in section and "the month" in section, "the units differ"
    assert "ever leaves the production" in section
    assert "outside the firm" in section
    assert "holds an internal decision back" in said(section)


def test_the_uniqueness_claim_is_one_mechanism_and_one_buyer_not_a_feature_list():
    section = DESCRIPTION[DESCRIPTION.index("What Archon is that our other entry is not") :]
    section = section[: section.index("### Built with")]
    assert len(section.split()) < 200, "if it takes a page to say, it is not a distinction"
