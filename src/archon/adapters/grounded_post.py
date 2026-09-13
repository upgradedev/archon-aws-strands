"""Conservative source checks after semantic extraction, before ledger posting."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from archon.adapters.inbound import UnreadablePost
from archon.domain.documents import Receipt


def validate_reading(body, reading):
    document = reading.document
    # This live input lane currently supports explicit ISO dates and EUR decimal
    # amounts. Semantic prose is allowed; unsupported formatting is not guessed.
    amounts = {Decimal(v.replace(",", "")) for v in
               re.findall(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?!\d)", body)}
    fields = ("amount",) if isinstance(document, Receipt) else ("net", "vat", "gross")
    if any(getattr(document, field) not in amounts for field in fields):
        raise UnreadablePost("An extracted amount has no exact numeric evidence in the source.")
    dates = {date.fromisoformat(value) for value in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", body)}
    fields = ("received_on",) if isinstance(document, Receipt) else ("issued", "due")
    if any(getattr(document, field) not in dates for field in fields):
        raise UnreadablePost("An extracted date has no explicit ISO-date evidence in the source.")
    identifier = document.settles if isinstance(document, Receipt) else document.doc_id
    if not re.search(r"(?<!\w)" + re.escape(identifier) + r"(?!\w)", body):
        raise UnreadablePost("The document reference is not present in the retained source.")
