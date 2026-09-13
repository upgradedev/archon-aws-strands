"""Explicit controlled-provider release evidence; the historical ruler stays unchanged."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infra"))
spec = importlib.util.spec_from_file_location("historical_release", ROOT / "infra/release_acceptance.py")
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
LIMITS = ("Fictional business data; actual Bedrock and controlled SES provider acceptance. "
          "No mailbox arrival, bank settlement, independent model superiority or human UAT proven.")
PROJECTS = {"desktop", "mobile", "webkit"}
BASIS = "GET /api/health; packaged source and deployment paths equal"
FIELDS = {"schema_version", "application", "environment", "frontend_commit", "backend_commit",
          "backend_identity_basis", "mode", "live_model", "live_send", "status", "run_id",
          "run_attempt", "run_url", "observed_at", "counts", "provider_checks", "human_uat",
          "limits", "checks"}
PROVIDER_FIELDS = {"model_calls", "input_tokens", "output_tokens", "emails_accepted", "delivery_proven"}


def pair(frontend, expected_backend=None, request=old.get_json, command=old.git):
    health = request(old.URL + "api/health")
    if health.get("mode") == "synthetic":
        return old.pair(frontend, expected_backend, request, command)
    backend = health.get("commit")
    old.compatible(frontend, backend, command)
    command("diff", "--exit-code", backend, frontend, "--", "deploy")
    old.require(expected_backend is None or backend == expected_backend, "backend changed")
    old.require(health.get("status") == "ok" and health.get("mode") == "controlled-live"
                and health.get("live_model") is True and health.get("live_send") is True
                and health.get("model") == "eu.anthropic.claude-opus-5"
                and health.get("provider") == "SES-controlled-recipient"
                and health.get("orchestration") == "Strands", "unexpected controlled providers")
    return {"frontend_commit": frontend, "backend_commit": backend,
            "backend_identity_basis": BASIS,
            "mode": "controlled-live", "live_model": True, "live_send": True}


def provider_counts(junit, proof_dir, before):
    data = Path(junit).read_bytes()
    old.require(0 < len(data) < 1000000 and b"<!" not in data, "invalid live JUnit")
    root = ET.fromstring(data)
    cases = list(root.iter("testcase"))
    old.require(len(cases) == 3 and int(root.attrib["tests"]) == 3, "three live viewports required")
    old.require(all(int(root.attrib.get(k, 0)) == 0 for k in ("failures", "errors", "skipped"))
                and not any(c.tag in {"failure", "error", "skipped", "flakyFailure", "rerunFailure"}
                            for case in cases for c in case.iter()), "failed live browser case")
    proofs = [json.loads(p.read_text()) for p in Path(proof_dir).glob("live-provider-*.json")]
    old.require(len(proofs) == 3 and {p["project"] for p in proofs} == PROJECTS, "missing live proofs")
    for p in proofs:
        old.require(p["scope"] == "actual_aws" and p["origin"] == old.URL.rstrip("/"), "not AWS proof")
        old.require(p["frontend_commit"] == before["frontend_commit"]
                    and p["backend_commit"] == before["backend_commit"], "proof revision mismatch")
        old.require(all(type(p.get(k)) is int and p[k] > 0 for k in
                        ("model_calls", "input_tokens", "output_tokens")) and p["model_calls"] >= 3,
                    "no actual model usage")
        old.require(p["email_accepted"] is True and p["replay_unchanged"] is True
                    and p["reload_retained"] is True
                    and p.get("legacy_consent_refused") is True, "incomplete provider journey")
        old.require(isinstance(p["message_id"], str) and bool(p["message_id"])
                    and not p["message_id"].startswith(("simulated-", "ci-")),
                    "not an actual SES acceptance id")
    old.require(len({p["message_id"] for p in proofs}) == 3, "each viewport must prove its own send")
    return {"total": 3, "passed": 3, "failed": 0, "skipped": 0}, {
        "model_calls": sum(p["model_calls"] for p in proofs),
        "input_tokens": sum(p["input_tokens"] for p in proofs),
        "output_tokens": sum(p["output_tokens"] for p in proofs),
        "emails_accepted": 3, "delivery_proven": False,
    }


def receipt(before, after, junit, proof_dir, environment=os.environ):
    if before["mode"] == "synthetic":
        return old.receipt(before, after, junit, environment)
    old.require(before == after, "release changed during live journeys")
    old.require(environment.get("GITHUB_REPOSITORY") == old.REPO
                and environment.get("GITHUB_REF") == "refs/heads/main"
                and environment.get("GITHUB_SHA") == before["frontend_commit"], "wrong release identity")
    old.require(all(environment.get(k) == "success" for k in
                    ("PREFLIGHT", "JOURNEYS", "POSTFLIGHT")), "all observed gates must pass")
    run, attempt = environment.get("GITHUB_RUN_ID", ""), environment.get("GITHUB_RUN_ATTEMPT", "")
    old.require(re.fullmatch(r"[1-9][0-9]*", run) and re.fullmatch(r"[1-9][0-9]*", attempt), "bad run")
    counts, providers = provider_counts(junit, proof_dir, before)
    return {"schema_version": 2, "application": "Archon", "environment": "live_aws", **before,
            "status": "CONTROLLED_PROVIDER_JOURNEYS_PASSED", "run_id": run, "run_attempt": attempt,
            "run_url": f"https://github.com/{old.REPO}/actions/runs/{run}/attempts/{attempt}",
            "observed_at": datetime.now(timezone.utc).isoformat(), "counts": counts,
            "provider_checks": providers, "human_uat": "NOT_RUN", "limits": LIMITS,
            "checks": {"preflight": "success", "journeys": "success", "postflight": "success"}}


def validate(value):
    old.require(isinstance(value, dict) and set(value) == FIELDS, "unexpected public fields")
    old.require(value.get("schema_version") == 2 and value.get("application") == "Archon"
                and value.get("environment") == "live_aws"
                and value.get("status") == "CONTROLLED_PROVIDER_JOURNEYS_PASSED", "bad identity")
    old.require(all(isinstance(value.get(k), str) and old.SHA.fullmatch(value[k])
                    for k in ("frontend_commit", "backend_commit")), "bad SHA")
    old.require(all(isinstance(value.get(k), str) and re.fullmatch(r"[1-9][0-9]*", value[k])
                    for k in ("run_id", "run_attempt")), "bad run")
    old.require(value["run_url"] == f"https://github.com/{old.REPO}/actions/runs/{value['run_id']}/attempts/{value['run_attempt']}", "bad link")
    old.require(value.get("mode") == "controlled-live" and value.get("live_model") is True
                and value.get("live_send") is True and value.get("human_uat") == "NOT_RUN"
                and value.get("limits") == LIMITS and value.get("backend_identity_basis") == BASIS,
                "bad proof scope")
    old.require(value.get("counts") == {"total": 3, "passed": 3, "failed": 0, "skipped": 0}
                and value.get("checks") == {"preflight": "success", "journeys": "success", "postflight": "success"}, "bad checks")
    p = value.get("provider_checks", {})
    old.require(isinstance(p, dict) and set(p) == PROVIDER_FIELDS
                and type(p.get("emails_accepted")) is int and p["emails_accepted"] == 3
                and p.get("delivery_proven") is False
                and all(type(p.get(k)) is int and p[k] > 0 for k in
                        ("model_calls", "input_tokens", "output_tokens")), "bad provider evidence")
    old.require(datetime.fromisoformat(value["observed_at"]).tzinfo is not None, "missing timezone")


def publish(value, command=old.aws, request=old.get_json):
    if value.get("schema_version") == 1:
        return old.publish(value, command, request)
    validate(value)
    current_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    old.require(re.fullmatch(r"[1-9][0-9]*", current_attempt)
                and int(value["run_attempt"]) <= int(current_attempt), "invalid producer attempt")
    old.require(os.environ.get("GITHUB_REF") == "refs/heads/main"
                and os.environ.get("GITHUB_SHA") == value["frontend_commit"]
                and os.environ.get("GITHUB_RUN_ID") == value["run_id"]
                and os.environ.get("ACCEPTANCE_RUN_ATTEMPT") == value["run_attempt"], "wrong publisher")
    def still_served():
        old.require(request(old.URL + "release.json")["commit"] == value["frontend_commit"], "stale release")
        old.served_frontend(value["frontend_commit"])
        pair(value["frontend_commit"], value["backend_commit"], request)
    still_served()
    stack = command("cloudformation", "describe-stacks", "--stack-name", "archon-frontend", "--region", "eu-west-1")
    outputs = {x["OutputKey"]: x["OutputValue"] for x in stack["Stacks"][0]["Outputs"]}
    bucket = outputs["FrontendBucket"]
    old.require(outputs["FrontendUrl"] == old.URL and re.fullmatch(r"archon-web-[0-9]{12}-eu-west-1", bucket), "wrong site")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "acceptance.json"
        path.write_text(json.dumps(value, indent=2) + "\n")
        key = f"acceptance/runs/{value['run_id']}-{value['run_attempt']}.json"
        try:
            command("s3api", "put-object", "--bucket", bucket, "--key", key, "--body", str(path),
                    "--content-type", "application/json", "--cache-control", "no-store,max-age=0",
                    "--if-none-match", "*", "--region", "eu-west-1")
        except subprocess.CalledProcessError as exc:
            old.require("PreconditionFailed" in (exc.stderr or "") or "(412)" in (exc.stderr or ""), "publication failed")
            old.require(request(old.URL + key) == value, "immutable receipt differs")
        still_served()
        command("s3api", "put-object", "--bucket", bucket, "--key", "acceptance.json", "--body", str(path),
                "--content-type", "application/json", "--cache-control", "no-store,max-age=0", "--region", "eu-west-1")
    return {"public_receipt": old.URL + key}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["pair", "receipt", "publish"])
    parser.add_argument("--sha")
    parser.add_argument("--backend")
    parser.add_argument("--output")
    parser.add_argument("--receipt", default="acceptance.json")
    args = parser.parse_args()
    if args.action == "pair":
        result = pair(args.sha, args.backend)
    elif args.action == "receipt":
        result = receipt(json.loads(Path("acceptance-preflight.json").read_text()),
                         json.loads(Path("acceptance-postflight.json").read_text()),
                         "frontend/artifacts/browser-junit.xml", "frontend/artifacts")
    else:
        result = publish(json.loads(Path(args.receipt).read_text()))
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
