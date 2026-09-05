"""Deterministic pre-LLM PII and financial sensitive entity sanitization filter.

Implements Enterprise privacy-by-design principles (GDPR Article 32, EU AI Act)
to ensure sensitive direct identifiers (IBANs, payment cards, national tax IDs,
direct contact coordinates) are redacted locally before prompt dispatch to Bedrock,
while strictly preserving commercial terms, invoice numbers, line items, and monetary balances.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Compiled regex patterns for entity detection
_RE_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# Common EU/International VAT/Tax ID patterns
_RE_TAX_ID = re.compile(
    r"\b(?:VAT|TAX\s*ID|AFM|TIN|CIF|NIF)[\s:#]+([A-Z0-9]{8,14})\b",
    re.IGNORECASE,
)

# Explicit country-prefixed VAT IDs (e.g. EL123456789, DE123456789, FR12345678901)
_RE_EU_VAT = re.compile(
    r"\b(EL|GR|DE|FR|IT|GB|ES|NL|BE|AT|SE|DK|PL|IE)[0-9]{8,12}\b"
)

# Credit / Debit Cards (13 to 19 digits, space or dash separated)
_RE_PAYMENT_CARD = re.compile(
    r"\b(?:\d{4}[-\s]){3}\d{4}\b|\b\d{15,16}\b"
)

# IBAN: two letters, two check digits, then the body. Real ones are printed in
# groups of four and the contiguous-only pattern this replaced matched none of
# them, so a real IBAN survived into the prompt. Groups are matched explicitly
# rather than by allowing an optional space before every character, because
# that form runs into the following sentence: it eats the " A" of "at Alpha
# Bank" and leaves "lpha Bank" behind.
_RE_IBAN = re.compile(
    r"\b([A-Z]{2}[0-9]{2})((?:[ ][A-Z0-9]{4})+(?:[ ][A-Z0-9]{1,4})?|[A-Z0-9]{4,30})\b"
)

# SWIFT / BIC pattern when preceded by keyword
_RE_SWIFT = re.compile(
    r"\b(?:SWIFT|BIC)[\s:#]+([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b",
    re.IGNORECASE,
)

# A number counts as a phone only when it is announced as one, by a keyword or
# an international prefix. The pattern this replaced made every part optional,
# which matches invoice totals and reference numbers, and redacting the
# commercial content would be a worse failure than sending a phone number.
_RE_PHONE = re.compile(
    r"(?:(?:TEL|PHONE|MOBILE|CELL|FAX)[\s:#]*|\+)\d[\d\s().-]{6,18}\d",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SanitizedDocument:
    """Represents a document whose sensitive identifiers have been redacted."""

    original_length: int
    sanitized_text: str
    redactions_count: int
    redacted_categories: list[str] = field(default_factory=list)

    @property
    def is_modified(self) -> bool:
        """True if any sensitive entities were redacted."""
        return self.redactions_count > 0


def _mask_iban(match: re.Match[str]) -> str:
    prefix = match.group(1)  # Country + 2 check digits
    body = match.group(2).replace(" ", "")  # grouped IBANs carry spaces
    if len(body) <= 4:
        return f"{prefix}{'*' * len(body)}"
    masked_inner = "*" * (len(body) - 4)
    suffix = body[-4:]
    return f"{prefix}{masked_inner}{suffix}"


def sanitize_text(text: str) -> tuple[str, int, list[str]]:
    """Redact identifiers, keep the commerce.

    **Order is the correctness here, not a detail.** Each rule runs over the
    output of the last, so a greedy early rule can leave a later one nothing to
    match and a real identifier half exposed. Three orderings were wrong before
    this comment existed, and each was invisible until the filter was wired to
    something real:

    * the payment-card rule ran first and matched four-digit groups inside a
      grouped IBAN, turning `GR16 0110 1250 0000 0001 2300 695` into
      `GR16 [REDACTED_PAYMENT_CARD] 2300 695`, which leaks the tail;
    * the IBAN rule ran before the tax rule and matched `EL123456789`, masking a
      VAT number as though it were an account and leaving eight of its eleven
      characters visible;
    * the phone rule was defined and never applied at all.

    So: the most specific and keyword-anchored rules run first, the longest
    structures before the ones that could match inside them, and the loosest
    last.

    Returns:
        (sanitized_text, redactions_count, redacted_categories)
    """
    if not text:
        return text, 0, []

    redactions = 0
    categories: list[str] = []

    def redact(label: str) -> object:
        def replace(_: re.Match[str]) -> str:
            nonlocal redactions
            redactions += 1
            return f"[REDACTED_{label}]"

        return replace

    def mask_iban(match: re.Match[str]) -> str:
        nonlocal redactions
        redactions += 1
        return _mask_iban(match)

    #: (category, pattern, replacement). Order is load-bearing; see the docstring.
    rules = [
        ("swift_bic", _RE_SWIFT, redact("BIC")),
        ("tax_id", _RE_TAX_ID, redact("TAX_ID")),
        ("tax_id", _RE_EU_VAT, redact("TAX_ID")),
        ("iban", _RE_IBAN, mask_iban),
        ("payment_card", _RE_PAYMENT_CARD, redact("PAYMENT_CARD")),
        ("phone", _RE_PHONE, redact("PHONE")),
        ("email", _RE_EMAIL, redact("EMAIL")),
    ]

    new_text = text
    for category, pattern, replacement in rules:
        new_text, count = pattern.subn(replacement, new_text)
        if count > 0 and category not in categories:
            categories.append(category)

    return new_text, redactions, categories


def sanitize_payload(content: str) -> SanitizedDocument:
    """Wrapper that returns a structured SanitizedDocument."""
    sanitized, count, categories = sanitize_text(content)
    return SanitizedDocument(
        original_length=len(content),
        sanitized_text=sanitized,
        redactions_count=count,
        redacted_categories=categories,
    )
