"""Submission and recording text must describe the actual public path, not a demo send."""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DESCRIPTION = (ROOT / "docs/SUBMISSION-DESCRIPTION.md").read_text(encoding="utf-8")
SCRIPT = (ROOT / "docs/VIDEO-SCRIPT.md").read_text(encoding="utf-8")


def said(text):
    return " ".join(text.replace(">", " ").split()).lower()


@pytest.mark.parametrize("text", [DESCRIPTION, SCRIPT])
def test_public_documents_bind_the_demo_to_live_identity_and_limits(text):
    for required in ("https://d2ssmv59q16d0b.cloudfront.net/", "joiner", "records",
                     "strands", "six", "scripted", "simulated", "no real email",
                     "not_run", "withdrawn", "zero archon chases", "hash identifies bytes",
                     "release.json", "/api/health"):
        assert required in said(text), required
    for forbidden in ("no public deployment", "reads anything", "sent to my own inbox",
                      "three times out of three", "| 10 / 20 |"):
        assert forbidden not in said(text)


def test_documented_sample_arithmetic_comes_from_current_sources():
    from archon.web import workspace
    state = workspace.fresh()
    for key in ("invoice", "payment"):
        workspace.intake(state, workspace.SAMPLES[key])
    actual = workspace.books_for(state).sales_settlements()[0]
    for text in (DESCRIPTION, SCRIPT):
        for amount in (actual.gross, actual.settled, actual.outstanding):
            assert f"{amount:,.2f} EUR" in text


def test_script_does_not_treat_an_unavailable_api_as_permission_to_simulate_success():
    assert "there is no ses fallback shot" in said(SCRIPT)
    assert "refresh durable state before any retry" in said(SCRIPT)
    assert "provider acceptance does not prove arrival" in said(SCRIPT)
    assert "script, not a completed video" in said(SCRIPT)


def test_the_script_forbids_the_things_that_would_overclaim():
    forbidden = said(SCRIPT[SCRIPT.index("What must not be said"):])
    for rule in ("do not call the offline run agentic", "do not claim a live mailbox",
                 "real email delivery", "ocr", "circular benchmark", "compliance",
                 "measured time savings", "live model result"):
        assert rule in forbidden


def test_the_script_fits_in_five_minutes():
    seconds = [int(s) for s in re.findall(r"— (\d+) seconds", SCRIPT)]
    assert len(seconds) == 7
    assert sum(seconds) <= 300


def test_the_description_names_the_sdk_and_operator_model_separately():
    from archon.adapters.bedrock import MODEL_ID
    assert "Strands Agents" in DESCRIPTION and "SDK graph" in DESCRIPTION
    assert MODEL_ID in DESCRIPTION and "not the public scripted mode" in DESCRIPTION


def test_disclosures_and_licenses_travel_with_the_description():
    normalized = " ".join(DESCRIPTION.split())
    assert "Ten earlier Archon repositories" in normalized
    assert "No code from any of them is in this repository" in normalized
    assert "pre-existing-work-disclosed" in DESCRIPTION
    assert "THIRD-PARTY.md" in DESCRIPTION
