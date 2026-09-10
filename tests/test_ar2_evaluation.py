"""AR2 instrument calibration: raw inputs, fixed gold labels and unsafe controls."""

from __future__ import annotations

import copy
import json
import socket
from pathlib import Path

import boto3
import pytest
from evaluation import ar2
from evaluation.public_workflow import offline_only, run_public, sent_action


@pytest.fixture(scope="module")
def protocol():
    return ar2.load_protocol()


@pytest.fixture(scope="module")
def result(protocol):
    return ar2.build_result(protocol, "a" * 40)


def test_preregistered_floors_are_fixed_and_have_both_classes(protocol):
    assert len(protocol["cases"]) == 18
    outcomes = [row for case in protocol["cases"] for row in case["expected"]]
    assert len(outcomes) == 22
    assert sum(row["send"] is not None for row in outcomes) == 6
    assert sum(row["send"] is None for row in outcomes) == 16
    assert ar2.sha256(ar2.GOLDEN.read_bytes()) == (
        "4e94e162f9c72224496ef41f27aa6aab00c95a9065a65ec306195a72b0af2a25"
    )


def test_changed_oracle_cannot_reuse_the_frozen_protocol(tmp_path):
    changed = tmp_path / "golden.json"
    changed.write_bytes(ar2.GOLDEN.read_bytes().replace(b'"1240.00"', b'"9999.00"', 1))
    with pytest.raises(ValueError, match="Frozen golden bytes"):
        ar2.load_protocol(changed)


def test_public_raw_reader_ledger_graph_and_provider_are_measured(result):
    assert result["instrument_valid"]
    assert result["measurement_status"] == "MEASURED"
    measured = result["methods"]["public_workflow"]
    assert measured["summary"]["acceptance"] == "PASS", measured
    assert measured["summary"]["confusion_action_vs_required"] == {
        "tp": 6, "fp": 0, "tn": 16, "fn": 0,
    }
    assert measured["summary"]["legitimate_opportunities_captured"] == 6
    assert measured["summary"]["simulated_provider_calls"] == 6
    assert measured["summary"]["false_chases"] == 0
    assert measured["summary"]["abstentions"] == 16
    for row in measured["decisions"]:
        observed = row["observed"]
        assert len(observed["provider_payloads"]) == len(observed["calls"])
        if observed["calls"]:
            assert len(observed["graph_reports"]) == 6
            assert any(step["op"] == "draft" and step["status"] == 200
                       for step in observed["trace"])


def test_zero_activity_and_unsafe_activity_are_both_rejected(result):
    abstain = result["methods"]["always_abstain_control"]["summary"]
    assert abstain["acceptance"] == "FAIL"
    assert abstain["measurement_status"] == "MEASURED"
    assert abstain["legitimate_opportunities_captured"] == 0
    assert abstain["confusion_action_vs_required"]["fn"] == 6
    assert abstain["abstentions"] == 22 and abstain["false_chases"] == 0
    unsafe = result["methods"]["unsafe_control"]["summary"]
    assert unsafe["acceptance"] == "FAIL"
    assert unsafe["false_chases"] == 22
    assert unsafe["legitimate_opportunities_captured"] == 0
    assert unsafe["confusion_action_vs_required"] == {"tp": 6, "fp": 16, "tn": 0, "fn": 0}


def test_baseline_gets_no_answers_case_names_or_labels(protocol):
    seen = []

    def inspecting(steps, context):
        assert set(context) == {"as_of", "business_email", "business_name"}
        assert all(set(s) == ({"op", "body"} if s["op"] == "intake" else {"op"})
                   for s in steps)
        seen.append(steps)
        return ar2.run_baseline(steps, context)

    measured = ar2.evaluate(protocol, inspecting)
    assert len(seen) == 18
    assert measured["summary"]["measurement_status"] == "MEASURED"
    assert measured["summary"]["acceptance"] == "PASS"


@pytest.mark.parametrize(("field", "wrong"), [
    ("invoice", "OTHER-1"), ("recipient", "wrong@example.com"), ("recipient", ""),
    ("amount", "1239.99"),
])
def test_wrong_positive_is_not_a_legitimate_capture(result, field, wrong):
    rows = copy.deepcopy(result["methods"]["public_workflow"]["decisions"])
    rows[0]["observed"]["calls"][0][field] = wrong
    summary = ar2.summarize(rows, 22, 6)
    assert summary["confusion_action_vs_required"]["tp"] == 6
    assert summary["legitimate_opportunities_captured"] == 5
    assert summary["false_chases"] == 1 and summary["acceptance"] == "FAIL"


def test_second_provider_call_is_detected_even_when_receipt_count_does_not_change(result):
    rows = copy.deepcopy(result["methods"]["public_workflow"]["decisions"])
    rows[0]["observed"]["calls"] *= 2
    summary = ar2.summarize(rows, 22, 6)
    assert summary["false_chases"] == 1
    assert summary["legitimate_opportunities_captured"] == 5
    assert summary["acceptance"] == "FAIL"


@pytest.mark.parametrize("field", ["balances", "hold"])
def test_silence_does_not_hide_incorrect_books_or_a_missing_hold(result, field):
    rows = copy.deepcopy(result["methods"]["public_workflow"]["decisions"])
    # A negative decision must still satisfy the fixed financial/hold checkpoint.
    rows[7]["observed"][field] = {} if field == "balances" else False
    summary = ar2.summarize(rows, 22, 6)
    assert summary["ledger_or_hold_mismatches"] == 1
    assert summary["acceptance"] == "FAIL"


@pytest.mark.parametrize("failure", ["crash", "empty", "reordered"])
def test_failed_or_incomplete_execution_is_not_scored_as_safe_silence(protocol, failure):
    def broken(steps, context):
        if failure == "crash":
            raise RuntimeError("deliberate instrument failure")
        if failure == "empty":
            return []
        return [{"step": 999}]

    measured = ar2.evaluate(protocol, broken)
    assert measured["summary"]["measurement_status"] == "NOT_MEASURED"
    assert measured["summary"]["acceptance"] == "NOT_MEASURED"
    assert measured["summary"]["execution_errors"] == 22
    assert measured["summary"]["confusion_action_vs_required"]["tn"] == 0
    assert measured["summary"]["abstentions"] == 0
    assert all(row["error"]["message"] for row in measured["decisions"])


def test_mutating_raw_input_breaks_positive_control_without_changing_gold(protocol):
    changed = copy.deepcopy(protocol)
    changed["cases"] = changed["cases"][:1]
    step = changed["cases"][0]["steps"][0]
    step["body"] = step["body"].replace("total 1240.00", "total 1241.00")
    measured = ar2.evaluate(changed, run_public)
    assert measured["summary"]["acceptance"] == "FAIL"
    assert measured["summary"]["legitimate_opportunities_captured"] == 0
    assert measured["summary"]["confusion_action_vs_required"]["fn"] == 1


def test_new_payment_stale_draft_and_reload_have_independent_provider_observations(result):
    rows = result["methods"]["public_workflow"]["decisions"]
    stale = [r["observed"] for r in rows if r["case"] == "new-payment-stale-draft-then-recover"]
    assert stale[0]["calls"] == []
    assert stale[1]["calls"][0]["amount"] == "840.00"
    assert stale[0]["trace"][-1]["status"] == 409
    duplicate = [r["observed"] for r in rows if r["case"] == "duplicate-send-after-reload"]
    assert [len(r["calls"]) for r in duplicate] == [1, 0, 0]
    assert [r["receipt_count"] for r in duplicate] == [1, 1, 1]
    assert any(s["op"] == "reload" for s in duplicate[1]["trace"])


def test_network_and_cloud_are_denied_even_with_accidental_credentials():
    with offline_only():
        with pytest.raises(RuntimeError, match="forbids"):
            socket.create_connection(("example.com", 443))
        with pytest.raises(RuntimeError, match="forbids"):
            boto3.client("sesv2", region_name="eu-west-1")


def test_unscorable_provider_payload_fails_instead_of_becoming_abstention():
    with pytest.raises(ValueError, match="Unscorable"):
        sent_action({"Content": {"Simple": {"Body": {"Text": {"Data": "Malformed"}}}},
                     "Destination": {"ToAddresses": ["client@example.com"]}})


def test_failed_result_is_retained_with_checksums_and_cannot_be_overwritten(tmp_path, result):
    failed = copy.deepcopy(result)
    failed["candidate_acceptance"] = "FAIL"
    first, second = tmp_path / "first", tmp_path / "second"
    for path in (first, second):
        ar2.persist(failed, path, {"input": "abc"}, {"candidate_sha": "a" * 40})
    assert (first / "result.json").read_bytes() == (second / "result.json").read_bytes()
    assert json.loads((first / "result.json").read_bytes())["candidate_acceptance"] == "FAIL"
    for row in (first / "SHA256SUMS").read_text().splitlines():
        digest, name = row.split("  ")
        assert ar2.sha256((first / name).read_bytes()) == digest
    with pytest.raises(FileExistsError):
        ar2.persist(result, first, {}, {})
    assert json.loads((first / "result.json").read_bytes())["candidate_acceptance"] == "FAIL"


def test_cli_refuses_local_execution(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr("sys.argv", ["ar2", "--candidate-sha", "a" * 40,
                                     "--output", str(tmp_path / "not-created")])
    with pytest.raises(SystemExit) as error:
        ar2.main()
    assert error.value.code == 2
    assert not (tmp_path / "not-created").exists()


def test_workflow_retains_failures_and_checks_exact_candidate():
    workflow = (Path(__file__).parents[1] / ".github/workflows/ar2-evaluation.yml").read_text()
    assert "ref: ${{ env.CANDIDATE_SHA }}" in workflow
    assert "pull_request.head.sha || github.sha" in workflow
    assert "cmp ar2-output/result.json ar2-repeat/result.json" in workflow
    assert "if: always()" in workflow
    assert "retention-days: 90" in workflow
    assert "id-token:" not in workflow and "secrets." not in workflow


def test_result_leaves_real_ai_and_human_benefit_unmeasured(result):
    assert result["remaining_gates"]["C1_real_AI"] == "NOT_MEASURED"
    assert result["remaining_gates"]["human_benefit"] == "NOT_MEASURED"
    assert "not an industry" in __import__(
        "evaluation.reference_baseline", fromlist=["__doc__"],
    ).__doc__
