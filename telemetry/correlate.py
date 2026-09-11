"""Offline API response -> runtime receipt -> Lambda text REPORT join. No AWS client."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from .lambda_entry import HEADERS, PATTERNS, PREFIX, SCHEMA, valid

IDENTITY = ("source_sha", "function_arn", "function_version", "log_group")
NUMBER = r"[0-9]{1,8}(?:\.[0-9]{1,6})?"
REPORT = re.compile(
    rf"REPORT RequestId: (?P<request_id>{PATTERNS['request_id']})\s+"
    rf"Duration: (?P<duration_ms>{NUMBER}) ms\s+"
    r"Billed Duration: (?P<billed_duration_ms>[0-9]{1,8}) ms\s+"
    r"Memory Size: (?P<memory_mb>[0-9]{1,5}) MB\s+"
    r"Max Memory Used: (?P<max_memory_used_mb>[0-9]{1,5}) MB"
    rf"(?:\s+Init Duration: (?P<init_duration_ms>{NUMBER}) ms)?"
    r"(?:\s+Status: (?P<runtime_status>success|error|timeout))?"
    r"(?:\s+Error Type: [A-Za-z0-9_.-]{1,100})?\s*"
)


def capture_response(ordinal, status, header_pairs):
    """For a future runner: pass RESPONSE pairs, not request headers. No content retained."""
    selected = []
    for name, value in header_pairs:
        field = HEADERS.get(name.lower())
        if field:
            selected.append([name.lower(), value if valid(field, value) else None])
    return {"ordinal": ordinal, "status": status, "response_headers": selected}


def response_identity(request):
    if not isinstance(request, dict):
        return None
    pairs = request.get("response_headers", [])
    if not isinstance(pairs, list) or len(pairs) != len(HEADERS):
        return None
    values = {}
    for pair in pairs:
        if (not isinstance(pair, list) or len(pair) != 2
                or not isinstance(pair[0], str) or pair[0] not in HEADERS):
            return None
        name, value = pair
        if name in values or not valid(HEADERS[name], value):
            return None
        values[name] = value
    return {HEADERS[name]: value for name, value in values.items()}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def report_fields(message):
    match = REPORT.fullmatch(message)
    if not match:
        return None
    result = match.groupdict()
    for name in ("duration_ms", "billed_duration_ms", "init_duration_ms"):
        if result[name] is not None and Decimal(result[name]) > 3600000:
            return None
    if not 1 <= int(result["memory_mb"]) <= 10240:
        return None
    if int(result["max_memory_used_mb"]) > int(result["memory_mb"]):
        return None
    return result  # Decimal strings with explicit units; no duration -> dollars inference.


def correlate(bundle):
    requests, events = bundle["requests"], bundle["events"]
    expected = bundle["expected_runtime"]
    if not isinstance(requests, list) or not 1 <= len(requests) <= 1000:
        raise ValueError("Expected 1..1000 retained API request slots")
    if not isinstance(events, list) or len(events) > 10000:
        raise ValueError("Expected at most 10000 exported log events")
    expected_known = isinstance(expected, dict) and all(
        valid(key, expected.get(key)) for key in IDENTITY)
    receipts, reports = defaultdict(list), defaultdict(list)
    issues = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            issues.append({"event": index, "reason": "unsupported_event"})
            continue
        message = event.get("message", "")
        if not isinstance(message, str) or len(message.encode()) > 2048:
            issues.append({"event": index, "reason": "unsupported_event"})
            continue
        if message.startswith(PREFIX):
            try:
                receipt = json.loads(message[len(PREFIX):], object_pairs_hook=unique_object)
                if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
                    raise ValueError("schema")
                if not valid("request_id", receipt.get("request_id")):
                    raise ValueError("request identity")
                receipts[receipt["request_id"]].append((event, receipt))
            except ValueError:
                issues.append({"event": index, "reason": "malformed_receipt"})
        elif message.startswith("REPORT "):
            report = report_fields(message)
            if report is None:
                issues.append({"event": index, "reason": "unsupported_report"})
            else:
                reports[report["request_id"]].append((event, report))
        elif '"platform.report"' in message:
            issues.append({"event": index, "reason": "json_report_not_supported"})
    identities = [response_identity(request) for request in requests]
    counts = Counter(value["request_id"] for value in identities if value)
    rows = []
    for ordinal, (request, observed) in enumerate(zip(requests, identities, strict=True), 1):
        errors = []
        row = {"ordinal": ordinal, "request_id": observed["request_id"] if observed else None,
               "matched": False, "report": None, "errors": errors}
        rows.append(row)
        if (not isinstance(request, dict) or type(request.get("ordinal")) is not int
                or request["ordinal"] != ordinal):
            errors.append("invalid_slot_ordinal")
        if not expected_known:
            errors.append("unknown_expected_identity")
        if observed is None:
            errors.append("missing_duplicate_or_invalid_response_identity")
            continue
        request_id = observed["request_id"]
        if counts[request_id] != 1:
            errors.append("duplicate_api_request_id")
        found, billed = receipts[request_id], reports[request_id]
        if len(found) != 1:
            errors.append("missing_receipt" if not found else "duplicate_receipt")
        if len(billed) != 1:
            errors.append("missing_report" if not billed else "duplicate_report")
        if len(found) != 1 or len(billed) != 1 or not expected_known:
            continue
        log, receipt = found[0]
        report_log, report = billed[0]
        if receipt.get("identity_status") != "known" or not all(
                valid(key, receipt.get(key)) for key in PATTERNS):
            errors.append("unknown_runtime_identity")
        if any(receipt.get(key) != expected[key] for key in IDENTITY) or any(
                receipt.get(key) != value for key, value in observed.items()):
            errors.append("runtime_identity_mismatch")
        if (log.get("logGroupName") != expected["log_group"]
                or report_log.get("logGroupName") != expected["log_group"]
                or log.get("logStreamName") != receipt.get("log_stream")
                or report_log.get("logStreamName") != receipt.get("log_stream")):
            errors.append("resource_mismatch")
        status = request.get("status")
        if (type(status) is not int or not 100 <= status <= 599
                or type(receipt.get("status")) is not int or receipt.get("status") != status
                or receipt.get("outcome") != "returned"):
            errors.append("response_status_mismatch")
        if not errors:
            row.update(matched=True, report=report)
    matched = [row for row in rows if row["matched"]]
    return {
        "schema": "archon-x1-correlation-v1", "requests_total": len(rows),
        "matched_requests": len(matched), "unmatched_requests": len(rows) - len(matched),
        "complete": len(matched) == len(rows) and not issues,
        "complete_means": "correlation coverage, not API success or cost completeness",
        "rows": rows, "event_issues": issues,
        "matched_report_billed_duration_ms": str(sum(
            (Decimal(row["report"]["billed_duration_ms"]) for row in matched), Decimal(0))),
        "aws_infrastructure_usd": None, "model_usd": None,
        "cost_status": "UNKNOWN_NOT_DERIVED_FROM_DURATION",
        "limitations": "Join of supplied evidence, not cryptographic origin attestation; "
        "configured source SHA is not a deployment attestation. Text REPORT only. "
        "Lambda duration is neither model latency nor user time; billed duration is not full cost. "
        "Other services, requests, logs, storage, networking, pricing and billing are unmeasured.",
    }


def write_new(path, data):
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def export(source, output):
    with source.open("rb") as handle:
        raw = handle.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("Input exceeds 10 MiB bound")
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "input.json", raw)  # Original bytes durable BEFORE parsing.
    result = correlate(json.loads(raw, object_pairs_hook=unique_object))
    encoded = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    write_new(output / "result.json", encoded)
    manifest = {"input.json": hashlib.sha256(raw).hexdigest(),
                "result.json": hashlib.sha256(encoded).hexdigest()}
    write_new(output / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return 0 if export(args.input, args.output)["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
