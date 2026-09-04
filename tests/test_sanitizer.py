"""Tests for pre-LLM PII and sensitive financial data sanitizer."""

from archon.security.sanitizer import SanitizedDocument, sanitize_payload, sanitize_text


def test_sanitize_empty_string():
    text, count, categories = sanitize_text("")
    assert text == ""
    assert count == 0
    assert categories == []


def test_sanitize_clean_invoice_untouched():
    invoice = """
    INVOICE #INV-2026-8891
    Date: 2026-09-04
    Item: Cloud Hosting Services
    Quantity: 10
    Unit Price: 150.00 EUR
    Total: 1500.00 EUR
    Payment Terms: Net 30 Days
    """
    text, count, categories = sanitize_text(invoice)
    assert count == 0
    assert text == invoice
    assert categories == []


def test_sanitize_iban_masking():
    raw = "Please wire funds to IBAN: GR1601101250000000012345678 at Alpha Bank."
    text, count, categories = sanitize_text(raw)
    assert count == 1
    assert "iban" in categories
    assert "GR16*******************5678" in text
    assert "GR1601101250000000012345678" not in text

    # Edge case: short body (<= 4 chars)
    short_raw = "Short IBAN: FR14ABCD"
    short_text, _, _ = sanitize_text(short_raw)
    assert "FR14****" in short_text


def test_sanitize_email_redaction():
    raw = "Direct inquiries to billing-dept@supplier-corp.com or support@subcontractor.eu."
    text, count, categories = sanitize_text(raw)
    assert count == 2
    assert "email" in categories
    assert "billing-dept@supplier-corp.com" not in text
    assert "support@subcontractor.eu" not in text
    assert "[REDACTED_EMAIL]" in text


def test_sanitize_payment_card():
    raw = "Card on file: 4532-1234-5678-9012 for monthly debit."
    text, count, categories = sanitize_text(raw)
    assert count == 1
    assert "payment_card" in categories
    assert "4532-1234-5678-9012" not in text
    assert "[REDACTED_PAYMENT_CARD]" in text


def test_sanitize_tax_id():
    raw = "Supplier VAT: EL123456789, Customer AFM: 094123456."
    text, count, categories = sanitize_text(raw)
    assert count >= 1
    assert "tax_id" in categories
    assert "[REDACTED_TAX_ID]" in text


def test_sanitize_swift_bic():
    raw = "Remittance routing: SWIFT: ETHNGR2A via correspondent."
    text, count, categories = sanitize_text(raw)
    assert count == 1
    assert "swift_bic" in categories
    assert "[REDACTED_BIC]" in text


def test_sanitize_payload_wrapper():
    content = "Contact accounts-receivable@corp.com regarding GR1601101250000000012345678."
    doc = sanitize_payload(content)
    assert isinstance(doc, SanitizedDocument)
    assert doc.is_modified is True
    assert doc.redactions_count == 2
    assert "email" in doc.redacted_categories
    assert "iban" in doc.redacted_categories
    assert doc.original_length == len(content)
    assert "GR16*******************5678" in doc.sanitized_text
