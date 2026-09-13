"""Bounded real Bedrock calls with durable admission and usage, never hidden fallback."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from threading import Lock

from archon.store.execution import digest
from archon.store.sessions import Conflict

MODEL_ID = "eu.anthropic.claude-opus-5"
COUNT_MODEL_ID = "anthropic.claude-opus-5"


class LiveRefused(RuntimeError):
    """The caller can display a refusal, not turn it into a scripted success."""


def amount(value):
    result = Decimal(str(value))
    if not result.is_finite() or result <= 0:
        raise LiveRefused("A finite positive pricing value is required.")
    return result


class Admission:
    """Operator-created finite grant. Reservations never refund uncertain costs.

    This bounds admitted model/mail cost under the operator's verified price
    ceilings, not the account's total AWS bill. Storage/network/Lambda costs are
    separate. A missing/expired/disabled grant refuses, never creates one.
    """

    def __init__(self, journal, clock=lambda: datetime.now(UTC)):
        self.journal, self.clock = journal, clock

    def grant(self):
        grant, version = self.journal.read("operating-grant")
        if not grant or grant.get("enabled") is not True:
            raise LiveRefused("Real providers are paused: no enabled operating grant.")
        expiry = datetime.fromisoformat(grant["expires_at"])
        if expiry.tzinfo is None or self.clock() >= expiry:
            raise LiveRefused("The real-provider operating grant expired.")
        if grant.get("model_id") != MODEL_ID or not grant.get("pricing_basis"):
            raise LiveRefused("The exact model and verified pricing basis are required.")
        return grant, version

    def reserve(self, call_id, *, input_tokens=0, output_tokens=0, mail=False):
        # Two workers can each fan out six readers. A five-conflict ceiling can
        # refuse a healthy sixth reader; keep admission bounded above that fanout.
        for _ in range(20):
            grant, version = self.grant()
            entries = grant.get("reservations", {})
            if call_id in entries:
                raise LiveRefused("This provider attempt is already reserved; no replay.")
            if len(entries) >= min(int(grant["max_calls"]), 1000):
                raise LiveRefused("The global provider-call limit is exhausted.")
            if mail:
                if sum(r["kind"] == "mail" for r in entries.values()) >= int(grant["max_mail"]):
                    raise LiveRefused("The global email limit is exhausted.")
                cost = amount(grant["mail_usd_ceiling"])
            else:
                if not 0 < input_tokens <= int(grant["max_input_tokens"]):
                    raise LiveRefused("The exact provider token count exceeds the input limit.")
                if not 0 < output_tokens <= int(grant["max_output_tokens"]):
                    raise LiveRefused("The output ceiling exceeds the operating limit.")
                cost = (input_tokens * amount(grant["input_usd_per_million_ceiling"]) +
                        output_tokens * amount(grant["output_usd_per_million_ceiling"])) / 1000000
            cost = cost.quantize(Decimal("0.000001"), rounding=ROUND_CEILING)
            total = Decimal(str(grant.get("reserved_usd", "0"))) + cost
            if total > amount(grant["budget_usd"]):
                raise LiveRefused("The finite real-provider budget is exhausted.")
            grant["reserved_usd"] = str(total)
            entries[call_id] = {"kind": "mail" if mail else "model", "usd": str(cost)}
            grant["reservations"] = entries
            try:
                self.journal.update("operating-grant", grant, version)
                return str(cost)
            except Conflict:
                continue
        raise LiveRefused("Budget contention: no provider call was admitted.")

    def pause(self, reason):
        """Keep spent reservations, but stop admission after a provider contract violation."""
        for _ in range(20):
            grant, version = self.journal.read("operating-grant")
            if not grant:
                return
            grant.update(enabled=False, pause_reason=reason)
            try:
                self.journal.update("operating-grant", grant, version)
                return
            except Conflict:
                continue
        raise LiveRefused("Could not persist the provider stop; operator intervention required.")


class MeteredConverse:
    """The only inference entry point for intake AND every Strands tool turn."""

    def __init__(self, client, admission, journal, job_id, max_calls=20):
        self.client, self.admission, self.journal = client, admission, journal
        self.meta = client.meta
        self.job_id, self.max_calls, self.calls = job_id, max_calls, 0
        self.lock = Lock()

    def converse(self, **request):
        # A graph can fan out across threads; call identifiers must remain unique.
        with self.lock:
            if self.calls >= self.max_calls:
                raise LiveRefused("This job reached its model-call limit.")
            self.calls += 1
            call_id = f"{self.job_id}:{self.calls}"
        if request.get("modelId") != MODEL_ID:
            raise LiveRefused("This deployment permits only the configured EU model.")
        allowed = {"modelId", "messages", "system", "toolConfig", "inferenceConfig"}
        if set(request) - allowed:
            raise LiveRefused("Unpriced or unsupported provider request fields are refused.")
        raw = json.dumps(request, sort_keys=True, ensure_ascii=False).encode()
        if len(raw) > 128000:
            raise LiveRefused("The provider request exceeds the bounded text context.")
        output_limit = request.get("inferenceConfig", {}).get("maxTokens", 0)
        # Count the complete request, including tool schemas. Unsupported model
        # counting fails closed; do not invent a chars-to-token budget guarantee.
        count_input = {k: request[k] for k in ("messages", "system", "toolConfig") if k in request}
        self.admission.grant()
        try:
            counted = self.client.count_tokens(
                modelId=COUNT_MODEL_ID, input={"converse": count_input}
            )["inputTokens"]
        except Exception as exc:
            raise LiveRefused(
                "Token preflight is unavailable for this model. No inference was started. "
                "The operator must verify a compatible token-count adapter before activation."
            ) from exc
        if type(counted) is not int or type(output_limit) is not int:
            raise LiveRefused("The provider must return an exact integer input token count.")
        reserved = self.admission.reserve(
            call_id, input_tokens=counted, output_tokens=output_limit
        )
        key = "call:" + call_id
        row = {
            "job_id": self.job_id, "call_id": call_id, "status": "pending",
            "model_id": MODEL_ID, "request_hash": digest(request),
            "input_tokens_counted": counted, "output_tokens_limit": output_limit,
            "reserved_usd": reserved, "started_at": datetime.now(UTC).isoformat(),
            "revision": 0,
        }
        if not self.journal.create(key, row):
            raise LiveRefused("A durable attempt already exists; do not call again.")
        # Fetch its version before invoking, never after a potentially ambiguous send.
        saved, version = self.journal.read(key)
        try:
            response = self.client.converse(**request)
            usage = response.get("usage", {})
            saved.update(response=response, usage=usage)
            if not isinstance(usage, dict) or not all(
                type(usage.get(k)) is int and usage[k] >= 0
                for k in ("inputTokens", "outputTokens")
            ):
                self.admission.pause("Provider returned unusable usage evidence")
                raise LiveRefused("The model response has no usable token-usage evidence.")
            if usage["inputTokens"] > counted or usage["outputTokens"] > output_limit:
                self.admission.pause("Provider usage exceeded its reserved admission")
                raise LiveRefused("Provider usage exceeded admission; operator review required.")
            saved.update(status="completed", response=response, usage=usage,
                         finished_at=datetime.now(UTC).isoformat())
            self.journal.update(key, saved, version)
            return response
        except Exception as exc:
            # No refund and no provider retry on lost acknowledgment. Preserve class,
            # not raw SDK text which can include private input or resource details.
            saved.update(status="unknown", error=type(exc).__name__,
                         finished_at=datetime.now(UTC).isoformat())
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if isinstance(code, str) and code.replace("-", "").replace("_", "").isalnum():
                saved["provider_error_code"] = code[:80]
            self.journal.update(key, saved, version)
            raise LiveRefused(
                "Model execution failed or is uncertain. No automatic retry."
            ) from exc


def model_for(client):
    """Use the real SDK, non-streaming so every call has durable admission."""
    from strands.models import BedrockModel

    class Session:
        region_name = "eu-west-1"

        def client(self, **kwargs):
            return client

    return BedrockModel(
        boto_session=Session(), model_id=MODEL_ID, max_tokens=2048, streaming=False
    )
