"""Offline collector contract only; fake SDK responses are never real model evidence."""

import base64
import copy
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from evaluation import ar3
from evaluation import ar3_collect as collector

NOW = datetime(2026, 9, 11, tzinfo=UTC)
SHA = "a" * 40


@pytest.fixture(autouse=True)
def no_cloud_or_network():
    with ar3.offline_only():
        yield


@pytest.fixture
def prepared():
    exported = collector.export_plan()
    ctx = {"event": "workflow_dispatch", "repository": "upgradedev/archon-aws-strands",
           "actor": "parent-fixture", "run_number": "417", "run_attempt": "1",
           "workflow_ref": "upgradedev/archon-aws-strands/.github/workflows/ci.yml@refs/heads/test",
           "run_id": "123456", "sha": SHA}
    grant = {"schema": "archon-bounded-converse-v1", "candidate_sha": SHA,
             "instrument_sha": "deaf7bd57367ab5b35e964663a92a456ea120762",
             "protocol_sha256": "d62375bff7a023b87a252be32c2b3168ac6048cd2c0f7d7e77d0ae0791ff43d5",
             "plan_sha256": exported["plan_sha256"], "model_id": "eu.anthropic.claude-opus-5",
             "region": "eu-west-1", "max_calls": 12, "max_output_tokens": 4000,
             "max_input_tokens": 20000, "max_seconds": 900,
             "input_bound_method": "2x-serialized-utf8-bytes-plus-4096-parent-verified-v1",
             "input_bound_verified": True, "billing_assumptions_verified": True,
             "service_tier": "standard_default",
             "thinking_policy": "FROZEN_PROVIDER_DEFAULT_NO_OVERRIDE",
             "repository": ctx["repository"], "actor": "parent-fixture", "run_number": "417",
             "workflow_ref": ctx["workflow_ref"], "run_attempt": "1",
             "expires_utc": "2026-09-11T00:30:00Z", "grant_id": "FAKE-OFFLINE-ONLY",
             "parent_budget_ledger_ref": "fixture-not-a-real-reservation",
             "price_evidence": "offline fixture reference, not approved live prices",
             "input_bound_evidence": "offline fixture, not approved live assumption",
             "budget_usd": "3.00", "input_usd_per_million": "5.50",
             "output_usd_per_million": "27.50"}
    return exported, ctx, grant


class FakeClient:
    def __init__(self, answer=None):
        self.requests = []
        self.answer = answer or (lambda request: ar3.envelope({"kind": None}))

    def converse(self, **request):
        self.requests.append(copy.deepcopy(request))
        return self.answer(request)


def run_fixture(tmp_path, prepared, client, **kwargs):
    exported, ctx, grant = prepared
    raw = ar3.encoded(grant)
    return collector.collect(tmp_path / "run", exported, raw, ar3.sha256(raw), SHA, ctx,
                             lambda grant: client, execution_mode="OFFLINE_FAKE_NOT_MODEL",
                             now=NOW, **kwargs)


def test_complete_offline_collection_replay_and_stdout_bytes(tmp_path, prepared, capsys):
    client = FakeClient()
    result = run_fixture(tmp_path, prepared, client)
    assert result["collection_complete"] and result["calls_started"] == 12
    assert result["execution_mode"] == "OFFLINE_FAKE_NOT_MODEL"
    assert result["evaluation"]["summary"]["retained"] == 12
    assert result["evaluation"]["summary"]["correct_abstentions"] == 6
    assert result["evaluation"]["summary"]["exact_captures"] == 0
    assert result["evaluation"]["summary"]["contract"] == "FAIL"
    assert client.requests == [row["request"] for row in prepared[0]["plan"]["attempts"]]
    assert all(r["inferenceConfig"] == {"maxTokens": 4000} for r in client.requests)
    output = tmp_path / "run"
    assert len(list(output.rglob("00-unrun.json"))) == 12
    for line in (output / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ")
        assert ar3.sha256((output / name).read_bytes()) == digest
    packet = json.loads((output / "replay.json").read_text())
    assert all(row["request_id"] is None and row["usage"] is None for row in packet["attempts"])
    chunks = [json.loads(line.removeprefix("AR3_JOURNAL "))
              for line in capsys.readouterr().out.splitlines() if line.startswith("AR3_JOURNAL ")]
    name = "journal/converse/00/03-response.json"
    raw = b"".join(base64.b64decode(c["base64"]) for c in chunks if c["file"] == name)
    assert raw == (output / name).read_bytes()
    with pytest.raises(FileExistsError):
        run_fixture(tmp_path, prepared, client)
    assert len(client.requests) == 12


def test_export_matches_frozen_requests_no_gold_and_reports_finite_cost(prepared, monkeypatch):
    monkeypatch.setattr(ar3, "load_frozen", lambda: pytest.fail("Exporter must not read gold"))
    exported = collector.export_plan()
    assert exported == prepared[0]
    assert len(exported["sizes"]) == 12
    assert exported["totals"]["max_output_tokens"] == 48000
    assert exported["totals"]["max_input_token_bound"] < 20000
    for row, size in zip(exported["plan"]["attempts"], exported["sizes"], strict=True):
        assert size["serialized_request_utf8_bytes"] == len(ar3.encoded(row["request"]))
        assert size["input_token_bound"] == 2 * size["serialized_request_utf8_bytes"] + 4096
        assert size["max_output_tokens"] == 4000
    assert Decimal(exported["reference_only_not_a_grant"]["worst_cost_usd"]) < Decimal("3.00")


@pytest.mark.parametrize("key,value", [
    ("candidate_sha", "b" * 40), ("instrument_sha", "c" * 40), ("protocol_sha256", "d" * 64),
    ("plan_sha256", "e" * 64), ("model_id", "another-model"), ("region", "us-west-2"),
    ("max_output_tokens", 3999), ("max_calls", 13), ("max_seconds", 901),
    ("input_bound_verified", False), ("billing_assumptions_verified", False),
    ("service_tier", "priority"), ("thinking_policy", "disabled"),
    ("max_input_tokens", 1), ("max_input_tokens", True), ("max_input_tokens", 20001),
    ("run_number", "418"), ("run_attempt", "2"), ("actor", "different-person"),
    ("expires_utc", "2026-09-10T00:30:00Z"), ("budget_usd", "0.01"),
    ("budget_usd", "5.01"), ("input_usd_per_million", "NaN"),
    ("output_usd_per_million", "Infinity"), ("input_usd_per_million", "0"),
    ("output_usd_per_million", "-1"), ("output_usd_per_million", 27.5),
])
def test_wrong_binding_or_cost_denied_before_factory(tmp_path, prepared, key, value):
    exported, ctx, grant = prepared
    grant[key] = value
    raw = ar3.encoded(grant)
    with pytest.raises(collector.Denied):
        collector.collect(tmp_path / "denied", exported, raw, ar3.sha256(raw), SHA, ctx,
                          lambda grant: pytest.fail("No SDK factory allowed"),
                          execution_mode="OFFLINE_FAKE_NOT_MODEL", now=NOW)
    assert len(list((tmp_path / "denied").rglob("00-unrun.json"))) == 12
    assert not list((tmp_path / "denied").rglob("02-request.json"))


@pytest.mark.parametrize("mutation", ["hash", "export", "rerun", "push"])
def test_unapproved_bytes_inputs_and_context_are_refused(tmp_path, prepared, mutation):
    exported, ctx, grant = prepared
    raw = ar3.encoded(grant)
    digest = ar3.sha256(raw)
    if mutation == "hash":
        digest = "0" * 64
    elif mutation == "export":
        exported["plan"]["attempts"][0]["request"]["messages"][0]["content"][0]["text"] += "x"
    elif mutation == "rerun":
        ctx["run_attempt"] = "2"
    else:
        ctx["event"] = "push"
    with pytest.raises(collector.Denied):
        collector.collect(tmp_path / "denied", exported, raw, digest, SHA, ctx,
                          lambda grant: pytest.fail("No SDK factory allowed"),
                          execution_mode="OFFLINE_FAKE_NOT_MODEL", now=NOW)


def test_sdk_configuration_one_attempt_no_endpoint_override(monkeypatch):
    captured = {}

    def client(service, **kwargs):
        captured.update(service=service, **kwargs)
        return "stub"

    monkeypatch.setattr("boto3.client", client)
    assert collector.live_client({"region": "eu-west-1"}) == "stub"
    assert captured["config"].retries == {"total_max_attempts": 1, "mode": "standard"}
    assert captured["endpoint_url"] == "https://bedrock-runtime.eu-west-1.amazonaws.com"
    assert captured["config"].read_timeout == 60


def test_sdk_timeout_keeps_unknown_reservation_and_all_unrun_slots(tmp_path, prepared):
    def failed(request):
        raise TimeoutError("synthetic unknown response")

    client = FakeClient(failed)
    result = run_fixture(tmp_path, prepared, client)
    assert result["calls_started"] == len(client.requests) == 1
    assert not result["collection_complete"]
    assert result["evaluation"]["summary"]["statuses"]["execution_error"] == 12
    assert Decimal(result["started_reserved_usd"]) > 0
    packet = json.loads((tmp_path / "run/replay.json").read_text())
    assert packet["attempts"][0]["status"] == "unknown_outcome"
    assert sum(r["status"] == "unrun" for r in packet["attempts"]) == 11


@pytest.mark.parametrize("field,value", [("outputTokens", 4001), ("cacheWriteInputTokens", 1)])
def test_billing_boundary_violation_retains_response_and_stops(tmp_path, prepared, field, value):
    response = ar3.envelope({"kind": None})
    response["usage"] = {"inputTokens": 50, "outputTokens": 1, field: value}
    response["ResponseMetadata"] = {"RequestId": "FAKE-request", "HTTPStatusCode": 200,
                                    "RetryAttempts": 0}
    result = run_fixture(tmp_path, prepared, FakeClient(lambda request: response))
    assert result["calls_started"] == 1 and not result["collection_complete"]
    packet = json.loads((tmp_path / "run/replay.json").read_text())
    assert packet["attempts"][0]["request_id"] == "FAKE-request"
    assert packet["attempts"][0]["usage"] == response["usage"]
    assert (tmp_path / "run/journal/converse/00/03-response.json").read_bytes() == (
        ar3.encoded(response))


def test_reasoning_bytes_and_malformed_model_fields_are_not_repaired(tmp_path, prepared):
    response = ar3.envelope({"send": True})
    response["output"]["message"]["content"].append({
        "reasoningContent": {"redactedContent": b"\x00\xff\x01"}})
    result = run_fixture(tmp_path, prepared, FakeClient(lambda request: response))
    assert result["calls_started"] == 12
    assert result["evaluation"]["summary"]["statuses"]["invalid_response"] == 12
    assert result["evaluation"]["summary"]["correct_abstentions"] == 0
    saved = json.loads((tmp_path / "run/journal/converse/00/03-response.json").read_bytes())
    binary = saved["output"]["message"]["content"][1]["reasoningContent"]["redactedContent"]
    assert base64.b64decode(binary["__sdk_binary_base64__"]) == b"\x00\xff\x01"


def test_durable_write_failure_prevents_inference(tmp_path, prepared, monkeypatch):
    original = collector.Journal.write

    def fail(self, name, data):
        if name.endswith("02-request.json"):
            raise ar3.EvidenceWriteError("synthetic disk failure")
        return original(self, name, data)

    monkeypatch.setattr(collector.Journal, "write", fail)
    client = FakeClient()
    with pytest.raises(ar3.EvidenceWriteError):
        run_fixture(tmp_path, prepared, client)
    assert not client.requests
    assert (tmp_path / "run/journal/converse/00/01-reserved.json").is_file()


def test_stdout_backup_failure_stops_before_inference(tmp_path, prepared, monkeypatch):
    def broken_stdout(*args, **kwargs):
        raise BrokenPipeError("synthetic stdout failure")

    monkeypatch.setattr("builtins.print", broken_stdout)
    client = FakeClient()
    with pytest.raises(BrokenPipeError):
        run_fixture(tmp_path, prepared, client)
    assert not client.requests


def test_interrupt_after_response_retains_raw_before_inspection(tmp_path, prepared, monkeypatch):
    def interrupted(*args):
        raise KeyboardInterrupt("synthetic inspection interruption")

    monkeypatch.setattr(collector, "inspect_response", interrupted)
    client = FakeClient()
    with pytest.raises(KeyboardInterrupt):
        run_fixture(tmp_path, prepared, client)
    assert len(client.requests) == 1
    assert (tmp_path / "run/journal/converse/00/03-response.json").is_file()
    assert not (tmp_path / "run/result.json").exists()
    assert len(list((tmp_path / "run").rglob("00-unrun.json"))) == 12


def test_deadline_keeps_twelve_unrun_cases(tmp_path, prepared):
    times = iter([0, 900])
    client = FakeClient()
    result = run_fixture(tmp_path, prepared, client, clock=lambda: next(times))
    assert result["calls_started"] == 0 and not client.requests
    assert result["evaluation"]["summary"]["retained"] == 12
    assert not result["collection_complete"]


def test_accidental_real_factory_is_blocked_by_offline_fence(tmp_path, prepared):
    exported, ctx, grant = prepared
    raw = ar3.encoded(grant)
    result = collector.collect(tmp_path / "run", exported, raw, ar3.sha256(raw), SHA, ctx,
                               collector.live_client, execution_mode="OFFLINE_DENIAL_FIXTURE",
                               now=NOW)
    assert result["calls_started"] == 0
    assert result["evaluation"]["summary"]["statuses"]["execution_error"] == 12


def test_prepare_cli_is_inert_and_exact_source_bound(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    output = tmp_path / "plan.json"
    monkeypatch.setattr(sys, "argv", ["collector", "prepare", "--candidate-sha",
                                    ar3.git("rev-parse", "HEAD"), "--output", str(output)])
    # The product has intentionally changed. The frozen collector MUST refuse
    # it, including prepare: never repin an exposed instrument to manufacture green CI.
    with pytest.raises(subprocess.CalledProcessError) as denied:
        collector.main()
    assert denied.value.returncode == 1 and collector.INSTRUMENT_SHA in denied.value.cmd
    assert not output.exists()
    monkeypatch.setattr(sys, "argv", ["collector", "collect", "--candidate-sha", "b" * 40])
    with pytest.raises(collector.Denied, match="exact checked-out"):
        collector.main()


def test_frozen_compatible_snapshot_still_prepares_the_identical_inert_requests(tmp_path):
    # Positive control executes the historical collector and imports its own src.
    # No frozen file is edited; the worktree is created only on the CI runner.
    compatible = "d8194c0413d5414e3acf071f55efe2d820565af7"
    checkout = tmp_path / "frozen-compatible"
    output = tmp_path / "frozen-plan.json"
    ar3.git("worktree", "add", "--detach", str(checkout), compatible)
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "evaluation.ar3_collect", "prepare", "--candidate-sha",
             compatible, "--output", str(output)], cwd=checkout, check=True,
            env={**os.environ, "GITHUB_ACTIONS": "true", "PYTHONPATH": str(checkout / "src")},
            capture_output=True, text=True,
        )
        assert completed.returncode == 0
        assert json.loads(output.read_text()) == collector.export_plan()
    finally:
        ar3.git("worktree", "remove", str(checkout))


def test_process_kill_leaves_started_and_unrun_not_success(tmp_path, prepared):
    exported, ctx, grant = prepared
    config = tmp_path / "fixture.json"
    config.write_bytes(ar3.encoded({"export": exported, "context": ctx, "grant": grant}))
    script = """
import json, sys, time
from datetime import UTC, datetime
from pathlib import Path
from evaluation import ar3
from evaluation import ar3_collect as c
fixture = json.loads(Path(sys.argv[1]).read_text())
output = Path(sys.argv[2])
class Fake:
    calls = 0
    def converse(self, **request):
        self.calls += 1
        if self.calls == 2:
            (output / 'kill-ready').write_text('fixture')
            time.sleep(60)
        return ar3.envelope({'kind': None})
raw = ar3.encoded(fixture['grant'])
with ar3.offline_only():
    c.collect(output, fixture['export'], raw, ar3.sha256(raw), 'a'*40,
              fixture['context'], lambda grant: Fake(), execution_mode='OFFLINE_KILL_FIXTURE',
              now=datetime(2026,9,11,tzinfo=UTC))
"""
    output = tmp_path / "killed"
    child = subprocess.Popen([sys.executable, "-c", script, str(config), str(output)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        until = time.monotonic() + 15
        while not (output / "kill-ready").exists() and child.poll() is None:
            if time.monotonic() > until:
                pytest.fail("Child did not reach second fake call")
            time.sleep(0.01)
        assert (output / "kill-ready").exists()
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
        child.stderr.close()
    assert (output / "journal/converse/00/03-response.json").exists()
    assert (output / "journal/converse/01/02-request.json").exists()
    assert not (output / "journal/converse/02/01-reserved.json").exists()
    assert len(list(output.rglob("00-unrun.json"))) == 12
    assert not (output / "result.json").exists()


def test_manual_job_is_separate_and_source_job_cannot_activate():
    text = (ar3.ROOT / ".github/workflows/ci.yml").read_text()
    live = text.split("  ar3-parent-collection:", 1)[1].split("  ar3-source-preparation:", 1)[0]
    source = text.split("  ar3-source-preparation:", 1)[1]
    assert "github.event_name == 'workflow_dispatch'" in live
    assert "github.run_attempt == 1" in live and "environment: ar3-bounded-evaluation" in live
    assert live.index(" preflight ") < live.index("configure-aws-credentials")
    assert "bedrock:InvokeModel" in live and "inline-session-policy:" in live
    assert '"Action":"bedrock:*"' not in live
    assert "if: always()" in live and "retention-days: 90" in live
    assert "id-token:" not in source and "AR3_GRANT_JSON:" not in source
    assert "'evaluation.ar3_collect', 'prepare'" in source
    assert "collector.verify_source(candidate)" in source
    assert "SOURCE_CHANGED_COLLECTION_DENIED" in source
    assert "'evaluation.ar3_collect', 'collect'" not in source
    assert "ar3_collect collect" not in source and "collector.live_client" not in source
