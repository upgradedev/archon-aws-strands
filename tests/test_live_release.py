"""A new proof lane cannot relabel the historical synthetic acceptance as real providers."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "controlled_release", Path(__file__).resolve().parents[1] / "deploy/release_acceptance.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
FRONT, BACK = "1" * 40, "2" * 40
PAIR = {"frontend_commit": FRONT, "backend_commit": BACK,
        "backend_identity_basis": release.BASIS,
        "mode": "controlled-live", "live_model": True, "live_send": True}
ENV = {"GITHUB_REPOSITORY": release.old.REPO, "GITHUB_REF": "refs/heads/main",
       "GITHUB_SHA": FRONT, "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2",
       "PREFLIGHT": "success", "JOURNEYS": "success", "POSTFLIGHT": "success"}


@pytest.fixture
def artifacts(tmp_path):
    junit = tmp_path / "junit.xml"
    junit.write_text('<testsuites tests="3" failures="0" errors="0" skipped="0">'
                     '<testsuite><testcase/><testcase/><testcase/></testsuite></testsuites>')
    for name in release.PROJECTS:
        proof = {"scope": "actual_aws", "origin": release.old.URL.rstrip("/"),
                 "project": name, "frontend_commit": FRONT, "backend_commit": BACK,
                 "model_calls": 15, "input_tokens": 1500, "output_tokens": 300,
                 "email_accepted": True, "message_id": "provider-" + name,
                 "replay_unchanged": True, "reload_retained": True,
                 "legacy_consent_refused": True}
        (tmp_path / f"live-provider-{name}.json").write_text(json.dumps(proof))
    return junit, tmp_path


def test_explicit_controlled_receipt_has_separate_scope_and_no_mailbox_claim(artifacts):
    value = release.receipt(PAIR, PAIR, *artifacts, ENV)
    release.validate(value)
    assert value["counts"] == {"total": 3, "passed": 3, "failed": 0, "skipped": 0}
    assert value["provider_checks"]["model_calls"] == 45
    assert value["provider_checks"]["delivery_proven"] is False
    assert "No mailbox arrival" in value["limits"]


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_playwright_cdata_attachments_are_metadata_not_document_types(artifacts, encoding):
    junit, directory = artifacts
    xml = ('<testsuites tests="3" failures="0" errors="0" skipped="0">'
           '<!-- Playwright attachment metadata -->'
           '<testsuite><testcase><system-out><![CDATA['
           '[[ATTACHMENT|../test-results/trace.zip]]\n<!DOCTYPE is just text here'
           ']]></system-out></testcase><testcase/><testcase/></testsuite></testsuites>')
    junit.write_bytes(xml.encode(encoding))
    value = release.receipt(PAIR, PAIR, junit, directory, ENV)
    release.validate(value)
    assert value["counts"]["passed"] == 3
    assert "ATTACHMENT" not in json.dumps(value)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
@pytest.mark.parametrize("declaration", [
    '<!DOCTYPE testsuites>',
    '<!DOCTYPE testsuites SYSTEM "file:///etc/passwd">',
    '<!DOCTYPE testsuites [<!ENTITY expanded "unexpected">]>',
    '<!DOCTYPE testsuites [<!ENTITY external SYSTEM "https://invalid.example/data">]>',
])
def test_document_types_are_refused_independent_of_encoding(artifacts, encoding, declaration):
    junit, directory = artifacts
    junit.write_bytes((declaration + '<testsuites tests="3"><testsuite>'
                       '<testcase/><testcase/><testcase/></testsuite></testsuites>').encode(encoding))
    with pytest.raises(ValueError, match="document types"):
        release.receipt(PAIR, PAIR, junit, directory, ENV)


def test_cdata_does_not_hide_a_failed_browser_case(artifacts):
    junit, directory = artifacts
    junit.write_text('<testsuites tests="3"><testsuite><testcase>'
                     '<system-out><![CDATA[attachment]]></system-out><failure/>'
                     '</testcase><testcase/><testcase/></testsuite></testsuites>')
    with pytest.raises((AssertionError, RuntimeError, ValueError)):
        release.receipt(PAIR, PAIR, junit, directory, ENV)


@pytest.mark.parametrize("bad", [
    {"scope": "ci_fakeproviders"}, {"origin": "http://127.0.0.1:4173"},
    {"frontend_commit": "3" * 40}, {"backend_commit": "3" * 40},
    {"model_calls": 0}, {"input_tokens": True}, {"output_tokens": 0},
    {"email_accepted": False}, {"message_id": "ci-receipt"},
    {"replay_unchanged": False}, {"reload_retained": False},
    {"legacy_consent_refused": False}, {"legacy_consent_refused": None},
])
def test_incomplete_fake_or_wrong_release_proof_never_passes(artifacts, bad):
    junit, directory = artifacts
    path = directory / "live-provider-desktop.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), **bad}))
    with pytest.raises((AssertionError, RuntimeError, ValueError)):
        release.receipt(PAIR, PAIR, junit, directory, ENV)


@pytest.mark.parametrize("xml", [
    '<testsuites tests="3"><testsuite><testcase/><testcase/></testsuite></testsuites>',
    '<testsuites tests="3"><testsuite><testcase><failure/></testcase>'
    '<testcase/><testcase/></testsuite></testsuites>',
    '<!DOCTYPE testsuites><testsuites tests="3"/>',
])
def test_failed_or_missing_browser_cases_cannot_be_published(artifacts, xml):
    junit, directory = artifacts
    junit.write_text(xml)
    with pytest.raises((AssertionError, RuntimeError, ValueError)):
        release.receipt(PAIR, PAIR, junit, directory, ENV)


@pytest.mark.parametrize("bad", [
    {"private_session": "must not publish"}, {"human_uat": "PASS"},
    {"limits": "Delivered"}, {"live_send": False}, {"run_attempt": 2},
    {"run_url": "javascript:alert(1)"}, {"backend_identity_basis": "unchecked"},
    {"observed_at": "2026-09-13T00:00:00"},
])
def test_public_receipt_is_sanitized_and_scope_locked(artifacts, bad):
    value = release.receipt(PAIR, PAIR, *artifacts, ENV)
    value.update(bad)
    with pytest.raises((AssertionError, RuntimeError, ValueError)):
        release.validate(value)


def test_duplicate_send_id_cannot_count_as_three_new_provider_journeys(artifacts):
    for path in artifacts[1].glob("live-provider-*.json"):
        path.write_text(json.dumps({**json.loads(path.read_text()), "message_id": "same"}))
    with pytest.raises((AssertionError, RuntimeError, ValueError)):
        release.receipt(PAIR, PAIR, *artifacts, ENV)


def test_runtime_pair_checks_source_and_deployment_paths(monkeypatch):
    calls = []
    monkeypatch.setattr(release.old, "compatible", lambda *args: calls.append(args))
    health = {"status": "ok", "commit": BACK, "mode": "controlled-live", "live_model": True,
              "live_send": True, "model": "eu.anthropic.claude-opus-5",
              "provider": "SES-controlled-recipient", "orchestration": "Strands"}
    assert release.pair(FRONT, BACK, lambda _: health,
                        lambda *args: calls.append(args)) == PAIR
    assert calls[-1] == ("diff", "--exit-code", BACK, FRONT, "--", "deploy")
    health["live_model"] = False
    with pytest.raises((AssertionError, RuntimeError, ValueError)):
        release.pair(FRONT, BACK, lambda _: health, lambda *args: None)


def test_unknown_publisher_attempt_is_refused_before_any_aws_write(artifacts, monkeypatch):
    value = release.receipt(PAIR, PAIR, *artifacts, ENV)
    for key, val in ENV.items():
        monkeypatch.setenv(key, val)
    monkeypatch.setenv("ACCEPTANCE_RUN_ATTEMPT", "2")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    calls = []
    with pytest.raises((AssertionError, RuntimeError, ValueError)):
        release.publish(value, lambda *args: calls.append(args))
    assert not calls


def test_historical_synthetic_lane_is_delegated_unchanged(monkeypatch):
    original = {"mode": "synthetic"}
    monkeypatch.setattr(release.old, "receipt", lambda *args: original)
    assert release.receipt(copy.copy(original), {}, "unused", "unused", {}) is original
