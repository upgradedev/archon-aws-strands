"""A fixed, fictional quarter of trade; not extraction or bank-feed evidence.

The bundled records use the normal domain validation and posting rules. A
separate opt-in workspace keeps this larger example out of a visitor's books.
Nothing here invokes a model, sends mail or executes a payment.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

from archon.domain.books import Books
from archon.domain.documents import (
    Payment,
    PurchaseCreditNote,
    PurchaseInvoice,
    Receipt,
    SalesCreditNote,
    SalesInvoice,
)
from archon.domain.money import money
from archon.store.sqlite import _encode

VERSION = "business-v1"
SOURCE_COUNT = 240
INTERACTIVE_LIMIT = 50
COUNTS = {
    "SalesInvoice": 80, "PurchaseInvoice": 50,
    "Receipt": 50, "Payment": 30,
    "SalesCreditNote": 20, "PurchaseCreditNote": 10,
}
CLIENTS = (
    "Alder Workshop", "Cedar Kitchens", "Harbour Interiors", "Maple Fitouts",
    "Willow Homes", "Juniper Studios", "Birch Renovations", "Elm Works",
    "Ash Design", "Oakridge Rooms", "Fern Projects", "Hazel Spaces",
    "Linden Builds", "Pinecrest Joinery", "Rowan Interiors", "Laurel Living",
)
SUPPLIERS = (
    "Timber Yard", "Panel Supply", "Hardware Depot", "Finish Works", "Tool Workshop",
    "Packaging Store", "Safety Supply", "Freight Desk", "Workshop Utilities", "Glass Works",
)


def documents(recipient: str) -> list:
    """Versioned integer arithmetic, fixed dates and invented trade identities."""
    rows = []

    def ref():
        return f"demo:{len(rows) + 1:03d}"

    sales, purchases = [], []
    for index in range(80):
        issued = date(2026, 7, 1) + timedelta(days=(index * 7) % 66)
        net = money(Decimal(180 + (index * 137) % 3200))
        vat = money(net * Decimal("0.24"))
        invoice = SalesInvoice(
            doc_id=f"SV-{index + 1:04d}", client=CLIENTS[index % len(CLIENTS)],
            client_email=recipient, issued=issued, due=issued + timedelta(days=30),
            net=net, vat=vat, gross=net + vat, source_ref=ref(),
        )
        rows.append(invoice)
        sales.append(invoice)
    for index in range(50):
        issued = date(2026, 7, 2) + timedelta(days=(index * 11) % 64)
        net = money(Decimal(60 + (index * 83) % 1400))
        vat = money(net * Decimal("0.24"))
        invoice = PurchaseInvoice(
            doc_id=f"PV-{index + 1:04d}", supplier=SUPPLIERS[index % len(SUPPLIERS)],
            issued=issued, due=issued + timedelta(days=30),
            net=net, vat=vat, gross=net + vat, source_ref=ref(),
        )
        rows.append(invoice)
        purchases.append(invoice)
    # Credits affect debt, net sales/cost and VAT, never cash. They reference
    # invoices without cash postings so partial/full settlement stays inspectable.
    for index, invoice in enumerate(sales[50:70]):
        net = invoice.net if index % 4 == 0 else money(invoice.net / Decimal(4))
        vat = invoice.vat if index % 4 == 0 else money(net * Decimal("0.24"))
        rows.append(SalesCreditNote(
            doc_id=f"SC-{index + 1:04d}", settles=invoice.doc_id,
            issued=min(invoice.issued + timedelta(days=3), date(2026, 9, 9)),
            net=net, vat=vat, gross=net + vat, source_ref=ref(),
        ))
    for index, invoice in enumerate(purchases[30:40]):
        net = invoice.net if index % 3 == 0 else money(invoice.net / Decimal(4))
        vat = invoice.vat if index % 3 == 0 else money(net * Decimal("0.24"))
        rows.append(PurchaseCreditNote(
            doc_id=f"PC-{index + 1:04d}", settles=invoice.doc_id,
            issued=min(invoice.issued + timedelta(days=3), date(2026, 9, 9)),
            net=net, vat=vat, gross=net + vat, source_ref=ref(),
        ))
    for index, invoice in enumerate(sales[:50]):
        rows.append(Receipt(
            doc_id=f"RC-{index + 1:04d}", settles=invoice.doc_id,
            received_on=min(invoice.issued + timedelta(days=12), date(2026, 9, 9)),
            amount=invoice.gross if index % 3 else money(invoice.gross / Decimal(2)),
            transfer_id=f"FICTIONAL-IN-{index + 1:04d}", source_ref=ref(),
        ))
    for index, invoice in enumerate(purchases[:30]):
        rows.append(Payment(
            doc_id=f"PM-{index + 1:04d}", settles=invoice.doc_id,
            paid_on=min(invoice.issued + timedelta(days=15), date(2026, 9, 9)),
            amount=invoice.gross if index % 3 else money(invoice.gross / Decimal(2)),
            transfer_id=f"FICTIONAL-OUT-{index + 1:04d}", source_ref=ref(),
        ))
    return rows


def seed(state: dict) -> None:
    from archon.web import workspace

    expected = {**workspace.fresh(), "created_at": state.get("created_at"),
                **{k: state[k] for k in ("provider_mode", "test_recipient") if k in state}}
    if state != expected:
        raise ValueError("Business demo data can only be loaded into a new workspace.")
    books, sources = Books(), []
    for document in documents(state.get("test_recipient", "demo-client@archon.example")):
        books.record(document)
        encoded = json.loads(_encode(document))
        body = "Fictional business fixture, not an imported email or bank feed.\n" + json.dumps(
            {"kind": type(document).__name__, **encoded}, indent=2, sort_keys=True
        )
        sources.append({
            "id": document.source_ref, "hash": workspace.digest(body), "body": body,
            "at": state["created_at"], "status": "posted", "error": "",
            "kind": type(document).__name__, "document": encoded, "redactions": 0,
            "origin": "fictional-business-fixture",
        })
    actual = {kind: sum(s["kind"] == kind for s in sources) for kind in COUNTS}
    if len(sources) != SOURCE_COUNT or actual != COUNTS or books.ledger.trial_balance() != 0:
        raise ValueError("Business demo failed validation. No workspace was created.")
    # Commit to the fresh state only after the complete bundle validates.
    state.update(sources=sources, demo_seed=VERSION)
    workspace.event(state, "Fictional business portfolio loaded",
                    "240 versioned records; six document types, normal ledger validation. "
                    "No AI extraction, bank connection, payment execution or email send.")


def interactive_count(state: dict) -> int:
    """Fixed server-authored bundle is separate from the existing 50-input cap.

    Unknown/missing markers or malformed bundles get no capacity exemption.
    There is no request field for caller-provided seeds or bulk document bodies.
    """
    sources = state["sources"]
    if state.get("demo_seed") == VERSION and len(sources) >= SOURCE_COUNT:
        bundled = sources[:SOURCE_COUNT]
        if all(s["id"] == f"demo:{i + 1:03d}"
               and s.get("origin") == "fictional-business-fixture"
               and s["status"] == "posted" for i, s in enumerate(bundled)):
            return len(sources) - SOURCE_COUNT
    return len(sources)
