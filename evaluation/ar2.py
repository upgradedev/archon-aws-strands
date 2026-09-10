"""Frozen synthetic collection instrument. Execute only in GitHub Actions.

Run: python -m evaluation.ar2 --candidate-sha <HEAD> --output <new-directory>
The JSON result is deterministic; the receipt additionally records the CI run.
An instrument completion and a candidate passing its contract are separate facts.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
from importlib.metadata import version
from pathlib import Path

from .public_workflow import run_public
from .reference_baseline import run_baseline

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "evidence/ar2-golden-v1.json"
PREREGISTRATION = "33dbe4f534b02fb07945561264879a46e8c9793e"
GOLDEN_SHA256 = "4e94e162f9c72224496ef41f27aa6aab00c95a9065a65ec306195a72b0af2a25"
CASE_COUNT, DECISION_COUNT, OPPORTUNITY_COUNT = 18, 22, 6
REQUIRED_COVERAGE = {
    "must-act", "duplicate-transfer-ids", "supplier-direction", "ambiguous-direction",
    "missing-transfer-reference", "missing-invoice-reference", "ambiguous-payment",
    "new-payment", "stale-draft", "duplicate-send-suppression",
}


def encoded(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_protocol(path: Path = GOLDEN) -> dict:
    data = path.read_bytes()
    if sha256(data) != GOLDEN_SHA256:
        raise ValueError("Frozen golden bytes changed; requires a separately reviewed version")
    protocol = json.loads(data)
    cases = protocol["cases"]
    if len(cases) != CASE_COUNT or len({c["id"] for c in cases}) != CASE_COUNT:
        raise ValueError("Missing or duplicate golden case")
    decisions = [expectation for case in cases for expectation in case["expected"]]
    if len(decisions) != DECISION_COUNT or sum(e["send"] is not None for e in decisions) != 6:
        raise ValueError("Positive/negative opportunity floor changed")
    if not REQUIRED_COVERAGE.issubset({tag for c in cases for tag in c["covers"]}):
        raise ValueError("Missing required coverage")
    for case in cases:
        expected_steps = [e["step"] for e in case["expected"]]
        approvals = [i for i, step in enumerate(case["steps"]) if step["op"] == "approve"]
        if expected_steps != approvals:
            raise ValueError("Every approval must have exactly one predeclared oracle")
        for step in case["steps"]:
            if step["op"] not in {"intake", "draft", "approve", "reload"}:
                raise ValueError("Unknown task operation")
            allowed = {"op", "body"} if step["op"] == "intake" else {"op"}
            if set(step) != allowed:
                raise ValueError("Method input contains undeclared context or answer labels")
    return protocol


def summarize(rows: list[dict], expected_total: int, expected_positive: int) -> dict:
    """Binary confusion counts plus exact correctness; a wrong positive is never a capture."""
    counts = dict(tp=0, fp=0, tn=0, fn=0)
    captured = abstentions = false_chases = calls = contract_failures = errors = 0
    for row in rows:
        if row.get("error"):
            errors += 1
            continue
        expected, observed = row["expected"], row["observed"]
        positive, active = expected["send"] is not None, bool(observed["calls"])
        counts[("tp" if active else "fn") if positive else ("fp" if active else "tn")] += 1
        exact = positive and observed["calls"] == [expected["send"]]
        captured += int(exact)
        calls += len(observed["calls"])
        # An extra call is unsafe even when the first call matches the oracle.
        matched_once = int(positive and expected["send"] in observed["calls"])
        false_chases += len(observed["calls"]) - matched_once
        abstentions += int(not active)
        contract_failures += int(
            observed["balances"] != expected["balances"] or observed["hold"] != expected["hold"]
        )
    complete = len(rows) == expected_total and errors == 0
    passed = (complete and expected_positive > 0 and captured == expected_positive
              and false_chases == 0 and contract_failures == 0
              and counts["fp"] == 0 and counts["fn"] == 0)
    return {
        "measurement_status": "MEASURED" if complete else "NOT_MEASURED",
        "acceptance": "PASS" if passed else "FAIL" if complete else "NOT_MEASURED",
        "decision_points_expected": expected_total,
        "decision_points_measured": sum(counts.values()),
        "confusion_action_vs_required": counts,
        "legitimate_opportunities": expected_positive,
        "legitimate_opportunities_captured": captured,
        "legitimate_opportunities_missed_or_wrong": expected_positive - captured,
        "simulated_provider_calls": calls,
        "false_chases": false_chases,
        "abstentions": abstentions,
        "ledger_or_hold_mismatches": contract_failures,
        "execution_errors": errors,
    }


def evaluate(protocol: dict, method) -> dict:
    rows = []
    context = {key: protocol[key] for key in ("as_of", "business_email", "business_name")}
    for case in protocol["cases"]:
        try:
            # Neither expected outcomes, coverage tags nor case names are method inputs.
            observed = method(copy.deepcopy(case["steps"]), copy.deepcopy(context))
            if [row["step"] for row in observed] != [row["step"] for row in case["expected"]]:
                raise ValueError("Missing, repeated or reordered decision observation")
            for actual in observed:
                if (not isinstance(actual["calls"], list)
                        or not isinstance(actual["balances"], dict)
                        or type(actual["hold"]) is not bool):
                    raise ValueError("Malformed decision observation")
        except Exception as exc:
            # Preserve instrument faults as faults, never convert a crash into safe silence.
            rows.extend({"case": case["id"], "expected": expected,
                         "error": {"type": type(exc).__name__, "message": str(exc)}}
                        for expected in case["expected"])
            continue
        rows.extend({"case": case["id"], "expected": expected, "observed": actual}
                    for expected, actual in zip(case["expected"], observed, strict=True))
    total = sum(len(case["expected"]) for case in protocol["cases"])
    positives = sum(e["send"] is not None for c in protocol["cases"] for e in c["expected"])
    return {"summary": summarize(rows, total, positives), "decisions": rows}


def always_abstain(steps: list[dict], context: dict) -> list[dict]:
    rows = run_baseline(steps, context)
    for row in rows:
        row["calls"] = []
    return rows


def unsafe(steps: list[dict], context: dict) -> list[dict]:
    rows = run_baseline(steps, context)
    for row in rows:
        row["calls"] = [{"invoice": "UNSAFE-1", "recipient": "wrong@example.com",
                         "amount": "9999.99"}]
    return rows


def build_result(protocol: dict, candidate_sha: str) -> dict:
    methods = {"public_workflow": evaluate(protocol, run_public),
               "reference_baseline": evaluate(protocol, run_baseline),
               "always_abstain_control": evaluate(protocol, always_abstain),
               "unsafe_control": evaluate(protocol, unsafe)}
    controls_rejected = all(methods[name]["summary"]["acceptance"] == "FAIL"
                            for name in ("always_abstain_control", "unsafe_control"))
    measured = all(value["summary"]["measurement_status"] == "MEASURED"
                   for value in methods.values())
    return {
        "schema": "archon-ar2-result-v1", "candidate_sha": candidate_sha,
        "preregistration_commit": PREREGISTRATION, "golden_sha256": GOLDEN_SHA256,
        "instrument_valid": measured and controls_rejected,
        "measurement_status": "MEASURED" if measured else "NOT_MEASURED",
        "candidate_acceptance": methods["public_workflow"]["summary"]["acceptance"],
        "scope": protocol["scope"], "baseline_definition": protocol["baseline"],
        "count_definition": {
            "unit": "Each predeclared approve step, including stale/repeat approvals",
            "confusion": "TP/FP mean any action, not correctness; exact captures are separate",
            "false_chases": "Calls with no legitimate match plus calls beyond one valid match",
            "abstentions": "No new simulated provider call, including holds and replay suppression",
            "capture": "Exactly one call at the fixed invoice, recipient and amount",
        },
        "limitations": [
            "Author-created synthetic golden cases; no held-out or population accuracy claim",
            "Shared reader and business context; baseline is not commercial software",
            "Public ASGI application in temporary SQLite; not live AWS or browser acceptance",
            "Deterministic scripted model and simulated provider; no AI quality measured",
            "Approval attempts are automated fixtures; no human approval or user benefit measured",
            "Reload tests new API client/store access, not process termination or concurrent sends",
        ],
        "remaining_gates": {"AR2": "bounded synthetic evaluation only",
                            "C1_real_AI": "NOT_MEASURED", "human_benefit": "NOT_MEASURED"},
        "methods": methods,
    }


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def source_manifest() -> dict:
    files = git("ls-files", "src", "evaluation", "tests/test_ar2_evaluation.py",
                "evidence/ar2-golden-v1.json", ".github/workflows/ar2-evaluation.yml",
                "pyproject.toml").splitlines()
    return {name: sha256((ROOT / name).read_bytes()) for name in sorted(files)}


def persist(result: dict, output: Path, manifest: dict, receipt: dict) -> None:
    # Create-only: an old failed result can never be silently replaced by a retry.
    output.mkdir(parents=True, exist_ok=False)
    files = {"result.json": encoded(result), "source-sha256.json": encoded(manifest),
             "receipt.json": encoded(receipt)}
    for name, data in files.items():
        (output / name).write_bytes(data)
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(data)}  {name}\n" for name, data in sorted(files.items())),
        encoding="utf-8", newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("AR2 execution is CI-only")
    if not re.fullmatch(r"[a-f0-9]{40}", args.candidate_sha) or git("rev-parse", "HEAD") != (
        args.candidate_sha
    ):
        parser.error("Candidate must be the exact checked-out commit")
    git("merge-base", "--is-ancestor", PREREGISTRATION, args.candidate_sha)
    git("diff", "--exit-code", "HEAD", "--", "src", "evaluation", "evidence", "tests",
        "pyproject.toml", ".github/workflows/ar2-evaluation.yml")
    protocol = load_protocol()
    result = build_result(protocol, args.candidate_sha)
    receipt = {
        "candidate_sha": args.candidate_sha,
        "run_url": (f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
                    f"/actions/runs/{os.environ['GITHUB_RUN_ID']}"),
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "command": "python -m evaluation.ar2 --candidate-sha $CANDIDATE_SHA --output $OUTPUT",
        "dependencies": {name: version(name) for name in ("strands-agents", "fastapi", "httpx")},
        "evidence_level": "Pipeline, offline synthetic only",
    }
    persist(result, args.output, source_manifest(), receipt)
    print(json.dumps({name: value["summary"] for name, value in result["methods"].items()},
                     sort_keys=True, indent=2))
    return 0 if result["instrument_valid"] and result["candidate_acceptance"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
