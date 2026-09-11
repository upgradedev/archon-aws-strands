"""One-shot, parent-granted Converse collection; no activation on import or source CI."""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import re
import time
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from importlib.metadata import version
from pathlib import Path

from botocore.config import Config

from . import ar3

INSTRUMENT_SHA = "deaf7bd57367ab5b35e964663a92a456ea120762"
REPOSITORY = "upgradedev/archon-aws-strands"
MAX_INPUT = 20000
MAX_OUTPUT = 4000
CALLS = 12
SECONDS = 900
BOUND = "2x-serialized-utf8-bytes-plus-4096-parent-verified-v1"
MODE = "DIRECT_BEDROCK_CONVERSE_NO_STRANDS_LOOP"
REFERENCE_RATES = {"input_usd_per_million": "5.50", "output_usd_per_million": "27.50"}


class Denied(ValueError):
    """No inference is permitted by this request/grant/context."""


class Journal(ar3.Journal):
    def write(self, name, data):
        super().write(name, data)
        # Chunked exact bytes, flushed before proceeding. Backup, not guaranteed log delivery.
        for offset in range(0, len(data), 3072):
            print("AR3_JOURNAL " + json.dumps({"file": name, "sha256": ar3.sha256(data),
                  "offset": offset, "bytes": len(data),
                  "base64": base64.b64encode(data[offset:offset + 3072]).decode()}), flush=True)


def frozen_inputs():
    """Prompt preparation reads inputs/protocol only, never gold."""
    values = []
    for name in ("protocol.json", "inputs.json"):
        raw = (ar3.DATA / name).read_bytes()
        if ar3.sha256(raw) != ar3.PINS[name]:
            raise Denied(f"Frozen input changed: {name}")
        values.append(ar3.strict_json(raw.decode()))
    return values


def export_plan():
    protocol, inputs = frozen_inputs()
    with ar3.offline_only():
        plan = ar3.request_plan(protocol, inputs)
    sizes = []
    for row in plan["attempts"]:
        request = row["request"]
        data = ar3.encoded(request)
        sizes.append({"case_id": row["case_id"], "request_sha256": ar3.sha256(data),
                      "serialized_request_utf8_bytes": len(data),
                      "prompt_utf8_bytes": len(
                          request["messages"][0]["content"][0]["text"].encode()),
                      "input_token_bound": 2 * len(data) + 4096,
                      "max_output_tokens": request["inferenceConfig"]["maxTokens"]})
    return {"instrument_sha": INSTRUMENT_SHA, "mode": MODE, "bound_method": BOUND,
            "bound_status": "CONDITIONAL_ON_PARENT_MODEL_SPECIFIC_VERIFICATION_NOT_TOKEN_COUNT",
            "plan_sha256": ar3.sha256(ar3.encoded(plan)), "plan": plan, "sizes": sizes,
            "totals": {"request_bytes": sum(s["serialized_request_utf8_bytes"] for s in sizes),
                       "max_request_bytes": max(s["serialized_request_utf8_bytes"] for s in sizes),
                       "input_token_bound": sum(s["input_token_bound"] for s in sizes),
                       "max_input_token_bound": max(s["input_token_bound"] for s in sizes),
                       "max_output_tokens": CALLS * MAX_OUTPUT},
            "reference_only_not_a_grant": {**REFERENCE_RATES, "worst_cost_usd": str(sum(
                (cost(s["input_token_bound"], MAX_OUTPUT, REFERENCE_RATES) for s in sizes),
                Decimal(0))), "status": "CONDITIONAL_RATE_BASED_ESTIMATE_NOT_SPEND_OR_AUTHORITY"}}


def sdk_config():
    # total_max_attempts includes the initial request. No SDK or application retries.
    return Config(retries={"total_max_attempts": 1, "mode": "standard"},
                  connect_timeout=5, read_timeout=60, max_pool_connections=1)


def amount(value):
    if (not isinstance(value, str) or len(value) > 20
            or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,6})?", value)):
        raise Denied("Dollar values/rates must be finite nonnegative decimal strings")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise Denied("Invalid decimal") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise Denied("Zero/negative rates or budget are not authorization")
    return parsed


def cost(input_tokens, output_tokens, grant):
    value = (input_tokens * amount(grant["input_usd_per_million"])
             + output_tokens * amount(grant["output_usd_per_million"])) / Decimal(1000000)
    return value.quantize(Decimal("0.000001"), rounding=ROUND_CEILING)


def context():
    return {key: os.getenv(name, "") for key, name in {
        "event": "GITHUB_EVENT_NAME", "repository": "GITHUB_REPOSITORY",
        "actor": "GITHUB_ACTOR", "run_number": "GITHUB_RUN_NUMBER",
        "run_attempt": "GITHUB_RUN_ATTEMPT", "workflow_ref": "GITHUB_WORKFLOW_REF",
        "run_id": "GITHUB_RUN_ID", "sha": "GITHUB_SHA"}.items()}


def validate(grant_bytes, approved_hash, exported, candidate, ctx, now=None):
    if not re.fullmatch(r"[a-f0-9]{64}", approved_hash or ""):
        raise Denied("Missing parent-configured exact grant hash")
    if ar3.sha256(grant_bytes) != approved_hash:
        raise Denied("Grant bytes do not match parent configuration")
    grant = ar3.strict_json(grant_bytes.decode())
    required = {
        "schema": "archon-bounded-converse-v1", "candidate_sha": candidate,
        "instrument_sha": INSTRUMENT_SHA, "protocol_sha256": ar3.PINS["protocol.json"],
        "plan_sha256": exported["plan_sha256"], "model_id": "eu.anthropic.claude-opus-5",
        "region": "eu-west-1", "max_calls": CALLS, "max_output_tokens": MAX_OUTPUT,
        "max_seconds": SECONDS, "input_bound_method": BOUND, "input_bound_verified": True,
        "billing_assumptions_verified": True, "service_tier": "standard_default",
        "thinking_policy": "FROZEN_PROVIDER_DEFAULT_NO_OVERRIDE",
        "repository": REPOSITORY, "actor": ctx["actor"], "run_number": ctx["run_number"],
        "workflow_ref": ctx["workflow_ref"], "run_attempt": "1",
    }
    for key, expected in required.items():
        if type(grant.get(key)) is not type(expected) or grant[key] != expected:
            raise Denied(f"Wrong grant binding: {key}")
    if (ctx["event"] != "workflow_dispatch" or ctx["repository"] != REPOSITORY
            or ctx["run_attempt"] != "1" or ctx["sha"] != candidate
            or not re.fullmatch(r"[a-f0-9]{40}", candidate)
            or not ctx["actor"] or not ctx["run_number"].isdigit() or not ctx["run_id"].isdigit()
            or not ctx["workflow_ref"].startswith(REPOSITORY + "/.github/workflows/ci.yml@")):
        raise Denied("Only the exact first manual workflow run is authorized; reruns forbidden")
    current = now or datetime.now(UTC)
    expiry = datetime.fromisoformat(grant["expires_utc"].replace("Z", "+00:00"))
    if expiry.tzinfo is None or not 0 < (expiry - current).total_seconds() <= 3600:
        raise Denied("Grant must expire within one hour")
    for key in ("grant_id", "parent_budget_ledger_ref", "price_evidence", "input_bound_evidence"):
        if not isinstance(grant.get(key), str) or not grant[key].strip():
            raise Denied(f"Missing parent evidence: {key}")
    limit = grant.get("max_input_tokens")
    if type(limit) is not int or not 0 < limit <= MAX_INPUT:
        raise Denied("Invalid finite input token ceiling")
    if len(exported["sizes"]) != CALLS:
        raise Denied("Frozen case count changed")
    for row, size in zip(exported["plan"]["attempts"], exported["sizes"], strict=True):
        request = row["request"]
        if (size["input_token_bound"] > limit or size["max_output_tokens"] != MAX_OUTPUT
                or request["modelId"] != grant["model_id"]
                or set(request) != {"modelId", "messages", "inferenceConfig"}
                or request["inferenceConfig"] != {"maxTokens": MAX_OUTPUT}
                or ar3.sha256(ar3.encoded(request)) != row["request_sha256"]):
            raise Denied("Input/request/model/output ceiling mismatch")
    total = sum((cost(s["input_token_bound"], MAX_OUTPUT, grant)
                 for s in exported["sizes"]), Decimal(0))
    budget = amount(grant["budget_usd"])
    if budget > 5 or total > budget:
        raise Denied("Worst-case cohort exceeds the explicitly allocated app grant")
    return grant, total


def verify_source(candidate):
    if os.getenv("GITHUB_ACTIONS") != "true" or ar3.git("rev-parse", "HEAD") != candidate:
        raise Denied("CI-only exact checked-out source required")
    ar3.git("merge-base", "--is-ancestor", INSTRUMENT_SHA, candidate)
    ar3.git("diff", "--exit-code", INSTRUMENT_SHA, "HEAD", "--", "src", "evaluation/ar3.py",
            "evaluation/ar3_data", "evaluation/ar2.py", "evaluation/public_workflow.py",
            "pyproject.toml")
    ar3.git("diff", "--exit-code", "HEAD", "--", "evaluation", "src", ".github")


def live_client(grant):
    import boto3

    return boto3.client("bedrock-runtime", region_name=grant["region"], config=sdk_config(),
                        endpoint_url="https://bedrock-runtime.eu-west-1.amazonaws.com")


def sdk_bytes(response):
    # Converse can return opaque redacted reasoning bytes even on text-only requests.
    # Preserve their type/base64, never silently discard them to satisfy the evaluator.
    def binary(value):
        if isinstance(value, bytes | bytearray):
            return {"__sdk_binary_base64__": base64.b64encode(value).decode()}
        raise TypeError(f"Unsupported SDK value: {type(value).__name__}")

    return (json.dumps(response, sort_keys=True, indent=2, allow_nan=False, default=binary)
            + "\n").encode()


def inspect_response(response, size, grant):
    """Optional metadata is not a quality gate; unknown billing retains worst reservation."""
    mapping = response if isinstance(response, dict) else {}
    usage = mapping.get("usage")
    metadata = mapping.get("ResponseMetadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    tokens = [usage.get("inputTokens"), usage.get("outputTokens")] if isinstance(
        usage, dict) else [None, None]
    known = all(type(value) is int and 0 <= value <= 10000000 for value in tokens)
    cache_write = usage.get("cacheWriteInputTokens", 0) if isinstance(usage, dict) else 0
    violation = (known and (tokens[0] > size["input_token_bound"] or tokens[1] > MAX_OUTPUT)
                 or metadata.get("RetryAttempts", 0) != 0
                 or metadata.get("HTTPStatusCode", 200) != 200 or cache_write != 0)
    return {"usage": usage, "request_id": metadata.get("RequestId"),
            "rate_based_estimate_usd": str(cost(*tokens, grant)) if known else None,
            "cost_status": "RATE_BASED_ESTIMATE_NOT_BILL" if known else "UNKNOWN_RESERVED_WORST",
            "ceiling_or_transport_violation": bool(violation)}


def collect(output, exported, grant_bytes, approved_hash, candidate, ctx, factory,
            *, execution_mode, clock=time.monotonic, now=None):
    protocol, inputs = frozen_inputs()
    journal = Journal(output, inputs, ["converse"])
    journal.write("grant.json", grant_bytes)
    journal.write("export.json", ar3.encoded(exported))
    journal.write("context.json", ar3.encoded({**ctx, "candidate_sha": candidate,
                  "instrument_sha": INSTRUMENT_SHA, "mode": MODE,
                  "execution_mode": execution_mode, "boto3": version("boto3"),
                  "botocore": version("botocore")}))
    # Independently regenerate the fixed prompts; supplied exports are not authority.
    if exported != export_plan():
        raise Denied("Export differs from frozen source")
    grant, total = validate(grant_bytes, approved_hash, exported, candidate, ctx, now)
    journal.write("cohort-reservation.json", ar3.encoded({"worst_case_usd": str(total),
                  "parent_budget_ledger_ref": grant["parent_budget_ledger_ref"],
                  "shared_budget_remaining": "UNKNOWN_PARENT_OWNED",
                  "never_refund_unknown_or_release_reservations_in_this_run": True}))
    rows = [{"case_id": r["case_id"], "request_sha256": r["request_sha256"],
             "raw_response": None, "error": "UNRUN", "status": "unrun"}
            for r in exported["plan"]["attempts"]]
    client = None
    started = 0
    calls = 0
    spent_reservations = Decimal(0)
    deadline = clock() + SECONDS
    for index, (request_row, size) in enumerate(zip(exported["plan"]["attempts"],
                                                   exported["sizes"], strict=True)):
        # Recheck expiry/context before each reservation; no input/prompt/config mutation.
        validate(grant_bytes, approved_hash, exported, candidate, ctx, now)
        if clock() >= deadline or started >= CALLS:
            break
        slot = f"journal/converse/{index:02d}"
        reserve = cost(size["input_token_bound"], MAX_OUTPUT, grant)
        spent_reservations += reserve
        journal.write(f"{slot}/01-reserved.json", ar3.encoded({
            "status": "reserved_call_not_confirmed", "worst_case_usd": str(reserve),
            "cumulative_reserved_usd": str(spent_reservations), "input_token_bound":
            size["input_token_bound"], "max_output_tokens": MAX_OUTPUT, "attempt": 1}))
        journal.write(f"{slot}/02-request.json", ar3.encoded(request_row["request"]))
        started += 1
        row = rows[index]
        try:
            if client is None:
                client = factory(grant)
            calls += 1
            response = client.converse(**copy.deepcopy(request_row["request"]))
        except Exception as exc:
            details = {"type": type(exc).__name__, "message": str(exc),
                       "sdk_response": getattr(exc, "response", None)}
            journal.write(f"{slot}/03-exception.json", sdk_bytes(details))
            row.update(error=f"UNKNOWN_OUTCOME: {type(exc).__name__}", status="unknown_outcome")
            journal.write(f"{slot}/04-outcome.json", ar3.encoded(row))
            break  # Never retry, repair, fallback or consume another case after SDK failure.
        raw = sdk_bytes(response)
        journal.write(f"{slot}/03-response.json", raw)  # Full SDK envelope BEFORE interpretation.
        row.update(raw_response=raw.decode(), response_sha256=ar3.sha256(raw), error=None,
                   status="response_received", reserved_worst_case_usd=str(reserve),
                   **inspect_response(response, size, grant))
        journal.write(f"{slot}/04-outcome.json", ar3.encoded(row))
        if row["ceiling_or_transport_violation"]:
            break
    packet = {"provenance": {"mode": MODE, "execution_mode": execution_mode,
              "candidate_sha": candidate,
              "grant_sha256": approved_hash, "plan_sha256": exported["plan_sha256"],
              "run_id": ctx["run_id"]}, "attempts": rows}
    journal.write("replay.json", ar3.encoded(packet))
    # Gold is first read AFTER every possible inference. Evaluation itself blocks all network.
    _, _, gold = ar3.load_frozen()
    replay = ar3.evaluate(inputs, gold, protocol, ar3.Replay(packet, inputs))
    result = {"mode": MODE, "execution_mode": execution_mode, "calls_started": calls,
              "slots_reserved": started, "cohort_reserved_usd": str(total),
              "started_reserved_usd": str(spent_reservations), "aws_infrastructure_usd": None,
              "shared_budget_remaining": "UNKNOWN_PARENT_OWNED", "evaluation": replay,
              "collection_complete": all(r["status"] == "response_received" for r in rows)
              and not any(r.get("ceiling_or_transport_violation") for r in rows),
              "limitations": "Development cases; plain Converse, not Strands graph/user benefit; "
              "full SDK envelope, not original wire bytes; costs are not a billing measurement"}
    journal.finalize(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "preflight", "collect"])
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    verify_source(args.candidate_sha)
    exported = export_plan()
    if args.command == "prepare":
        if args.output is None:
            parser.error("--output required")
        with args.output.open("xb") as handle:
            handle.write(ar3.encoded(exported))
        return 0
    grant = os.getenv("AR3_GRANT_JSON", "").encode()
    approved_hash = os.getenv("AR3_GRANT_SHA256", "")
    ctx = context()
    validate(grant, approved_hash, exported, args.candidate_sha, ctx)
    if args.command == "preflight":
        print("Parent-bound preflight passed; no AWS client or invocation created", flush=True)
        return 0
    if args.output is None:
        parser.error("--output required")
    result = collect(args.output, exported, grant, approved_hash, args.candidate_sha, ctx,
                     live_client, execution_mode="LIVE_PARENT_GRANTED")
    return 0 if result["collection_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
