"""New controlled-mode API template; historical infrastructure bytes stay unchanged."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "infra"))
from archon_api_stack import template as historical_template


def template():
    result = historical_template()
    result["Description"] = "Archon workspace API with separately reviewed real-provider opt-in."
    result["Parameters"].update({
        "LiveEnabled": {"Type": "String", "AllowedValues": ["false", "true"], "Default": "false"},
        "LiveWorkerArn": {"Type": "String", "Default": "",
                          "AllowedPattern": "^$|arn:aws:lambda:eu-west-1:[0-9]{12}:function:archon-afh-providers"},
        "LiveSender": {"Type": "String", "Default": ""},
        "LiveRecipient": {"Type": "String", "Default": ""},
    })
    environment = result["Resources"]["Function"]["Properties"]["Environment"]["Variables"]
    for suffix, parameter in (("ENABLED", "LiveEnabled"), ("WORKER_ARN", "LiveWorkerArn"),
                              ("SENDER", "LiveSender"), ("RECIPIENT", "LiveRecipient")):
        environment["ARCHON_LIVE_" + suffix] = {"Ref": parameter}
    result["Resources"]["State"]["Properties"]["LifecycleConfiguration"]["Rules"].append({
        "Id": "provider-journal-retention", "Status": "Enabled",
        "Prefix": "provider/", "ExpirationInDays": 90,
    })
    return result


if __name__ == "__main__":
    print(json.dumps(template(), indent=2))
