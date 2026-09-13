"""EU token counting for Claude models without native bedrock-runtime counting.

Only the count_tokens endpoint is called here. Inference stays on the explicit
EU Bedrock profile through the metered runtime client.
"""
from __future__ import annotations

import json
from urllib.request import HTTPRedirectHandler, Request, build_opener

from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

COUNT_URL = "https://bedrock-mantle.eu-west-1.api.aws/anthropic/v1/messages/count_tokens"
MODEL = "anthropic.claude-opus-5"


def content_block(block):
    if set(block) == {"text"}:
        return {"type": "text", "text": block["text"]}
    if set(block) == {"toolUse"}:
        use = block["toolUse"]
        return {"type": "tool_use", "id": use["toolUseId"],
                "name": use["name"], "input": use["input"]}
    if set(block) == {"toolResult"}:
        result = block["toolResult"]
        converted = {"type": "tool_result", "tool_use_id": result["toolUseId"],
                     "content": [content_block(c) for c in result["content"]]}
        if "status" in result:
            converted["is_error"] = result["status"] == "error"
        return converted
    if set(block) == {"reasoningContent"}:
        reasoning = block["reasoningContent"].get("reasoningText", {})
        if set(reasoning) == {"text", "signature"}:
            return {"type": "thinking", "thinking": reasoning["text"],
                    "signature": reasoning["signature"]}
    # Do not estimate or silently drop images, citations, JSON tool blocks,
    # redacted thinking bytes, cache points or unsupported provider extensions.
    raise ValueError("Unsupported content cannot be counted exactly.")


def native_request(converse):
    if set(converse) - {"messages", "system", "toolConfig"}:
        raise ValueError("Unmapped provider fields cannot be counted exactly.")
    result = {"model": MODEL, "messages": [
        {"role": message["role"], "content": [content_block(c) for c in message["content"]]}
        for message in converse["messages"]
    ]}
    if converse.get("system"):
        result["system"] = [content_block(block) for block in converse["system"]]
    tools = converse.get("toolConfig")
    if tools:
        if set(tools) - {"tools", "toolChoice"}:
            raise ValueError("Unmapped tool configuration cannot be counted exactly.")
        result["tools"] = []
        for entry in tools["tools"]:
            if set(entry) != {"toolSpec"}:
                raise ValueError("Unsupported tool block.")
            spec = entry["toolSpec"]
            if set(spec) - {"name", "description", "inputSchema"}:
                raise ValueError("Unsupported tool feature.")
            result["tools"].append({
                "name": spec["name"], "description": spec.get("description", ""),
                "input_schema": spec["inputSchema"]["json"],
            })
        if "toolChoice" in tools:
            choice = tools["toolChoice"]
            if set(choice) == {"auto"}:
                result["tool_choice"] = {"type": "auto"}
            elif set(choice) == {"any"}:
                result["tool_choice"] = {"type": "any"}
            elif set(choice) == {"tool"}:
                result["tool_choice"] = {"type": "tool", "name": choice["tool"]["name"]}
            else:
                raise ValueError("Unsupported tool choice.")
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Token counter redirects are refused.")


class CountingRuntime:
    """A narrow boto-compatible adapter: signed count-only HTTP and real Converse."""

    def __init__(self, runtime, session, opener=None):
        self.runtime, self.session, self.meta = runtime, session, runtime.meta
        self.opener = opener if opener is not None else build_opener(NoRedirect())

    def converse(self, **kwargs):
        return self.runtime.converse(**kwargs)

    def count_tokens(self, *, modelId, input):
        if modelId != MODEL or set(input) != {"converse"}:
            raise ValueError("Only the configured Claude text conversation can be counted.")
        body = json.dumps(native_request(input["converse"])).encode()
        credentials = self.session.get_credentials()
        if credentials is None:
            raise ValueError("The worker has no signing identity.")
        signed = AWSRequest(method="POST", url=COUNT_URL, data=body, headers={
            "Content-Type": "application/json", "anthropic-version": "2023-06-01",
        })
        SigV4Auth(credentials.get_frozen_credentials(), "bedrock-mantle", "eu-west-1").add_auth(
            signed
        )
        request = Request(COUNT_URL, data=body, headers=dict(signed.headers.items()), method="POST")
        with self.opener.open(request, timeout=20) as response:
            if response.status != 200:
                raise ValueError("Token counting was not accepted.")
            data = json.loads(response.read(32768))
        tokens = data.get("input_tokens")
        if type(tokens) is not int or tokens <= 0:
            raise ValueError("The counter returned no valid input token count.")
        return {"inputTokens": tokens}
