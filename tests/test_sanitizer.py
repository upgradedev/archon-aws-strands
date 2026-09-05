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


# --- regressions, all five found by wiring the filter to a real email ---------


REAL_EMAIL = (
    "Our bank details: IBAN GR16 0110 1250 0000 0001 2300 695, VAT EL123456789.\n"
    "Any queries call +30 210 1234567 or email billing@wholesaler.example.\n"
    "Invoice WA-5512 dated 2026-09-01, net 1,000.00 EUR, VAT 240.00, total 1,240.00 EUR."
)


def test_an_iban_printed_in_groups_of_four_is_masked():
    """The contiguous-only pattern matched no real IBAN, because none are printed that way."""
    text, _, categories = sanitize_text(REAL_EMAIL)
    assert "iban" in categories
    assert "0110 1250" not in text
    assert "2300 695" not in text
    assert "GR16*******************0695" in text


def test_the_card_rule_no_longer_eats_the_middle_of_an_iban():
    """It ran first and left `GR16 [REDACTED_PAYMENT_CARD] 2300 695`, tail exposed."""
    text, _, _ = sanitize_text(REAL_EMAIL)
    assert "[REDACTED_PAYMENT_CARD]" not in text


def test_a_vat_number_is_redacted_not_weakly_masked():
    """The IBAN rule used to match it and leave eight of eleven characters."""
    text, _, categories = sanitize_text(REAL_EMAIL)
    assert "tax_id" in categories
    assert "EL123456789" not in text
    assert "EL12***6789" not in text
    assert "[REDACTED_TAX_ID]" in text


def test_the_phone_rule_is_actually_applied():
    """It was defined and never called, so every phone number went to the model."""
    text, _, categories = sanitize_text(REAL_EMAIL)
    assert "phone" in categories
    assert "+30 210 1234567" not in text
    assert "[REDACTED_PHONE]" in text


def test_redaction_leaves_the_commerce_alone():
    """Redacting the figures would be a worse failure than sending a phone number."""
    text, _, _ = sanitize_text(REAL_EMAIL)
    for kept in ("WA-5512", "2026-09-01", "1,000.00", "240.00", "1,240.00"):
        assert kept in text, kept


def test_an_iban_does_not_run_into_the_following_sentence():
    text, _, _ = sanitize_text("IBAN GR16 0110 1250 0000 0001 2300 695 at Alpha Bank.")
    assert "at Alpha Bank." in text


def test_a_category_is_listed_once_however_many_rules_hit_it():
    _, _, categories = sanitize_text("VAT EL123456789 and TAX ID: DE999888777")
    assert categories.count("tax_id") == 1
