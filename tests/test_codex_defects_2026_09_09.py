"""Three defects an independent review reproduced, pinned so they stay fixed.

Codex ran offline probes against this repository on 2026-09-09 and found two
things green CI did not. Both were reproduced here before anything was changed,
and a third followed from reading the first properly.

* **AR-03-R1.** `save`/`load` walked the documents only, so a restart forgot
  every agreed payment plan. A client who had agreed terms was chased again the
  next morning. The ledger balance stayed right and the behaviour was wrong,
  which is the worst shape of bug this project can have.
* **AR-02-R1.** Every exception from SES was recorded as `failed`, including a
  timeout. A timeout is the one case where the request may well have been
  accepted, so a retry sent a second demand for money. Measured: two calls.
* **the baseline.** Money received *before* an arrangement was agreed counted
  towards keeping it, so a client who paid nothing after agreeing could look
  like they were up to date.
"""

from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal

import pytest

from archon.adapters.ses import Outbox, SendRefused, _is_confirmed_rejection
from archon.demo import TODAY, keep_the_books, the_post
from archon.domain.arrangement import Instalment, consider
from archon.domain.money import money
from archon.store.sqlite import (
    FAILED,
    PROVIDER_ACCEPTED,
    QUEUED,
    UNKNOWN,
    SendLog,
    load,
    save,
)
from archon.web.app import Session


@pytest.fixture
def store(tmp_path):
    return str(tmp_path / "books.db")


class LostAcknowledgement:
    """SES took the request. The answer never came back."""

    def __init__(self) -> None:
        self.calls = 0

    def send_email(self, **kwargs):
        self.calls += 1
        raise TimeoutError("read timeout waiting for the response")


class ClientError(Exception):
    """botocore's name for: the request arrived and the API said no."""


class Refusing:
    def __init__(self) -> None:
        self.calls = 0

    def send_email(self, **kwargs):
        self.calls += 1
        raise ClientError("MessageRejected: address not verified")


class Working:
    def __init__(self) -> None:
        self.calls = 0

    def send_email(self, **kwargs):
        self.calls += 1
        return {"MessageId": f"ses-{self.calls:04d}"}


def session_with(store, client):
    session = Session(store_path=store)
    session.outbox = Outbox(client=client, sender="books@archon.example", log=SendLog(store))
    return session


# --- AR-02-R1: an ambiguous outcome is not a failure --------------------------


def test_a_timeout_is_recorded_as_unknown_not_failed(store):
    client = LostAcknowledgement()
    session = session_with(store, client)
    draft = session.draft()

    with pytest.raises(SendRefused, match="nobody knows whether it went"):
        session.outbox.send(draft, session.verdict(draft))

    assert SendLog(store).find(draft.fingerprint()).state == UNKNOWN
    assert client.calls == 1


def test_an_unknown_outcome_is_never_retried_on_its_own(store):
    """The defect. It used to call SES a second time."""
    client = LostAcknowledgement()
    first = session_with(store, client)
    draft = first.draft()
    with pytest.raises(SendRefused):
        first.outbox.send(draft, first.verdict(draft))

    second = session_with(store, client)
    with pytest.raises(SendRefused, match="'unknown'"):
        second.outbox.send(second.draft(), second.verdict(second.draft()))

    assert client.calls == 1, "a second demand for money went out after a timeout"


def test_the_refusal_says_why_it_will_not_try_again(store):
    session = session_with(store, LostAcknowledgement())
    draft = session.draft()
    with pytest.raises(SendRefused) as caught:
        session.outbox.send(draft, session.verdict(draft))
    said = " ".join(str(caught.value).split())
    assert "recorded as unknown" in said
    assert "a person can clear the record" in said


def test_a_confirmed_rejection_is_a_failure_and_may_be_tried_again(store):
    """The other half. Making everything unretryable would be its own bug."""
    refusing = Refusing()
    session = session_with(store, refusing)
    draft = session.draft()

    with pytest.raises(ClientError):
        session.outbox.send(draft, session.verdict(draft))
    assert SendLog(store).find(draft.fingerprint()).state == FAILED

    working = Working()
    session.outbox = Outbox(client=working, sender="books@archon.example", log=SendLog(store))
    receipt = session.outbox.send(draft, session.verdict(draft))

    assert working.calls == 1
    assert receipt.message_id
    assert SendLog(store).find(draft.fingerprint()).state == PROVIDER_ACCEPTED


def test_only_a_recognised_rejection_counts_as_one():
    """Anything unrecognised is ambiguous, because guessing sends twice."""
    assert _is_confirmed_rejection(ClientError("no"))
    assert not _is_confirmed_rejection(TimeoutError("read timeout"))
    assert not _is_confirmed_rejection(OSError("connection reset"))
    assert not _is_confirmed_rejection(Exception("something odd"))


def test_eight_callers_at_once_send_exactly_one_email(store):
    """Two tabs, two workers, a double-click. Only one may send."""
    client = Working()
    session = Session(store_path=store)
    draft = session.draft()
    release = session.verdict(draft)
    refused: list[str] = []

    def attempt():
        outbox = Outbox(client=client, sender="books@archon.example", log=SendLog(store))
        try:
            outbox.send(draft, release)
        except SendRefused as stopped:
            refused.append(str(stopped))

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert client.calls == 1, f"{client.calls} emails for one approved draft"


def test_the_states_distinguish_what_is_known_from_what_is_not():
    from archon.store.sqlite import DELIVERED, NO_RESEND

    assert QUEUED in NO_RESEND and UNKNOWN in NO_RESEND
    assert PROVIDER_ACCEPTED in NO_RESEND and DELIVERED in NO_RESEND
    assert FAILED not in NO_RESEND, "a confirmed rejection is the one retryable state"


def test_delivered_is_declared_and_never_written():
    """The difference between provider acceptance and arrival is the point."""
    from archon.store.sqlite import DELIVERED, SCHEMA

    assert DELIVERED == "delivered"
    said = " ".join(SCHEMA.split())
    assert "independent evidence of arrival" in said
    assert "the column is never" in said


# --- AR-03-R1: an agreed plan has to survive the process ----------------------


def plan_for(books, worst, first=None):
    owed = worst.outstanding
    head = first if first is not None else money(owed / 2)
    return consider(
        invoice_id=worst.doc_id,
        outstanding=owed,
        instalments=(
            Instalment(date(2026, 9, 20), head),
            Instalment(date(2026, 10, 5), money(owed - head)),
        ),
        as_of=TODAY,
        baseline=worst.gross - worst.outstanding,
        approved_by="owner",
    )


def test_an_agreed_plan_survives_a_restart(store):
    """The defect. A restart chased a client who had agreed terms."""
    books = keep_the_books(the_post())
    worst = books.worst_overdue(TODAY)
    books.agree(plan_for(books, worst))
    assert books.worst_overdue(TODAY) is None

    save(books, store)
    reopened = load(store)

    assert reopened.worst_overdue(TODAY) is None, "the agreed hold was lost"
    assert len(reopened.arrangements) == 1


def test_reopening_changes_no_figure_in_the_ledger(store):
    books = keep_the_books(the_post())
    worst = books.worst_overdue(TODAY)
    owed = worst.outstanding
    books.agree(plan_for(books, worst))
    save(books, store)

    reopened = load(store)
    still = next(s for s in reopened.uncollected() if s.doc_id == worst.doc_id)
    assert reopened.ledger.trial_balance() == 0
    assert still.outstanding == owed


def test_who_approved_it_and_what_had_been_paid_are_kept(store):
    books = keep_the_books(the_post())
    worst = books.worst_overdue(TODAY)
    paid_before = worst.gross - worst.outstanding
    books.agree(plan_for(books, worst))
    save(books, store)

    kept = load(store).arrangement_for(worst.doc_id)
    assert kept.approved_by == "owner"
    assert kept.baseline == paid_before
    assert kept.version == 1
    assert len(kept.instalments) == 2


def test_a_stored_plan_that_will_not_read_back_stops_the_open(store, tmp_path):
    import sqlite3

    books = keep_the_books(the_post())
    worst = books.worst_overdue(TODAY)
    books.agree(plan_for(books, worst))
    save(books, store)

    with sqlite3.connect(store) as db:
        db.execute("UPDATE arrangements SET instalments = ?", ("not json",))

    from archon.store.sqlite import StoreError

    with pytest.raises(StoreError, match="will not read back"):
        load(store)


# --- the baseline: money paid before a promise does not keep it ---------------


def test_earlier_receipts_do_not_pay_a_later_instalment():
    """Paid 480 before agreeing. The first instalment is 400 and nothing new arrived."""
    books = keep_the_books(the_post())
    worst = books.worst_overdue(TODAY)
    books.agree(plan_for(books, worst, first=money(Decimal("400.00"))))

    day_after = date(2026, 9, 21)
    assert books.worst_overdue(day_after) is not None, "old money kept a new promise"


def test_without_a_baseline_the_same_case_goes_unchased():
    """The behaviour being corrected, kept visible so the fix cannot be undone quietly."""
    books = keep_the_books(the_post())
    worst = books.worst_overdue(TODAY)
    owed = worst.outstanding
    head = money(Decimal("400.00"))
    books.agree(
        consider(
            invoice_id=worst.doc_id,
            outstanding=owed,
            instalments=(
                Instalment(date(2026, 9, 20), head),
                Instalment(date(2026, 10, 5), money(owed - head)),
            ),
            as_of=TODAY,
            baseline=Decimal("0.00"),
        )
    )
    assert books.worst_overdue(date(2026, 9, 21)) is None


def test_money_arriving_after_the_promise_does_keep_it():
    from archon.domain.documents import Receipt

    books = keep_the_books(the_post())
    worst = books.worst_overdue(TODAY)
    head = money(Decimal("400.00"))
    books.agree(plan_for(books, worst, first=head))
    books.record(Receipt("RC-NEW", worst.doc_id, date(2026, 9, 19), head, "email:new"))

    assert books.worst_overdue(date(2026, 9, 21)) is None


def test_a_credit_that_takes_receipts_below_the_baseline_is_not_negative():
    plan = consider(
        invoice_id="SI-001",
        outstanding=Decimal("1000.00"),
        instalments=(Instalment(date(2026, 10, 1), Decimal("1000.00")),),
        as_of=TODAY,
        baseline=Decimal("500.00"),
    )
    assert plan.paid_under_this(Decimal("100.00")) == Decimal("0.00")
