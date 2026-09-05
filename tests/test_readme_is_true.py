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
        "no persistence",
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
