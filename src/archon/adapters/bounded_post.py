"""Versioned public text reader; historical LocalReader controls remain unchanged."""

from __future__ import annotations

import re
from datetime import date

from archon.adapters.inbound import LocalReader, UnreadablePost

MONTHS = "January February March April May June July August September October November December"
_MONTH = "(?:" + "|".join(MONTHS.split()) + ")"
_DATE = re.compile(
    rf"(?:\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}} {_MONTH} \d{{4}}|"
    rf"{_MONTH} \d{{1,2}},? \d{{4}})(?![\w/-])", re.I,
)


def explicit_day(raw: str) -> str:
    found = _DATE.match(raw)
    if not found:
        raise UnreadablePost("Use an ISO date or an explicit English month, day and year.")
    value = found.group()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value).isoformat()
    parts = value.replace(",", "").split()
    day, month, year = parts if parts[0].isdigit() else [parts[1], parts[0], parts[2]]
    return date(int(year), MONTHS.lower().split().index(month.lower()) + 1, int(day)).isoformat()


def explicit_money(raw: str) -> str:
    # Never silently truncate 12.345, malformed grouping, a sign or 100.00e3.
    found = re.match(r"(?:EUR\s+|€\s*)?([+-]?\d[\w.,+-]*)", raw, re.I)
    value = found.group(1).rstrip(".") if found else ""
    if re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)\.\d{2}", value):
        return value.replace(",", "")
    if re.fullmatch(r"(?:\d+|\d{1,3}(?:\.\d{3})+),\d{2}", value):
        return value.replace(".", "").replace(",", ".")
    raise UnreadablePost("Use an unambiguous positive EUR amount with exactly two decimals.")


class PublicPostReader(LocalReader):
    """Bounded-post-v2; shared guards enforce direction, identity and arithmetic."""

    label = "bounded-post-v2; explicit dates and EUR amounts; no model call"

    def _fields(self, body: str) -> dict:
        fields = super()._fields(body)

        def unique(label: str, pattern: str, parse):
            values = {parse(body[m.end():].lstrip())
                      for m in re.finditer(pattern, body, re.I)}
            if len(values) > 1:
                raise UnreadablePost(f"Conflicting {label}; a person must resolve the source.")
            return next(iter(values), None)

        issued = unique(
            "document dates",
            r"\b(?:dated|issued|invoice date|value date)[ \t:]+"
            r"|\b(?:paid|sent|transferred|received|credited|remitted)\b"
            r"[^\n]{0,40}?\bon[ \t]+", explicit_day,
        )
        numeric = r"(?=(?:EUR\s+|€\s*)?[+-]?\d)"
        paid = unique("payment amounts", r"\b(?:paid|remitted|transferred)[ \t:]+" + numeric,
                      explicit_money)
        refs = {m.group(1).replace(" ", "").upper()
                for m in self._SETTLES.finditer(body)}
        if len(refs) > 1:
            raise UnreadablePost("Conflicting payment invoice references.")
        if paid and refs:
            return {"kind": "receipt", "doc_id": "pending-transfer-identity",
                    "settles": next(iter(refs)), "issued": issued, "amount": paid}
        if paid:
            raise UnreadablePost("A payment needs one explicit invoice reference after 'against'.")
        ids = {m.group(1).replace(" ", "").upper() for m in self._ID.finditer(body)}
        if len(ids) > 1:
            raise UnreadablePost("Conflicting invoice identifiers.")
        fields.update(
            doc_id=next(iter(ids), None), issued=issued,
            due=unique("due dates", r"(?<!amount )\bdue[ \t:]+(?:on[ \t:]+)?", explicit_day),
            net=unique("net amounts", r"\bnet[ \t:]+" + numeric, explicit_money),
            vat=unique("VAT amounts", r"\bvat[ \t:]+" + numeric, explicit_money),
            gross=unique("invoice totals", r"\b(?:total|gross|amount due)[ \t:]+" + numeric,
                         explicit_money),
        )
        return fields
