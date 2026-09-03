"""The email that may leave, and the rule that keeps it honest.

One structural rule does most of the work here: **no digit reaches a client
except through a verified claim.** The agent writes the opening and the closing,
which is where tone and judgment belong, and those two fields are refused if
they contain a number. Every figure in the body is rendered by the claim that
proved it.

This is cheaper and stricter than checking prose afterwards. A checker reading
"you owe us about two grand" has to interpret; a constructor that refuses digits
in free text does not have to interpret anything.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date

from .claims import Claim

_DIGIT = re.compile(r"\d")


class UnsafeDraft(ValueError):
    """A draft that states something outside a verified claim."""


@dataclass(frozen=True, slots=True)
class ChaseDraft:
    """A collection chase, assembled from claims the books confirmed."""

    invoice_id: str
    client: str
    to_address: str
    subject: str
    opening: str
    claims: tuple[Claim, ...]
    closing: str
    as_of: date

    def __post_init__(self) -> None:
        if not self.claims:
            raise UnsafeDraft("a chase that states no verified fact is not a chase")
        for field_name in ("subject", "opening", "closing"):
            text = getattr(self, field_name)
            if not text.strip():
                raise UnsafeDraft(f"{field_name} is empty")
            if _DIGIT.search(text):
                raise UnsafeDraft(
                    f"{field_name} contains a digit. Numbers reach a client only through a "
                    "claim the ledger has confirmed, never through free text."
                )
        if "@" not in self.to_address:
            raise UnsafeDraft(f"not an address: {self.to_address!r}")

    def body(self) -> str:
        """The exact text that will be sent."""
        lines = [self.opening.strip(), ""]
        lines.extend(claim.sentence() for claim in self.claims)
        lines.extend(["", self.closing.strip()])
        return "\n".join(lines)

    def wire(self) -> str:
        """Everything that goes out, as one canonical string."""
        return f"To: {self.to_address}\nSubject: {self.subject.strip()}\n\n{self.body()}\n"

    def fingerprint(self) -> str:
        """SHA-256 of the exact bytes that will be sent.

        Approval binds to this, so a byte of drift between what a human read and
        what would be sent invalidates the approval rather than sliding past it.
        """
        return hashlib.sha256(self.wire().encode("utf-8")).hexdigest()
