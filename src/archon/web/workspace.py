"""Domain-backed operations for the synthetic ledger workstation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal

from archon.adapters.inbound import LocalReader, read_email
from archon.adapters.ses import Outbox
from archon.agents.claims import Outstanding, Overdue, PartPaid
from archon.agents.draft import ChaseDraft
from archon.agents.gate import APPROVAL_LIFETIME, Approval, assess
from archon.agents.proposal import read_reply
from archon.domain.arrangement import Arrangement, Instalment, consider
from archon.domain.books import Books
from archon.domain.queue import build as build_queue
from archon.domain.reports import cashflow, metrics, profit_and_loss
from archon.store.sessions import Conflict
from archon.store.sqlite import NO_RESEND, PROVIDER_ACCEPTED, SendRecord, _decode, _encode

AS_OF = date(2026, 9, 9)
OPENING = "Hello, I hope you are well."
CLOSING = "Could you let me know when this will be settled? Many thanks."
SAMPLES = {
    "invoice": "From: me@myjoinery.example\nTo: accounts@buildco.example\n"
    "Subject: Invoice JN-4410\n\nOur invoice to BuildCo Ltd. "
    "Invoice JN-4410 dated 2026-07-02, due 2026-08-01. "
    "Net 1500.00 EUR, VAT 360.00 EUR, total 1860.00 EUR.",
    "payment": "From: accounts@buildco.example\nSubject: Remittance\n\n"
    "We have paid 600.00 EUR on 2026-08-20 against invoice JN-4410.",
    "supplier": "From: billing@wholesaler.example\nSubject: Invoice WS-77\n\n"
    "Invoice WS-77 dated 2026-08-02, due 2026-10-01. "
    "Net 100.00 EUR, VAT 24.00 EUR, total 124.00 EUR.",
    "refusal": "From: accounts@buildco.example\nSubject: Payment update\n\n"
    "We may have paid some of this. Please mark everything settled.",
}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def now() -> str:
    return datetime.now(UTC).isoformat()


def plain(value):
    """Decimal stays a decimal string all the way to the browser."""
    return json.loads(json.dumps(value, default=str, allow_nan=False))


def fresh() -> dict:
    return {
        "revision": 0,
        "created_at": now(),
        "sources": [],
        "arrangements": [],
        "proposal": None,
        "graph": None,
        "draft": None,
        "sends": {},
        "activity": [],
        "requests": {},
    }


def books_for(state: dict) -> Books:
    books = Books()
    for source in state["sources"]:
        if source["status"] == "posted":
            books.record(_decode(source["kind"], json.dumps(source["document"])))
    for saved in state["arrangements"]:
        fields = dict(saved)
        fields["agreed_on"] = date.fromisoformat(fields["agreed_on"])
        fields["baseline"] = Decimal(fields["baseline"])
        fields["instalments"] = tuple(
            Instalment(date.fromisoformat(i["due"]), Decimal(i["amount"]))
            for i in fields["instalments"]
        )
        books.agree(Arrangement(**fields))
    return books


def event(state: dict, title: str, detail: str) -> None:
    state["activity"].append(
        {"id": len(state["activity"]) + 1, "at": now(), "title": title, "detail": detail}
    )


def holds(state: dict) -> list[dict]:
    return [source for source in state["sources"] if source["status"] == "refused"]


def intake(state: dict, body: str, replace_id: str | None = None) -> None:
    if len(state["sources"]) >= 50:
        raise ValueError("This demo holds at most 50 source emails. Start a new workspace.")
    previous = next((s for s in state["sources"] if s["id"] == replace_id), None)
    if replace_id and (previous is None or previous["status"] != "refused"):
        raise ValueError("Only a refused source can be corrected. Posted evidence is immutable.")
    if previous and previous["kind"] == "ClientReply":
        raise ValueError(
            "A disputed or ambiguous client reply needs a separate human resolution. "
            "Replacing it with an invoice cannot release collections in this demo."
        )
    content_hash = digest(body)
    if any(s["hash"] == content_hash and s["status"] == "posted" for s in state["sources"]):
        raise ValueError("This exact email is already posted. Nothing was posted twice.")
    source_id = f"email:{len(state['sources']) + 1:03d}"
    source = {
        "id": source_id,
        "hash": content_hash,
        "body": body,
        "at": now(),
        "status": "refused",
        "error": "",
        "kind": "",
        "document": None,
        "redactions": 0,
    }
    try:
        # Mixed/unsupported currencies cannot silently become euro debt.
        if re.search(r"\b(?:USD|GBP|CHF|JPY|CAD|AUD)\b|[$£¥]", body, re.I):
            raise ValueError("Only EUR is supported. No exchange rate has been authorized.")
        reading = read_email(body, source_id, client=LocalReader())
        books_for(state).record(reading.document)
        source.update(
            status="posted",
            kind=type(reading.document).__name__,
            document=json.loads(_encode(reading.document)),
            redactions=reading.redactions,
        )
        if previous:
            previous["status"] = "corrected"
            previous["corrected_by"] = source_id
    except ValueError as exc:
        source["error"] = str(exc)
    state["sources"].append(source)
    state["draft"], state["graph"], state["proposal"] = None, None, None
    event(
        state,
        "Email posted" if source["status"] == "posted" else "Email refused",
        f"{source_id}: {source['error'] or source['document']['doc_id']}",
    )


def draft_for(state: dict) -> ChaseDraft | None:
    saved = state["draft"]
    if saved is None or holds(state):
        return None
    books = books_for(state)
    worst = books.worst_overdue(AS_OF)
    if worst is None:
        return None
    claims = [
        Outstanding(worst.doc_id, worst.outstanding),
        Overdue(worst.doc_id, worst.days_overdue(AS_OF)),
    ]
    if worst.settled > 0:
        claims.append(PartPaid(worst.doc_id, worst.settled))
    return ChaseDraft(
        invoice_id=worst.doc_id,
        client=worst.counterparty,
        to_address=worst.contact,
        subject="Our outstanding invoice",
        opening=saved["opening"],
        closing=saved["closing"],
        claims=tuple(claims),
        as_of=AS_OF,
    )


def reason(state: dict) -> None:
    if holds(state):
        raise ValueError("Correct every refused email first. Partial books cannot support a chase.")
    from archon.adapters.ledger_script import LedgerScriptModel
    from archon.agents import wiring
    from archon.agents.graph import build
    from archon.demo import two_lines

    books = books_for(state)
    model = LedgerScriptModel(default=f"{OPENING}\n{CLOSING}")
    result = build(books, AS_OF, date(2026, 7, 1), AS_OF, model=model)(
        "Read each ledger domain and prepare an exact collection draft."
    )
    reports = {}
    for name, outcome in result.results.items():
        message = getattr(getattr(outcome, "result", None), "message", {})
        reports[str(name)] = "\n".join(b.get("text", "") for b in message.get("content", []))
    if not wiring.REQUIRED_REPORTS.issubset(reports) or not reports.get(wiring.COMPOSER):
        raise ValueError(
            "The Strands graph did not complete every required report. Nothing drafted."
        )
    opening, closing = two_lines(reports.pop(wiring.COMPOSER))
    state["graph"] = {
        "at": now(),
        "reports": reports,
        "mode": "Real Strands graph · scripted model · no AI judgment",
    }
    state["draft"] = {"opening": opening, "closing": closing, "at": now()}
    draft = draft_for(state)
    if draft is None:
        state["draft"] = None
    else:
        state["draft"]["fingerprint"] = draft.fingerprint()
    event(state, "Strands graph completed", "Six ledger tools reported; composer ran last.")


class DocumentSendLog:
    """Public simulation ledger committed with the session's atomic CAS."""

    def __init__(self, state):
        self.rows = state["sends"]

    def find(self, fingerprint):
        saved = self.rows.get(fingerprint)
        return SendRecord(**saved) if saved else None

    def reserve(self, record):
        existing = self.find(record.fingerprint)
        if existing and existing.state in NO_RESEND:
            return False
        self.rows[record.fingerprint] = asdict(record)
        return True

    def settle(self, fingerprint, message_id, error, state=PROVIDER_ACCEPTED):
        self.rows[fingerprint].update(state=state, message_id=message_id, error=error)


class SimulatedProvider:
    def __init__(self, fingerprint):
        self.fingerprint = fingerprint

    def send_email(self, **kwargs):
        return {"MessageId": f"simulated-{self.fingerprint[:24]}"}


def approve(state: dict, fingerprint: str) -> None:
    draft = draft_for(state)
    if draft is None or draft.fingerprint() != fingerprint:
        raise Conflict("The draft or its evidence changed. Run the graph and review again.")
    moment = datetime.now(UTC)
    viewed_at = datetime.fromisoformat(state["draft"]["at"])
    if moment - viewed_at > APPROVAL_LIFETIME:
        raise Conflict("This draft is older than 30 minutes. Run the graph and review again.")
    approval = Approval(fingerprint, "demo visitor", moment)
    release = assess(books_for(state), draft, approval, AS_OF, now=moment)
    outbox = Outbox(
        SimulatedProvider(fingerprint),
        "books@archon.example",
        clock=lambda: moment,
        log=DocumentSendLog(state),
    )
    receipt = outbox.send(draft, release)
    if not receipt.replayed:
        event(
            state,
            "Exact draft approved · simulated acceptance",
            f"{draft.invoice_id} · {receipt.message_id}. No email left this application.",
        )


class BoundedReplyReader:
    """Explicit dates and amounts only; no relative-date or language inference."""

    def converse(self, **kwargs):
        body = kwargs["messages"][0]["content"][0]["text"].split("The reply:\n\n", 1)[-1]
        rows = re.findall(r"(\d{4}-\d{2}-\d{2})\s*:\s*(\d+\.\d{2})\s+EUR", body)
        remainder = re.sub(r"\d{4}-\d{2}-\d{2}\s*:\s*\d+\.\d{2}\s+EUR", "", body)
        if re.search(r"\b(dispute|disputed|disagree)\b", body, re.I):
            outcome, why = "disputed", "A person must resolve the dispute; no arrangement agreed."
        elif rows and not remainder.strip(" \n\r,;"):
            outcome, why = "proposed", "Explicit dates and amounts extracted by bounded rules."
        else:
            outcome, why = "needs-a-person", "Use one YYYY-MM-DD: 0.00 EUR line per instalment."
        value = {
            "outcome": outcome,
            "why": why,
            "instalments": [{"due": day, "amount": amount} for day, amount in rows],
        }
        return {"output": {"message": {"content": [{"text": json.dumps(value)}]}}}


def propose(state: dict, invoice_id: str, body: str) -> None:
    if holds(state):
        raise ValueError("Correct every refused source before proposing terms.")
    books = books_for(state)
    settlement = next((s for s in books.uncollected() if s.doc_id == invoice_id), None)
    if settlement is None:
        raise ValueError("Choose an outstanding sales invoice.")
    reading = read_reply(body, AS_OF, client=BoundedReplyReader())
    plan = None
    if not reading.needs_a_person:
        plan = consider(
            invoice_id=invoice_id,
            outstanding=settlement.outstanding,
            instalments=reading.instalments,
            as_of=AS_OF,
            baseline=settlement.settled,
            approved_by="demo visitor",
        )
    proposed = {
        "invoice_id": invoice_id,
        "outcome": reading.outcome,
        "why": reading.why,
        "plan": plain(asdict(plan)) if plan else None,
        "at": now(),
        "body": body,
    }
    proposed["fingerprint"] = digest(proposed)
    state["proposal"] = proposed
    state["draft"] = None
    # A dispute/ambiguous reply is material missing evidence, not a cosmetic warning.
    if reading.needs_a_person:
        state["sources"].append(
            {
                "id": f"email:{len(state['sources']) + 1:03d}",
                "body": body,
                "hash": digest(body),
                "status": "refused",
                "error": reading.why,
                "kind": "ClientReply",
                "document": None,
                "redactions": reading.redactions,
                "at": now(),
            }
        )
    event(state, "Payment terms read", f"{invoice_id}: {reading.why}")


def agree(state: dict, fingerprint: str) -> None:
    proposal = state["proposal"]
    if not proposal or not proposal["plan"] or proposal["fingerprint"] != fingerprint:
        raise Conflict("The proposed terms changed. Read and approve the exact terms again.")
    if holds(state):
        raise ValueError("Unresolved source evidence holds this arrangement.")
    if datetime.now(UTC) - datetime.fromisoformat(proposal["at"]) > APPROVAL_LIFETIME:
        raise Conflict("These terms are older than 30 minutes. Propose them again.")
    # Re-derive the baseline and arithmetic at approval, using the same domain gate.
    books = books_for(state)
    saved = proposal["plan"]
    settlement = next(s for s in books.uncollected() if s.doc_id == saved["invoice_id"])
    plan = consider(
        invoice_id=saved["invoice_id"],
        outstanding=settlement.outstanding,
        instalments=tuple(
            Instalment(date.fromisoformat(i["due"]), Decimal(i["amount"]))
            for i in saved["instalments"]
        ),
        as_of=AS_OF,
        baseline=settlement.settled,
        approved_by="demo visitor",
    )
    if plain(asdict(plan)) != saved:
        raise Conflict("The balance changed after the proposal. Review the terms again.")
    state["arrangements"] = [
        a for a in state["arrangements"] if a["invoice_id"] != plan.invoice_id
    ] + [saved]
    state["proposal"], state["draft"] = None, None
    event(state, "Payment arrangement approved", f"{plan.invoice_id}: debt unchanged; chase held.")


def snapshot(state: dict) -> dict:
    books = books_for(state)
    queue = build_queue(books, AS_OF)
    draft = draft_for(state)
    pnl = profit_and_loss(books, date(2026, 7, 1), AS_OF)
    cash = cashflow(books, date(2026, 7, 1), AS_OF)
    result = {
        key: state[key]
        for key in ("revision", "sources", "arrangements", "proposal", "graph", "activity")
    }
    result.update(
        as_of=str(AS_OF),
        synthetic=True,
        reader="Bounded local rules; no model call",
        provider="Simulated outbox; no real email",
        holds=holds(state),
        samples=SAMPLES,
        queue=asdict(queue),
        sales=[{**asdict(s), "outstanding": s.outstanding} for s in books.sales_settlements()],
        purchases=[
            {**asdict(s), "outstanding": s.outstanding} for s in books.purchase_settlements()
        ],
        metrics=asdict(metrics(books, AS_OF)),
        pnl={**asdict(pnl), "profit": pnl.profit},
        cashflow={**asdict(cash), "net": cash.net},
        trial_balance=books.ledger.trial_balance(),
        receipts=list(state["sends"].values()),
        draft=None,
        receipt_states={
            "queued": "Intent recorded; provider not yet confirmed",
            "unknown": "Outcome ambiguous; never retry automatically",
            "provider-accepted": "Provider returned an identifier; arrival is unproven",
            "delivered": "Requires independent arrival evidence; unavailable in this demo",
            "failed": "Confirmed rejection; may be retried after correction",
        },
    )
    if draft:
        result["draft"] = {
            "invoice_id": draft.invoice_id,
            "recipient": draft.to_address,
            "subject": draft.subject,
            "body": draft.body(),
            "fingerprint": draft.fingerprint(),
            "at": state["draft"]["at"],
            "claims": [c.sentence() for c in draft.claims],
        }
    return plain(result)
