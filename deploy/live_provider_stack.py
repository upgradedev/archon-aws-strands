"""Separate bounded provider worker. Rendering does not deploy or enable the public API."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "infra"))
from frontend_stack import attr, ref, sub


def template():
    eu_regions = ("eu-west-1", "eu-west-3", "eu-north-1",
                  "eu-central-1", "eu-south-1", "eu-south-2")
    model_arns = [sub(f"arn:${{AWS::Partition}}:bedrock:{region}::foundation-model/anthropic.claude-opus-5")
                  for region in eu_regions]
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Private Archon real-provider worker; API opt-in and operating grant are separate.",
        "Parameters": {
            "CodeBucket": {"Type": "String", "AllowedPattern": "archon-afh-deploy-[0-9]{12}-eu-west-1"},
            "CodeKey": {"Type": "String", "AllowedPattern": "releases/[0-9a-f]{40}/archon-api.zip"},
            "CommitSha": {"Type": "String", "AllowedPattern": "[0-9a-f]{40}"},
            "StateBucket": {"Type": "String", "AllowedPattern": "archon-afh-state-[0-9]{12}-eu-west-1"},
            "Sender": {"Type": "String", "AllowedPattern": r"[^\s@]+@[^\s@]+\.[^\s@]+"},
            "Recipient": {"Type": "String", "AllowedPattern": r"[^\s@]+@[^\s@]+\.[^\s@]+"},
            "ExpiresAt": {"Type": "String", "AllowedPattern": r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"},
        },
        "Resources": {
            "Logs": {"Type": "AWS::Logs::LogGroup", "Properties": {
                "LogGroupName": "/aws/lambda/archon-afh-providers", "RetentionInDays": 14,
            }},
            "Failures": {"Type": "AWS::SQS::Queue", "DeletionPolicy": "Retain",
                         "UpdateReplacePolicy": "Retain", "Properties": {
                "QueueName": "archon-afh-provider-failures", "SqsManagedSseEnabled": True,
                "MessageRetentionPeriod": 1209600,
            }},
            "Role": {"Type": "AWS::IAM::Role", "Properties": {
                "RoleName": "archon-afh-provider-runtime",
                "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{
                    "Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }]},
                "Policies": [{"PolicyName": "bounded-real-providers", "PolicyDocument": {
                    "Version": "2012-10-17", "Statement": [
                        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
                         "Resource": [sub("arn:${AWS::Partition}:s3:::${StateBucket}/sessions/*"),
                                      sub("arn:${AWS::Partition}:s3:::${StateBucket}/provider/*")]},
                        {"Effect": "Allow", "Action": ["bedrock:InvokeModel"],
                         "Resource": [sub("arn:${AWS::Partition}:bedrock:eu-west-1:${AWS::AccountId}:inference-profile/eu.anthropic.claude-opus-5"), *model_arns],
                         "Condition": {"DateLessThan": {"aws:CurrentTime": ref("ExpiresAt")}}},
                        {"Effect": "Allow", "Action": ["bedrock-mantle:CountTokens"],
                         "Resource": sub("arn:${AWS::Partition}:bedrock-mantle:eu-west-1:${AWS::AccountId}:project/default"),
                         "Condition": {"StringEquals": {"bedrock-mantle:Model": "anthropic.claude-opus-5"},
                                       "DateLessThan": {"aws:CurrentTime": ref("ExpiresAt")}}},
                        {"Effect": "Allow", "Action": ["ses:SendEmail"],
                         "Resource": [
                             sub("arn:${AWS::Partition}:ses:eu-west-1:${AWS::AccountId}:identity/${Sender}"),
                             sub("arn:${AWS::Partition}:ses:eu-west-1:${AWS::AccountId}:identity/${Recipient}"),
                         ],
                         "Condition": {"StringEquals": {"ses:FromAddress": ref("Sender")},
                                       "ForAllValues:StringEquals": {"ses:Recipients": [ref("Recipient")]},
                                       "DateLessThan": {"aws:CurrentTime": ref("ExpiresAt")}}},
                        {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                         "Resource": sub("arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/archon-afh-providers:*")},
                        {"Effect": "Allow", "Action": ["sqs:SendMessage"],
                         "Resource": attr("Failures", "Arn")},
                    ],
                }}],
            }},
            "Worker": {"Type": "AWS::Lambda::Function", "DependsOn": "Logs", "Properties": {
                "FunctionName": "archon-afh-providers", "Runtime": "python3.12",
                "Architectures": ["x86_64"], "Handler": "archon.web.live.handler",
                "Role": attr("Role", "Arn"), "Timeout": 840, "MemorySize": 1024,
                "ReservedConcurrentExecutions": 2,
                "Code": {"S3Bucket": ref("CodeBucket"), "S3Key": ref("CodeKey")},
                "Environment": {"Variables": {
                    "ARCHON_STATE_BUCKET": ref("StateBucket"), "ARCHON_STATE_PREFIX": "sessions/",
                    "ARCHON_COMMIT_SHA": ref("CommitSha"), "ARCHON_LIVE_ENABLED": "true",
                    "ARCHON_LIVE_SENDER": ref("Sender"), "ARCHON_LIVE_RECIPIENT": ref("Recipient"),
                    "ARCHON_LIVE_WORKER_ARN": sub("arn:${AWS::Partition}:lambda:${AWS::Region}:${AWS::AccountId}:function:archon-afh-providers"),
                }},
            }},
            "AsyncPolicy": {"Type": "AWS::Lambda::EventInvokeConfig", "Properties": {
                "FunctionName": ref("Worker"), "Qualifier": "$LATEST",
                "MaximumRetryAttempts": 0, "MaximumEventAgeInSeconds": 300,
                "DestinationConfig": {"OnFailure": {"Destination": attr("Failures", "Arn")}},
            }},
            "ApiDispatchOnly": {"Type": "AWS::IAM::Policy", "Properties": {
                "PolicyName": "invoke-own-provider-worker",
                "Roles": ["archon-afh-api-runtime"],
                "PolicyDocument": {"Version": "2012-10-17", "Statement": [{
                    "Effect": "Allow", "Action": ["lambda:InvokeFunction"],
                    "Resource": attr("Worker", "Arn"),
                }]},
            }},
            "FailureAlarm": {"Type": "AWS::CloudWatch::Alarm", "Properties": {
                "AlarmDescription": "Reconcile retained failed jobs; never automatically resend.",
                "Namespace": "AWS/SQS", "MetricName": "ApproximateNumberOfMessagesVisible",
                "Dimensions": [{"Name": "QueueName", "Value": attr("Failures", "QueueName")}],
                "Statistic": "Maximum", "Period": 60, "EvaluationPeriods": 1, "Threshold": 1,
                "ComparisonOperator": "GreaterThanOrEqualToThreshold", "TreatMissingData": "notBreaching",
            }},
        },
        "Outputs": {"WorkerArn": {"Value": attr("Worker", "Arn")},
                    "FailureQueueUrl": {"Value": ref("Failures")}},
    }


if __name__ == "__main__":
    print(json.dumps(template(), indent=2))
