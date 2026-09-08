"""The README is a claim, so it is tested like one.

Every submission standard this project works to has a row about the README, the
code, the video and the description agreeing. That row is usually kept by
somebody remembering. Here it is kept by the suite: if a number in the README
stops matching the thing it describes, this fails.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_headline_sentence_is_the_one_in_the_gate():
    """25 words, no em dash, mechanism plus consequence."""
    first = re.search(r"^\*\*(.+?)\*\*$", README, re.M).group(1)
    assert "—" not in first, "an em dash in the sentence the organiser might republish"
    assert len(first.split()) <= 25, f"{len(first.split())} words"
    assert "inbox" in first and "approve" in first


def test_the_comparison_table_matches_what_the_code_computes():
    from archon.evidence.compare import score_all

    by_method = {t.method: t for t in score_all()}
    assert by_method["reference matching"].missed == 13
    assert by_method["naive text extraction"].wrong_money == 19
    assert by_method["Archon"].correct == 20

    assert "| 0 / 20 | **13** | 7 |" in README
    assert "| 19 / 20 | 0 | 1 |" in README
    assert "| 0 / 20 | 0 | 20 |" in README


def test_the_live_row_is_reported_with_its_caveat():
    assert "a real Claude model, one pass, no ledger" in README
    assert "nothing in its answer tells you which" in README
    assert "partly circular" in README, "the weakest row must be named as weak"
    assert "friendly test" in README


def test_the_confidence_interval_is_quoted_beside_every_zero():
    from archon.evidence.compare import wilson

    _, high = wilson(0, 20)
    assert f"0.0% to {high:.1%}" in README, "a zero without its interval reads as certainty"


def test_the_test_count_and_coverage_are_not_stale():
    """The two numbers most likely to drift, and the least likely to be re-checked."""
    claimed_tests = int(re.search(r"(\d+) tests, (\d+)% branch coverage", README).group(1))
    claimed_cov = int(re.search(r"(\d+) tests, (\d+)% branch coverage", README).group(2))

    collected = sum(
        1
        for path in (ROOT / "tests").glob("test_*.py")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("def test_")
    )
    # Parametrised cases make the run larger than the count of functions, so the
    # README may claim more, never fewer, and never wildly more.
    assert collected <= claimed_tests <= collected * 2, (
        f"README claims {claimed_tests}; {collected} test functions are defined"
    )
    assert 85 <= claimed_cov <= 100


def test_the_sdk_versions_named_are_the_ones_it_runs_on():
    strands = pytest.importorskip("strands")
    version = getattr(strands, "__version__", "")
    if version:
        major_minor = ".".join(version.split(".")[:2])
        assert major_minor in README, f"running on {version}, README does not mention it"


def test_the_bedrock_model_named_is_the_one_configured():
    from archon.adapters.bedrock import MODEL_ID

    assert MODEL_ID in README


def test_every_prior_archon_repo_is_disclosed():
    """P2 asks for a named list. A short list is worse than none."""
    for repo in (
        "archon-cockroach-memory",
        "h0-archon",
        "archon-gcp-agentic",
        "archon-gcp",
        "archon-vibecoding",
        "archon_azure",
        "archon_nebius",
        "archon-qwen-autopilot",
        "archon-qwen-memoryagent",
        "archon-datahub",
    ):
        assert repo in README, f"{repo} is not disclosed"
    assert "No code from any of them is in this repository" in README
    assert "lasttake-aws" in README, "the reused scaffolding shape is disclosed too"


def test_the_limitations_are_not_quietly_dropped():
    for admission in (
        "SES sandbox",
        "entirely invented",
        "There is no tenancy",
        "No mailbox is connected",
        "Nothing is submitted to any tax authority",
    ):
        assert admission in README, f"missing admission: {admission}"


def test_the_offline_mode_is_not_dressed_up_as_agentic():
    assert "it does not judge" in README


def test_the_commands_it_tells_a_judge_to_run_exist():
    for module in ("archon.evidence.compare", "archon.demo", "archon.web.app"):
        assert module in README
        __import__(module)


def test_the_diagrams_are_present_and_renderable_by_github():
    fences = re.findall(r"```mermaid\n(.*?)```", README, re.S)
    assert len(fences) >= 2, "the rules ask for an architecture diagram; two are better"
    for body in fences:
        assert body.strip().startswith("flowchart")
        assert body.count("[") == body.count("]")


def test_the_readme_no_longer_says_scaffolding():
    assert "Scaffolding" not in README


def test_the_business_case_states_what_is_not_proven():
    """An investor section that only claims is worth less than one that also doubts."""
    assert "What would have to be true, and is not yet" in README
    for doubt in (
        "nothing here has tested with a real person",
        "the twenty scenarios do not probe",
        "None of those is answered by this repository",
    ):
        assert doubt in README, doubt


def test_the_external_statistics_carry_a_source_and_a_date():
    assert "EU Payment Report 2026" in README
    assert "EU Payment Observatory" in README
    assert "read 2026-09-05" in README


def test_the_unit_cost_is_measured_and_says_which_model_produced_it():
    assert "12,070 tokens" in README
    assert "one real run against Bedrock" in README
    assert "rather than the Opus 5 this project configures" in README, (
        "a cost measured on one model and attributed to another is a wrong number"
    )


def test_no_market_size_is_invented():
    """A TAM nobody computed is the fastest way to lose an investor's trust."""
    for invented in ("TAM", "total addressable", "$1bn", "billion market"):
        assert invented not in README, invented


def test_the_readme_answers_why_six_agents():
    """The strongest objection to the design, so it is answered rather than left."""
    assert "Why six agents and not one query" in README
    assert "restate what a deterministic tool returned" in README
    assert "URGENT" in README and "WATCH" in README


def test_the_disagreement_is_shown_from_a_real_run_not_asserted():

    assert "evidence/SIX-VIEWS-2026-09-05.txt" in README
    captured = ROOT / "evidence" / "SIX-VIEWS-2026-09-05.txt"
    assert captured.exists(), "the README quotes a run whose transcript is not in the repository"
    text = captured.read_text(encoding="utf-8")
    for reader in ("payroll", "suppliers", "metrics", "cash", "trading", "sales"):
        assert f"### {reader}" in text, reader
    assert "URGENT" in text and "WATCH" in text


def test_the_hard_table_matches_what_the_code_computes():
    from archon.evidence.compare import score_all
    from archon.evidence.hard import all_hard_scenarios

    by_method = {t.method: t for t in score_all(all_hard_scenarios())}
    assert by_method["reference matching"].missed == 6
    assert by_method["Archon"].correct == 15

    assert "| 0 / 15 | **6** | 9 |" in README
    assert "| 0 / 15 | 0 | 15 |" in README


def test_the_injection_finding_is_stated_with_its_own_caveat():
    assert "complied three times out of three" in README
    assert "a real attacker would write a better one" in README
    assert "cannot reach a decision that no model makes" in README


def test_the_hard_writeup_is_in_the_repository():
    assert (ROOT / "evidence" / "RESULTS-HARD-2026-09-08.md").exists()
    assert (ROOT / "evidence" / "HARD-LIVE-2026-09-08.txt").exists()


def test_the_badges_point_at_this_repository_and_this_branch():
    """A badge from another repo or a dead branch is a broken promise on line five."""
    assert "upgradedev/archon-aws-strands/actions/workflows/ci.yml/badge.svg?branch=main" in README
    assert "licence-MIT-blue" in README


def test_the_badge_numbers_match_the_ones_below_them():
    claimed = re.search(r"branch%20coverage-(\d+)%25", README).group(1)
    stated = re.search(r"(\d+)% branch coverage", README).group(1)
    assert claimed == stated, f"badge says {claimed}%, the table says {stated}%"

    badge_tests = re.search(r"tests-(\d+)%20offline", README).group(1)
    stated_tests = re.search(r"(\d+) tests, \d+% branch coverage", README).group(1)
    assert badge_tests == stated_tests, f"badge says {badge_tests}, the table says {stated_tests}"


def test_the_badge_does_not_claim_more_than_ci_checks():
    assert "asserts the Strands API surface" in README
    assert "fails if a number in this README stops matching" in README
