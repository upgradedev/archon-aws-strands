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


#: Exception types that mean the request reached SES and SES refused it. Only
#: these are safe to call a failure, because only these prove nothing was sent.
#: Everything else — a timeout, a dropped connection, a process killed mid-call —
#: is ambiguous, and ambiguous means unknown.
CONFIRMED_REJECTIONS = (
    "ParamValidationError",
    "MessageRejected",
    "AccountSendingPausedException",
    "MailFromDomainNotVerifiedException",
    "AccountSuspendedException",
    "SendingPausedException",
)

#: botocore raises `ClientError` for everything the API answers with, including
#: a 500 and a throttle. A 5xx reached SES and says nothing about whether it
#: sent, so the class alone cannot decide this: the error code inside it can.
CONFIRMED_REJECTION_CODES = frozenset(
    {
        "MessageRejected",
        "MailFromDomainNotVerified",
        "AccountSendingPaused",
        "AccountSuspended",
        "InvalidParameterValue",
        "ValidationException",
        "AccessDeniedException",
    }
)


def _is_confirmed_rejection(failure: BaseException) -> bool:
    """Did the provider answer and say no, in a way that proves nothing was sent?

    Conservative on purpose: anything not positively recognised is treated as
    unknown. Getting this backwards sends a second email, and the whole point of
    the distinction is that one direction is recoverable and the other is not.

    `ClientError` used to be on the recognised list, which was wrong. botocore
    raises it for everything the API answers with, a 500 and a throttle
    included, and a 5xx reached SES and tells us nothing about whether it sent.
    The error code inside it is what decides.
    """
    names = {type(failure).__name__} | {c.__name__ for c in type(failure).__mro__}
    if names & set(CONFIRMED_REJECTIONS):
        return True

    response = getattr(failure, "response", None)
    if isinstance(response, dict):
        code = str(response.get("Error", {}).get("Code", ""))
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if isinstance(status, int) and status >= 500:
            return False
        return code in CONFIRMED_REJECTION_CODES
    return False


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
    controlled_recipient: str | None = None

    def send(self, draft: ChaseDraft, release: Release) -> Receipt:
        if self.controlled_recipient and draft.to_address != self.controlled_recipient:
            raise SendRefused("Live sending is restricted to the operator's verified recipient.")
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
                    "an attempt to send this exact text is recorded as "
                    f"{written.state!r}, which means nobody knows whether it went. "
                    "The connection may have timed out after SES accepted it, or "
                    "the process may have stopped between the call and the reply. "
                    "It is not sent again automatically, because a second demand "
                    "for money cannot be recalled. Check the mailbox, then clear "
                    "the record deliberately."
                )
            # Exactly one caller may proceed. Two tabs, two workers or a
            # double-click all reach this line; only the one that wins the
            # insert sends.
            if not self.log.reserve(_record_for(draft, at=self.clock())):
                raise SendRefused(
                    "another caller is already sending this exact text. Only one "
                    "of them may, and it is not this one."
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
                from archon.store.sqlite import FAILED, UNKNOWN

                confirmed = _is_confirmed_rejection(failure)
                self.log.settle(
                    fingerprint,
                    message_id=None,
                    error=f"{type(failure).__name__}: {failure}",
                    state=FAILED if confirmed else UNKNOWN,
                )
                if not confirmed:
                    raise SendRefused(
                        "the send did not come back with an answer, so nobody "
                        f"knows whether it went: {type(failure).__name__}: {failure}. "
                        "It is recorded as unknown and will not be tried again on "
                        "its own. If it did go, retrying sends a second demand for "
                        "money; if it did not, a person can clear the record."
                    ) from failure
            raise

        message_id = (response or {}).get("MessageId")
        if not message_id:
            if self.log is not None:
                from archon.store.sqlite import UNKNOWN

                # Not a failure. SES answering without an identifier does not
                # prove it did not accept the message, and recording it as a
                # rejection would make it retryable — the same mistake as
                # treating a timeout as failure, one layer along.
                self.log.settle(
                    fingerprint,
                    message_id=None,
                    error="SES returned no MessageId",
                    state=UNKNOWN,
                )
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


def live_outbox(
    sender: str, region: str = "eu-west-1", *, log=None,
    controlled_recipient: str | None = None, authorized: bool = False,
) -> Outbox:
    """A real SES sender, with the client's own retries turned off.

    This matters more than it looks. Everything above here works to make one
    approved draft into exactly one email: the fingerprint, the durable record,
    the atomic reservation. botocore's default is to retry a failed call several
    times on its own, underneath all of it, so a timeout that this code would
    record once as unknown could already have put three messages in somebody's
    inbox.

    Retries are a decision about a demand for money and they belong here, where
    the record is, not in a transport default nobody set.

    The region is Europe for the same reason the model's is: the recipient is a
    European client and the message carries their name and what they owe.
    """
    import boto3
    from botocore.config import Config

    if not authorized or log is None or not controlled_recipient:
        raise SendRefused(
            "Live send needs explicit operator authorization, a durable send ledger, "
            "and a controlled verified recipient. The public API cannot enable this."
        )

    return Outbox(
        client=boto3.client(
            "sesv2",
            region_name=region,
            config=Config(retries={"total_max_attempts": 1, "mode": "standard"}),
        ),
        sender=sender,
        log=log,
        controlled_recipient=controlled_recipient,
    )
