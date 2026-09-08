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


def test_the_description_quotes_the_friendly_table_the_code_computes():
    from archon.evidence.compare import score_all

    by_method = {t.method: t for t in score_all()}
    assert by_method["reference matching"].missed == 13
    assert by_method["Archon"].missed == 0

    assert "| 0 / 20 | **13** |" in DESCRIPTION
    assert "| 0 / 20 | 0 |" in DESCRIPTION


def test_the_description_quotes_the_hard_table_the_code_computes():
    from archon.evidence.compare import score_all
    from archon.evidence.hard import all_hard_scenarios

    by_method = {t.method: t for t in score_all(all_hard_scenarios())}
    assert by_method["reference matching"].missed == 6

    assert "| 0 / 15 | **6** |" in DESCRIPTION
    assert "| 0 / 15 | 0 |" in DESCRIPTION


def test_the_statutory_interest_figure_is_the_one_the_ledger_produces():
    from decimal import Decimal

    from archon.demo import TODAY, keep_the_books, the_post
    from archon.domain.completeness import statutory_interest

    books = keep_the_books(the_post())
    worst = books.worst_overdue(TODAY)
    due = statutory_interest(worst.outstanding, worst.days_overdue(TODAY))
    assert due == Decimal("37.67")
    assert "37.67 EUR" in DESCRIPTION


def test_the_injection_debt_is_the_one_in_the_scenarios():
    from archon.evidence.hard import all_hard_scenarios

    injected = [c for c in all_hard_scenarios() if c.name.startswith("instruction")]
    assert len(injected) == 3
    assert all(str(c.truth) == "3720.00" for c in injected)

    for text in (DESCRIPTION, SCRIPT):
        assert "three times out of three" in said(text)
        spoken = said(text)
        assert "3,720" in spoken or "three thousand seven hundred and twenty" in spoken


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
        "circular in both sets",
        "SES sandbox",
        "No mailbox is connected",
        "no OCR",
        "invented",
        "a real attacker would write a better one",
    ],
)
def test_the_description_keeps_its_admissions(admission):
    assert admission in DESCRIPTION, admission


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
