"""Fake/already-spent fixtures only. These tests establish an instrument, not AI quality."""

import copy
import json
import socket
import subprocess
import sys
import textwrap

import pytest

from evaluation import ar3


@pytest.fixture
def frozen():
    return ar3.load_frozen()


def fixture_fields():
    # Literal independent test fixture, not constructed from evaluator gold.
    return {"kind": "sales_invoice", "doc_id": "JN-101", "counterparty": "BuildCo",
            "issued": "2026-09-01", "due": "2026-09-20", "net": "100.00",
            "vat": "20.00", "gross": "120.00"}


def valid_response(view):
    return ar3.envelope(ar3.add_literal_citations(fixture_fields(), view))


def test_frozen_hashes_and_prior_commit(frozen):
    protocol, inputs, gold = frozen
    assert len(inputs) == len(gold) == 12
    assert sum(value is not None for value in gold.values()) == 6
    assert protocol["sample_plan"]["retries"] == 0
    ar3.git("merge-base", "--is-ancestor", ar3.PREREGISTRATION, "HEAD")
    assert set(ar3.git("diff-tree", "--no-commit-id", "--name-only", "-r",
                       ar3.PREREGISTRATION).splitlines()) == {
        f"evaluation/ar3_data/{name}" for name in ar3.PINS}


def test_changed_gold_bytes_refused(tmp_path, monkeypatch):
    for name in ar3.PINS:
        (tmp_path / name).write_bytes((ar3.DATA / name).read_bytes())
    (tmp_path / "gold.json").write_text("{}")
    monkeypatch.setattr(ar3, "DATA", tmp_path)
    with pytest.raises(ValueError, match="Frozen bytes"):
        ar3.load_frozen()


def test_null_kind_contract_is_preserved_without_claiming_a_current_reader_bug(frozen):
    _, inputs, _ = frozen
    assert ar3.add_literal_citations({"kind": None}, ar3.source_view(inputs[0])) == {"kind": None}


@pytest.mark.parametrize("index", [6, 10])
def test_real_local_reader_missing_and_unknown_inputs_abstain(frozen, index):
    protocol, inputs, _ = frozen
    row = ar3.observe(inputs[index], protocol, ar3.baseline)
    assert row["status"] == "abstained"
    assert json.loads(row["raw_response"])["output"]["message"]["content"] == [
        {"text": '{"kind": null}'}]


def test_existing_adapter_receives_identical_redacted_request_without_gold(frozen):
    protocol, inputs, gold = frozen
    plan = ar3.request_plan(protocol, inputs)
    seen = []

    def adapter(request, view):
        seen.append(copy.deepcopy(request))
        assert "accounts@buildco.example" not in json.dumps(request)
        assert set(view) == {"source_ref", "revision", "source_sha256", "text"}
        assert "gold.json" not in json.dumps(request)
        assert "doc-01" not in json.dumps(request)
        return ar3.encoded(valid_response(view)).decode()

    row = ar3.observe(inputs[0], protocol, adapter)
    assert row["document"] == gold["doc-01"]
    assert row["request"] == seen[0] == plan["attempts"][0]["request"]
    assert row["request_sha256"] == plan["attempts"][0]["request_sha256"]
    assert row["usage"] is None and row["model_cost_usd"] is None
    assert row["response_sha256"] == ar3.sha256(row["raw_response"].encode())


@pytest.mark.parametrize("fault", [
    "source_ref", "source_sha256", "revision", "missing", "quote", "offset", "empty",
    "bool_offset", "outside", "field", "action", "tool", "truncated", "blocks", "kind",
    "unknown_stop", "missing_stop",
])
def test_deliberate_unsafe_results_never_count_as_captures_or_correct_abstention(frozen, fault):
    protocol, inputs, _ = frozen

    def adapter(request, view):
        response = valid_response(view)
        fields = json.loads(response["output"]["message"]["content"][0]["text"])
        if fault in {"source_ref", "source_sha256"}:
            fields[fault] = "different-source"
        elif fault == "revision":
            fields["revision"] = 0
        elif fault == "missing":
            del fields["citations"]["gross"]
        elif fault == "quote":
            fields["citations"]["gross"]["quote"] = "unrelated quote"
        elif fault == "offset":
            fields["citations"]["gross"]["start"] += 1
        elif fault == "empty":
            fields["citations"]["gross"]["end"] = fields["citations"]["gross"]["start"]
        elif fault == "bool_offset":
            fields["citations"]["gross"]["start"] = True
        elif fault == "outside":
            fields["citations"]["gross"]["end"] = len(view["text"]) + 50
        elif fault == "field":
            fields["gross"] = "999.00"
        elif fault == "action":
            fields["send"] = True
        elif fault == "kind":
            fields["kind"] = "payment_order"
        response = ar3.envelope(fields)
        if fault == "tool":
            response["output"]["message"]["content"] = [{"toolUse": {"name": "send"}}]
        elif fault == "truncated":
            response["stopReason"] = "max_tokens"
        elif fault == "blocks":
            response["output"]["message"]["content"] *= 2
        elif fault == "unknown_stop":
            response["stopReason"] = "not_a_final_reason"
        elif fault == "missing_stop":
            del response["stopReason"]
        return ar3.encoded(response).decode()

    row = ar3.observe(inputs[0], protocol, adapter)
    assert row["status"] == "invalid_response", row
    assert row["document"] is None and row["raw_response"]


@pytest.mark.parametrize("raw", ["not JSON", "[]", '{"a":1,"a":2}', '{"n":NaN}',
                                 '{"output":{"message":{"content":[]}}}'])
def test_malformed_response_bytes_retained(frozen, raw):
    protocol, inputs, _ = frozen
    row = ar3.observe(inputs[0], protocol, lambda request, view: raw)
    assert row["status"] == "invalid_response"
    assert row["raw_response"] == raw
    assert row["response_sha256"] == ar3.sha256(raw.encode())


def test_all_failures_preserve_fixed_denominators(frozen):
    protocol, inputs, gold = frozen

    def broken(request, view):
        raise TimeoutError("already-spent fixture failure")

    result = ar3.evaluate(inputs, gold, protocol, broken)
    assert len(result["attempts"]) == 12
    assert result["summary"]["statuses"]["execution_error"] == 12
    assert result["summary"]["correct_abstentions"] == 0
    assert result["summary"]["missed_or_wrong_opportunities"] == 6
    assert result["summary"]["contract"] == "FAIL"


def test_baseline_completes_without_improving_or_hiding_its_limits(frozen):
    protocol, inputs, gold = frozen
    result = ar3.evaluate(inputs, gold, protocol, ar3.baseline)
    summary = result["summary"]
    assert summary["planned"] == summary["retained"] == 12
    assert summary["contract"] == "FAIL"  # Instrument completion is not baseline superiority.
    assert result["attempts"][0]["document"] == gold["doc-01"]
    assert result["attempts"][3]["status"] == "abstained"  # unsupported paraphrase
    assert result["attempts"][8]["status"] == "document"  # first of conflicting totals
    assert summary["false_positives"] >= 1


def test_all_abstain_is_not_quality_and_missing_metadata_does_not_block(frozen):
    protocol, inputs, gold = frozen
    result = ar3.evaluate(inputs, gold, protocol,
                          lambda request, view: ar3.encoded(ar3.envelope({"kind": None})).decode())
    assert result["summary"]["exact_captures"] == 0
    assert result["summary"]["correct_abstentions"] == 6
    assert result["summary"]["statuses"]["abstained"] == 12
    assert result["summary"]["contract"] == "FAIL"


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra", "reorder", "hash"])
def test_offline_replay_rejects_noncomparable_cohorts(frozen, mutation):
    protocol, inputs, gold = frozen
    attempts = ar3.request_plan(protocol, inputs)["attempts"]
    for row in attempts:
        row["raw_response"] = ar3.encoded(ar3.envelope({"kind": None})).decode()
    if mutation == "missing":
        attempts.pop()
    elif mutation == "duplicate":
        attempts[1] = copy.deepcopy(attempts[0])
    elif mutation == "extra":
        attempts.append(copy.deepcopy(attempts[0]))
    elif mutation == "reorder":
        attempts.reverse()
    else:
        attempts[0]["request_sha256"] = "wrong"
    replay = ar3.Replay({"attempts": attempts}, inputs)
    result = ar3.evaluate(inputs, gold, protocol, replay)
    assert result["summary"]["retained"] == 12
    assert result["summary"]["statuses"]["execution_error"] >= 1
    assert result["summary"]["contract"] == "FAIL"


def test_valid_fake_replay_preserves_usage_and_exact_request_binding(frozen):
    protocol, inputs, gold = frozen
    baseline = ar3.evaluate(inputs, gold, protocol, ar3.baseline)
    replay = ar3.Replay({"attempts": baseline["attempts"]}, inputs)
    replayed = ar3.evaluate(inputs, gold, protocol, replay)
    assert replayed == baseline
    view = ar3.source_view(inputs[0])
    response = valid_response(view)
    response["usage"] = {"inputTokens": 123, "outputTokens": 45}
    row = ar3.observe(inputs[0], protocol, lambda request, view: ar3.encoded(response).decode())
    assert row["usage"] == {"inputTokens": 123, "outputTokens": 45}
    assert row["model_cost_usd"] is None


def test_prior_inventory_hashes_are_retained_not_reinterpreted_as_comparable_evidence():
    inventory = json.loads((ar3.DATA / "prior-inventory.json").read_text())
    assert inventory["comparable_replay_count"] == 0
    for entry in inventory["source_entries"]:
        data = (ar3.ROOT / entry["path"]).read_bytes().replace(b"\r\n", b"\n")
        assert ar3.sha256(data) == entry["sha256_lf"]
        assert entry["model_call_run_url"] is None


def test_source_workflow_has_no_live_activation_and_uploads_failure_evidence():
    workflow = (ar3.ROOT / ".github/workflows/ci.yml").read_text()
    job = workflow.split("  ar3-source-preparation:", 1)[1]
    assert "id-token:" not in job and "secrets." not in job
    assert "workflow_dispatch" in job and "!= 'workflow_dispatch'" in job
    assert "if: always()" in job and "retention-days: 90" in job
    assert "python -m evaluation.ar3" in job


def test_shared_offline_fence_denies_network(frozen):
    protocol, inputs, gold = frozen

    def network(request, view):
        socket.create_connection(("127.0.0.1", 80))

    result = ar3.evaluate(inputs, gold, protocol, network)
    assert result["summary"]["statuses"]["execution_error"] == 12
    assert all("forbids network" in row["error"] for row in result["attempts"])


@pytest.mark.parametrize("failed_step", ["01-started.json", "02-request.json"])
def test_durable_checkpoint_failure_prevents_adapter(frozen, tmp_path, monkeypatch, failed_step):
    protocol, inputs, gold = frozen
    journal = ar3.Journal(tmp_path / "run", inputs, ["baseline"])
    original = journal.write
    calls = []

    def fail(name, data):
        if name.endswith(failed_step):
            raise ar3.EvidenceWriteError("synthetic durable write failure")
        original(name, data)

    monkeypatch.setattr(journal, "write", fail)
    with pytest.raises(ar3.EvidenceWriteError):
        ar3.evaluate(inputs, gold, protocol, lambda request, view: calls.append(request),
                     journal, "baseline")
    assert calls == []
    assert len(list(journal.output.rglob("00-unrun.json"))) == 12
    assert not (journal.output / "result.json").exists()


def test_raw_response_is_durable_before_parser_interrupt(frozen, tmp_path, monkeypatch):
    protocol, inputs, gold = frozen
    journal = ar3.Journal(tmp_path / "run", inputs, ["baseline"])

    def interrupted(raw, view):
        raise KeyboardInterrupt("synthetic parser interruption")

    monkeypatch.setattr(ar3, "validate_response", interrupted)
    with pytest.raises(KeyboardInterrupt):
        ar3.evaluate(inputs, gold, protocol, lambda request, view: "malformed raw bytes",
                     journal, "baseline")
    slot = journal.output / "journal/baseline/00"
    assert (slot / "02-request.json").exists()
    assert (slot / "03-response.txt").read_bytes() == b"malformed raw bytes"
    assert not (slot / "04-result.json").exists()
    assert not (journal.output / "result.json").exists()


def test_process_kill_retains_completed_started_and_unrun_slots(tmp_path):
    output = tmp_path / "killed"
    script = textwrap.dedent('''
        import sys
        import time
        from pathlib import Path
        from evaluation import ar3
        protocol, inputs, gold = ar3.load_frozen()
        journal = ar3.Journal(Path(sys.argv[1]), inputs, ["baseline"])
        calls = 0
        def adapter(request, view):
            global calls
            calls += 1
            if calls == 2:
                print("second-adapter-started", flush=True)
                time.sleep(60)
            return ar3.baseline(request, view)
        result = ar3.evaluate(inputs, gold, protocol, adapter, journal, "baseline")
        journal.finalize(result)
    ''')
    child = subprocess.Popen([sys.executable, "-u", "-c", script, str(output)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "second-adapter-started"
        child.kill()
        child.wait(timeout=5)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        child.stdout.close()
        child.stderr.close()
    slots = output / "journal/baseline"
    assert len(list(slots.rglob("00-unrun.json"))) == 12
    assert json.loads((slots / "00/04-result.json").read_text())["status"] == "document"
    assert (slots / "00/03-response.txt").is_file()
    assert (slots / "01/02-request.json").is_file()
    assert not (slots / "01/03-response.txt").exists()
    assert not (slots / "02/01-started.json").exists()
    assert not (output / "result.json").exists()
    assert not (output / "SHA256SUMS").exists()


def test_replay_original_bytes_retained_before_parsing_or_evaluation(frozen, tmp_path, monkeypatch):
    replay = tmp_path / "prior.json"
    replay.write_bytes(b"not JSON, retained exactly\xff")
    output = tmp_path / "evidence"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(sys, "argv", ["ar3", "--candidate-sha", ar3.git("rev-parse", "HEAD"),
                                    "--output", str(output), "--replay", str(replay)])

    def interrupted(*args, **kwargs):
        assert (output / "replay-input.json").read_bytes() == replay.read_bytes()
        raise KeyboardInterrupt("before first adapter")

    monkeypatch.setattr(ar3, "load_frozen", lambda: frozen)
    monkeypatch.setattr(ar3, "strict_json", interrupted)
    with pytest.raises(KeyboardInterrupt):
        ar3.main()
    assert len(list(output.rglob("00-unrun.json"))) == 48
    assert not (output / "result.json").exists()


def test_source_cli_persists_baseline_controls_requests_and_all_hashes(tmp_path, monkeypatch):
    output = tmp_path / "evidence"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(sys, "argv", ["ar3", "--candidate-sha", ar3.git("rev-parse", "HEAD"),
                                    "--output", str(output)])
    assert ar3.main() == 0
    result = json.loads((output / "result.json").read_text())
    assert result["instrument_valid"] is True
    assert result["remaining_gates"] == {"AR3": "OPEN", "C1": "OPEN", "activation": "OWNER_GATED"}
    assert result["methods"]["baseline"]["summary"]["retained"] == 12
    assert result["real_model_measurement"].startswith("NOT_MEASURED")
    for line in (output / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ")
        assert ar3.sha256((output / name).read_bytes()) == digest
    original = (output / "result.json").read_bytes()
    with pytest.raises(FileExistsError):
        ar3.main()
    assert (output / "result.json").read_bytes() == original


def test_cli_refuses_local_execution_before_evaluation(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    result = subprocess.run([sys.executable, "-m", "evaluation.ar3", "--candidate-sha", "wrong",
                             "--output", str(tmp_path / "refused")], capture_output=True, text=True)
    assert result.returncode != 0 and "source CI-only" in result.stderr
    assert not (tmp_path / "refused").exists()
