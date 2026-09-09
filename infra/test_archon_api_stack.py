"""Offline least-privilege and durable-state checks for the public API stack."""
import unittest
from archon_api_stack import template


class ApiStackContract(unittest.TestCase):
    def setUp(self):
        self.resources = template()["Resources"]

    def test_runtime_has_only_own_sessions_and_no_live_adapters(self):
        statements = self.resources["Role"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
        s3 = next(row for row in statements if row["Effect"] == "Allow" and "s3:PutObject" in row["Action"])
        self.assertEqual(s3["Resource"], {"Fn::Sub": "${State.Arn}/sessions/*"})
        self.assertNotIn("s3:DeleteObject", s3["Action"])
        denied = next(row for row in statements if row["Effect"] == "Deny")
        self.assertIn("ses:*", denied["Action"])
        self.assertIn("bedrock:InvokeModel", denied["Action"])

    def test_state_survives_stack_replacement_and_is_not_public(self):
        state = self.resources["State"]
        self.assertEqual(state["DeletionPolicy"], "Retain")
        self.assertEqual(state["UpdateReplacePolicy"], "Retain")
        self.assertTrue(all(state["Properties"]["PublicAccessBlockConfiguration"].values()))
        self.assertEqual(state["Properties"]["VersioningConfiguration"]["Status"], "Enabled")

    def test_api_is_bounded_and_configuration_matches_handler(self):
        function = self.resources["Function"]["Properties"]
        self.assertEqual(function["Handler"], "archon.web.lambda_handler.handler")
        self.assertEqual(function["Runtime"], "python3.12")
        self.assertLessEqual(function["Timeout"], 29)
        self.assertEqual(function["ReservedConcurrentExecutions"], 5)
        self.assertIn("ARCHON_STATE_BUCKET", function["Environment"]["Variables"])
        self.assertIn("ARCHON_COMMIT_SHA", function["Environment"]["Variables"])
        self.assertEqual(self.resources["Integration"]["Properties"]["PayloadFormatVersion"], "2.0")

    def test_existing_archon_services_are_not_targets(self):
        names = [entry["Properties"].get("FunctionName") for entry in self.resources.values()]
        self.assertEqual([name for name in names if isinstance(name, str)], ["archon-afh-api"])
        self.assertFalse(any(item["Type"] == "AWS::Lambda::Url" for item in self.resources.values()))
        self.assertEqual(self.resources["Invoke"]["Properties"]["Principal"], "apigateway.amazonaws.com")


if __name__ == "__main__":
    unittest.main(verbosity=2)
