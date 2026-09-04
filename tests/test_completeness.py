"""Unit tests for Archon Completeness Engine and Memory Dissent verification."""

from archon.domain.completeness import (
    CompletenessReport,
    FindingKind,
    audit_discrepancy,
    audit_statutory_interest,
    audit_unmatched_lines,
    evaluate_completeness,
)


def test_evaluate_clean_report():
    report = evaluate_completeness()
    assert isinstance(report, CompletenessReport)
    assert report.is_clean is True
    assert report.total_gaps_count == 0
    assert report.at_risk_amount_cents == 0
    assert report.has_dissent is False


def test_audit_unmatched_bank_lines():
    bank_lines = [
        {"reference": "WIRE-2026-001", "amount_cents": 150000},
        {"reference": "WIRE-2026-002", "amount_cents": 25000},
    ]
    invoice_refs = {"WIRE-2026-001"}  # WIRE-2026-002 is missing an invoice

    findings = audit_unmatched_lines(bank_lines, invoice_refs)
    assert len(findings) == 1
    assert findings[0].kind == FindingKind.MISSING_INVOICE
    assert findings[0].reference == "WIRE-2026-002"
    assert findings[0].amount_cents == 25000
    assert findings[0].severity == "medium"
    assert "no matching invoice" in findings[0].evidence


def test_audit_unmatched_high_amount_severity():
    bank_lines = [{"reference": "WIRE-BIG", "amount_cents": 800000}]
    findings = audit_unmatched_lines(bank_lines, set())
    assert len(findings) == 1
    assert findings[0].severity == "high"


def test_audit_discrepancy_memory_dissent():
    # Vendor claims 20% discount, but contract on file says 10%
    dissent = audit_discrepancy(
        claimed_discount_pct=20.0,
        contract_discount_pct=10.0,
        reference="INV-DISPUTE-99",
        invoice_amount_cents=100000,
    )
    assert dissent is not None
    assert dissent.kind == FindingKind.MEMORY_DISSENT
    assert dissent.severity == "critical"
    assert dissent.amount_cents == 10000  # 10% of 100000
    assert "persistent contract memory records 10%" in dissent.evidence
    d_dict = dissent.as_dict()
    assert d_dict["kind"] == "memory_dissent"


def test_audit_discrepancy_matches():
    dissent = audit_discrepancy(
        claimed_discount_pct=15.0,
        contract_discount_pct=15.0,
        reference="INV-OK",
        invoice_amount_cents=50000,
    )
    assert dissent is None


def test_audit_statutory_interest_overdue():
    # 45 days overdue -> medium severity
    finding = audit_statutory_interest(
        days_overdue=45,
        disputed_amount_cents=1000000,  # 10,000 EUR
        reference="INV-LATE-45",
    )
    assert finding is not None
    assert finding.kind == FindingKind.STATUTORY_INTEREST_RISK
    assert finding.severity == "medium"
    assert finding.amount_cents > 0

    # 75 days overdue -> high severity
    finding_high = audit_statutory_interest(
        days_overdue=75,
        disputed_amount_cents=1000000,
        reference="INV-LATE-75",
    )
    assert finding_high is not None
    assert finding_high.severity == "high"


def test_audit_statutory_interest_within_terms():
    finding = audit_statutory_interest(
        days_overdue=20,
        disputed_amount_cents=1000000,
        reference="INV-ON-TIME",
    )
    assert finding is None


def test_consolidated_completeness_report():
    bank_lines = [{"reference": "TX-01", "amount_cents": 50000}]
    report = evaluate_completeness(
        bank_lines=bank_lines,
        invoice_refs=set(),
        claimed_discount_pct=25.0,
        contract_discount_pct=10.0,
        invoice_amount_cents=200000,
        reference="INV-MULTI-01",
        days_overdue=40,
    )
    assert report.is_clean is False
    assert report.total_gaps_count == 3  # unmatched + dissent + statutory interest
    assert report.has_dissent is True
    assert report.at_risk_amount_cents > 50000
