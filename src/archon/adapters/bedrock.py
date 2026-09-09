"""The real model, on Amazon Bedrock.

Thin on purpose. Everything Archon decides lives in ``archon.agents``; this file
chooses a model and a region and gets out of the way.

**Europe, on purpose, since 2026-09-09.** The SDK's default region is
`us-west-2` and this ran there for a week because that is what a default does:
nobody chooses it. The buyer is a European sole trader. Every address, IBAN, tax
number and phone number is redacted before anything leaves this machine, but
what remains — company names, amounts, dates — is still a European business's
commercial data, and it belongs in the EU.

**The prefix matters more than the region argument.** `global.` is Bedrock's
cross-region inference form and it may route a request wherever there is
capacity, including out of Europe. `eu.` keeps inference in the European
regions. Both were called live on 2026-09-09 from `eu-west-1` and both answered.

**Two facts printed by CI rather than recalled**, from `strands.models.bedrock`:
`DEFAULT_BEDROCK_MODEL_ID` is `global.anthropic.claude-sonnet-4-6` and
`DEFAULT_BEDROCK_REGION` is `us-west-2`. Both are recorded here as the defaults
this project deliberately does not use.

**Bedrock model access is granted per account and per region and is an owner
action in the console.** An id that is correct and not enabled fails exactly the
same way as an id that is wrong.
"""

from __future__ import annotations

import os

#: Printed by CI from `strands.models.bedrock`, run 33721934523.
STRANDS_DEFAULT_MODEL_ID = "global.anthropic.claude-sonnet-4-6"
STRANDS_DEFAULT_REGION = "us-west-2"

#: Where this project actually runs. Not the SDK default, and the difference is
#: the point: `eu.` is the European inference profile, so a request is not routed
#: out of the EU to find capacity.
ARCHON_REGION = "eu-west-1"
ARCHON_MODEL_ID = "eu.anthropic.claude-opus-5"

#: What Archon asks for unless the environment says otherwise. Verified against a
#: live endpoint from eu-west-1 on 2026-09-09.
MODEL_ID = os.environ.get("ARCHON_BEDROCK_MODEL_ID", ARCHON_MODEL_ID)
REGION = os.environ.get("ARCHON_BEDROCK_REGION", ARCHON_REGION)

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
