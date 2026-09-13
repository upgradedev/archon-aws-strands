"""Synthetic-only correlation controls; no deployment or observed AWS billing evidence."""

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from evaluation.ar3 import offline_only
from telemetry import correlate as instrument
from telemetry import lambda_entry as entry

SHA = "a" * 40
REQUEST = "11111111-2222-4333-8444-555555555555"
SECOND = "66666666-7777-4888-9999-aaaaaaaaaaaa"
ARN = "arn:aws:lambda:eu-west-1:123456789012:function:archon-fixture"
GROUP = "/aws/lambda/archon-fixture"
STREAM = "2026/09/11/[12]abcdef0123456789"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("ARCHON_COMMIT_SHA", SHA)
    with offline_only():
        yield


def context(request_id=REQUEST):
    return SimpleNamespace(aws_request_id=request_id, invoked_function_arn=ARN,
                           function_version="12", log_group_name=GROUP, log_stream_name=STREAM)


def log_event(message):
    return {"logGroupName": GROUP, "logStreamName": STREAM, "message": message}


def bundle():
    runtime = entry.identity(context())
    receipt = {"schema": entry.SCHEMA, **runtime, "identity_status": "known",
               "status": 200, "outcome": "returned"}
    return {
        "expected_runtime": {key: runtime[key] for key in instrument.IDENTITY},
        "requests": [instrument.capture_response(1, 200, [
            (name, runtime[field]) for name, field in entry.HEADERS.items()])],
        "events": [log_event(entry.PREFIX + json.dumps(receipt)), log_event(
            f"REPORT RequestId: {REQUEST}\tDuration: 15.74 ms\tBilled Duration: 147 ms\t"
            "Memory Size: 128 MB\tMax Memory Used: 56 MB\tInit Duration: 130.49 ms\n")],
    }


def test_wrapper_ignores_caller_ids_preserves_contract_and_logs_no_content(monkeypatch, capsys):
    response = {"statusCode": 409, "body": "unchanged-private-output", "isBase64Encoded": False,
                "headers": {"Content-Type": "application/json",
                            "X-Archon-Lambda-Request-Id": SECOND}, "cookies": ["preserved"]}

    def application(event, ctx):
        assert entry.current_context()["request_id"] == REQUEST
        entry.current_context()["request_id"] = "cannot-mutate-context"
        assert entry.current_context()["request_id"] == REQUEST
        assert ctx.aws_request_id == REQUEST and event["body"] == "private-input"
        return response

    monkeypatch.setattr(entry, "application_handler", application)
    event = {"request_id": SECOND, "headers": {"Authorization": "secret-token",
             "x-archon-lambda-request-id": SECOND}, "body": "private-input"}
    observed = entry.handler(event, context())
    assert observed["headers"]["x-archon-lambda-request-id"] == REQUEST
    assert observed["headers"]["Content-Type"] == "application/json"
    assert {k: v for k, v in observed.items() if k != "headers"} == {
        k: v for k, v in response.items() if k != "headers"}
    assert response["headers"]["X-Archon-Lambda-Request-Id"] == SECOND
    assert entry.current_context() is None
    raw = capsys.readouterr().out
    assert len(raw.encode()) <= 2049
    assert not any(value in raw for value in (SECOND, "secret-token", "private-input",
                                              "unchanged-private-output", "Authorization"))
    assert json.loads(raw.removeprefix(entry.PREFIX))["status"] == 409


def test_nested_invocation_context_is_reset_on_exception(monkeypatch, capsys):
    def application(event, ctx):
        if ctx.aws_request_id == SECOND:
            assert entry.current_context()["request_id"] == SECOND
            raise RuntimeError("sensitive-exception-text")
        with pytest.raises(RuntimeError):
            entry.handler({}, context(SECOND))
        assert entry.current_context()["request_id"] == REQUEST
        return {"statusCode": 200, "headers": {}, "body": "ok"}

    monkeypatch.setattr(entry, "application_handler", application)
    entry.handler({}, context())
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2 and "sensitive-exception-text" not in str(lines)
    assert json.loads(lines[0][len(entry.PREFIX):])["outcome"] == "raised"
    assert entry.current_context() is None


@pytest.mark.parametrize("ctx", [None, context("attacker\nFORGED"), context("x" * 10000)])
def test_unknown_context_never_falls_back_to_caller(monkeypatch, capsys, ctx):
    monkeypatch.setattr(entry, "application_handler", lambda *_: {
        "statusCode": 200, "headers": {"x-archon-lambda-request-id": SECOND}, "body": "ok"})
    response = entry.handler({"request_id": SECOND}, ctx)
    assert "x-archon-lambda-request-id" not in response["headers"]
    log = capsys.readouterr().out
    assert SECOND not in log and "attacker" not in log and len(log) < 2048
    assert json.loads(log[len(entry.PREFIX):])["identity_status"] == "unknown"


def test_logger_failure_does_not_change_api_and_oversized_record_is_not_logged(monkeypatch):
    entry.emit({"arbitrary": "x" * 3000})
    monkeypatch.setattr(entry, "application_handler", lambda *_: {"statusCode": True, "body": "ok"})

    def closed(*args, **kwargs):
        raise ValueError("closed output")

    monkeypatch.setattr("builtins.print", closed)
    assert entry.handler({}, context())["body"] == "ok"
    assert entry.current_context() is None


def test_real_handler_to_capture_export_fullflow(tmp_path, monkeypatch, capsys):
    from archon.store.sessions import SQLiteSessions
    from archon.web import api

    monkeypatch.setattr(api, "store", lambda: SQLiteSessions(str(tmp_path / "state.sqlite3")))
    event = {"requestContext": {"http": {"method": "GET", "path": "/api/health"}},
             "headers": {}, "body": ""}
    response = entry.handler(event, context())
    assert response["statusCode"] == 200
    health = json.loads(response["body"])
    assert health["commit"] == SHA and health["live_model"] is False
    data = bundle()
    data["requests"] = [instrument.capture_response(1, 200, response["headers"].items())]
    data["events"][0] = log_event(capsys.readouterr().out.rstrip())
    source = tmp_path / "source.json"
    source.write_bytes(json.dumps(data).encode())
    output = tmp_path / "evidence"
    monkeypatch.setattr(sys, "argv", ["correlate", "--input", str(source), "--output", str(output)])
    assert instrument.main() == 0
    result = json.loads((output / "result.json").read_bytes())
    assert result["complete"] and result["matched_requests"] == result["requests_total"] == 1
    assert result["matched_report_billed_duration_ms"] == "147"
    assert result["rows"][0]["report"]["duration_ms"] == "15.74"
    assert result["rows"][0]["report"]["init_duration_ms"] == "130.49"
    assert result["aws_infrastructure_usd"] is None and result["model_usd"] is None
    assert "NOT_DERIVED_FROM_DURATION" in result["cost_status"]
    for name, sha in json.loads((output / "manifest.json").read_bytes()).items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == sha
    before = (output / "input.json").read_bytes()
    with pytest.raises(FileExistsError):
        instrument.export(source, output)
    assert (output / "input.json").read_bytes() == before


@pytest.mark.parametrize("defect", [
    "missing_header", "duplicate_header", "invalid_header", "missing_receipt", "missing_report",
    "duplicate_receipt", "duplicate_report", "wrong_source", "wrong_function", "wrong_version",
    "wrong_group", "wrong_stream", "unknown_identity", "unknown_expected", "wrong_status",
    "wrong_id", "bad_ordinal", "duplicate_api", "raised",
])
def test_negative_correlations_preserve_request_denominator(defect):
    data = bundle()
    request = data["requests"][0]
    receipt = json.loads(data["events"][0]["message"][len(entry.PREFIX):])
    if defect == "missing_header":
        request["response_headers"].pop()
    elif defect == "duplicate_header":
        request["response_headers"][1] = request["response_headers"][0]
    elif defect == "invalid_header":
        request["response_headers"][0][1] = "caller-secret\ninjection"
    elif defect == "missing_receipt":
        data["events"].pop(0)
    elif defect == "missing_report":
        data["events"].pop()
    elif defect == "duplicate_receipt":
        data["events"].append(copy.deepcopy(data["events"][0]))
    elif defect == "duplicate_report":
        data["events"].append(copy.deepcopy(data["events"][1]))
    elif defect == "wrong_source":
        receipt["source_sha"] = "b" * 40
    elif defect == "wrong_function":
        receipt["function_arn"] = ARN + "-other"
    elif defect == "wrong_version":
        receipt["function_version"] = "13"
    elif defect == "wrong_group":
        data["events"][1]["logGroupName"] += "-other"
    elif defect == "wrong_stream":
        data["events"][1]["logStreamName"] += "-other"
    elif defect == "unknown_identity":
        receipt["identity_status"] = "unknown"
    elif defect == "unknown_expected":
        data["expected_runtime"]["source_sha"] = "unknown"
    elif defect == "wrong_status":
        receipt["status"] = 500
    elif defect == "wrong_id":
        receipt["request_id"] = SECOND
    elif defect == "bad_ordinal":
        request["ordinal"] = 2
    elif defect == "duplicate_api":
        data["requests"].append({**copy.deepcopy(request), "ordinal": 2})
    elif defect == "raised":
        receipt["outcome"] = "raised"
    if defect not in ("missing_receipt", "duplicate_receipt"):
        data["events"][0]["message"] = entry.PREFIX + json.dumps(receipt)
    result = instrument.correlate(data)
    assert result["requests_total"] == len(data["requests"])
    assert result["unmatched_requests"] == len(data["requests"])
    assert not result["complete"] and result["matched_report_billed_duration_ms"] == "0"
    assert all(row["errors"] and row["report"] is None for row in result["rows"])
    assert result["aws_infrastructure_usd"] is None


@pytest.mark.parametrize("message", [
    "REPORT RequestId: unsupported", entry.PREFIX + "{", entry.PREFIX + "[]",
    entry.PREFIX + '{"schema":"wrong"}',
    entry.PREFIX + json.dumps({"schema": entry.SCHEMA, "request_id": "bad"}),
    '{"type":"platform.report","record":{}}', "x" * 2049, None,
])
def test_malformed_or_unsupported_log_format_never_claims_complete(message):
    data = bundle()
    data["events"].append(log_event(message))
    result = instrument.correlate(data)
    assert not result["complete"] and result["event_issues"]
    assert result["requests_total"] == 1


@pytest.mark.parametrize("old,new", [("15.74", "NaN"), ("15.74", "99999999"),
                                     ("128 MB", "0 MB"), ("56 MB", "129 MB")])
def test_invalid_report_numbers_are_unknown(old, new):
    data = bundle()
    data["events"][1]["message"] = data["events"][1]["message"].replace(old, new)
    assert instrument.correlate(data)["unmatched_requests"] == 1


def test_capture_allowlist_retains_duplicate_denial_but_no_secrets():
    captured = instrument.capture_response(1, 200, [("Authorization", "secret"),
        ("Set-Cookie", "private"), ("X-Archon-Lambda-Request-Id", "bad\nvalue"),
        ("x-archon-lambda-request-id", REQUEST)])
    assert captured["response_headers"] == [
        ["x-archon-lambda-request-id", None], ["x-archon-lambda-request-id", REQUEST]]
    assert instrument.response_identity(captured) is None


def test_two_requests_join_by_runtime_id_not_event_order():
    first, second = bundle(), bundle()
    second = json.loads(json.dumps(second).replace(REQUEST, SECOND).replace("147 ms", "947 ms"))
    second["requests"][0]["ordinal"] = 2
    first["requests"].extend(second["requests"])
    first["events"] = [second["events"][1], first["events"][0],
                       log_event("START ignored without inferring usage"),
                       second["events"][0], first["events"][1]]
    result = instrument.correlate(first)
    assert result["complete"] and result["requests_total"] == result["matched_requests"] == 2
    assert [row["report"]["billed_duration_ms"] for row in result["rows"]] == ["147", "947"]
    assert result["matched_report_billed_duration_ms"] == "1094"


@pytest.mark.parametrize("record", [None, {"response_headers": [None, None, None]},
                                    {"response_headers": [[[], "x"], ["x"], []]}])
def test_malformed_request_shape_is_a_retained_unknown_slot(record):
    data = bundle()
    data["requests"] = [record]
    result = instrument.correlate(data)
    assert result["requests_total"] == result["unmatched_requests"] == 1
    assert not result["complete"]


def test_duplicate_json_keys_and_oversized_input_fail_with_no_success(tmp_path):
    source = tmp_path / "duplicate.json"
    source.write_bytes(b'{"requests":[],"requests":[{}]}')
    output = tmp_path / "duplicate"
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        instrument.export(source, output)
    assert (output / "input.json").read_bytes() == source.read_bytes()
    assert not (output / "result.json").exists()
    source.write_bytes(b" " * (10 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="10 MiB"):
        instrument.export(source, tmp_path / "too-large")
    assert not (tmp_path / "too-large").exists()


@pytest.mark.parametrize("field,value", [("requests", []), ("requests", [None] * 1001),
                                        ("events", [None] * 10001)])
def test_finite_export_limits(field, value):
    data = bundle()
    data[field] = value
    with pytest.raises(ValueError):
        instrument.correlate(data)


def test_malformed_input_retained_before_parse_and_interrupted_export(tmp_path, monkeypatch):
    source = tmp_path / "malformed.json"
    source.write_bytes(b'{"broken"')
    output = tmp_path / "malformed"
    with pytest.raises(ValueError):
        instrument.export(source, output)
    assert (output / "input.json").read_bytes() == source.read_bytes()
    assert not (output / "result.json").exists()
    source.write_bytes(json.dumps(bundle()).encode())
    output = tmp_path / "interrupted"

    def interrupted(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(instrument, "correlate", interrupted)
    with pytest.raises(KeyboardInterrupt):
        instrument.export(source, output)
    assert (output / "input.json").read_bytes() == source.read_bytes()
    assert not (output / "manifest.json").exists()


def test_incomplete_cli_and_durable_failure_before_parse(tmp_path, monkeypatch):
    source = tmp_path / "missing.json"
    data = bundle()
    data["events"] = []
    source.write_bytes(json.dumps(data).encode())
    output = tmp_path / "missing"
    monkeypatch.setattr(sys, "argv", ["correlate", "--input", str(source), "--output", str(output)])
    assert instrument.main() == 2

    def failure(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(instrument, "write_new", failure)
    monkeypatch.setattr(instrument, "correlate",
                        lambda _: pytest.fail("parsed before durable write"))
    with pytest.raises(OSError):
        instrument.export(source, tmp_path / "refused")


def test_frozen_instruments_stay_pinned_without_requalifying_the_changed_product():
    root = Path(__file__).resolve().parents[1]
    paths = ["src", "evaluation/ar3.py", "evaluation/ar3_data", "evaluation/ar3_collect.py",
             "evaluation/ar2.py", "frontend/benchmarks", "pyproject.toml", "infra"]
    pinned = "b5df90772c9213ffd5a6120b6ef1dd3a72347028"
    compatible = "d8194c0413d5414e3acf071f55efe2d820565af7"
    subprocess.run(["git", "diff", "--exit-code", pinned, compatible, "--", *paths],
                   cwd=root, check=True)
    # Product evolution is not a telemetry/evaluator rebaseline. Their bytes
    # stay frozen; a changed app cannot reuse the historical qualification.
    frozen = [p for p in paths if p not in {"src", "pyproject.toml"}]
    subprocess.run(["git", "diff", "--exit-code", pinned, "HEAD", "--", *frozen],
                   cwd=root, check=True)
    subprocess.run(["git", "diff", "--exit-code", compatible, "HEAD", "--", "telemetry"],
                   cwd=root, check=True)
    changed = subprocess.run(["git", "diff", "--quiet", pinned, "HEAD", "--", "src"],
                             cwd=root, check=False)
    assert changed.returncode == 1, "New product source is not the frozen qualification"
    workflow = (root / ".github/workflows/ci.yml").read_text()
    assert "ruff check src tests telemetry" in workflow
    assert "pytest tests/test_x1_correlation.py" in workflow
    assert "--cov=telemetry --cov-fail-under=85" in workflow
