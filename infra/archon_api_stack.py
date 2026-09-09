"""CloudFormation for Archon's isolated public synthetic workspace API.

No SES, Bedrock, customer stack, or external-send permissions. The separate
operator-controlled live adapters remain outside this anonymous execution role.
"""
from __future__ import annotations

import json

from frontend_stack import attr, ref, sub


def template():
    private = {
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True, "BlockPublicPolicy": True,
            "IgnorePublicAcls": True, "RestrictPublicBuckets": True,
        },
        "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
        "BucketEncryption": {"ServerSideEncryptionConfiguration": [
            {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
        ]},
        "VersioningConfiguration": {"Status": "Enabled"},
    }
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Archon Agents for Humans synthetic session API, independent of other Archon deployments.",
        "Parameters": {
            "CodeBucket": {"Type": "String", "AllowedPattern": "archon-afh-deploy-[0-9]{12}-eu-west-1"},
            "CodeKey": {"Type": "String", "AllowedPattern": "releases/[0-9a-f]{40}/archon-api.zip"},
            "CommitSha": {"Type": "String", "AllowedPattern": "[0-9a-f]{40}"},
        },
        "Resources": {
            "State": {
                "Type": "AWS::S3::Bucket", "DeletionPolicy": "Retain", "UpdateReplacePolicy": "Retain",
                "Properties": {
                    **private, "BucketName": sub("archon-afh-state-${AWS::AccountId}-${AWS::Region}"),
                    "LifecycleConfiguration": {"Rules": [
                        {"Id": "synthetic-session-retention", "Status": "Enabled", "Prefix": "sessions/", "ExpirationInDays": 90},
                        {"Id": "old-session-versions", "Status": "Enabled", "NoncurrentVersionExpirationInDays": 30},
                    ]},
                    "Tags": [{"Key": "project", "Value": "archon-agentsforhumans"}],
                },
            },
            "StateTls": {
                "Type": "AWS::S3::BucketPolicy",
                "Properties": {"Bucket": ref("State"), "PolicyDocument": {
                    "Version": "2012-10-17", "Statement": [{
                        "Effect": "Deny", "Principal": "*", "Action": "s3:*",
                        "Resource": [attr("State", "Arn"), sub("${State.Arn}/*")],
                        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                    }],
                }},
            },
            "Logs": {
                "Type": "AWS::Logs::LogGroup",
                "Properties": {"LogGroupName": "/aws/lambda/archon-afh-api", "RetentionInDays": 14},
            },
            "Role": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": "archon-afh-api-runtime",
                    "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{
                        "Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole",
                    }]},
                    "Policies": [{"PolicyName": "synthetic-session-storage-only", "PolicyDocument": {
                        "Version": "2012-10-17", "Statement": [
                            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
                             "Resource": sub("${State.Arn}/sessions/*")},
                            {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                             "Resource": sub("arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/archon-afh-api:*")},
                            {"Effect": "Deny", "Action": ["ses:*", "bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"], "Resource": "*"},
                        ],
                    }}],
                },
            },
            "Function": {
                "Type": "AWS::Lambda::Function", "DependsOn": "Logs",
                "Properties": {
                    "FunctionName": "archon-afh-api", "Runtime": "python3.12",
                    "Architectures": ["x86_64"], "Handler": "archon.web.lambda_handler.handler",
                    "Role": attr("Role", "Arn"),
                    "Code": {"S3Bucket": ref("CodeBucket"), "S3Key": ref("CodeKey")},
                    "Timeout": 28, "MemorySize": 1024, "ReservedConcurrentExecutions": 5,
                    "Environment": {"Variables": {
                        "ARCHON_STATE_BUCKET": ref("State"), "ARCHON_STATE_PREFIX": "sessions/",
                        "ARCHON_COMMIT_SHA": ref("CommitSha"),
                    }},
                    "Tags": [{"Key": "project", "Value": "archon-agentsforhumans"}],
                },
            },
            "Api": {
                "Type": "AWS::ApiGatewayV2::Api",
                "Properties": {"Name": "archon-afh-api", "ProtocolType": "HTTP",
                               "Description": "Anonymous synthetic workspace, no live sends or model billing."},
            },
            "Integration": {
                "Type": "AWS::ApiGatewayV2::Integration",
                "Properties": {
                    "ApiId": ref("Api"), "IntegrationType": "AWS_PROXY",
                    "IntegrationUri": attr("Function", "Arn"),
                    "PayloadFormatVersion": "2.0", "TimeoutInMillis": 29000,
                },
            },
            "Route": {
                "Type": "AWS::ApiGatewayV2::Route",
                "Properties": {"ApiId": ref("Api"), "RouteKey": "$default",
                               "Target": sub("integrations/${Integration}")},
            },
            "Stage": {
                "Type": "AWS::ApiGatewayV2::Stage",
                "Properties": {"ApiId": ref("Api"), "StageName": "$default", "AutoDeploy": True,
                               "DefaultRouteSettings": {"ThrottlingRateLimit": 5, "ThrottlingBurstLimit": 10}},
            },
            "Invoke": {
                "Type": "AWS::Lambda::Permission",
                "Properties": {
                    "FunctionName": ref("Function"), "Action": "lambda:InvokeFunction",
                    "Principal": "apigateway.amazonaws.com",
                    "SourceArn": sub("arn:${AWS::Partition}:execute-api:${AWS::Region}:${AWS::AccountId}:${Api}/*"),
                },
            },
            "Errors": {
                "Type": "AWS::CloudWatch::Alarm",
                "Properties": {
                    "AlarmName": "archon-afh-api-errors", "AlarmDescription": "Inspect public workspace API failures. No notification subscription is configured.",
                    "Namespace": "AWS/Lambda", "MetricName": "Errors", "Statistic": "Sum",
                    "Period": 300, "EvaluationPeriods": 1, "Threshold": 5,
                    "ComparisonOperator": "GreaterThanOrEqualToThreshold", "TreatMissingData": "notBreaching",
                    "Dimensions": [{"Name": "FunctionName", "Value": ref("Function")}],
                },
            },
        },
        "Outputs": {
            "ApiUrl": {"Value": sub("https://${Api}.execute-api.${AWS::Region}.amazonaws.com/")},
            "ApiDomain": {"Value": sub("${Api}.execute-api.${AWS::Region}.amazonaws.com")},
            "FunctionName": {"Value": ref("Function")},
            "StateBucket": {"Value": ref("State")},
            "DeployedSha": {"Value": ref("CommitSha")},
        },
    }


if __name__ == "__main__":
    print(json.dumps(template(), indent=2))
