"""Source-only checks; no credential or provisioned resource is required."""
import unittest

from archon_api_stack import template as api_template
from live_provider_stack import template


class LiveWorkerContract(unittest.TestCase):
    def test_private_worker_has_no_public_entry_and_no_unbounded_allow(self):
        resources = template()["Resources"]
        self.assertFalse(any(r["Type"] in {"AWS::Lambda::Url", "AWS::ApiGatewayV2::Api"}
                             for r in resources.values()))
        policy = resources["Role"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
        for row in policy:
            self.assertNotEqual(row["Resource"], "*")
            self.assertNotIn("s3:DeleteObject", row["Action"])
        ses = next(row for row in policy if "ses:SendEmail" in row["Action"])
        self.assertIn("ses:Recipients", ses["Condition"]["ForAllValues:StringEquals"])
        invocation = resources["ApiDispatchOnly"]["Properties"]["PolicyDocument"]["Statement"]
        self.assertEqual(invocation[0]["Action"], ["lambda:InvokeFunction"])

    def test_no_retry_and_recoverable_failure_records(self):
        resources = template()["Resources"]
        self.assertEqual(resources["AsyncPolicy"]["Properties"]["MaximumRetryAttempts"], 0)
        self.assertEqual(resources["Worker"]["Properties"]["ReservedConcurrentExecutions"], 2)
        self.assertLess(resources["Worker"]["Properties"]["Timeout"], 900)
        self.assertEqual(resources["Failures"]["DeletionPolicy"], "Retain")
        self.assertTrue(resources["Failures"]["Properties"]["SqsManagedSseEnabled"])

    def test_api_stays_off_by_default_and_keeps_direct_provider_denies(self):
        api = api_template()
        self.assertEqual(api["Parameters"]["LiveEnabled"]["Default"], "false")
        statements = api["Resources"]["Role"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
        denied = next(row for row in statements if row["Effect"] == "Deny")
        self.assertIn("ses:*", denied["Action"])
        self.assertIn("bedrock:InvokeModel", denied["Action"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
