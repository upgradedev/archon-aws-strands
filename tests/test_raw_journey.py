"""AR-01: raw invoice plus partial payment, through the screen, to a balance.

This journey did not work before 2026-09-09 and it was hard to see, because the
demo books were seeded with sales invoices and the screen looked complete. Three
things stood in the way, each of which looked like a design decision:

* the offline reader labelled **every** invoice a purchase, so money owed *to*
  the trader — the thing this product exists for — could not be produced from a
  pasted email at all;
* redaction masked every address before the reader saw it, so a sales invoice,
  which needs somewhere to send a chase, was always refused;
* a remittance saying "paid 600.00 on 2026-08-20" was refused for having no
  date, which was true of the word "dated" and false of the email.

The address is now lifted from the raw text on this machine and handed to the
document directly. The model still sees `[REDACTED_EMAIL]`, and a test below
asserts it, because the fix must not have widened what leaves the host.
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from archon.adapters.inbound import LocalReader, addresses_on, read_email  # noqa: E402
from archon.domain import queue  # noqa: E402
from archon.web.app import app, session  # noqa: E402

INVOICE = (
    "From: me@myjoinery.example\n"
    "To: accounts@buildco.example\n"
    "Subject: Invoice JN-4410\n\n"
    "Our invoice to BuildCo Ltd. Invoice JN-4410 dated 2026-07-02, due 2026-08-01. "
    "Net 1500.00 EUR, VAT 360.00 EUR, total 1860.00 EUR."
)

REMITTANCE = (
    "From: accounts@buildco.example\n"
    "Subject: Remittance\n\n"
    "We have paid 600.00 EUR on 2026-08-20 against invoice JN-4410."
)


@pytest.fixture
def client():
    session.reset()
    with TestClient(app) as c:
        yield c
    session.reset()


def plain(html: str, start: str, length: int = 900) -> str:
    cut = html[html.index(start) : html.index(start) + length]
    return " ".join(re.sub(r"<[^>]+>", " ", cut).split())


def test_a_raw_invoice_and_a_partial_payment_give_the_right_balance(client):
    """The whole of AR-01 in one test."""
    client.post("/post", data={"body": INVOICE, "reader": "rules"})
    client.post("/post", data={"body": REMITTANCE, "reader": "rules"})

    built = queue.build(session.books, __import__("archon.demo", fromlist=["TODAY"]).TODAY)
    item = next(i for i in built.ready if i.invoice_id == "JN-4410")

    assert item.outstanding == 1860 - 600
    assert item.client == "BuildCo Ltd"
    assert item.recipient == "accounts@buildco.example"


def test_the_balance_is_on_the_screen_with_the_recipient(client):
    client.post("/post", data={"body": INVOICE, "reader": "rules"})
    client.post("/post", data={"body": REMITTANCE, "reader": "rules"})
    shown = plain(client.get("/").text, "What is worth doing next")

    assert "JN-4410" in shown
    assert "1,260.00 EUR" in shown
    assert "accounts@buildco.example" in shown


def test_an_invoice_the_trader_issued_is_read_as_one():
    reading = read_email(INVOICE, "email:x", client=LocalReader())
    document = reading.document
    assert type(document).__name__ == "SalesInvoice"
    assert document.client == "BuildCo Ltd"
    assert document.client_email == "accounts@buildco.example"


def test_an_invoice_the_trader_received_is_still_a_purchase():
    """The default has not been inverted; it is now decided rather than assumed."""
    received = (
        "From: billing@thewholesaler.example\n"
        "Subject: Invoice WS-77\n\n"
        "Invoice WS-77 dated 2026-07-02, due 2026-08-01. "
        "Net 100.00 EUR, VAT 24.00 EUR, total 124.00 EUR."
    )
    reading = read_email(received, "email:y", client=LocalReader())
    assert type(reading.document).__name__ == "PurchaseInvoice"


def test_the_client_address_never_reaches_the_model():
    """The fix put an address back into the document. It must not widen the boundary."""

    class Watching(LocalReader):
        def __init__(self) -> None:
            self.shown: list[str] = []

        def converse(self, **kwargs):
            self.shown.append(kwargs["messages"][0]["content"][0]["text"])
            return super().converse(**kwargs)

    watcher = Watching()
    reading = read_email(INVOICE, "email:x", client=watcher)

    assert reading.document.client_email == "accounts@buildco.example"
    assert "accounts@buildco.example" not in watcher.shown[0]
    assert "me@myjoinery.example" not in watcher.shown[0]
    assert "[REDACTED_EMAIL]" in watcher.shown[0]


def test_the_client_name_stops_where_the_sentence_does():
    """It once produced "BuildCo Ltd. Invoice JN-4410" as a company name."""
    assert LocalReader._client_name("Our invoice to BuildCo Ltd. Invoice JN-4410 dated") == (
        "BuildCo Ltd"
    )


def test_addresses_are_read_from_the_raw_text_only():
    found = addresses_on(INVOICE)
    assert found["From"] == "me@myjoinery.example"
    assert found["To"] == "accounts@buildco.example"
    assert addresses_on("no headers here") == {}


def test_a_remittance_dated_with_on_is_read():
    reading = read_email(REMITTANCE, "email:z", client=LocalReader())
    assert type(reading.document).__name__ == "Receipt"
    assert str(reading.document.amount) == "600.00"


def test_the_screen_never_falls_back_to_the_other_reader(client):
    """AR-01 forbids a scripted success when the chosen path fails."""
    response = client.post("/post", data={"body": INVOICE, "reader": "something-else"})
    assert response.status_code < 500
    assert "JN-4410" not in plain(client.get("/").text, "What is worth doing next")


def test_which_reader_ran_is_recorded(client):
    client.post("/post", data={"body": INVOICE, "reader": "rules"})
    assert session.read_by == "rules"


# --- from the adversarial review of 2026-09-09 --------------------------------


def test_a_date_after_a_bare_on_is_not_an_invoice_date():
    """The pattern was widened to read a remittance and took too much with it.

    "We are closed on 2026-08-24" is not an issue date, and a reader that takes
    it produces an invoice aged from the wrong day.
    """
    reader = LocalReader()
    assert reader._DATED.search("Our office reopens on 2026-09-01.") is None
    assert reader._DATED.search("The skip is collected on 2026-09-03.") is None


def test_the_payment_date_is_still_read_through_the_amount():
    """A person writes the figure between the verb and the date."""
    found = LocalReader()._DATED.search("We have paid 600.00 EUR on 2026-08-20 against JN-1.")
    assert found is not None
    assert "2026-08-20" in found.groups()


def test_an_invoice_date_wins_over_a_stray_one_elsewhere_in_the_email():
    reader = LocalReader()
    found = reader._DATED.search("We are closed on 2026-08-24. Invoice JN-2 dated 2026-07-05.")
    assert next(g for g in found.groups() if g) == "2026-07-05"


def test_a_redaction_marker_is_never_used_as_a_client_address():
    """The model is shown the marker and sometimes echoes it back.

    That echo is truthy, so a plain falsiness check let it stand where an
    address belonged and skipped the local fill-in entirely.
    """
    from archon.adapters.inbound import _usable_address

    assert not _usable_address("[REDACTED_EMAIL]")
    assert not _usable_address("")
    assert not _usable_address(None)
    assert _usable_address("accounts@buildco.example")


def test_the_counterparty_is_the_other_side_of_the_email():
    """When the firm is the recipient, To: is the firm itself.

    Filling the chase address from To: regardless would address a demand for
    money to the person sending it.
    """
    received = (
        "From: accounts@buildco.example\n"
        "To: me@myjoinery.example\n"
        "Subject: Invoice BC-9\n\n"
        "Our invoice to My Joinery. Invoice BC-9 dated 2026-07-02, due 2026-08-01. "
        "Net 100.00 EUR, VAT 24.00 EUR, total 124.00 EUR."
    )
    reading = read_email(received, "email:r", client=LocalReader(), ours="me@myjoinery.example")
    document = reading.document
    if type(document).__name__ == "SalesInvoice":
        assert document.client_email == "accounts@buildco.example"
        assert document.client_email != "me@myjoinery.example"
