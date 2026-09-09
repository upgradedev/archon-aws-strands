"""Keeping the books between one Sunday night and the next.

**What is stored is the post, not the position.** Documents are written down;
the ledger, the settlements and every report are derived from them on load by
replaying each document through `Books.record`, which is the same path a live
email takes. Storing the position instead would mean storing something that can
disagree with the documents it came from, and this project already refuses that
one level up: settlement is derived, never held as a flag.

The property that falls out of it is worth having. **A store cannot hold books
that do not balance**, because loading runs the same validation as receiving: an
invoice whose VAT stopped adding up, a payment against an invoice that is not
there, a duplicate id, all fail on load rather than producing a ledger that is
quietly wrong. A corrupt row is a loud error, not a silent 40 EUR.

`sqlite3` is in the standard library, so this adds no dependency and runs
anywhere the rest of it runs, including for a judge with nothing installed. The
memory layer this project intends for deployment is Aurora DSQL; the seam is
`save` and `load` over a path, and swapping the backing store does not reach into
the domain.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from archon.domain.arrangement import Arrangement, Instalment
from archon.domain.books import Books
from archon.domain.documents import (
    Payment,
    PayrollRun,
    PurchaseInvoice,
    Receipt,
    SalesInvoice,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id   TEXT NOT NULL,
    kind     TEXT NOT NULL,
    received INTEGER NOT NULL,
    body     TEXT NOT NULL,
    PRIMARY KEY (kind, doc_id)
);

-- What was sent, or attempted, keyed by the fingerprint of the exact bytes.
--
-- This is the only table that has to survive a crash to be correct. The send
-- ledger used to live in the Outbox, in memory, so restarting the process
-- emptied it and one approved draft became two emails to a client. That was
-- measured, not theorised: the fake SES client received two.
--
-- The states are deliberately not a single "sent" flag:
--   queued             the row exists and SES has not been called yet
--   unknown            SES was called and the outcome is not known: the
--                      connection timed out, or the process died between the
--                      call and the reply. The request may well have been
--                      accepted. NOTHING RESENDS FROM HERE automatically
--   provider-accepted  SES returned a MessageId. That is acceptance by the
--                      provider and nothing more; it is not evidence that
--                      anybody received anything
--   delivered          independent evidence of arrival exists. Nothing in this
--                      project can produce it today, so the column is never
--                      written; it is declared because the difference between
--                      it and provider-accepted is the point
--   failed             SES answered and refused. The request reached it and was
--                      rejected, so nothing was sent and a retry is safe
--
-- The distinction that matters is failed versus unknown. A confirmed rejection
-- can be retried. An ambiguous one cannot, because the email may already be in
-- somebody's inbox and a retry puts a second demand for money there. Treating a
-- timeout as failure was measured to send twice.
-- Arrangements a person approved. Not documents: nothing here has ever produced
-- a journal entry and nothing here ever will.
--
-- They are stored because they were being lost. `save`/`load` walked the
-- documents only, so restarting the process forgot every agreed payment plan
-- and the client who had agreed terms was chased again the next morning. The
-- ledger balance was right and the behaviour was wrong, which is the worst
-- shape of bug this project can have.
--
-- `baseline` is what had already been received when the owner agreed. Without
-- it, money paid before the promise counts towards keeping it.
CREATE TABLE IF NOT EXISTS arrangements (
    invoice_id  TEXT PRIMARY KEY,
    agreed_on   TEXT NOT NULL,
    baseline    TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    version     INTEGER NOT NULL,
    instalments TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sends (
    fingerprint TEXT PRIMARY KEY,
    state       TEXT NOT NULL,
    message_id  TEXT,
    to_address  TEXT NOT NULL,
    invoice_id  TEXT NOT NULL,
    amount      TEXT NOT NULL,
    at          TEXT NOT NULL,
    error       TEXT
);
"""

#: The order documents are replayed in. Invoices before the payments that settle
#: them, because `Books.record` refuses a payment whose invoice it has not seen,
#: and that refusal is the point rather than an obstacle.
REPLAY_ORDER = ("PurchaseInvoice", "SalesInvoice", "PayrollRun", "Payment", "Receipt")

KINDS = {
    "PurchaseInvoice": PurchaseInvoice,
    "SalesInvoice": SalesInvoice,
    "Payment": Payment,
    "Receipt": Receipt,
    "PayrollRun": PayrollRun,
}

_DATE_FIELDS = {"issued", "due", "paid_on", "received_on", "run_on"}
_MONEY_FIELDS = {"net", "vat", "gross", "amount"}


class StoreError(RuntimeError):
    """A store that cannot be turned back into books anyone may rely on."""


def _encode(document: object) -> str:
    fields = {}
    for name in document.__slots__:  # type: ignore[attr-defined]
        value = getattr(document, name)
        fields[name] = str(value) if isinstance(value, (Decimal, date)) else value
    return json.dumps(fields, sort_keys=True)


def _decode(kind: str, body: str) -> object:
    cls = KINDS[kind]
    fields = json.loads(body)
    for name, value in list(fields.items()):
        if name in _DATE_FIELDS and isinstance(value, str):
            fields[name] = date.fromisoformat(value)
        elif name in _MONEY_FIELDS and isinstance(value, str):
            fields[name] = Decimal(value)
    return cls(**fields)


def _documents(books: Books) -> list[object]:
    return [*books.purchases, *books.sales, *books.payroll, *books.payments, *books.receipts]


@contextlib.contextmanager
def _connect(path: str | pathlib.Path):
    """Commit and then close.

    `with sqlite3.connect(...)` commits the transaction and leaves the connection
    open, which on Windows holds a lock on the file: deleting the store fails
    with a PermissionError, and in a long-running process the handles simply
    accumulate. Both are the same bug and this is where it is fixed.
    """
    db = sqlite3.connect(str(path))
    try:
        with db:
            yield db
    finally:
        db.close()


def save(books: Books, path: str | pathlib.Path) -> int:
    """Write every document down. Returns how many."""
    with _connect(path) as db:
        db.executescript(SCHEMA)
        rows = [
            (
                doc.doc_id,
                type(doc).__name__,
                order,
                _encode(doc),
            )
            for order, doc in enumerate(_documents(books))
        ]
        db.executemany(
            "INSERT OR REPLACE INTO documents (doc_id, kind, received, body) VALUES (?, ?, ?, ?)",
            rows,
        )
        db.execute("DELETE FROM arrangements")
        db.executemany(
            "INSERT INTO arrangements "
            "(invoice_id, agreed_on, baseline, approved_by, version, instalments) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    plan.invoice_id,
                    plan.agreed_on.isoformat(),
                    str(plan.baseline),
                    plan.approved_by,
                    plan.version,
                    json.dumps(
                        [
                            {"due": i.due.isoformat(), "amount": str(i.amount)}
                            for i in plan.instalments
                        ]
                    ),
                )
                for plan in books.arrangements.values()
            ],
        )
    return len(rows)


def load(path: str | pathlib.Path) -> Books:
    """Rebuild the books by replaying the post through the same validation.

    Raises `StoreError` naming the row rather than returning books that are
    subtly wrong. A store that can produce an unbalanced ledger is worse than one
    that will not open.
    """
    books = Books()
    if not pathlib.Path(path).exists():
        return books

    with _connect(path) as db:
        db.executescript(SCHEMA)
        rows = db.execute("SELECT kind, doc_id, body FROM documents ORDER BY received").fetchall()
        agreed = db.execute(
            "SELECT invoice_id, agreed_on, baseline, approved_by, version, instalments "
            "FROM arrangements"
        ).fetchall()

    by_kind: dict[str, list[tuple[str, str]]] = {kind: [] for kind in REPLAY_ORDER}
    for kind, doc_id, body in rows:
        if kind not in by_kind:
            raise StoreError(f"{doc_id}: stored as a {kind!r}, which nothing here can post")
        by_kind[kind].append((doc_id, body))

    for kind in REPLAY_ORDER:
        for doc_id, body in by_kind[kind]:
            try:
                books.record(_decode(kind, body), replay_legacy=True)
            except Exception as broken:
                raise StoreError(
                    f"{doc_id} ({kind}) will not post: {broken}. The store is not opened "
                    "rather than opened wrong."
                ) from broken

    # Arrangements last, because they are about documents that must already be
    # there. They post nothing, so replaying them cannot move the ledger.
    for invoice_id, agreed_on, baseline, approved_by, version, instalments in agreed:
        try:
            plan = Arrangement(
                invoice_id=invoice_id,
                agreed_on=date.fromisoformat(agreed_on),
                instalments=tuple(
                    Instalment(due=date.fromisoformat(i["due"]), amount=Decimal(i["amount"]))
                    for i in json.loads(instalments)
                ),
                baseline=Decimal(baseline),
                approved_by=approved_by,
                version=int(version),
            )
        except (ValueError, KeyError, TypeError) as broken:
            raise StoreError(
                f"the arrangement on {invoice_id} will not read back: {broken}. The store is "
                "not opened rather than opened with a payment plan nobody can check."
            ) from broken
        books.agree(plan)
    return books


def forget(path: str | pathlib.Path) -> None:
    """Remove the store. Used by the demo's reset, never by the product."""
    pathlib.Path(path).unlink(missing_ok=True)


# --- the send ledger, which has to survive a crash ----------------------------

QUEUED = "queued"
UNKNOWN = "unknown"
PROVIDER_ACCEPTED = "provider-accepted"
DELIVERED = "delivered"
FAILED = "failed"

#: Kept so older callers and stored rows still read. `requested` was the name
#: before the ambiguous case was separated from the confirmed one.
REQUESTED = QUEUED

#: Nothing may leave again while a row is in one of these.
NO_RESEND = frozenset({QUEUED, UNKNOWN, PROVIDER_ACCEPTED, DELIVERED})


@dataclass(frozen=True, slots=True)
class SendRecord:
    """One attempt to send one exact draft."""

    fingerprint: str
    state: str
    to_address: str
    invoice_id: str
    amount: str
    at: str
    message_id: str | None = None
    error: str | None = None

    @property
    def reached_the_provider(self) -> bool:
        return self.state == PROVIDER_ACCEPTED

    @property
    def in_flight(self) -> bool:
        """Nobody knows whether the provider saw it, so nothing may go again.

        Two things land here. A crash between the call and the reply, and a
        connection that timed out. Both mean the request may well have been
        accepted, and a second attempt is a second demand for money to a client
        who has already had one.
        """
        return self.state in {QUEUED, UNKNOWN}

    @property
    def settled(self) -> bool:
        """The outcome is known, either way."""
        return self.state in {PROVIDER_ACCEPTED, DELIVERED, FAILED}

    @property
    def may_send(self) -> bool:
        """A confirmed rejection is the only state a fresh attempt is safe from."""
        return self.state == FAILED


class SendLog:
    """The record of what has been sent, kept on disk rather than in memory.

    Writing happens in two steps on purpose. The row is written **before** SES is
    called, not after, because a process that dies between the call and the write
    would otherwise restart with no memory of an email that is already gone.
    Recording the intention first means the worst case is an email nobody is sure
    about, which a person can check, rather than an email sent twice, which a
    person cannot unsend.
    """

    def __init__(self, path: str | pathlib.Path) -> None:
        self.path = pathlib.Path(path)

    def _open(self):
        db = sqlite3.connect(str(self.path))
        db.executescript(SCHEMA)
        return db

    def find(self, fingerprint: str) -> SendRecord | None:
        with contextlib.closing(self._open()) as db:
            row = db.execute(
                "SELECT fingerprint, state, message_id, to_address, invoice_id, amount, at, error "
                "FROM sends WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
        if row is None:
            return None
        fp, state, message_id, to_address, invoice_id, amount, at, error = row
        return SendRecord(
            fingerprint=fp,
            state=state,
            message_id=message_id,
            to_address=to_address,
            invoice_id=invoice_id,
            amount=amount,
            at=at,
            error=error,
        )

    def reserve(self, record: SendRecord) -> bool:
        """Claim the right to send this exact text. True only for the winner.

        Two callers can reach a send at the same moment: two browser tabs, two
        workers, a person double-clicking. `INSERT OR REPLACE` let both through,
        because it succeeds for everybody. This inserts and reports whether the
        row was new, so exactly one caller proceeds and the rest are told the
        send is already in hand.

        The one row that may be claimed again is a confirmed rejection, where
        the provider answered and refused, so nothing was sent.
        """
        with contextlib.closing(self._open()) as db, db:
            cursor = db.execute(
                "INSERT INTO sends "
                "(fingerprint, state, message_id, to_address, invoice_id, amount, at, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(fingerprint) DO UPDATE SET state = excluded.state, at = excluded.at, "
                "error = NULL WHERE sends.state = ?",
                (
                    record.fingerprint,
                    QUEUED,
                    None,
                    record.to_address,
                    record.invoice_id,
                    record.amount,
                    record.at,
                    None,
                    FAILED,
                ),
            )
            return cursor.rowcount > 0

    def requested(self, record: SendRecord) -> None:
        """Write the intention down before anything leaves."""
        with contextlib.closing(self._open()) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO sends "
                "(fingerprint, state, message_id, to_address, invoice_id, amount, at, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.fingerprint,
                    REQUESTED,
                    None,
                    record.to_address,
                    record.invoice_id,
                    record.amount,
                    record.at,
                    None,
                ),
            )

    def settle(
        self,
        fingerprint: str,
        *,
        message_id: str | None,
        error: str | None,
        state: str | None = None,
    ) -> None:
        """Say how it ended, and be honest when that is not known.

        `state` is passed explicitly for the ambiguous case. Without it the old
        behaviour holds: a MessageId means accepted, anything else means the
        provider refused. That default was wrong for timeouts and is why the
        caller now decides.
        """
        state = state or (PROVIDER_ACCEPTED if message_id else FAILED)
        with contextlib.closing(self._open()) as db, db:
            db.execute(
                "UPDATE sends SET state = ?, message_id = ?, error = ? WHERE fingerprint = ?",
                (state, message_id, error, fingerprint),
            )

    def all(self) -> list[SendRecord]:
        with contextlib.closing(self._open()) as db:
            rows = db.execute("SELECT fingerprint FROM sends ORDER BY at").fetchall()
        return [record for (fp,) in rows if (record := self.find(fp)) is not None]
