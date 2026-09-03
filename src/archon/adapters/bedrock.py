"""The real model, on Amazon Bedrock.

Thin on purpose. Everything Archon decides lives in ``archon.agents``; this file
chooses a model and a region and gets out of the way.

**Two facts printed by CI rather than recalled**, from
`strands.models.bedrock`: `DEFAULT_BEDROCK_MODEL_ID` is
`global.anthropic.claude-sonnet-4-6` and `DEFAULT_BEDROCK_REGION` is
`us-west-2`. The `global.` prefix is Bedrock's cross-region inference form, and
the id below follows that same shape for a more capable model.

**The model id is UNVERIFIED against a live endpoint and the label stays until a
run removes it.** CI has no AWS credentials, so nothing here has been called.
Worse, it cannot be verified by code alone: **Bedrock model access is granted
per account and per region and is an owner action in the console.** An id that
is correct and not enabled fails exactly the same way as an id that is wrong, so
the first real call is the test, and it is owner-gated.
"""

from __future__ import annotations

import os

#: Printed by CI from `strands.models.bedrock`, run 33721934523.
STRANDS_DEFAULT_MODEL_ID = "global.anthropic.claude-sonnet-4-6"
STRANDS_DEFAULT_REGION = "us-west-2"

#: What Archon asks for unless the environment says otherwise. Follows the
#: `global.anthropic.` cross-region shape observed above. UNVERIFIED: see module docstring.
MODEL_ID = os.environ.get("ARCHON_BEDROCK_MODEL_ID", "global.anthropic.claude-opus-5")
REGION = os.environ.get("ARCHON_BEDROCK_REGION", STRANDS_DEFAULT_REGION)

#: Six readers each summarise one domain and the composer writes two lines, so
#: nothing here needs a long answer. Kept small deliberately: an agent given room
#: to ramble is an agent that pads a report a human then has to read.
MAX_TOKENS = int(os.environ.get("ARCHON_BEDROCK_MAX_TOKENS", "1024"))


def bedrock_model(model_id: str | None = None, region: str | None = None):
    """Build the Bedrock model Archon's agents run on.

    Imported lazily so that `archon.adapters.bedrock` can be read, and this
    function's defaults inspected, without the SDK resolving a client or looking
    for a credential.
    """
    from strands.models import BedrockModel

    return BedrockModel(
        region_name=region or REGION,
        model_id=model_id or MODEL_ID,
        max_tokens=MAX_TOKENS,
        streaming=True,
    )
