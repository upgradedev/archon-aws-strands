"""Bind public automated evidence to the tested frontend/backend pair.

The browser job has no AWS identity. A separate main-only publisher receives only
this sanitized summary, verifies the still-served pair and writes to its own site.
Git source compatibility is not binary attestation or human acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from frontend_publish import aws

URL = "https://d2ssmv59q16d0b.cloudfront.net/"
REPO = "upgradedev/archon-aws-strands"
SHA = re.compile(r"[0-9a-f]{40}")
RUNTIME_PATHS = ("src", "pyproject.toml", "setup.cfg", "setup.py", "requirements*",
                 "uv.lock", "poetry.lock", "infra/archon_api_stack.py",
                 ".github/workflows/aws-api-package.yml")
LIMITS = "Synthetic data; scripted Strands model; simulated outbox. No real email, bank verification or measured user benefit."


def require(condition, message):
    if not condition:
        raise ValueError(message)


def get_json(url):
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=30) as response:
        require(response.status == 200, "live read failed")
        body = response.read(1024 * 1024 + 1)
    require(len(body) <= 1024 * 1024, "oversized live response")
    return json.loads(body)


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def compatible(frontend, backend, command=git):
    require(isinstance(frontend, str) and SHA.fullmatch(frontend), "full frontend SHA required")
    require(isinstance(backend, str) and SHA.fullmatch(backend), "full backend SHA required")
    require(command("rev-parse", "HEAD") == frontend, "workflow checkout differs from requested release")
    command("merge-base", "--is-ancestor", backend, frontend)
    # Fail before publishing new frontend bytes if deployed packaged inputs differ.
    command("diff", "--exit-code", backend, frontend, "--", *RUNTIME_PATHS)


def pair(frontend, expected_backend=None, request=get_json, command=git):
    health = request(URL + "api/health")
    backend = health.get("commit")
    compatible(frontend, backend, command)
    if expected_backend is not None:
        require(backend == expected_backend, "backend changed during release acceptance")
    require(health.get("status") == "ok" and health.get("mode") == "synthetic", "unexpected runtime mode")
    require(health.get("live_send") is False and health.get("live_model") is False,
            "public acceptance must not exercise live sends/models")
    require(health.get("model") == "LedgerScriptModel" and health.get("provider") == "SimulatedProvider"
            and health.get("orchestration") == "Strands", "unexpected public provider")
    return {"frontend_commit": frontend, "backend_commit": backend,
            "backend_identity_basis": "GET /api/health; packaged source paths equal at both Git commits",
            "mode": "synthetic", "live_send": False, "live_model": False}


def junit_counts(path):
    data = Path(path).read_bytes()
    require(0 < len(data) <= 10 * 1024 * 1024, "missing or oversized JUnit")
    require(b"<!DOCTYPE" not in data.upper() and b"<!ENTITY" not in data.upper(), "JUnit entities forbidden")
    root = ET.fromstring(data)
    require(root.tag in {"testsuites", "testsuite"}, "unexpected JUnit root")
    cases = list(root.iter("testcase"))
    total = len(cases)
    require(total >= 34, "incomplete browser journey set")
    require(int(root.attrib["tests"]) == total, "JUnit total does not match actual cases")
    for name in ("failures", "errors", "skipped"):
        require(int(root.attrib.get(name, "0")) == 0, "JUnit contains unsuccessful cases")
    identities = {(s.get("name"), s.get("hostname"), c.get("classname"), c.get("name"))
                  for s in root.iter("testsuite") for c in s.findall("testcase")}
    require(len(identities) == total, "duplicate JUnit cases")
    forbidden = {"failure", "error", "skipped", "flakyFailure", "flakyError", "rerunFailure", "rerunError"}
    require(not any(child.tag in forbidden for c in cases for child in c.iter()),
            "JUnit contains failure, skip or retry evidence")
    return {"total": total, "passed": total, "failed": 0, "skipped": 0}


def receipt(before, after, junit, environment=os.environ):
    require(before == after, "preflight/postflight pair mismatch")
    require(environment.get("GITHUB_REPOSITORY") == REPO, "wrong repository")
    require(environment.get("GITHUB_REF") == "refs/heads/main", "main only")
    require(environment.get("GITHUB_SHA") == before["frontend_commit"], "wrong workflow revision")
    for key in ("PREFLIGHT", "JOURNEYS", "POSTFLIGHT"):
        require(environment.get(key) == "success", "all observed gates must succeed")
    run, attempt = environment.get("GITHUB_RUN_ID", ""), environment.get("GITHUB_RUN_ATTEMPT", "")
    require(re.fullmatch(r"[1-9][0-9]*", run) and re.fullmatch(r"[1-9][0-9]*", attempt), "invalid run identity")
    return {"schema_version": 1, "application": "Archon", "environment": "live_aws",
            "status": "AUTOMATED_JOURNEYS_PASSED", **before,
            "run_id": run, "run_attempt": attempt,
            "run_url": f"https://github.com/{REPO}/actions/runs/{run}/attempts/{attempt}",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "checks": {"preflight": "success", "journeys": "success", "postflight": "success"},
            "counts": junit_counts(junit), "human_uat": "NOT_RUN", "limits": LIMITS}


def validate_receipt(value):
    require(set(value) == {"schema_version", "application", "environment", "status", "frontend_commit",
                          "backend_commit", "backend_identity_basis", "mode", "live_send", "live_model",
                          "run_id", "run_attempt", "run_url", "observed_at", "checks", "counts", "human_uat", "limits"},
            "unexpected public receipt fields")
    require(value.get("schema_version") == 1 and value.get("application") == "Archon"
            and value.get("environment") == "live_aws" and value.get("status") == "AUTOMATED_JOURNEYS_PASSED",
            "invalid receipt identity")
    for field in ("frontend_commit", "backend_commit"):
        require(isinstance(value.get(field), str) and SHA.fullmatch(value[field]), "invalid receipt SHA")
    run, attempt = value.get("run_id", ""), value.get("run_attempt", "")
    require(isinstance(run, str) and re.fullmatch(r"[1-9][0-9]*", run), "invalid run")
    require(isinstance(attempt, str) and re.fullmatch(r"[1-9][0-9]*", attempt), "invalid attempt")
    require(value.get("run_url") == f"https://github.com/{REPO}/actions/runs/{run}/attempts/{attempt}", "invalid run link")
    require(value.get("human_uat") == "NOT_RUN" and value.get("limits") == LIMITS, "invalid scope")
    require(value.get("mode") == "synthetic" and value.get("live_send") is False and value.get("live_model") is False,
            "invalid runtime scope")
    require(value.get("backend_identity_basis") == "GET /api/health; packaged source paths equal at both Git commits",
            "invalid identity basis")
    require(datetime.fromisoformat(value["observed_at"]).tzinfo is not None, "timestamp needs timezone")
    require(value.get("checks") == {"preflight": "success", "journeys": "success", "postflight": "success"}, "unsuccessful checks")
    counts = value.get("counts", {})
    require(type(counts.get("total")) is int and counts["total"] >= 34
            and counts == {"total": counts["total"], "passed": counts["total"], "failed": 0, "skipped": 0},
            "invalid counts")


def publish(value, command=aws, request=get_json, git_command=git):
    validate_receipt(value)
    require(os.environ.get("GITHUB_REF") == "refs/heads/main", "publisher main only")
    require(os.environ.get("GITHUB_SHA") == value["frontend_commit"], "publisher checkout mismatch")
    require(os.environ.get("GITHUB_RUN_ID") == value["run_id"]
            and os.environ.get("GITHUB_RUN_ATTEMPT") == value["run_attempt"], "receipt from another run")
    require(request(URL + "release.json").get("commit") == value["frontend_commit"], "stale frontend receipt")
    pair(value["frontend_commit"], value["backend_commit"], request, git_command)
    response = command("cloudformation", "describe-stacks", "--stack-name", "archon-frontend", "--region", "eu-west-1")
    outputs = {item["OutputKey"]: item["OutputValue"] for item in response["Stacks"][0]["Outputs"]}
    require(outputs["FrontendUrl"] == URL, "wrong frontend stack URL")
    bucket = outputs["FrontendBucket"]
    require(re.fullmatch(r"archon-web-[0-9]{12}-eu-west-1", bucket), "wrong frontend bucket")
    with tempfile.TemporaryDirectory(prefix="acceptance-") as directory:
        target = Path(directory) / "acceptance.json"
        target.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        key = f"acceptance/runs/{value['run_id']}-{value['run_attempt']}.json"
        command("s3api", "put-object", "--bucket", bucket, "--key", key, "--body", str(target),
                "--content-type", "application/json", "--cache-control", "no-store,max-age=0",
                "--if-none-match", "*", "--region", "eu-west-1")
        # Recheck after the immutable write. A late deployment leaves historical proof only.
        require(request(URL + "release.json").get("commit") == value["frontend_commit"], "release changed before latest update")
        pair(value["frontend_commit"], value["backend_commit"], request, git_command)
        command("s3api", "put-object", "--bucket", bucket, "--key", "acceptance.json", "--body", str(target),
                "--content-type", "application/json", "--cache-control", "no-store,max-age=0", "--region", "eu-west-1")
    return {"public_receipt": URL + key, "latest": URL + "acceptance.json"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["pair", "receipt", "publish"])
    parser.add_argument("--sha")
    parser.add_argument("--backend")
    parser.add_argument("--output")
    parser.add_argument("--before", default="acceptance-preflight.json")
    parser.add_argument("--after", default="acceptance-postflight.json")
    parser.add_argument("--junit", default="frontend/artifacts/browser-junit.xml")
    parser.add_argument("--receipt", default="acceptance.json")
    args = parser.parse_args()
    if args.action == "pair":
        result = pair(args.sha, args.backend)
    elif args.action == "receipt":
        result = receipt(json.loads(Path(args.before).read_text()), json.loads(Path(args.after).read_text()), args.junit)
    else:
        result = publish(json.loads(Path(args.receipt).read_text()))
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
