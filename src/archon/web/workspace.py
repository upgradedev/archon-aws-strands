"""Domain-backed operations for the synthetic ledger workstation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from decimal import Decimal

from archon.adapters.bounded_post import PublicPostReader
from archon.adapters.inbound import BUSINESS_EMAIL, BUSINESS_NAME, read_email
from archon.adapters.ses import Outbox
from archon.agents.claims import Outstanding, Overdue, PartPaid
from archon.agents.draft import ChaseDraft
from archon.agents.gate import APPROVAL_LIFETIME, Approval, assess
from archon.agents.proposal import read_reply
from archon.domain.arrangement import Arrangement, Instalment, consider
from archon.domain.books import Books
from archon.domain.documents import Payment, Receipt, transfer_identity
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
    "We have paid 600.00 EUR on 2026-08-20 against invoice JN-4410.\n"
    "Transfer ID: DEMO-BANK-600-A",
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
            document = _decode(source["kind"], json.dumps(source["document"]))
            attested = state.get("transfer_attestations", {}).get(document.doc_id)
            if attested and isinstance(document, (Receipt, Payment)) and not document.transfer_id:
                # An additive human attestation changes the projection, never stored evidence.
                document = replace(document, transfer_id=attested)
            books.record(document, replay_legacy=True)
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


def seed_demo(state: dict) -> None:
    """Load fixed fictional evidence only into fresh books; no model or send."""
    if state != {**fresh(), "created_at": state.get("created_at"),
                 **{k: state[k] for k in ("provider_mode", "test_recipient") if k in state}}:
        raise ValueError("Demo data can only be loaded into a new workspace.")
    recipient = state.get("test_recipient", "accounts@buildco.example")
    invoice = SAMPLES["invoice"].replace("accounts@buildco.example", recipient)
    payment = SAMPLES["payment"].replace("accounts@buildco.example", recipient)
    paid_invoice = invoice.replace("JN-4410", "JN-4411").replace("BuildCo Ltd", "Oak Studio Ltd")
    paid_receipt = payment.replace("JN-4410", "JN-4411").replace("600.00", "1860.00").replace(
        "DEMO-BANK-600-A", "DEMO-BANK-1860-B")
    for body in (invoice, payment, SAMPLES["supplier"], paid_invoice, paid_receipt):
        intake(state, body)
        if state["sources"][-1]["status"] != "posted":
            raise ValueError("Demo evidence could not be validated. No workspace was created.")
        state["sources"][-1]["origin"] = "fictional-demo-template"
    state["demo_seed"] = "joinery-v1"
    event(state, "Fictional demo loaded", "Fixed example emails parsed with local rules. "
          "Balances computed from posted evidence; no Bedrock call, AI report or email send.")


def event(state: dict, title: str, detail: str) -> None:
    state["activity"].append(
        {"id": len(state["activity"]) + 1, "at": now(), "title": title, "detail": detail}
    )


def holds(state: dict) -> list[dict]:
    held = [source for source in state["sources"] if source["status"] == "refused"]
    legacy = legacy_documents(state)
    review_ids = set(books_for(state).legacy_payment_holds)
    for source in held:
        candidate = source.get("document")
        if candidate and source["error"].startswith("Ambiguous payment identity:"):
            review_ids.update(d["doc_id"] for d in legacy
                              if d["settles"] == candidate.get("settles")
                              and d["amount"] == candidate.get("amount"))
    for doc_id in sorted(review_ids):
        source = next(s for s in state["sources"] if s["document"]
                      and s["document"]["doc_id"] == doc_id)
        held.append({**source, "kind": "LegacyPaymentReview", "status": "refused",
                     "error": "Historical payments involved in ambiguity lack bank identities. "
                              "Records are "
                              "retained; reconcile them with a person before collections.",
                     "legacy_documents": legacy_documents(state)})
    return held


def legacy_documents(state: dict) -> list[dict]:
    return [s["document"] for s in state["sources"] if s["status"] == "posted"
            and s["kind"] in ("Receipt", "Payment") and not s["document"].get("transfer_id")
            and s["document"]["doc_id"] not in state.get("transfer_attestations", {})]


def intake(state: dict, body: str, replace_id: str | None = None, *, reader=None,
           validate_reading=None) -> None:
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
        reading = read_email(
            body, source_id, client=reader if reader is not None else PublicPostReader(),
            ours=BUSINESS_EMAIL,
            business_name=BUSINESS_NAME,
        )
        if validate_reading is not None:
            validate_reading(body, reading)
        source.update(kind=type(reading.document).__name__,
                      document=json.loads(_encode(reading.document)),
                      redactions=reading.redactions)
        if previous and previous["kind"] == "Receipt":
            if source["kind"] != "Receipt" or (
                previous["document"] and
                previous["document"]["settles"] != source["document"]["settles"]
            ):
                raise ValueError("Correct the same payment evidence; an invoice cannot resolve it.")
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
        if "Payment identity" in source["error"]:
            source["kind"] = "Receipt"
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
        subject=("[Archon controlled test] Our outstanding invoice"
                 if state.get("provider_mode") == "live" else "Our outstanding invoice"),
        opening=saved["opening"],
        closing=saved["closing"],
        claims=tuple(claims),
        as_of=AS_OF,
    )


def reason(state: dict, *, model=None, model_label: str | None = None,
           structured_composer: bool = False) -> None:
    if holds(state):
        raise ValueError("Correct every refused email first. Partial books cannot support a chase.")
    from archon.adapters.composition import (
        COMPOSER_JSON_RULES,
        READER_REPORT_RULES,
        composer_lines,
    )
    from archon.adapters.ledger_script import LedgerScriptModel
    from archon.agents import wiring
    from archon.agents.graph import build
    from archon.demo import two_lines

    books = books_for(state)
    if model is None:
        model = LedgerScriptModel(default=f"{OPENING}\n{CLOSING}")
    options = {"composer_suffix": COMPOSER_JSON_RULES,
               "reader_suffix": READER_REPORT_RULES} if structured_composer else {}
    result = build(books, AS_OF, date(2026, 7, 1), AS_OF, model=model, **options)(
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
    parse = composer_lines if structured_composer else two_lines
    opening, closing = parse(reports.pop(wiring.COMPOSER))
    state["graph"] = {
        "at": now(),
        "reports": reports,
        "mode": model_label or "Real Strands graph · scripted model · no AI judgment",
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


def approve(state: dict, fingerprint: str, *, outbox=None) -> None:
    draft = draft_for(state)
    if draft is None or draft.fingerprint() != fingerprint:
        raise Conflict("The draft or its evidence changed. Run the graph and review again.")
    moment = datetime.now(UTC)
    viewed_at = datetime.fromisoformat(state["draft"]["at"])
    if moment - viewed_at > APPROVAL_LIFETIME:
        raise Conflict("This draft is older than 30 minutes. Run the graph and review again.")
    approval = Approval(fingerprint, "demo visitor", moment)
    release = assess(books_for(state), draft, approval, AS_OF, now=moment)
    real_provider = outbox is not None
    outbox = outbox if real_provider else Outbox(
        SimulatedProvider(fingerprint),
        "books@archon.example",
        clock=lambda: moment,
        log=DocumentSendLog(state),
    )
    receipt = outbox.send(draft, release)
    if real_provider:
        state["sends"][fingerprint] = asdict(outbox.log.find(fingerprint))
    if not receipt.replayed:
        event(
            state,
            "Exact draft approved · SES acceptance" if real_provider else
            "Exact draft approved · simulated acceptance",
            f"{draft.invoice_id} · {receipt.message_id}. " + (
                "Provider accepted; delivery is not proven." if real_provider else
                "No email left this application."),
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
    state.setdefault("terms_history", []).append({"decision": "client-proposal", **proposed})
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
                "invoice_id": invoice_id,
                "document": None,
                "redactions": reading.redactions,
                "at": now(),
            }
        )
    event(state, "Payment terms read", f"{invoice_id}: {reading.why}")


def resolve(state: dict, source_id: str, decision: str, note: str,
            duplicate_of: str | None = None, identities: dict[str, str] | None = None) -> None:
    """Record a human resolution, never a replacement journal entry or automatic resend."""
    source = next((s for s in holds(state) if s["id"] == source_id), None)
    if source is None:
        raise Conflict("That source is no longer held. Refresh and inspect the current record.")
    if len(note.strip()) < 20:
        raise ValueError("Record the human evidence and reason in at least 20 characters.")
    if decision == "attest-legacy-payments":
        expected = {d["doc_id"] for d in legacy_documents(state)}
        if source["kind"] != "LegacyPaymentReview" or not expected or not identities:
            raise ValueError("Select a historical payment hold and supply its bank references.")
        if set(identities) != expected or len(identities) > 50:
            raise ValueError(
                "Supply references for every listed historical payment, and only those."
            )
        if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _/-]{2,79}", v)
               for v in identities.values()):
            raise ValueError(
                "Each supplied bank reference must be 3–80 letters, digits, spaces, /, _ or -."
            )
        attested = {**state.get("transfer_attestations", {}),
                    **{k: transfer_identity(v) for k, v in identities.items()}}
        # Validate the entire replay before storing any attestation. Duplicate events stay held;
        # they require an operator's accounting correction, not a fabricated second reference.
        candidate = {**state, "transfer_attestations": attested}
        if books_for(candidate).legacy_payment_holds:
            raise ValueError("Historical payment ambiguity remains. No resolution recorded.")
        state["transfer_attestations"] = attested
        state.setdefault("resolutions", []).append({
            "source_id": source_id, "decision": decision, "note": note.strip(),
            "identities": dict(identities), "at": now(), "revision": state["revision"],
            "approved_by": "demo visitor", "verification": "Human supplied; not bank verified",
        })
    elif decision == "duplicate-payment":
        target = next((s for s in state["sources"] if s["id"] == duplicate_of
                       and s["status"] == "posted" and s["kind"] == "Receipt"), None)
        if source["kind"] != "Receipt" or target is None:
            raise ValueError("Select the posted receipt for this duplicate payment.")
        candidate = source["document"]
        if candidate and any(candidate[k] != target["document"][k]
                             for k in ("settles", "amount", "received_on")):
            raise ValueError("The payment facts conflict. Correct the source before resolving it.")
    elif decision == "resume-collection":
        if source["kind"] != "ClientReply" or not source.get("invoice_id"):
            raise ValueError("Only an invoice-linked client reply can have this resolution.")
        if not any(s.doc_id == source["invoice_id"] for s in books_for(state).uncollected()):
            raise ValueError("This invoice is no longer outstanding. Review the current books.")
    else:
        raise ValueError("Choose a supported human resolution.")
    if decision != "attest-legacy-payments":
        source["status"] = "resolved"
        source["resolution"] = {"decision": decision, "note": note.strip(), "at": now(),
                            "duplicate_of": duplicate_of, "approved_by": "demo visitor",
                            "revision": state["revision"]}
    state["draft"], state["graph"], state["proposal"] = None, None, None
    event(state, "Human resolution recorded", f"{source_id}: {decision}; fresh review required.")


def checked_terms(state: dict, fingerprint: str) -> tuple[dict, Arrangement]:
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
    return proposal, plan


def counter(state: dict, fingerprint: str, body: str) -> None:
    """Record an owner-reviewed counteroffer, never client acceptance or a payment."""
    original, plan = checked_terms(state, fingerprint)
    reading = read_reply(body, AS_OF, client=BoundedReplyReader())
    if reading.needs_a_person:
        raise ValueError("A counterproposal requires explicit dated amounts, not a dispute.")
    replacement = consider(
        invoice_id=plan.invoice_id,
        outstanding=sum((i.amount for i in plan.instalments), Decimal("0")),
        instalments=reading.instalments, as_of=AS_OF, baseline=plan.baseline,
        approved_by="demo visitor",
    )
    if replacement.instalments == plan.instalments:
        raise ValueError("These are the original terms. Approve them or enter different dates.")
    record = {"decision": "owner-counterproposal", "invoice_id": plan.invoice_id,
              "at": now(), "body": body, "plan": plain(asdict(replacement)),
              "original": original, "status": "pending-client-acceptance",
              "revision": state["revision"], "approved_by": "demo visitor"}
    record["fingerprint"] = digest(record)
    state.setdefault("terms_history", []).append(record)
    state["proposal"], state["draft"], state["graph"] = None, None, None
    event(state, "Owner counterproposal recorded",
          f"{plan.invoice_id}: awaiting client acceptance; "
          "no message sent, no debt or hold changed.")


def agree(state: dict, fingerprint: str) -> None:
    proposal, plan = checked_terms(state, fingerprint)
    saved = proposal["plan"]
    state.setdefault("terms_history", []).append({"decision": "arrangement-approved",
                                                  "at": now(), "original": proposal})
    state["arrangements"] = [
        a for a in state["arrangements"] if a["invoice_id"] != plan.invoice_id
    ] + [saved]
    state["proposal"], state["draft"] = None, None
    event(state, "Payment arrangement approved", f"{plan.invoice_id}: debt unchanged; chase held.")


def snapshot(state: dict) -> dict:
    from archon.web.live import enabled

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
        demo_seed=state.get("demo_seed"),
        live_available=enabled(),
        as_of=str(AS_OF),
        business={"name": BUSINESS_NAME, "email": BUSINESS_EMAIL,
                  "source": "Received post; explicit original headers for outbound/forwarded mail"},
        synthetic=True,
        reader="Bounded local rules; no model call",
        provider="Simulated outbox; no real email",
        holds=holds(state),
        resolutions=state.get("resolutions", []),
        terms_history=state.get("terms_history", []),
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
    if state.get("provider_mode") == "live":
        from archon.web.live import public_job

        result.update(
            reader="Amazon Bedrock semantic extraction; source checks before posting",
            provider="Amazon SES; restricted verified test recipient",
            live={"model": True, "mail": True, "data": "fictional business examples",
                  "job": public_job(state.get("provider_job")),
                  "history": state.get("provider_history", [])},
            samples={k: v.replace("accounts@buildco.example", state["test_recipient"])
                     for k, v in SAMPLES.items()},
        )
        result["receipt_states"]["delivered"] = "Requires independent delivery evidence"
        result["receipt_states"]["failed"] = "Confirmed rejection; operator review before resend"
    return plain(result)
