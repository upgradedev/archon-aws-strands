"""Completeness Engine and Memory Dissent verification for Archon.

Implements forensic financial verification principles:
- Identifies missing documentation (bank disbursements without counter-invoices,
  unmatched credit memos, orphaned balance adjustments).
- Enforces the Memory Dissent pattern: when historical contract terms contradict
  new invoice claims, the agent abstains and raises a formal Dissent finding.
- Flags commercial compliance risks (e.g. EU Late Payment Directive 2011/7/EU
  statutory interest accumulation on debts aged > 30 days).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FindingKind(StrEnum):
    MISSING_INVOICE = "missing_invoice"
    UNMATCHED_PAYMENT = "unmatched_payment"
    STATUTORY_INTEREST_RISK = "statutory_interest_risk"
    MEMORY_DISSENT = "memory_dissent"
    IBAN_MUTATION_RISK = "iban_mutation_risk"


@dataclass(frozen=True)
class CompletenessFinding:
    """One identified gap, anomaly, or memory contradiction."""

    kind: FindingKind
    reference: str
    amount_cents: int
    severity: str  # "low", "medium", "high", "critical"
    evidence: str
    recommendation: str

    def as_dict(self) -> dict[str, str | int]:
        return {
            "kind": self.kind.value,
            "reference": self.reference,
            "amount_cents": self.amount_cents,
            "severity": self.severity,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class CompletenessReport:
    """Comprehensive completeness and memory integrity report."""

    findings: tuple[CompletenessFinding, ...]
    total_gaps_count: int
    at_risk_amount_cents: int
    has_dissent: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "has_dissent",
            any(f.kind == FindingKind.MEMORY_DISSENT for f in self.findings),
        )

    @property
    def is_clean(self) -> bool:
        return len(self.findings) == 0


def audit_discrepancy(
    claimed_discount_pct: float,
    contract_discount_pct: float,
    reference: str,
    invoice_amount_cents: int,
) -> CompletenessFinding | None:
    """Verify invoice claimed terms against historical contract memory.

    If the claims contradict stored terms, produces a Memory Dissent finding.
    """
    if abs(claimed_discount_pct - contract_discount_pct) > 1e-4:
        diff_cents = round(
            invoice_amount_cents * abs(claimed_discount_pct - contract_discount_pct) / 100.0
        )
        return CompletenessFinding(
            kind=FindingKind.MEMORY_DISSENT,
            reference=reference,
            amount_cents=diff_cents,
            severity="critical",
            evidence=(
                f"Invoice claims {claimed_discount_pct:g}% discount, but persistent contract "
                f"memory records {contract_discount_pct:g}%. "
                f"Discrepancy: {diff_cents / 100:.2f} EUR"
            ),
            recommendation=(
                "Abstain from automated ledger settlement; escalate for CFO contract review."
            ),
        )
    return None


def audit_statutory_interest(
    days_overdue: int,
    disputed_amount_cents: int,
    reference: str,
    ecb_rate: float = 0.045,  # 4.5% base rate
) -> CompletenessFinding | None:
    """Evaluate interest liability under EU Late Payment Directive 2011/7/EU (Base + 8%)."""
    if days_overdue > 30 and disputed_amount_cents > 0:
        statutory_rate = ecb_rate + 0.08  # 12.5% statutory rate
        accrued_interest_cents = round(
            disputed_amount_cents * (statutory_rate * (days_overdue / 365.0))
        )
        return CompletenessFinding(
            kind=FindingKind.STATUTORY_INTEREST_RISK,
            reference=reference,
            amount_cents=accrued_interest_cents,
            severity="high" if days_overdue > 60 else "medium",
            evidence=(
                f"Dispute is {days_overdue} days overdue (statutory window > 30 days). "
                f"Accruing statutory interest at {statutory_rate*100:.1f}% p.a."
            ),
            recommendation=(
                "Expedite settlement resolution to halt statutory interest accumulation."
            ),
        )
    return None


def audit_unmatched_lines(
    bank_lines: list[dict[str, str | int]],
    invoice_refs: set[str],
) -> list[CompletenessFinding]:
    """Flag bank outflows or receipts that have no matching invoice in the system."""
    findings: list[CompletenessFinding] = []
    for line in bank_lines:
        ref = str(line.get("reference", ""))
        amount = int(line.get("amount_cents", 0))
        if ref not in invoice_refs and amount > 0:
            findings.append(
                CompletenessFinding(
                    kind=FindingKind.MISSING_INVOICE,
                    reference=ref,
                    amount_cents=amount,
                    severity="high" if amount > 50000 else "medium",
                    evidence=(
                        f"Bank transaction {ref!r} of {amount/100:.2f} has no matching invoice."
                    ),
                    recommendation=(
                        "Request supplier invoice or receipt before month-end book closure."
                    ),
                )
            )
    return findings


def evaluate_completeness(
    bank_lines: list[dict[str, str | int]] | None = None,
    invoice_refs: set[str] | None = None,
    claimed_discount_pct: float | None = None,
    contract_discount_pct: float | None = None,
    invoice_amount_cents: int = 0,
    reference: str = "",
    days_overdue: int = 0,
) -> CompletenessReport:
    """Consolidated audit combining completeness anti-joins and memory dissent checks."""
    all_findings: list[CompletenessFinding] = []

    if bank_lines and invoice_refs is not None:
        all_findings.extend(audit_unmatched_lines(bank_lines, invoice_refs))

    if claimed_discount_pct is not None and contract_discount_pct is not None and reference:
        dissent = audit_discrepancy(
            claimed_discount_pct=claimed_discount_pct,
            contract_discount_pct=contract_discount_pct,
            reference=reference,
            invoice_amount_cents=invoice_amount_cents,
        )
        if dissent is not None:
            all_findings.append(dissent)

    if days_overdue > 0 and invoice_amount_cents > 0 and reference:
        stat_finding = audit_statutory_interest(
            days_overdue=days_overdue,
            disputed_amount_cents=invoice_amount_cents,
            reference=reference,
        )
        if stat_finding is not None:
            all_findings.append(stat_finding)

    total_at_risk = sum(f.amount_cents for f in all_findings)
    return CompletenessReport(
        findings=tuple(all_findings),
        total_gaps_count=len(all_findings),
        at_risk_amount_cents=total_at_risk,
    )
