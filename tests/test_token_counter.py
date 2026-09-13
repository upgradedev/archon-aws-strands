"""Native token-counter mapping and signed request contracts; no network in CI."""
import io
import json
from types import SimpleNamespace

import pytest
from botocore.credentials import Credentials

from archon.adapters.token_counter import (
    COUNT_URL,
    MODEL,
    CountingRuntime,
    NoRedirect,
    content_block,
    native_request,
)


def conversation():
    return {"system": [{"text": "Read only."}], "messages": [
        {"role": "user", "content": [{"text": "State the ledger."}]},
        {"role": "assistant", "content": [
            {"reasoningContent": {"reasoningText": {
                "text": "Inspect the source.", "signature": "sig"}}},
            {"toolUse": {"toolUseId": "tool-1", "name": "sales", "input": {}}},
        ]},
        {"role": "user", "content": [{"toolResult": {
            "toolUseId": "tool-1", "status": "success", "content": [{"text": "1260.00 EUR"}],
        }}]},
    ], "toolConfig": {"tools": [{"toolSpec": {
        "name": "sales", "description": "Ledger source",
        "inputSchema": {"json": {"type": "object"}},
    }}], "toolChoice": {"auto": {}}}}


def test_conversion_keeps_system_tools_reasoning_and_tool_results():
    native = native_request(conversation())
    assert native["system"] == [{"type": "text", "text": "Read only."}]
    assert native["tools"][0]["input_schema"] == {"type": "object"}
    assert native["messages"][1]["content"][0]["signature"] == "sig"
    assert native["messages"][1]["content"][1]["id"] == "tool-1"
    result = native["messages"][2]["content"][0]
    assert result["tool_use_id"] == "tool-1" and result["is_error"] is False
    assert result["content"] == [{"type": "text", "text": "1260.00 EUR"}]


@pytest.mark.parametrize("choice,expected", [
    ({"auto": {}}, {"type": "auto"}), ({"any": {}}, {"type": "any"}),
    ({"tool": {"name": "sales"}}, {"type": "tool", "name": "sales"}),
])
def test_tool_choice_is_counted(choice, expected):
    value = conversation()
    value["toolConfig"]["toolChoice"] = choice
    assert native_request(value)["tool_choice"] == expected


@pytest.mark.parametrize("block", [
    {"image": {}}, {"json": {"value": 2}}, {"cachePoint": {}},
    {"text": "x", "unknown": True}, {"reasoningContent": {"redactedContent": "opaque"}},
])
def test_unsupported_blocks_are_not_approximated(block):
    with pytest.raises(ValueError, match="cannot be counted"):
        content_block(block)


@pytest.mark.parametrize("change", [
    lambda c: c.update(additionalModelRequestFields={}),
    lambda c: c["toolConfig"].update(cachePoint={}),
    lambda c: c["toolConfig"]["tools"].append({"cachePoint": {}}),
    lambda c: c["toolConfig"]["tools"][0]["toolSpec"].update(strict=True),
    lambda c: c["toolConfig"].update(toolChoice={"unknown": {}}),
])
def test_unmapped_request_features_stop_before_network(change):
    value = conversation()
    change(value)
    with pytest.raises(ValueError):
        native_request(value)


def test_signed_request_has_fixed_count_only_destination_and_no_inference():
    requests = []
    runtime = SimpleNamespace(meta=SimpleNamespace(region_name="eu-west-1"),
                              converse=lambda **kw: {"response": kw})
    session = SimpleNamespace(get_credentials=lambda: Credentials("unit-key", "unit-secret"))

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            assert request.full_url == COUNT_URL and timeout == 20
            assert "bedrock-mantle" in request.get_header("Authorization")
            assert json.loads(request.data)["model"] == MODEL
            stream = io.BytesIO(b'{"input_tokens":15}')
            stream.status = 200
            return stream

    counter = CountingRuntime(runtime, session, Opener())
    assert counter.count_tokens(modelId=MODEL, input={"converse": conversation()}) == {
        "inputTokens": 15,
    }
    assert len(requests) == 1
    assert counter.converse(test="value") == {"response": {"test": "value"}}
    with pytest.raises(ValueError):
        counter.count_tokens(modelId="another", input={"converse": conversation()})
    counter.session = SimpleNamespace(get_credentials=lambda: None)
    with pytest.raises(ValueError, match="signing identity"):
        counter.count_tokens(modelId=MODEL, input={"converse": conversation()})
    with pytest.raises(ValueError, match="redirects"):
        NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.test")


@pytest.mark.parametrize("status,payload", [(503, {}), (200, {"input_tokens": False}),
                                           (200, {"input_tokens": -1}), (200, {})])
def test_http_and_invalid_counter_results_are_refused(status, payload):
    class Opener:
        def open(self, request, timeout):
            stream = io.BytesIO(json.dumps(payload).encode())
            stream.status = status
            return stream

    counter = CountingRuntime(
        SimpleNamespace(meta=None), SimpleNamespace(
            get_credentials=lambda: Credentials("unit-key", "unit-secret")), Opener()
    )
    with pytest.raises(ValueError):
        counter.count_tokens(modelId=MODEL, input={"converse": conversation()})
