"""The six questions the owner asked, answered off one ledger.

    1. what invoices have my suppliers sent me   -> purchases_owed / purchases_all
    2. which of them have I paid                 -> Settlement.is_paid
    3. what sales have I made                    -> sales_all
    4. which of those have I collected            -> Settlement.is_paid
    5. have I paid my staff                       -> payroll_unpaid
    6. P&L, cashflow, metrics                     -> archon.domain.reports

Every answer is derived, never stored twice. A stored "paid" flag and a ledger
that disagrees with it is the classic way books start lying, so the flag does
not exist: cash and credits are computed separately from their invoice references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .documents import (
    Payment,
    PayrollRun,
    PurchaseCreditNote,
    PurchaseInvoice,
    Receipt,
    SalesCreditNote,
    SalesInvoice,
    transfer_identity,
)
from .ledger import Ledger
from .money import ZERO, money


class SettlementError(ValueError):
    """Cash or a credit that cannot be applied to its referenced invoice."""


@dataclass(frozen=True, slots=True)
class Settlement:
    """Cash settled and credit granted against an invoice, kept distinct."""

    doc_id: str
    counterparty: str
    contact: str
    gross: Decimal
    settled: Decimal
    due: date
    credited: Decimal = ZERO

    @property
    def outstanding(self) -> Decimal:
        return money(self.gross - self.settled - self.credited)

    @property
    def is_paid(self) -> bool:
        """True only when cash covers the original invoice in full."""
        return self.settled >= self.gross

    @property
    def is_settled(self) -> bool:
        """Nothing remains due, whether cleared by cash, credit, or both."""
        return self.outstanding <= ZERO

    def is_overdue(self, as_of: date) -> bool:
        return not self.is_settled and self.due < as_of

    def days_overdue(self, as_of: date) -> int:
        return max(0, (as_of - self.due).days) if not self.is_settled else 0


@dataclass
class Books:
    """Every document received, and the ledger they produced."""

    ledger: Ledger = field(default_factory=Ledger)
    purchases: list[PurchaseInvoice] = field(default_factory=list)
    sales: list[SalesInvoice] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)
    receipts: list[Receipt] = field(default_factory=list)
    payroll: list[PayrollRun] = field(default_factory=list)
    #: Promises, keyed by invoice. Deliberately not documents: nothing in here
    #: has ever produced a journal entry, and nothing in here ever will. An
    #: arrangement changes when a chase fires, never what is owed.
    arrangements: dict = field(default_factory=dict)
    legacy_payment_holds: list[str] = field(default_factory=list)
    sales_credits: list[SalesCreditNote] = field(default_factory=list)
    purchase_credits: list[PurchaseCreditNote] = field(default_factory=list)

    # ---- taking documents in -------------------------------------------------

    def record(self, document: object, *, replay_legacy: bool = False) -> None:
        """Post a document and file it under the right domain.

        Unknown types are refused rather than ignored. A document that silently
        does nothing is worse than one that fails, because the books then look
        complete while missing it.

        **All or nothing.** A document producing two entries must post both or
        neither. Half a payroll run, booked but unpaid because the second entry
        raised, is a ledger that balances and lies, and every report above it
        would inherit the lie without any of them being wrong.
        """
        bucket = {
            PurchaseInvoice: self.purchases,
            SalesInvoice: self.sales,
            Payment: self.payments,
            Receipt: self.receipts,
            PayrollRun: self.payroll,
            SalesCreditNote: self.sales_credits,
            PurchaseCreditNote: self.purchase_credits,
        }.get(type(document))
        if bucket is None:
            raise TypeError(f"Archon has no posting rule for {type(document).__name__}")

        entry_count = len(self.ledger.entries)
        hold_count = len(self.legacy_payment_holds)
        try:
            self._check_credit(document)
            self._check_settles(document, replay_legacy=replay_legacy)
            entries = list(document.entries())  # type: ignore[attr-defined]
            for entry in entries:
                self.ledger.post(entry)
        except Exception:
            del self.ledger.entries[entry_count:]
            del self.legacy_payment_holds[hold_count:]
            raise
        bucket.append(document)  # type: ignore[arg-type]

    def _check_credit(self, document: object) -> None:
        """Bound each credit by original net/VAT and the balance after cash."""
        if isinstance(document, SalesCreditNote):
            invoices, credits = self.sales, self.sales_credits
            settlements = self.sales_settlements()
            noun = "sales invoice"
        elif isinstance(document, PurchaseCreditNote):
            invoices, credits = self.purchases, self.purchase_credits
            settlements = self.purchase_settlements()
            noun = "purchase invoice"
        else:
            return
        invoice = next((inv for inv in invoices if inv.doc_id == document.settles), None)
        if invoice is None:
            raise SettlementError(
                f"{document.doc_id} credits {document.settles}, which is not a {noun} "
                "in these books."
            )
        if document.issued < invoice.issued:
            raise SettlementError(
                f"{document.doc_id}: credit issue {document.issued} precedes "
                f"invoice issue {invoice.issued}"
            )
        previous = [credit for credit in credits if credit.settles == invoice.doc_id]
        for name in ("net", "vat"):
            credited = sum((getattr(credit, name) for credit in previous), ZERO)
            if credited + getattr(document, name) > getattr(invoice, name):
                raise SettlementError(
                    f"{document.doc_id}: cumulative {name} credit exceeds "
                    f"{invoice.doc_id}'s original {name} of {getattr(invoice, name)}"
                )
        outstanding = next(s.outstanding for s in settlements if s.doc_id == invoice.doc_id)
        if document.gross > outstanding:
            raise SettlementError(
                f"{document.doc_id} credits {document.gross} against {invoice.doc_id}, "
                f"which has only {outstanding} outstanding after cash and credits."
            )

    def _check_settles(self, document: object, *, replay_legacy: bool = False) -> None:
        """A payment must point at a real invoice and must not overpay it.

        Both failures are the quiet kind. A payment against a typo'd reference
        posts happily, moves the bank, and leaves the invoice open forever; the
        owner then chases a client who paid. An overpayment drives an invoice
        negative and the outstanding column reads as a credit nobody granted.
        """
        if isinstance(document, Payment):
            known = {inv.doc_id: inv.gross for inv in self.purchases}
            settled = self.purchase_settlements()
            noun = "purchase invoice"
        elif isinstance(document, Receipt):
            known = {inv.doc_id: inv.gross for inv in self.sales}
            settled = self.sales_settlements()
            noun = "sales invoice"
        else:
            return

        # A reference names a bank event across messages, invoices and directions.
        # Old/manual documents can lack one; repeated equal amounts then require
        # human evidence rather than an inference that two instalments are one.
        identity = transfer_identity(document.transfer_id)
        for previous in (*self.payments, *self.receipts):
            previous_identity = transfer_identity(previous.transfer_id)
            if identity and identity == previous_identity:
                raise SettlementError(
                    "This transfer identity is already recorded. Review the original payment; "
                    "a forwarded or corrected email cannot credit it again."
                )
            if (
                type(previous) is type(document)
                and previous.settles == document.settles
                and previous.amount == document.amount
                and (not identity or not previous_identity)
            ):
                if replay_legacy and not identity and not previous_identity:
                    self.legacy_payment_holds.append(document.doc_id)
                    continue
                raise SettlementError(
                    "Ambiguous payment identity: equal amounts may be distinct instalments. "
                    "A person must reconcile the bank references before another posting."
                )

        if document.settles not in known:
            raise SettlementError(
                f"{document.doc_id} settles {document.settles}, which is not a {noun} "
                "in these books. Archon does not post against a reference it cannot find."
            )
        outstanding = next(s.outstanding for s in settled if s.doc_id == document.settles)
        if document.amount > outstanding:
            raise SettlementError(
                f"{document.doc_id} is {document.amount} against {document.settles}, "
                f"which has only {outstanding} outstanding of {known[document.settles]}."
            )

    # ---- 1 and 2: suppliers --------------------------------------------------

    def purchase_settlements(self) -> list[Settlement]:
        paid: dict[str, Decimal] = {}
        for payment in self.payments:
            paid[payment.settles] = paid.get(payment.settles, ZERO) + payment.amount
        credited: dict[str, Decimal] = {}
        for credit in self.purchase_credits:
            credited[credit.settles] = credited.get(credit.settles, ZERO) + credit.gross
        return [
            Settlement(
                doc_id=inv.doc_id,
                counterparty=inv.supplier,
                contact="",
                gross=inv.gross,
                settled=money(paid.get(inv.doc_id, ZERO)),
                due=inv.due,
                credited=money(credited.get(inv.doc_id, ZERO)),
            )
            for inv in self.purchases
        ]

    def owed_to_suppliers(self) -> list[Settlement]:
        """Supplier invoices still open, soonest due first."""
        return sorted(
            (s for s in self.purchase_settlements() if not s.is_settled),
            key=lambda s: (s.due, -s.outstanding),
        )

    # ---- 3 and 4: clients ----------------------------------------------------

    def sales_settlements(self) -> list[Settlement]:
        received: dict[str, Decimal] = {}
        for receipt in self.receipts:
            received[receipt.settles] = received.get(receipt.settles, ZERO) + receipt.amount
        credited: dict[str, Decimal] = {}
        for credit in self.sales_credits:
            credited[credit.settles] = credited.get(credit.settles, ZERO) + credit.gross
        return [
            Settlement(
                doc_id=inv.doc_id,
                counterparty=inv.client,
                contact=inv.client_email,
                gross=inv.gross,
                settled=money(received.get(inv.doc_id, ZERO)),
                due=inv.due,
                credited=money(credited.get(inv.doc_id, ZERO)),
            )
            for inv in self.sales
        ]

    # ---- arrangements, which change when a chase fires and never what is owed --

    def agree(self, arrangement) -> None:
        """Record a promise. Deliberately not `record`, which posts.

        `Books.record` takes documents and writes journal entries. This takes a
        promise and writes nothing, and the two are separate methods so that
        nobody can reach an arrangement through the door that posts.
        """
        self.arrangements[arrangement.invoice_id] = arrangement

    def arrangement_for(self, invoice_id: str):
        return self.arrangements.get(invoice_id)

    def is_held_by_arrangement(self, settlement, as_of: date) -> bool:
        """True when a live promise says this debt is not chaseable today.

        A promise that has been kept so far holds the chase. A promise that has
        been broken does not, and the debt it was about is chaseable for its
        whole outstanding balance, because an arrangement never moved it.
        """
        arrangement = self.arrangements.get(settlement.doc_id)
        if arrangement is None:
            return False
        # Everything received against this invoice, ever. The arrangement
        # subtracts what had already arrived when it was agreed.
        received = settlement.settled
        if arrangement.is_broken(as_of, received):
            return False
        return not arrangement.is_finished(as_of)

    def uncollected(self) -> list[Settlement]:
        """Open sales invoices, oldest debt first. The hero journey starts here."""
        return sorted(
            (s for s in self.sales_settlements() if not s.is_settled),
            key=lambda s: (s.due, -s.outstanding),
        )

    def overdue(self, as_of: date) -> list[Settlement]:
        """Overdue and not held by a promise somebody is still keeping."""
        if self.legacy_payment_holds:
            return []
        return [
            s
            for s in self.uncollected()
            if s.is_overdue(as_of) and not self.is_held_by_arrangement(s, as_of)
        ]

    def worst_overdue(self, as_of: date) -> Settlement | None:
        """The single receivable the chase is written about.

        Oldest first, and the largest of the equally old, because age is what a
        client cannot argue with and size is what makes the email worth sending.
        """
        overdue = self.overdue(as_of)
        return overdue[0] if overdue else None

    # ---- 5: staff ------------------------------------------------------------

    def payroll_unpaid(self) -> list[PayrollRun]:
        return [run for run in self.payroll if not run.is_paid]

    def staff_are_paid(self) -> bool:
        return not self.payroll_unpaid()
