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
    """Superseded 2026-09-09 by the fair table; kept pointing at the live one."""
    from archon.evidence.fair import METHODS, score
    from archon.evidence.independent import scored

    rows = {name: score(name, run, scored()).counts for name, run in METHODS.items()}
    assert rows["naive text extraction"]["wrong-money"] == 11
    assert "| 11 / 20 | 5 | 4 | 11 | **0** |" in README


def test_the_live_row_is_reported_with_its_caveat():
    assert "live Bedrock reader" in README
    assert "Archon, live Bedrock reader" in README
    assert "nothing in its answer tells you which" in README
    assert "partly circular" in README, "the weakest row must be named as weak"
    assert "friendly test" in README


def test_a_published_zero_says_how_it_was_earned():
    """Superseded the interval check on 2026-09-09.

    A 95% interval beside `0 / 20` was the honest thing while the zero meant
    "sent twenty times and never wrong". It now means "sent nothing", and the
    sentence that says so does more work than an interval ever did. The interval
    is still printed by `python -m archon.evidence.fair`.
    """
    said = " ".join(README.split())
    assert "| **0 / 20** | 15 | 5 | **0** | **0** |" in README
    assert "Archon sends nothing at all" in said
    assert "achieved by not acting" in said

    from archon.evidence.fair import report

    assert "95% CI, wrong money" in report()


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
    for module in ("archon.evidence.fair", "archon.demo", "archon.web.app"):
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


def test_the_readme_quotes_the_fair_table_the_code_computes():
    """The only comparison this project is allowed to quote, as of 2026-09-09."""
    from archon.evidence.fair import METHODS, score
    from archon.evidence.independent import scored

    cases = scored()
    rows = {name: score(name, run, cases) for name, run in METHODS.items()}

    baseline = rows["reference matching (baseline)"].counts
    archon = rows["Archon"].counts
    assert baseline["wrong-money"] == 10
    assert archon["wrong-money"] == 0
    assert archon["missed"] == 15

    assert "| 10 / 20 | 6 | 4 | 10 | **0** |" in README
    assert "| **0 / 20** | 15 | 5 | **0** | **0** |" in README

    said = " ".join(README.split())
    assert "Archon sends nothing at all" in said, "the zero has to say how it was earned"
    assert "safe and not yet useful" in said


def test_the_withdrawn_tables_stay_withdrawn():
    said = " ".join(README.split())
    assert "Both earlier comparisons are withdrawn and stay withdrawn" in said
    assert "a ledger agreeing with itself" in said


def test_the_injection_finding_says_which_set_it_came_from():
    """It was measured on a withdrawn set, so the README says so where it stands."""
    said = " ".join(README.split())
    assert "Measured on the withdrawn set of 2026-09-08" in said
    assert "has not been re-run on the independent post" in said


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


def test_the_architecture_diagram_exists_as_an_image_not_only_as_mermaid():
    """The FAQ never said whether inline Mermaid counts, and a form renders none."""
    svg = ROOT / "docs" / "architecture.svg"
    assert svg.exists()
    assert 'src="docs/architecture.svg"' in README
    assert "no Mermaid" in README


def test_the_diagram_is_valid_and_self_contained():
    import xml.etree.ElementTree as ET

    text = (ROOT / "docs" / "architecture.svg").read_text(encoding="utf-8")
    ET.fromstring(text)
    assert "http://" not in text.replace("http://www.w3.org/2000/svg", "")
    assert "<image" not in text and "@import" not in text


def test_the_diagram_describes_itself_for_a_reader_who_cannot_see_it():
    text = (ROOT / "docs" / "architecture.svg").read_text(encoding="utf-8")
    assert "<title" in text and "<desc" in text
    assert 'alt="Archon architecture' in README


def test_the_diagram_names_what_the_code_actually_does():
    from archon.agents import wiring

    text = (ROOT / "docs" / "architecture.svg").read_text(encoding="utf-8")
    for reader in wiring.READERS:
        assert f">{reader.name}<" in text, reader.name
    assert "holds no tools" in text
    for verdict in wiring.VERDICTS:
        assert verdict in text


def test_the_diagram_shows_the_gate_branching_rather_than_chaining():
    """Gate to Held to SES would read as if a held draft still goes out."""
    text = (ROOT / "docs" / "architecture.svg").read_text(encoding="utf-8")
    assert ">released<" in text and ">held<" in text
    assert "Held — nothing is sent" in text


def test_ci_runs_the_quickstart_the_readme_prints():
    """S4 fails silently: a file listing looks complete until somebody clones it."""
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "the quickstart a judge is told to run" in workflow

    quickstart = README[README.index("## Run it") : README.index("## How it is put together")]
    commands = {
        line.strip()
        for block in re.findall(r"```bash\n(.*?)```", quickstart, re.S)
        for line in block.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    # Everything the README tells someone to run, except the two that need AWS
    # and the pip install the workflow does in its own step.
    offline = {
        c.split("#")[0].strip()
        for c in commands
        if "--live" not in c and not c.startswith("pip install")
    }
    for command in offline:
        module = re.search(r"python -m ([\w.]+)", command)
        assert module, command
        assert module.group(1) in workflow, f"{module.group(1)} is not exercised by CI"
