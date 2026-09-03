"""A model that answers from a script, so the graph runs with no AWS account.

**This is not a test double that leaked into the source tree; it is a shipped
feature and S9 is the reason.** The submission has to stay testable by a judge
`free of charge and without any restriction` until the judging period ends. A
judge who has to create an AWS account, enable Bedrock model access and wait for
a quota before anything moves is a judge who stops.

So Archon runs in two modes. With Bedrock it reasons. With this it walks the
same graph, the same six domains, the same gate and the same governed write,
and every number on screen is still computed by the ledger, because the ledger
never asked a model for a number in the first place.

What it cannot do is judge. Tone, and the decision that a chase is worth
sending, are the model's work, and a script does not do that. The README must
say so plainly rather than letting a scripted run read as an agentic one.

The stream shape is the one CI printed from ``strands.types.streaming``:
``messageStart``, ``contentBlockDelta`` carrying ``contentBlockIndex`` and
``delta``, ``contentBlockStop``, then ``messageStop``.
"""

from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass, field
from typing import Any

from strands.models.model import Model


@dataclass
class Ask:
    """One request the graph made of the model, kept for assertions."""

    system_prompt: str | None
    messages: list[Any]


@dataclass
class ScriptedModel(Model):
    """Replies from ``script`` in order, then repeats ``default`` forever."""

    script: list[str] = field(default_factory=list)
    default: str = "Noted."
    asks: list[Ask] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    def _next_reply(self) -> str:
        if len(self.asks) <= len(self.script):
            return self.script[len(self.asks) - 1]
        return self.default

    async def stream(
        self,
        messages: list[Any],
        tool_specs: list[Any] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[dict[str, Any]]:
        self.asks.append(Ask(system_prompt=system_prompt, messages=list(messages)))
        text = self._next_reply()
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": text}}}
        yield {"contentBlockStop": {"contentBlockIndex": 0}}
        yield {"messageStop": {"stopReason": "end_turn"}}

    async def structured_output(self, output_model: Any, prompt: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "ScriptedModel does not do structured output. Nothing in Archon asks for it, "
            "and a stub that pretended to would be the kind of fiction this file exists to avoid."
        )
        yield {}  # pragma: no cover - unreachable, keeps this an async generator

    def get_config(self) -> dict[str, Any]:
        return dict(self.config)

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    @property
    def prompts_seen(self) -> list[str]:
        """Every system prompt the graph put in front of the model."""
        return [ask.system_prompt or "" for ask in self.asks]
