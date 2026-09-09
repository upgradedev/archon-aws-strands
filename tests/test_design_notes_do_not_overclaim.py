"""A document in the repository is read as a description of the repository.

`docs/BEDROCK_AGENTCORE_ARCHITECTURE.md` describes a deployment on Bedrock
AgentCore that does not exist. That is fine as a plan and dangerous as prose,
because nothing on the page said which it was. These keep it saying so.
"""

from __future__ import annotations

import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOTE = (ROOT / "docs" / "BEDROCK_AGENTCORE_ARCHITECTURE.md").read_text(encoding="utf-8")

#: The prose as a reader takes it in. The file is wrapped to a column and
#: blockquoted, so a sentence that reads as one line is several in the bytes;
#: asserting on the bytes fails for the wrong reason, which it has done twice
#: in this repository already.
PROSE = " ".join(NOTE.replace(">", " ").split())


def test_it_says_in_its_first_lines_that_it_is_not_implemented():
    assert "not a description of what runs" in PROSE[:1600]
    assert "None of the AgentCore runtime described below is implemented" in PROSE[:1600]


def test_the_claim_that_nothing_calls_agentcore_is_true():
    """The document offers a command; the command has to give that answer."""
    found = subprocess.run(
        ["git", "grep", "-ril", "agentcore", "--", "src/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert not found.stdout.strip(), f"src/ mentions AgentCore: {found.stdout}"


def test_the_model_it_names_is_the_one_actually_configured():
    from archon.adapters.bedrock import MODEL_ID

    assert MODEL_ID in NOTE
    assert "it named **Claude 3.5 Sonnet**" in PROSE, "the correction has to stay visible"


def test_it_no_longer_calls_archon_a_dispute_engine_without_saying_that_was_wrong():
    assert "it called Archon a **dispute resolution** engine" in PROSE
    assert "records bounded human resolutions; it is not a dispute engine" in PROSE


def test_the_threshold_it_describes_is_named_as_not_how_the_gate_works():
    """A judge reading "holds above €5,000" would think the gate has a floor."""
    assert "is **not** how the gate works and never was" in PROSE
    assert "There is no amount at which" in PROSE


def test_what_exists_and_what_does_not_is_a_table_not_a_paragraph():
    table = NOTE[NOTE.index("| described here |") : NOTE.index("The threshold in the mapping")]
    assert table.count("**no**") >= 2, "the absent things have to be marked absent"
    assert table.count("**yes**") >= 4
    for module in ("archon.security.sanitizer", "archon.domain.ledger", "archon.agents.gate"):
        assert module in table
        __import__(module)
