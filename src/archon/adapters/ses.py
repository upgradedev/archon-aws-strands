"""The one write: an email that actually leaves.

Three things this module refuses to do, and each is a way the send goes wrong
after everything upstream went right.

**It will not send what the gate did not release.** The gate has already decided;
checking again here costs nothing and means the refusal cannot be bypassed by
calling the sender directly, which is the shape a later caller is most likely to
reach for.

**It will not send the same email twice.** A retry, a double-clicked approval, a
Lambda redelivery: all of them arrive as the same fingerprint, and a client who
receives the same demand for money twice in a minute is a client who calls. The
first send's receipt is returned instead, so a caller cannot tell the difference
and does not need to.

**It will not claim a send it cannot evidence.** A receipt carries the provider's
own message id, and a send that returns no id raises rather than reporting
success, because "sent" with nothing to read back is the claim this whole project
exists to refuse.

On the sandbox: this account has `ProductionAccessEnabled: false`, measured
2026-09-04, so mail may go only to verified addresses at 200 a day. That is
enough for the demo by design, because the chase goes to an inbox we own and
show on screen rather than to the reader's own address.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from archon.agents.draft import ChaseDraft
from archon.agents.gate import Release


class SendRefused(RuntimeError):
    """A send that must not happen, or one that cannot be evidenced."""


@dataclass(frozen=True, slots=True)
class Receipt:
    """Evidence that one exact email left, and which one."""

    message_id: str
    fingerprint: str
    to_address: str
    sent_at: datetime
    replayed: bool = False

    def replay(self) -> Receipt:
        return Receipt(
            message_id=self.message_id,
            fingerprint=self.fingerprint,
            to_address=self.to_address,
            sent_at=self.sent_at,
            replayed=True,
        )


class SesClient(Protocol):
    """The slice of `boto3.client("sesv2")` this module uses."""

    def send_email(self, **kwargs: Any) -> dict[str, Any]: ...


def _record_for(draft: ChaseDraft, at):
    """The row written before a send, naming the whole external act.

    Recipient, invoice and amount travel with the fingerprint so that the record
    is readable on its own. A row saying only that some bytes were sent is not an
    audit trail anybody can use.
    """
    from archon.store.sqlite import REQUESTED, SendRecord

    outstanding = next(
        (str(c.amount) for c in draft.claims if hasattr(c, "amount")),
        "",
    )
    return SendRecord(
        fingerprint=draft.fingerprint(),
        state=REQUESTED,
        to_address=draft.to_address,
        invoice_id=draft.invoice_id,
        amount=outstanding,
        at=at().isoformat(timespec="seconds") if callable(at) else str(at),
    )


@dataclass
class Outbox:
    """Sends, and remembers exactly what it sent.

    The memory is deliberately part of the sender rather than a concern of the
    caller. An idempotency key a caller has to remember to pass is an idempotency
    key that gets forgotten on the path that matters.
    """

    client: SesClient
    sender: str
    clock: Any = datetime.now
    sent: dict[str, Receipt] = field(default_factory=dict)
    #: Where the record survives a restart. Without one this outbox forgets
    #: everything when the process ends, which was measured to send a second
    #: email to a client for one approved draft.
    log: Any = None

    def send(self, draft: ChaseDraft, release: Release) -> Receipt:
        if not release.allowed:
            raise SendRefused(
                "the gate held this draft and the sender does not overrule it: "
                + "; ".join(release.reasons)
            )

        fingerprint = draft.fingerprint()
        already = self.sent.get(fingerprint)
        if already is not None:
            return already.replay()

        # The durable record, consulted before anything leaves. In memory this
        # outbox is authoritative only for the life of one process, and a client
        # does not care which process was running when they were asked twice.
        if self.log is not None:
            written = self.log.find(fingerprint)
            if written is not None and written.reached_the_provider:
                receipt = Receipt(
                    message_id=written.message_id,
                    fingerprint=fingerprint,
                    to_address=written.to_address,
                    sent_at=self.clock(),
                )
                self.sent[fingerprint] = receipt
                return receipt.replay()
            if written is not None and written.in_flight:
                raise SendRefused(
                    "an attempt to send this exact text was written down and never "
                    "settled, which means the process stopped between calling SES "
                    "and hearing back. It may already have gone. Nothing is sent "
                    "again automatically: check the mailbox, then clear the record."
                )
            self.log.requested(
                _record_for(draft, at=self.clock()),
            )

        try:
            response = self.client.send_email(
                FromEmailAddress=self.sender,
                Destination={"ToAddresses": [draft.to_address]},
                Content={
                    "Simple": {
                        "Subject": {"Data": draft.subject.strip(), "Charset": "UTF-8"},
                        "Body": {"Text": {"Data": draft.body(), "Charset": "UTF-8"}},
                    }
                },
            )
        except Exception as failure:
            if self.log is not None:
                self.log.settle(fingerprint, message_id=None, error=str(failure))
            raise

        message_id = (response or {}).get("MessageId")
        if not message_id:
            if self.log is not None:
                self.log.settle(fingerprint, message_id=None, error="SES returned no MessageId")
            raise SendRefused(
                "SES returned no MessageId, so this send cannot be evidenced. "
                "Reporting it as sent would be a claim with nothing to read back."
            )

        receipt = Receipt(
            message_id=message_id,
            fingerprint=fingerprint,
            to_address=draft.to_address,
            sent_at=self.clock(),
        )
        if self.log is not None:
            self.log.settle(fingerprint, message_id=message_id, error=None)
        self.sent[fingerprint] = receipt
        return receipt

    def receipt_for(self, draft: ChaseDraft) -> Receipt | None:
        """Read back what was sent for this exact text, if anything was."""
        return self.sent.get(draft.fingerprint())


def live_outbox(sender: str, region: str = "us-west-2") -> Outbox:
    """An Outbox wired to the real SES. Imported lazily; see adapters.bedrock."""
    import boto3

    return Outbox(client=boto3.client("sesv2", region_name=region), sender=sender)
