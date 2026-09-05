"""Attachments, which is how real invoices actually arrive.

The property under test is not "it reads PDFs". It is that reading one does not
quietly widen what leaves the machine: redaction cannot reach inside a file, so
the text is pulled out here and only the redacted text is sent.
"""

from __future__ import annotations

import pathlib

import pytest

from archon.adapters.inbound import (
    LocalReader,
    UnreadableAttachment,
    read_attachment,
    text_of_pdf,
)
from archon.domain.documents import PurchaseInvoice

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
INVOICE = (FIXTURES / "invoice.pdf").read_bytes()
SCAN = (FIXTURES / "scanned.pdf").read_bytes()


class RecordingReader(LocalReader):
    """The rule-based reader, but it keeps what it was shown."""

    def __init__(self) -> None:
        self.shown: list[str] = []

    def converse(self, **kwargs):
        self.shown.append(kwargs["messages"][0]["content"][0]["text"])
        return super().converse(**kwargs)


def test_an_attached_invoice_becomes_a_document():
    reading = read_attachment(INVOICE, "invoice.pdf", "email:pdf", client=LocalReader())
    assert isinstance(reading.document, PurchaseInvoice)
    assert reading.document.doc_id == "WA-7788"
    assert str(reading.document.gross) == "992.00"


def test_nothing_printed_on_the_pdf_reaches_the_model():
    """The whole reason the file is opened here rather than sent."""
    reader = RecordingReader()
    read_attachment(INVOICE, "invoice.pdf", "email:pdf", client=reader)
    sent = reader.shown[0]

    # Deliberately different from the sample email on the screen, so a hit here
    # can only have come from the PDF.
    assert "DE89 3704 0044 0532 0130 00" not in sent
    assert "DE811569869" not in sent
    assert "+49 30 9876543" not in sent
    assert "billing@printworks.example" not in sent


def test_the_commercial_content_of_the_pdf_does_reach_it():
    reader = RecordingReader()
    read_attachment(INVOICE, "invoice.pdf", "email:pdf", client=reader)
    sent = reader.shown[0]

    for kept in ("WA-7788", "2026-09-03", "2026-10-03", "800.00", "192.00", "992.00"):
        assert kept in sent, kept


def test_what_was_hidden_is_counted():
    reading = read_attachment(INVOICE, "invoice.pdf", "email:pdf", client=LocalReader())
    assert reading.redactions >= 4
    assert {"iban", "phone", "email", "tax_id"} <= set(reading.redacted_categories)


def test_a_scan_is_refused_rather_than_guessed_at():
    """Archon has no OCR, and four stray characters read as a document is worse."""
    with pytest.raises(UnreadableAttachment, match="no text layer"):
        read_attachment(SCAN, "scan.pdf", "email:scan", client=LocalReader())


def test_the_refusal_tells_the_person_what_to_do_instead():
    with pytest.raises(UnreadableAttachment) as caught:
        text_of_pdf(SCAN)
    assert "Forward the email body instead" in str(caught.value)


def test_a_file_that_is_not_a_pdf_at_all_is_refused():
    with pytest.raises(UnreadableAttachment, match="will not open"):
        read_attachment(b"this is not a pdf", "broken.pdf", "email:x", client=LocalReader())


def test_a_format_with_no_reader_is_refused_rather_than_guessed():
    with pytest.raises(UnreadableAttachment, match="reads PDFs and plain text"):
        read_attachment(b"\x00\x01", "invoice.docx", "email:x", client=LocalReader())


def test_plain_text_attachments_are_read():
    body = (
        b"From: accounts@supplier.example\n"
        b"Invoice TX-11 dated 2026-09-01, due 2026-10-01.\n"
        b"Net 100.00 EUR, VAT 24.00 EUR, total 124.00 EUR."
    )
    reading = read_attachment(body, "invoice.txt", "email:txt", client=LocalReader())
    assert reading.document.doc_id == "TX-11"


def test_the_pdf_text_is_extracted_locally_not_remotely():
    """Asserted on the imports: nothing in this path hands bytes to a client."""
    import ast
    import importlib.util

    spec = importlib.util.find_spec("archon.adapters.inbound")
    tree = ast.parse(pathlib.Path(spec.origin).read_text(encoding="utf-8"))
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "text_of_pdf"
    )
    calls = [
        node.func.attr
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "converse" not in calls, "the PDF path talks to a model before redacting"
