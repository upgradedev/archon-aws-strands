"""The send, and the four ways it goes wrong after everything upstream went right."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from archon.adapters.ses import Outbox, SendRefused
from archon.agents.claims import Outstanding, Overdue, PartPaid
from archon.agents.draft import ChaseDraft
from archon.agents.gate import Approval, assess

TODAY = date(2026, 9, 3)
NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)


class FakeSes:
    """Records what it was asked to send and hands back message ids."""

    def __init__(self, message_ids=None):
        self.calls = []
        # `or` would be wrong here: an empty list is the interesting case and it
        # is falsy, so it would silently get the defaults and the test would pass
        # for the wrong reason.
        default = ["msg-0001", "msg-0002", "msg-0003"]
        self.message_ids = list(default if message_ids is None else message_ids)

    def send_email(self, **kwargs):
        self.calls.append(kwargs)
        return {"MessageId": self.message_ids.pop(0)} if self.message_ids else {}


def _draft(**overrides) -> ChaseDraft:
    base = dict(
        invoice_id="SI-001",
        client="Cafe on the corner",
        to_address="accounts@cafe.example",
        subject="Our outstanding invoice",
        opening="Hello, I hope the summer has been kind to you.",
        claims=(
            Outstanding("SI-001", Decimal("2000.00")),
            Overdue("SI-001", 55),
            PartPaid("SI-001", Decimal("480.00")),
        ),
        closing="Could you let me know when this will be settled? Many thanks.",
        as_of=TODAY,
    )
    base.update(overrides)
    return ChaseDraft(**base)


def _released(books, draft):
    approval = Approval(fingerprint=draft.fingerprint(), approved_by="the owner", approved_at=NOW)
    return assess(books, draft, approval, TODAY, now=NOW)


def _outbox(ses=None):
    return Outbox(client=ses or FakeSes(), sender="books@archon.example", clock=lambda: NOW)


def test_a_released_chase_is_sent_and_evidenced(books):
    draft = _draft()
    ses = FakeSes()
    receipt = _outbox(ses).send(draft, _released(books, draft))

    assert receipt.message_id == "msg-0001"
    assert receipt.to_address == "accounts@cafe.example"
    assert receipt.fingerprint == draft.fingerprint()
    assert not receipt.replayed
    assert len(ses.calls) == 1


def test_the_wire_carries_the_verified_figures_and_nothing_else(books):
    draft = _draft()
    ses = FakeSes()
    _outbox(ses).send(draft, _released(books, draft))

    body = ses.calls[0]["Content"]["Simple"]["Body"]["Text"]["Data"]
    assert "2,000.00 EUR" in body and "480.00 EUR" in body and "55 days" in body
    assert ses.calls[0]["Destination"]["ToAddresses"] == ["accounts@cafe.example"]


def test_the_sender_does_not_overrule_the_gate(books):
    """The refusal must survive somebody calling the sender directly."""
    held = _draft(client="Letting agent")
    with pytest.raises(SendRefused, match="the gate held this draft"):
        _outbox().send(held, _released(books, held))


def test_the_same_email_is_never_sent_twice(books):
    # A retry, a double-clicked approval, a Lambda redelivery: same fingerprint.
    draft = _draft()
    ses = FakeSes()
    outbox = _outbox(ses)
    first = outbox.send(draft, _released(books, draft))
    second = outbox.send(draft, _released(books, draft))

    assert len(ses.calls) == 1, "SES was called twice for one email"
    assert second.message_id == first.message_id
    assert second.replayed and not first.replayed


def test_a_genuinely_different_email_still_goes(books):
    ses = FakeSes()
    outbox = _outbox(ses)
    first = _draft()
    outbox.send(first, _released(books, first))

    second = _draft(closing="Could you let me know when this will be settled? Thanks.")
    outbox.send(second, _released(books, second))
    assert len(ses.calls) == 2


def test_a_send_with_no_message_id_is_not_reported_as_sent(books):
    draft = _draft()
    with pytest.raises(SendRefused, match="cannot be evidenced"):
        _outbox(FakeSes(message_ids=[])).send(draft, _released(books, draft))


def test_an_unevidenced_send_is_not_remembered_as_done(books):
    """Otherwise the retry would be swallowed by idempotency and nothing arrives."""
    draft = _draft()
    ses = FakeSes(message_ids=[])
    outbox = _outbox(ses)
    with pytest.raises(SendRefused):
        outbox.send(draft, _released(books, draft))
    assert outbox.receipt_for(draft) is None

    ses.message_ids = ["msg-retry"]
    assert outbox.send(draft, _released(books, draft)).message_id == "msg-retry"


def test_a_receipt_can_be_read_back_by_the_text_it_was_for(books):
    draft = _draft()
    outbox = _outbox()
    assert outbox.receipt_for(draft) is None
    outbox.send(draft, _released(books, draft))
    assert outbox.receipt_for(draft).message_id == "msg-0001"


def test_a_lapsed_approval_stops_the_send_at_the_gate(books):
    draft = _draft()
    approval = Approval(
        fingerprint=draft.fingerprint(), approved_by="the owner", approved_at=NOW
    )
    late = assess(books, draft, approval, TODAY, now=NOW + timedelta(hours=2))
    with pytest.raises(SendRefused):
        _outbox().send(draft, late)
