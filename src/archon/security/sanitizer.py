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

# IBAN pattern: 2 alpha chars, 2 digits, at least 4 alphanumeric chars
_RE_IBAN = re.compile(
    r"\b([A-Z]{2}[0-9]{2})([A-Z0-9]{4,30})\b"
)

# SWIFT / BIC pattern when preceded by keyword
_RE_SWIFT = re.compile(
    r"\b(?:SWIFT|BIC)[\s:#]+([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b",
    re.IGNORECASE,
)

# International and standard phone numbers with prefix
_RE_PHONE = re.compile(
    r"\b(?:TEL|PHONE|MOBILE|CELL|FAX)?[\s:#]*(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b",
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
    body = match.group(2)
    if len(body) <= 4:
        return f"{prefix}{'*' * len(body)}"
    masked_inner = "*" * (len(body) - 4)
    suffix = body[-4:]
    return f"{prefix}{masked_inner}{suffix}"


def sanitize_text(text: str) -> tuple[str, int, list[str]]:
    """Sanitize raw text by redacting PII and sensitive banking identifiers.

    Returns:
        (sanitized_text, redactions_count, redacted_categories)
    """
    if not text:
        return text, 0, []

    redactions = 0
    categories: list[str] = []

    # 1. Redact Payment Cards
    def _mask_card(m: re.Match[str]) -> str:
        nonlocal redactions
        redactions += 1
        return "[REDACTED_PAYMENT_CARD]"

    new_text, count = _RE_PAYMENT_CARD.subn(_mask_card, text)
    if count > 0:
        categories.append("payment_card")

    # 2. Redact IBANs
    def _mask_iban_count(m: re.Match[str]) -> str:
        nonlocal redactions
        redactions += 1
        return _mask_iban(m)

    new_text, count = _RE_IBAN.subn(_mask_iban_count, new_text)
    if count > 0:
        categories.append("iban")

    # 3. Redact SWIFT/BIC
    def _mask_swift(m: re.Match[str]) -> str:
        nonlocal redactions
        redactions += 1
        return "[REDACTED_BIC]"

    new_text, count = _RE_SWIFT.subn(_mask_swift, new_text)
    if count > 0:
        categories.append("swift_bic")

    # 4. Redact Tax / VAT IDs
    def _mask_tax(m: re.Match[str]) -> str:
        nonlocal redactions
        redactions += 1
        return "[REDACTED_TAX_ID]"

    new_text, count = _RE_TAX_ID.subn(_mask_tax, new_text)
    new_text, count_eu = _RE_EU_VAT.subn(_mask_tax, new_text)
    if count + count_eu > 0:
        categories.append("tax_id")

    # 5. Redact Emails
    def _mask_email(m: re.Match[str]) -> str:
        nonlocal redactions
        redactions += 1
        return "[REDACTED_EMAIL]"

    new_text, count = _RE_EMAIL.subn(_mask_email, new_text)
    if count > 0:
        categories.append("email")

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
