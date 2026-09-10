"""CI-only structural regression checks for main -> deploy -> live UAT."""
import copy
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def read_workflow(name):
    # BaseLoader preserves GitHub's 'on' and booleans as strings (YAML 1.1 differs).
    return yaml.load((ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader)


def validate(deploy, uat):
    assert deploy["on"]["push"] == {"branches": ["main"]}
    assert "workflow_dispatch" in deploy["on"]
    assert deploy["concurrency"]["queue"] == "max"
    assert deploy["concurrency"]["cancel-in-progress"] == "false"
    jobs = deploy["jobs"]
    assert jobs["verify"]["uses"] == "./.github/workflows/frontend-ci.yml"
    assert jobs["release"]["needs"] == "verify"
    assert jobs["release"]["if"] == "github.ref == 'refs/heads/main'"
    acceptance = jobs["acceptance"]
    assert acceptance["needs"] == "release"
    assert acceptance["uses"] == "./.github/workflows/aws-uat.yml"
    assert acceptance["with"]["release_sha"] == "${{ github.sha }}"
    assert acceptance["permissions"] == {"contents": "read", "actions": "read", "id-token": "write"}
    assert acceptance["with"]["backend_sha"] == "${{ needs.release.outputs.backend_sha }}"
    assert "continue-on-error" not in acceptance
    assert "secrets" not in acceptance
    for trigger in ("workflow_call", "workflow_dispatch"):
        value = uat["on"][trigger]["inputs"]["release_sha"]
        assert value["required"] == "true" and value["type"] == "string"
    assert uat["permissions"] == {"contents": "read"}
    assert uat["concurrency"]["group"] != deploy["concurrency"]["group"]
    assert uat["concurrency"]["queue"] == "max"
    assert uat["concurrency"]["cancel-in-progress"] == "false"
    job = uat["jobs"]["acceptance"]
    assert job["permissions"] == {"contents": "read"}
    assert "continue-on-error" not in job
    assert job["env"]["EXPECTED_RELEASE"] == "${{ inputs.release_sha }}"
    steps = job["steps"]
    indexed = {step.get("id"): step for step in steps if "id" in step}
    assert indexed["journeys"]["run"] == "npm run test:e2e -- --forbid-only"
    assert "continue-on-error" not in indexed["journeys"]
    assert "frontend_smoke.py" in indexed["preflight"]["run"]
    assert "frontend_smoke.py" in indexed["postflight"]["run"]
    assert indexed["postflight"]["if"] == "always() && steps.journeys.outcome != 'skipped'"
    assert steps.index(indexed["preflight"]) < steps.index(indexed["journeys"])
    assert steps.index(indexed["postflight"]) > steps.index(indexed["journeys"])
    assert not any("configure-aws-credentials" in step.get("uses", "") for step in steps)
    artifact = next((step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@") and step.get("if") == "always()"), None)
    assert artifact is not None
    assert artifact["if"] == "always()"
    assert artifact["with"]["retention-days"] == "90"
    for path in ("frontend/test-results/", "frontend/artifacts/browser-junit.xml",
                 "frontend/playwright-report/", "frontend/UAT.testbook.*"):
        assert path in artifact["with"]["path"].splitlines()
    for stage in ("preflight", "postflight"):
        assert 'release_acceptance.py pair' in indexed[stage]["run"]
        assert '--backend "$EXPECTED_BACKEND"' in indexed[stage]["run"]
    release_steps = jobs["release"]["steps"]
    backend = next(step for step in release_steps if step.get("id") == "backend")
    publish_frontend = next(step for step in release_steps if "frontend_publish.py" in step.get("run", ""))
    assert release_steps.index(backend) < release_steps.index(publish_frontend)
    assert 'release_acceptance.py pair' in backend["run"]
    publisher = uat["jobs"]["publish"]
    assert publisher["needs"] == "acceptance" and publisher["if"] == "github.ref == 'refs/heads/main'"
    assert publisher["permissions"] == {"contents": "read", "actions": "read", "id-token": "write"}
    assert not any("playwright" in step.get("run", "") or "npm" in step.get("run", "") for step in publisher["steps"])
    assert any("release_acceptance.py publish" in step.get("run", "") for step in publisher["steps"])
    assert job["outputs"] == {"receipt_artifact": "${{ steps.receipt.outputs.artifact }}",
                              "receipt_attempt": "${{ steps.receipt.outputs.attempt }}"}
    assert publisher["env"]["ACCEPTANCE_RUN_ATTEMPT"] == "${{ needs.acceptance.outputs.receipt_attempt }}"
    download = next(step for step in publisher["steps"] if "actions/download-artifact@" in step.get("uses", ""))
    assert download["with"]["name"] == "${{ needs.acceptance.outputs.receipt_artifact }}"
    assert publisher["concurrency"] == jobs["release"]["concurrency"] == {
        "group": "archon-frontend-writer", "cancel-in-progress": "false", "queue": "max"}


class MainAcceptanceContract(unittest.TestCase):
    def setUp(self):
        self.deploy = read_workflow("frontend-deploy.yml")
        self.uat = read_workflow("aws-uat.yml")

    def test_checked_in_pipeline(self):
        validate(self.deploy, self.uat)

    def test_missing_main_trigger_is_rejected(self):
        self.deploy["on"]["push"]["branches"] = ["dev"]
        with self.assertRaises(AssertionError):
            validate(self.deploy, self.uat)

    def test_test_before_deployment_is_rejected(self):
        self.deploy["jobs"]["acceptance"]["needs"] = "verify"
        with self.assertRaises(AssertionError):
            validate(self.deploy, self.uat)

    def test_dropped_pending_merges_are_rejected(self):
        self.deploy["concurrency"]["queue"] = "single"
        with self.assertRaises(AssertionError):
            validate(self.deploy, self.uat)

    def test_wrong_tested_commit_is_rejected(self):
        self.deploy["jobs"]["acceptance"]["with"]["release_sha"] = "main"
        with self.assertRaises(AssertionError):
            validate(self.deploy, self.uat)

    def test_ignored_browser_failure_is_rejected(self):
        self.deploy["jobs"]["acceptance"]["continue-on-error"] = "true"
        with self.assertRaises(AssertionError):
            validate(self.deploy, self.uat)

    def test_cloud_credentials_in_browser_job_are_rejected(self):
        self.uat["permissions"]["id-token"] = "write"
        with self.assertRaises(AssertionError):
            validate(self.deploy, self.uat)

    def test_job_level_browser_credentials_are_rejected(self):
        self.uat["jobs"]["acceptance"]["permissions"]["id-token"] = "write"
        with self.assertRaises(AssertionError):
            validate(self.deploy, self.uat)

    def test_publisher_cannot_run_before_acceptance(self):
        self.uat["jobs"]["publish"]["needs"] = "release"
        with self.assertRaises(AssertionError):
            validate(self.deploy, self.uat)

    def test_publisher_retry_cannot_replace_producer_identity(self):
        self.uat["jobs"]["publish"]["env"]["ACCEPTANCE_RUN_ATTEMPT"] = "${{ github.run_attempt }}"
        with self.assertRaises(AssertionError):
            validate(self.deploy, self.uat)

    def test_frontend_and_receipt_publishers_cannot_have_different_writer_locks(self):
        self.uat["jobs"]["publish"]["concurrency"]["group"] = "unrelated-lock"
        with self.assertRaises(AssertionError):
            validate(self.deploy, self.uat)

    def test_backend_check_cannot_be_removed(self):
        for step in self.deploy["jobs"]["release"]["steps"]:
            if step.get("id") == "backend":
                step["run"] = "true"
        with self.assertRaises(AssertionError):
            validate(self.deploy, self.uat)

    def test_missing_postflight_or_failure_artifacts_are_rejected(self):
        for broken in ("postflight", "artifact"):
            uat = copy.deepcopy(self.uat)
            for step in uat["jobs"]["acceptance"]["steps"]:
                if broken == "postflight" and step.get("id") == "postflight":
                    step["run"] = "true"
                if broken == "artifact" and step.get("uses", "").startswith("actions/upload-artifact@"):
                    step["if"] = "success()"
            with self.subTest(broken=broken), self.assertRaises(AssertionError):
                validate(self.deploy, uat)


if __name__ == "__main__":
    unittest.main(verbosity=2)
