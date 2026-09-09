"""Current documentation contracts; historical benchmark bytes are not fresh scores."""

from __future__ import annotations

import pathlib
import re
import tomllib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_headline_sentence_is_the_one_in_the_gate():
    """25 words, no em dash, mechanism plus consequence."""
    first = re.search(r"^\*\*(.+?)\*\*$", README, re.M).group(1)
    assert "—" not in first, "an em dash in the sentence the organiser might republish"
    assert len(first.split()) <= 25, f"{len(first.split())} words"
    assert "inbox" in first and "approve" in first


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


def test_no_market_size_is_invented():
    """A TAM nobody computed is the fastest way to lose an investor's trust."""
    for invented in ("TAM", "total addressable", "$1bn", "billion market"):
        assert invented not in README, invented


def test_the_hard_writeup_is_in_the_repository():
    assert (ROOT / "evidence" / "RESULTS-HARD-2026-09-08.md").exists()
    assert (ROOT / "evidence" / "HARD-LIVE-2026-09-08.txt").exists()


def test_the_badges_point_at_this_repository_and_this_branch():
    """A badge from another repo or a dead branch is a broken promise on line five."""
    assert "upgradedev/archon-aws-strands/actions/workflows/ci.yml/badge.svg?branch=main" in README
    assert "licence-MIT-blue" in README


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


def test_the_sender_region_matches_the_model_region():
    """A chase composed in Europe and posted from Oregon is a strange shape."""
    import inspect

    from archon.adapters.bedrock import REGION
    from archon.adapters.ses import live_outbox

    assert f'region: str = "{REGION}"' in inspect.getsource(live_outbox)


DOCS = ["README.md", "docs/SUBMISSION-DESCRIPTION.md", "docs/VIDEO-SCRIPT.md",
        "docs/THIRD-PARTY.md", "docs/DIFFERENTIATION.md", "docs/BEDROCK_AGENTCORE_ARCHITECTURE.md",
        "evidence/RESULTS-2026-09-04.md", "evidence/RESULTS-HARD-2026-09-08.md",
        "evidence/RESULTS-CORRECTED-2026-09-08.md", "evidence/RESULTS-FAIR-2026-09-09.md"]


@pytest.mark.parametrize("path", DOCS)
def test_every_tracked_document_starts_with_the_current_public_scope(path):
    first_screen = (ROOT / path).read_text(encoding="utf-8")[:3000].lower()
    for required in ("joiner", "https://d2ssmv59q16d0b.cloudfront.net/", "records",
                     "strands", "scripted", "simulated", "evidence", "disclosures"):
        assert required in first_screen, (path, required)


def test_no_frozen_test_badge_or_new_benchmark_score_masquerades_as_current():
    for obsolete in ("tests, 90% branch coverage", "branch%20coverage-", "tests-494",
                     "| 10 / 20 |", "| 11 / 20 |", "reads anything", "No public deployment",
                     "complied three times out of three"):
        assert obsolete not in README
    for required in ("exact-SHA CI", "zero Archon chases", "achieved by not acting",
                     "earlier comparisons are withdrawn", "no current advantage",
                     "Fresh synthetic contract tests", "nonempty correct recipient"):
        assert required in " ".join(README.split())


def test_runtime_and_evidence_claims_are_scoped_and_recoverable():
    for required in ("release.json", "/api/health", "not evidence that this SHA is deployed",
                     "seven days", "Refresh durable state", "unknown sends",
                     "model is **scripted**", "outbox is **simulated**",
                     "identity-attestation", "does not rewrite posted sources",
                     "Human active time", "Unknown", "Human UAT stays NOT_RUN",
                     "hash is not proof", "redacted", "operator accounting correction"):
        assert required in " ".join(README.split()), required


def test_operator_configuration_and_public_mode_are_separate():
    from archon.adapters.bedrock import MAX_TOKENS, MODEL_ID, REGION
    assert all(str(value) in README for value in (MODEL_ID, REGION, MAX_TOKENS))
    assert "separate 4000-token budget" in README
    assert "ARCHON_BUSINESS_EMAIL" in README and "ARCHON_BUSINESS_NAME" in README
    assert "strands-agents>=1.53.0" in README
    assert "removing strands prevents draft preparation" in README.lower()


def test_prior_acceptance_and_full_history_retention_have_exact_provenance():
    for required in ("34357703424", "10106786411",
                     "519a1e7c11a995529113161344192240fd031459",
                     "SHA256 manifest", "fetch-depth: 0", "--log-opts=--all", "ninety days"):
        assert required in README
    workflow = (ROOT / ".github/workflows/frontend-ci.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in workflow and "--log-opts=--all" in workflow
    assert "--log-opts=-1" not in workflow
    assert "thresholds: { lines: 85, functions: 85, statements: 85, branches: 85 }" in (
        ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")


def test_python_coverage_floor_is_enforced_without_source_or_branch_exclusions():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    coverage = config["tool"]["coverage"]
    assert coverage["report"]["fail_under"] == 85
    assert coverage["run"]["branch"] is True
    assert coverage["run"]["source"] == ["src/archon"]
    assert not coverage["run"].get("omit")
    assert not coverage["report"].get("omit")
    for name in ("ci.yml", "frontend-ci.yml"):
        workflow = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
        assert "--cov" in workflow
        overrides = re.findall(r"--cov-fail-under[= ](\d+)", workflow)
        assert all(int(floor) >= 85 for floor in overrides)
