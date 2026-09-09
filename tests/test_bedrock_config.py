"""What Archon asks Bedrock for, without asking Bedrock for anything.

No AWS call is made here and none can be: the SDK import lives inside
``bedrock_model`` precisely so the defaults can be read without a client being
resolved or a credential being looked for. What these tests pin is the
configuration, which is the part that can be wrong silently.
"""

from __future__ import annotations

import importlib

import pytest

from archon.adapters import bedrock


def test_the_strands_defaults_are_the_ones_ci_printed():
    # From strands.models.bedrock in CI run 33721934523. Written down so a
    # future SDK bump that moves them is noticed here rather than in a bill.
    assert bedrock.STRANDS_DEFAULT_MODEL_ID == "global.anthropic.claude-sonnet-4-6"
    assert bedrock.STRANDS_DEFAULT_REGION == "us-west-2"


def test_archon_asks_for_a_more_capable_model_than_the_sdk_default():
    assert bedrock.MODEL_ID != bedrock.STRANDS_DEFAULT_MODEL_ID
    assert "opus" in bedrock.MODEL_ID


def test_the_region_is_europe_and_not_the_sdk_default():
    """Changed 2026-09-09. The SDK default was inherited rather than chosen.

    The buyer is a European sole trader. Redaction means no address, IBAN, tax
    number or phone number leaves this machine, but the commercial content that
    does is a European business's data.
    """
    assert bedrock.REGION == "eu-west-1"
    assert bedrock.REGION != bedrock.STRANDS_DEFAULT_REGION


def test_the_inference_profile_keeps_the_request_in_europe():
    """`global.` may route wherever there is capacity. `eu.` may not."""
    assert bedrock.MODEL_ID.startswith("eu.")
    assert not bedrock.MODEL_ID.startswith("global.")


def test_max_tokens_is_small_on_purpose():
    # Six readers summarise one domain each and the composer writes two lines.
    # Room to ramble is room to pad a report a human then has to read.
    assert 0 < bedrock.MAX_TOKENS <= 4096


@pytest.mark.parametrize(
    ("variable", "attribute", "value"),
    [
        ("ARCHON_BEDROCK_MODEL_ID", "MODEL_ID", "global.anthropic.claude-sonnet-5"),
        ("ARCHON_BEDROCK_REGION", "REGION", "us-east-1"),
        ("ARCHON_BEDROCK_MAX_TOKENS", "MAX_TOKENS", "512"),
    ],
)
def test_the_environment_can_override_every_choice(monkeypatch, variable, attribute, value):
    # The model id is unverified against a live endpoint and Bedrock access is
    # granted per account. Whoever runs this must be able to change it without
    # editing source.
    monkeypatch.setenv(variable, value)
    reloaded = importlib.reload(bedrock)
    try:
        expected = int(value) if attribute == "MAX_TOKENS" else value
        assert getattr(reloaded, attribute) == expected
    finally:
        monkeypatch.delenv(variable, raising=False)
        importlib.reload(bedrock)


def test_reading_this_module_does_not_import_the_sdk_client():
    """The import is inside the function. Reading config must stay side-effect free."""
    import ast
    import pathlib

    src = pathlib.Path(bedrock.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    module_level = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    names = {
        alias.name for node in module_level if isinstance(node, ast.Import) for alias in node.names
    } | {node.module or "" for node in module_level if isinstance(node, ast.ImportFrom)}
    assert not any(name.startswith(("strands", "boto3")) for name in names), names
