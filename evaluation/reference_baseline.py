"""A shared-reader flat reference ledger, not an industry or AI baseline.

It receives only the raw event stream and declared business/date. It refreshes
the balance before approval and remembers exact sent tuples across reload.
Sharing the reader deliberately limits the comparison to downstream workflow;
this cannot estimate reading quality relative to another extraction system.
"""

from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal

from archon.adapters.inbound import LocalReader, read_email
from archon.domain.documents import PurchaseInvoice, Receipt, SalesInvoice

from .public_workflow import offline_only


def run_baseline(steps: list[dict], context: dict) -> list[dict]:
    sales, paid, transfers, documents = {}, {}, set(), set()
    sent, observations = [], []
    held = False
    draft = None

    def balances():
        return {key: f"{inv.gross - paid.get(key, Decimal('0')):.2f}"
                for key, inv in sales.items()}

    def current():
        if held:
            return None
        owing = balances()
        eligible = sorted(
            (inv for key, inv in sales.items()
             if inv.due < date.fromisoformat(context["as_of"]) and Decimal(owing[key]) > 0),
            key=lambda inv: (inv.due, -Decimal(owing[inv.doc_id]), inv.doc_id),
        )
        if not eligible:
            return None
        inv = eligible[0]
        return {"invoice": inv.doc_id, "recipient": inv.client_email, "amount": owing[inv.doc_id]}

    with offline_only():
        for index, step in enumerate(steps):
            if step["op"] == "intake":
                try:
                    doc = read_email(step["body"], f"baseline:{index}", client=LocalReader(),
                                     ours=context["business_email"],
                                     business_name=context["business_name"]).document
                    if doc.doc_id in documents:
                        raise ValueError("Duplicate document")
                    if isinstance(doc, SalesInvoice):
                        sales[doc.doc_id] = doc
                    elif isinstance(doc, Receipt):
                        identity = " ".join(doc.transfer_id.upper().split())
                        if not identity or identity in transfers or doc.settles not in sales:
                            raise ValueError("Unresolved payment identity or invoice")
                        amount = paid.get(doc.settles, Decimal("0")) + doc.amount
                        if amount > sales[doc.settles].gross:
                            raise ValueError("Overpayment")
                        paid[doc.settles] = amount
                        transfers.add(identity)
                    elif not isinstance(doc, PurchaseInvoice):
                        raise ValueError("Unsupported document")
                    documents.add(doc.doc_id)
                except ValueError:
                    held = True
            elif step["op"] == "draft":
                draft = current()
            elif step["op"] == "reload":
                # Retain the flat state for this task; no process-persistence claim.
                sent = copy.deepcopy(sent)
            elif step["op"] == "approve":
                calls = []
                if draft is not None and draft == current() and draft not in sent:
                    calls.append(copy.deepcopy(draft))
                    sent.append(copy.deepcopy(draft))
                observations.append({"step": index, "calls": calls,
                                     "balances": balances(), "hold": held})
    return observations
