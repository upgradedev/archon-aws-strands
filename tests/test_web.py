"""The screen. Asserted on what a visitor sees and on what pressing things does.

The interesting tests here are the two refusals, because a page that shows a
gate but does not enforce it through the browser round trip is a picture of a
gate.
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("fastapi", reason="the screen needs fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from archon.web.app import app, session  # noqa: E402

FINGERPRINT = re.compile(r'name="fingerprint" value="([0-9a-f]{64})"')


@pytest.fixture
def client():
    session.reset()
    with TestClient(app) as c:
        yield c
    session.reset()


def _fingerprint(html: str) -> str:
    found = FINGERPRINT.search(html)
    assert found, "no approvable draft on the page"
    return found.group(1)


def _note(html: str) -> str:
    found = re.search(r'<div class="note">(.*?)</div>', html, re.S)
    return " ".join(found.group(1).split()) if found else ""


def test_the_page_leads_with_the_debt_a_person_would_act_on(client):
    html = client.get("/").text
    assert "Cafe on the corner owes 2,000.00 EUR" in html
    assert "55 days late" in html
    assert "already paid 480.00 EUR" in html


def test_every_figure_in_the_email_is_a_verified_claim(client):
    html = client.get("/").text
    for sentence in (
        "Invoice SI-001 is still outstanding at 2,000.00 EUR.",
        "It fell due 55 days ago.",
        "We have received 480.00 EUR against it, with thanks.",
    ):
        assert sentence in html, sentence


def test_the_page_computes_nothing_of_its_own(client):
    """Every number on screen must also be derivable from the ledger."""
    from archon.domain.reports import metrics
    from archon.web.app import TODAY

    html = client.get("/").text
    m = metrics(session.books, TODAY)
    assert f"{m.bank:,.2f} EUR" in html
    assert f"{m.owed_by_clients:,.2f} EUR" in html
    assert f"{m.owed_to_staff:,.2f} EUR" in html


def test_the_gate_verdict_is_shown_before_anything_can_be_sent(client):
    html = client.get("/").text
    assert "Released" in html
    assert "every stated fact was re-derived from the books" in html


def test_approving_sends_once_and_shows_the_receipt(client):
    html = client.get("/").text
    client.post("/approve", data={"fingerprint": _fingerprint(html)})
    after = client.get("/").text
    assert "Sent" in after
    assert "message id" in after
    assert "offline-0001" in after


def test_a_second_approval_does_not_send_a_second_email(client):
    html = client.get("/").text
    fp = _fingerprint(html)
    client.post("/approve", data={"fingerprint": fp})
    first = session.receipt.message_id
    client.post("/approve", data={"fingerprint": fp})
    assert session.receipt.message_id == first


def test_money_arriving_after_the_page_loaded_stops_the_send(client):
    """The strongest thing on the page, and it has to work through a browser."""
    html = client.get("/").text
    stale = _fingerprint(html)

    client.post("/pay")  # part of it arrives at lunchtime
    client.post("/approve", data={"fingerprint": stale})

    assert session.receipt is None, "an email went out on a stale approval"
    note = _note(client.get("/").text)
    assert "books moved while this page was open" in note
    assert "Nothing was sent" in note


def test_the_chase_survives_a_part_payment_with_new_numbers(client):
    client.post("/pay")
    html = client.get("/").text
    assert "Approve and send this exact text" in html, "the chase should still be owed, for less"
    assert "1,000.00 EUR" in html


def test_paying_it_all_leaves_nothing_to_chase(client):
    for _ in range(14):  # halves until under a euro, then settles the rest
        client.post("/pay")
    html = client.get("/").text
    assert "Nothing is overdue" in html
    assert "saying nothing is the right answer" in html


def test_reset_puts_the_month_back(client):
    html = client.get("/").text
    client.post("/approve", data={"fingerprint": _fingerprint(html)})
    client.post("/reset")
    back = client.get("/").text
    assert "Approve and send this exact text" in back
    assert session.receipt is None


def test_the_evidence_table_carries_the_live_row_and_the_caveat(client):
    html = client.get("/").text
    assert "a real Claude model, one pass, no ledger" in html
    assert "nothing in its answer tells you which three" in html
    assert "python -m archon.evidence.compare" in html


def test_the_page_needs_no_external_asset(client):
    """A page that fetches from somebody else's host can go dark unnoticed."""
    html = client.get("/").text
    assert "http://" not in html.replace('action="/', "")
    assert "cdn" not in html.lower()
    assert "<script" not in html.lower()


def test_the_footer_says_what_is_running_and_whose_data_it_is(client):
    # Whitespace-normalised, because the source wraps mid-sentence and a person
    # reads the rendered line, not the bytes.
    html = " ".join(client.get("/").text.split())
    assert "no customer data is present" in html
    assert "the composer holds no tools" in html
