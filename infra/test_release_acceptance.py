"""CI-only release identity, refusal and immutable evidence controls."""
import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import release_acceptance as gate

FRONT = "1" * 40
BACK = "2" * 40


class ReleaseAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.junit = Path(self.temp.name) / "junit.xml"
        cases = "".join(f'<testcase classname="workspace" name="case-{n}"/>' for n in range(17))
        self.xml = '<testsuites tests="34" failures="0" errors="0" skipped="0">' + "".join(
            f'<testsuite name="workspace" hostname="{project}">{cases}</testsuite>'
            for project in ("desktop", "mobile")) + '</testsuites>'
        self.junit.write_text(self.xml)
        self.health = {"commit": BACK, "status": "ok", "mode": "synthetic", "live_send": False,
                       "live_model": False, "model": "LedgerScriptModel", "provider": "SimulatedProvider",
                       "orchestration": "Strands"}
        self.env = {"GITHUB_REPOSITORY": gate.REPO, "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": FRONT,
                    "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2",
                    "ACCEPTANCE_RUN_ATTEMPT": "2",
                    "PREFLIGHT": "success", "JOURNEYS": "success", "POSTFLIGHT": "success"}

    def git(self, *args):
        return FRONT if args == ("rev-parse", "HEAD") else ""

    def request(self, url):
        return {"commit": FRONT} if url.endswith("release.json") else self.health

    def html(self, url):
        return f'<html><head><meta name="application-commit" content="{FRONT}"></head></html>'

    def pair(self):
        return gate.pair(FRONT, BACK, self.request, self.git)

    def receipt(self):
        return gate.receipt(self.pair(), self.pair(), self.junit, self.env)

    def test_equal_packaged_sources_allow_different_revision_pair(self):
        self.assertEqual(self.pair()["backend_commit"], BACK)
        self.assertNotEqual(self.pair()["frontend_commit"], BACK)

    def test_backend_change_and_unexpected_provider_refused(self):
        for key, value in (("commit", "3" * 40), ("live_send", True), ("live_model", True),
                           ("mode", "production"), ("provider", "SES"), ("status", "down")):
            with self.subTest(key=key), patch.dict(self.health, {key: value}), self.assertRaises(ValueError):
                self.pair()

    def test_missing_identity_and_checkout_refused(self):
        for value in (None, "main", "--help", "A" * 40):
            with self.subTest(value=value), patch.dict(self.health, {"commit": value}), self.assertRaises(ValueError):
                self.pair()
        with self.assertRaises(ValueError):
            gate.pair(FRONT, BACK, self.request, lambda *args: BACK)

    def test_actual_git_packaged_change_is_refused_but_docs_pass(self):
        root = Path(self.temp.name) / "repo"
        root.mkdir()
        def command(*args):
            return subprocess.run(["git", "-C", str(root), *args], check=True,
                                  capture_output=True, text=True).stdout.strip()
        command("init")
        command("config", "user.name", "fixture")
        command("config", "user.email", "fixture@example.invalid")
        (root / "src").mkdir()
        (root / "src" / "app.py").write_text("version = 1\n")
        command("add", ".")
        command("commit", "-m", "fixture runtime")
        backend = command("rev-parse", "HEAD")
        (root / "README.md").write_text("fixture description\n")
        command("add", ".")
        command("commit", "-m", "fixture docs")
        gate.compatible(command("rev-parse", "HEAD"), backend, command)
        (root / "src" / "app.py").write_text("version = 2\n")
        command("add", ".")
        command("commit", "-m", "fixture incompatible runtime")
        with self.assertRaises(subprocess.CalledProcessError):
            gate.compatible(command("rev-parse", "HEAD"), backend, command)

    def test_actual_junit_cases_aggregate_without_publishing_test_data(self):
        result = self.receipt()
        self.assertEqual(result["counts"], {"total": 34, "passed": 34, "failed": 0, "skipped": 0})
        self.assertNotIn("case-", json.dumps(result))
        gate.validate_receipt(result)

    def test_junit_summary_cannot_hide_failed_skipped_or_retried_case(self):
        for tag in ("failure", "error", "skipped", "flakyFailure", "rerunError"):
            self.junit.write_text(self.xml.replace('name="case-0"/>', f'name="case-0"><{tag}/></testcase>', 1))
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                self.receipt()

    def test_junit_missing_incomplete_duplicate_and_entity_refused(self):
        for xml in ('<testsuites tests="0"/>', self.xml.replace('tests="34"', 'tests="33"'),
                    self.xml.replace('name="case-1"', 'name="case-0"'), '<!DOCTYPE x>' + self.xml):
            self.junit.write_text(xml)
            with self.subTest(xml=xml[:50]), self.assertRaises(ValueError):
                self.receipt()

    def test_only_successful_matching_main_run_can_produce_receipt(self):
        for key, value in (("PREFLIGHT", "failure"), ("JOURNEYS", "skipped"), ("POSTFLIGHT", "failure"),
                           ("GITHUB_REF", "refs/heads/topic"), ("GITHUB_SHA", BACK), ("GITHUB_RUN_ID", "../x")):
            with self.subTest(key=key), patch.dict(self.env, {key: value}), self.assertRaises(ValueError):
                self.receipt()
        changed = {**self.pair(), "backend_commit": "3" * 40}
        with self.assertRaises(ValueError):
            gate.receipt(self.pair(), changed, self.junit, self.env)

    def command(self, *args):
        self.calls.append(args)
        if args[:2] == ("cloudformation", "describe-stacks"):
            return {"Stacks": [{"Outputs": [{"OutputKey": key, "OutputValue": value} for key, value in
                    {"FrontendUrl": gate.URL, "FrontendBucket": "archon-web-123456789012-eu-west-1"}.items()]}]}
        return {}

    def test_publisher_creates_immutable_first_then_latest_no_deletes(self):
        self.calls = []
        with patch.dict(os.environ, self.env):
            gate.publish(self.receipt(), self.command, self.request, self.git, self.html)
        writes = [args for args in self.calls if args[:2] == ("s3api", "put-object")]
        self.assertEqual(len(writes), 2)
        self.assertIn("acceptance/runs/123-2.json", writes[0])
        self.assertIn("--if-none-match", writes[0])
        self.assertIn("acceptance.json", writes[1])
        self.assertFalse(any("delete" in " ".join(args).lower() for args in self.calls))

    def test_stale_frontend_and_extra_public_fields_cause_no_writes(self):
        self.calls = []
        value = self.receipt()
        with patch.dict(os.environ, self.env), self.assertRaises(ValueError):
            gate.publish(value, self.command, lambda url: {"commit": BACK}, self.git, self.html)
        self.assertEqual(self.calls, [])
        for key, added in (("raw_session", "private"), ("human_uat", "PASS"), ("run_url", "javascript:alert(1)")):
            bad = {**copy.deepcopy(value), key: added}
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.validate_receipt(bad)

    def test_late_release_change_keeps_history_but_never_updates_latest(self):
        self.calls = []
        reads = 0
        def request(url):
            nonlocal reads
            if url.endswith("release.json"):
                reads += 1
                return {"commit": FRONT if reads == 1 else BACK}
            return self.health
        with patch.dict(os.environ, self.env), self.assertRaises(ValueError):
            gate.publish(self.receipt(), self.command, request, self.git, self.html)
        writes = [args for args in self.calls if args[:2] == ("s3api", "put-object")]
        self.assertEqual(len(writes), 1)
        self.assertIn("acceptance/runs/123-2.json", writes[0])

    def test_html_marker_missing_duplicate_or_partial_rollback_refused(self):
        for html in ("<html></html>", self.html("").replace(FRONT, BACK), self.html("") * 2):
            self.calls = []
            with self.subTest(html=html), patch.dict(os.environ, self.env), self.assertRaises(ValueError):
                gate.publish(self.receipt(), self.command, self.request, self.git, lambda url: html)
            self.assertEqual(self.calls, [])

    def test_late_html_switch_keeps_history_only(self):
        self.calls = []
        reads = iter((self.html(""), self.html("").replace(FRONT, BACK)))
        with patch.dict(os.environ, self.env), self.assertRaises(ValueError):
            gate.publish(self.receipt(), self.command, self.request, self.git, lambda url: next(reads))
        self.assertEqual(sum(args[:2] == ("s3api", "put-object") for args in self.calls), 1)

    def test_publisher_retry_preserves_producer_attempt_and_identical_history(self):
        value = self.receipt()
        for conflict in (False, True):
            self.calls = []
            def command(*args):
                if args[:2] == ("s3api", "put-object") and "--if-none-match" in args:
                    self.calls.append(args)
                    raise subprocess.CalledProcessError(255, args, stderr="An error occurred (PreconditionFailed)")
                if args[:2] == ("s3api", "get-object"):
                    self.calls.append(args)
                    Path(args[-1]).write_text("{}" if conflict else json.dumps(value, indent=2) + "\n", encoding="utf-8")
                    return {}
                return self.command(*args)
            with self.subTest(conflict=conflict), patch.dict(os.environ, {**self.env, "GITHUB_RUN_ATTEMPT": "3"}):
                if conflict:
                    with self.assertRaises(ValueError):
                        gate.publish(value, command, self.request, self.git, self.html)
                else:
                    result = gate.publish(value, command, self.request, self.git, self.html)
                    self.assertIn("123-2.json", result["public_receipt"])
            latest = [args for args in self.calls if args[:2] == ("s3api", "put-object") and "acceptance.json" in args]
            self.assertEqual(len(latest), 0 if conflict else 1)

    def test_publisher_cannot_substitute_another_producer_attempt(self):
        value = self.receipt()
        for producer in ("", "1", "3", "../2"):
            self.calls = []
            with self.subTest(producer=producer), patch.dict(os.environ, {**self.env, "ACCEPTANCE_RUN_ATTEMPT": producer}), self.assertRaises(ValueError):
                gate.publish(value, self.command, self.request, self.git, self.html)
            self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
