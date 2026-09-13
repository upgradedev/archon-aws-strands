"""Explicit text contract for the live composer, without changing historical prompts."""
from __future__ import annotations

import json

from archon.agents.draft import UnsafeDraft

READER_REPORT_RULES = (
    "Live workspace report contract: call your assigned ledger tool, then return "
    "a concise report of at most 120 words for your own domain only. State the "
    "relevant tool facts, one sentence of assessment, and the required verdict. "
    "Do not draft an email or repeat other domains' reports. Do not infer missing "
    "transactions or a customer's intentions. The composer alone writes email lines."
)

COMPOSER_JSON_RULES = (
    "Output contract for this application: return ONLY one JSON object with exactly "
    "two string keys, opening and closing. These are the two email lines requested "
    "above. No markdown, headings, invoice identifiers, commentary or other fields. "
    "Each value must be a nonempty single line, with no digits. The application "
    "inserts all invoice references and figures from verified ledger claims."
)


def composer_lines(reply: str) -> tuple[str, str]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result

    try:
        value = json.loads(reply, object_pairs_hook=unique)
        if not isinstance(value, dict) or set(value) != {"opening", "closing"}:
            raise ValueError("unexpected shape")
        lines = tuple(value[name] for name in ("opening", "closing"))
        if any(not isinstance(line, str) or not line.strip() or len(line) > 2000
               or any(c in line for c in "\r\n") for line in lines):
            raise ValueError("invalid line")
        return lines
    except (ValueError, TypeError) as exc:
        raise UnsafeDraft(
            "The model did not return the required opening/closing text contract. "
            "No draft was released."
        ) from exc
