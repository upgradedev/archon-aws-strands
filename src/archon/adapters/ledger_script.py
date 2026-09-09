"""A disclosed deterministic model that actually calls each Strands reader tool."""

from __future__ import annotations

from archon.adapters.scripted import ScriptedModel


class LedgerScriptModel(ScriptedModel):
    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        # A reader's first turn asks its one bound tool; its second reports the
        # real tool result. No synthetic judgment or captured report is substituted.
        if tool_specs:
            results = [
                block["toolResult"]
                for message in messages
                for block in message.get("content", [])
                if "toolResult" in block
            ]
            if not results:
                name = tool_specs[0]["name"]
                yield {"messageStart": {"role": "assistant"}}
                yield {
                    "contentBlockStart": {
                        "contentBlockIndex": 0,
                        "start": {"toolUse": {"toolUseId": f"read-{name}", "name": name}},
                    }
                }
                yield {
                    "contentBlockDelta": {
                        "contentBlockIndex": 0,
                        "delta": {"toolUse": {"input": "{}"}},
                    }
                }
                yield {"contentBlockStop": {"contentBlockIndex": 0}}
                yield {"messageStop": {"stopReason": "tool_use"}}
                return
            if any(result.get("status") == "error" for result in results):
                raise ValueError("A ledger reader failed; the composer cannot proceed.")
            text = "\n".join(block.get("text", "") for block in results[-1].get("content", []))
            if not text.strip():
                raise ValueError("A ledger reader returned no report.")
        else:
            text = self.default
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": text}}}
        yield {"contentBlockStop": {"contentBlockIndex": 0}}
        yield {"messageStop": {"stopReason": "end_turn"}}
