"""One invented business, used by every test.

Nothing here is a real supplier, client or employee. S11 forbids customer data
in the bundle and the README says so out loud; a fixture is where that promise
is either kept or quietly broken, so it is kept here.
"""

from __future__ import annotations

from datetime import date

import pytest

from archon.domain.books import Books
from archon.domain.documents import (
    Payment,
    PayrollRun,
    PurchaseInvoice,
    Receipt,
    SalesInvoice,
)

TODAY = date(2026, 9, 3)


@pytest.fixture
def books() -> Books:
    """A one-person electrical firm, three months in.

    Two supplier bills, one paid. Three jobs invoiced, one collected, one part
    collected, one long overdue. Payroll run for August and not yet paid.
    """
    b = Books()
    b.record(
        PurchaseInvoice(
            doc_id="PI-001",
            supplier="Wholesaler A",
            issued=date(2026, 7, 4),
            due=date(2026, 8, 3),
            net="1000.00",
            vat="240.00",
            gross="1240.00",
            source_ref="email:001",
        )
    )
    b.record(
        PurchaseInvoice(
            doc_id="PI-002",
            supplier="Van Leasing B",
            issued=date(2026, 8, 1),
            due=date(2026, 9, 30),
            net="400.00",
            vat="96.00",
            gross="496.00",
            source_ref="email:002",
        )
    )
    b.record(
        Payment(
            doc_id="PAY-001",
            settles="PI-001",
            paid_on=date(2026, 8, 2),
            amount="1240.00",
            source_ref="email:003",
        )
    )
    b.record(
        SalesInvoice(
            doc_id="SI-001",
            client="Cafe on the corner",
            client_email="accounts@cafe.example",
            issued=date(2026, 6, 10),
            due=date(2026, 7, 10),
            net="2000.00",
            vat="480.00",
            gross="2480.00",
            source_ref="email:010",
        )
    )
    b.record(
        SalesInvoice(
            doc_id="SI-002",
            client="Letting agent",
            client_email="pay@letting.example",
            issued=date(2026, 7, 20),
            due=date(2026, 8, 19),
            net="800.00",
            vat="192.00",
            gross="992.00",
            source_ref="email:011",
        )
    )
    b.record(
        SalesInvoice(
            doc_id="SI-003",
            client="New build site",
            client_email="ap@newbuild.example",
            issued=date(2026, 8, 25),
            due=date(2026, 9, 24),
            net="1500.00",
            vat="360.00",
            gross="1860.00",
            source_ref="email:012",
        )
    )
    b.record(
        Receipt(
            doc_id="RC-001",
            settles="SI-002",
            received_on=date(2026, 8, 20),
            amount="992.00",
            source_ref="email:013",
        )
    )
    b.record(
        Receipt(
            doc_id="RC-002",
            settles="SI-001",
            received_on=date(2026, 8, 1),
            amount="480.00",
            source_ref="email:014",
        )
    )
    b.record(
        PayrollRun(
            doc_id="PR-2026-08",
            period="August 2026",
            run_on=date(2026, 8, 31),
            gross="1100.00",
            paid_on=None,
            source_ref="email:020",
        )
    )
    return b
