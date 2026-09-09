"""The record of what was sent, which has to survive the process ending.

This exists because of a measurement rather than a worry. The send ledger lived
in the `Outbox`, in memory. A restart emptied it, and one approved draft became
two emails to a client: a fake SES client counted the calls and saw two. With
live SES that is a second demand for money to somebody who has already had one.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from archon.adapters.ses import Outbox, SendRefused
from archon.store.sqlite import FAILED, PROVIDER_ACCEPTED, REQUESTED, SendLog, SendRecord
from archon.web.app import Session


class Counting:
    """A SES client that says how many emails it was actually asked to send."""

    def __init__(self) -> None:
        self.calls = 0

    def send_email(self, **kwargs):
        self.calls += 1
        return {"MessageId": f"ses-{self.calls:04d}"}


class ClientError(Exception):
    """botocore's name for a request that arrived and was refused.

    The class name matters: after 2026-09-09 the outbox only calls something a
    failure when it recognises it as a confirmed rejection. A bare RuntimeError
    is ambiguous, and ambiguous means unknown, because a timeout that is treated
    as a failure is retried and sends a second email.
    """


class Refusing:
    def send_email(self, **kwargs):
        raise ClientError("SES said no")


@pytest.fixture
def store(tmp_path):
    return str(tmp_path / "books.db")


def outbox_for(store, client):
    return Outbox(client=client, sender="books@archon.example", log=SendLog(store))


def test_asking_twice_in_one_session_sends_once(store):
    client = Counting()
    session = Session(store_path=store)
    session.outbox = outbox_for(store, client)
    draft = session.draft()

    first = session.outbox.send(draft, session.verdict(draft))
    again = session.outbox.send(draft, session.verdict(draft))

    assert client.calls == 1
    assert again.message_id == first.message_id


def test_a_restart_does_not_send_the_same_draft_again(store):
    """The defect this file exists for. Measured before it was fixed."""
    client = Counting()
    first_run = Session(store_path=store)
    first_run.outbox = outbox_for(store, client)
    draft = first_run.draft()
    sent = first_run.outbox.send(draft, first_run.verdict(draft))

    del first_run
    second_run = Session(store_path=store)
    second_run.outbox = outbox_for(store, client)
    again = second_run.outbox.send(second_run.draft(), second_run.verdict(second_run.draft()))

    assert client.calls == 1, "the client received a second email for one approved draft"
    assert again.message_id == sent.message_id


def test_the_record_names_the_whole_external_act(store):
    session = Session(store_path=store)
    session.outbox = outbox_for(store, Counting())
    draft = session.draft()
    session.outbox.send(draft, session.verdict(draft))

    record = SendLog(store).find(draft.fingerprint())
    assert record.state == PROVIDER_ACCEPTED
    assert record.to_address == draft.to_address
    assert record.invoice_id == draft.invoice_id
    assert record.message_id
    assert record.amount, "the figure that was demanded travels with the record"


def test_the_intention_is_written_before_anything_leaves(store):
    """A crash between calling SES and hearing back must not lose the attempt."""
    session = Session(store_path=store)
    written: list[str] = []

    class Watching:
        def send_email(self, **kwargs):
            # By now the row must already exist, or a crash here is invisible.
            record = SendLog(store).find(session.draft().fingerprint())
            written.append(record.state if record else "nothing written")
            return {"MessageId": "ses-0001"}

    session.outbox = outbox_for(store, Watching())
    draft = session.draft()
    session.outbox.send(draft, session.verdict(draft))

    assert written == [REQUESTED]


def test_an_attempt_that_never_settled_is_not_retried_automatically(store):
    """It may already have gone. A second try is a second email."""
    session = Session(store_path=store)
    draft = session.draft()
    log = SendLog(store)
    log.requested(
        SendRecord(
            fingerprint=draft.fingerprint(),
            state=REQUESTED,
            to_address=draft.to_address,
            invoice_id=draft.invoice_id,
            amount="2000.00",
            at="2026-09-08T12:00:00",
        )
    )

    client = Counting()
    session.outbox = outbox_for(store, client)
    with pytest.raises(SendRefused, match="nobody knows whether it went"):
        session.outbox.send(draft, session.verdict(draft))
    assert client.calls == 0


def test_a_refusal_by_the_provider_is_recorded_as_failed(store):
    session = Session(store_path=store)
    session.outbox = outbox_for(store, Refusing())
    draft = session.draft()

    with pytest.raises(ClientError):
        session.outbox.send(draft, session.verdict(draft))

    record = SendLog(store).find(draft.fingerprint())
    assert record.state == FAILED
    assert "SES said no" in record.error
    assert record.message_id is None


def test_a_failed_send_can_be_tried_again(store):
    """Failed is not in flight. Nothing left, so nothing is duplicated."""
    session = Session(store_path=store)
    draft = session.draft()
    session.outbox = outbox_for(store, Refusing())
    with pytest.raises(ClientError):
        session.outbox.send(draft, session.verdict(draft))

    client = Counting()
    session.outbox = outbox_for(store, client)
    receipt = session.outbox.send(draft, session.verdict(draft))
    assert client.calls == 1
    assert receipt.message_id


def test_there_is_no_delivered_state_because_there_is_no_evidence_of_delivery():
    """SES accepting a message is not somebody receiving it."""
    import archon.store.sqlite as store_module

    states = {REQUESTED, PROVIDER_ACCEPTED, FAILED}
    assert "delivered" not in states
    assert "delivered" not in store_module.SCHEMA.lower().split("--")[0]
    assert "not evidence that" in store_module.SCHEMA


# --- what the screen says about a send ----------------------------------------


def test_the_five_states_are_explained_apart_on_the_page(store):
    """AR-02: queued, unknown, provider-accepted, delivered and failed, kept apart."""
    from archon.web import render

    source = render.__file__
    text = pathlib.Path(source).read_text(encoding="utf-8")
    for state in ("queued", "unknown", "provider-accepted", "delivered", "failed"):
        assert f'"{state}"' in text, state


@pytest.fixture
def screen_session(store):
    """Swap the module-level session, and put the old one back.

    Leaving a replacement in place leaked into every later test in the run and
    failed two of them for reasons that had nothing to do with what they check.
    """
    import archon.web.app as web
    from archon.web.app import Session

    original = web.session
    web.session = Session(store_path=store)
    try:
        yield web.session
    finally:
        web.session = original


def test_provider_acceptance_is_not_presented_as_delivery(store, screen_session):
    import archon.web.app as web
    from archon.web.app import app
    web.session.outbox = outbox_for(store, Counting())
    draft = web.session.draft()
    web.session.outbox.send(draft, web.session.verdict(draft))

    with TestClient(app) as client:
        html = client.get("/").text

    assert "Accepted by Amazon SES" in html
    assert "not evidence that anyone received it" in html
    assert "Delivered, with evidence" not in html


def test_an_unknown_send_says_so_on_the_page(store, screen_session):
    import archon.web.app as web
    from archon.web.app import app

    class LostAck:
        def send_email(self, **kwargs):
            raise TimeoutError("read timeout")

    web.session.outbox = outbox_for(store, LostAck())
    draft = web.session.draft()
    with pytest.raises(SendRefused):
        web.session.outbox.send(draft, web.session.verdict(draft))

    with TestClient(app) as client:
        html = client.get("/").text

    assert "nobody knows whether it arrived" in html
    assert "cannot be recalled" in html
