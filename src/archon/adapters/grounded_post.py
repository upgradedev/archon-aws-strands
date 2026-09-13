"""Conservative source checks after semantic extraction, before ledger posting."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from archon.adapters.inbound import UnreadablePost
from archon.domain.documents import Receipt


class SourceFields:
    """Live extraction field meanings, outside the historical reader protocol.

    These instructions reach the metered client before counting and admission.
    The default local reader and frozen evaluation requests stay unchanged.
    """

    def __init__(self, client):
        self.client = client

    def converse(self, **request):
        instructions = (
            "Field meanings: for an invoice, issued is its issue date. For a receipt, "
            "issued is the explicitly stated payment date (paid, sent, received or "
            "transferred on), not an invoice issue date. Never substitute today's date "
            "or an invoice due date for a missing payment date. Return null if absent."
        )
        request["system"] = [*request.get("system", []), {"text": instructions}]
        return self.client.converse(**request)


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
