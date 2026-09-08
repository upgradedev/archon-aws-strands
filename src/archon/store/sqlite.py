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
--   requested          the row exists and SES has not been called yet, or the
--                      process died between calling it and hearing back
--   provider-accepted  SES returned a MessageId. That is acceptance by the
--                      provider and nothing more; it is not evidence that
--                      anybody received anything
--   failed             SES refused, with the reason kept
--
-- There is no "delivered" state, because nothing here has delivery evidence. A
-- column that could only ever be filled in by guessing does not exist.
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

    by_kind: dict[str, list[tuple[str, str]]] = {kind: [] for kind in REPLAY_ORDER}
    for kind, doc_id, body in rows:
        if kind not in by_kind:
            raise StoreError(f"{doc_id}: stored as a {kind!r}, which nothing here can post")
        by_kind[kind].append((doc_id, body))

    for kind in REPLAY_ORDER:
        for doc_id, body in by_kind[kind]:
            try:
                books.record(_decode(kind, body))
            except Exception as broken:
                raise StoreError(
                    f"{doc_id} ({kind}) will not post: {broken}. The store is not opened "
                    "rather than opened wrong."
                ) from broken
    return books


def forget(path: str | pathlib.Path) -> None:
    """Remove the store. Used by the demo's reset, never by the product."""
    pathlib.Path(path).unlink(missing_ok=True)


# --- the send ledger, which has to survive a crash ----------------------------

REQUESTED = "requested"
PROVIDER_ACCEPTED = "provider-accepted"
FAILED = "failed"


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
        """Written down, and nobody knows whether SES saw it.

        A crash between the call and the reply lands here. It must never be
        retried automatically: the provider may well have accepted it, and a
        second attempt is a second email to a client who is already annoyed.
        """
        return self.state == REQUESTED


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

    def settle(self, fingerprint: str, *, message_id: str | None, error: str | None) -> None:
        """Say how it ended: accepted by the provider, or refused."""
        state = PROVIDER_ACCEPTED if message_id else FAILED
        with contextlib.closing(self._open()) as db, db:
            db.execute(
                "UPDATE sends SET state = ?, message_id = ?, error = ? WHERE fingerprint = ?",
                (state, message_id, error, fingerprint),
            )

    def all(self) -> list[SendRecord]:
        with contextlib.closing(self._open()) as db:
            rows = db.execute("SELECT fingerprint FROM sends ORDER BY at").fetchall()
        return [record for (fp,) in rows if (record := self.find(fp)) is not None]
