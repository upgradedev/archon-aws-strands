"""Asynchronous real-provider workspace jobs; no external effects in the API process."""
from __future__ import annotations

import copy
import json
import os
import secrets
from datetime import UTC, datetime

from archon.adapters.grounded_post import SourceFields, validate_reading
from archon.adapters.metered import Admission, LiveRefused, MeteredConverse, model_for
from archon.adapters.ses import live_outbox
from archon.adapters.token_counter import CountingRuntime
from archon.agents.draft import UnsafeDraft
from archon.store.execution import DurableSendLog, Journal
from archon.store.sessions import Conflict, S3Sessions, configured_store
from archon.web import workspace

OPERATIONS = frozenset({"intake", "reason", "approve"})


def enabled():
    return os.environ.get("ARCHON_LIVE_ENABLED") == "true"


def configuration():
    if not enabled():
        raise LiveRefused("Real providers are not enabled in this deployment.")
    values = {name: os.environ.get("ARCHON_LIVE_" + name.upper(), "") for name in
              ("worker_arn", "sender", "recipient")}
    if not all(values.values()) or any("\n" in value or "\r" in value for value in values.values()):
        raise LiveRefused("The operator's live-provider configuration is incomplete.")
    return values


def enqueue(handle, job_id):
    import boto3
    from botocore.config import Config

    config = configuration()
    client = boto3.client("lambda", config=Config(retries={"total_max_attempts": 1}))
    response = client.invoke(
        FunctionName=config["worker_arn"], InvocationType="Event",
        Payload=json.dumps({"session": handle, "job_id": job_id}).encode(),
    )
    if response.get("StatusCode") != 202:
        raise LiveRefused("The durable job exists but worker scheduling is unconfirmed.")


def submit(store, handle, state, version, operation, payload, request_id, revision, dispatch=None):
    dispatch = dispatch or enqueue
    config = configuration()
    if operation not in OPERATIONS or state.get("provider_mode") != "live":
        raise LiveRefused("This session does not support that live operation.")
    if operation == "approve" and payload.get("live_send_consent") != "real-email":
        raise ValueError(
            "Explicit real-email consent is required. Refresh and review the live draft."
        )
    signature = workspace.digest({"operation": operation, "payload": payload})
    previous = state["requests"].get(request_id)
    if previous:
        if previous != signature:
            raise Conflict("This request identifier was already used for different content.")
        job = state.get("provider_job")
        if job and job["request_id"] == request_id and job["status"] == "queued":
            dispatch(handle, job["id"])
        return workspace.snapshot(state)
    job = state.get("provider_job")
    if job and job["status"] in {"queued", "running"}:
        raise Conflict("A durable provider job is pending. Refresh; do not start another action.")
    if revision != state["revision"]:
        raise Conflict("Books changed in another tab. Refresh and review again.")
    if state.get("provider_job_count", 0) >= 20:
        raise LiveRefused("This session reached its twenty-job limit.")
    if operation == "approve":
        draft = workspace.draft_for(state)
        if not draft or draft.fingerprint() != payload["fingerprint"]:
            raise Conflict("The exact draft must be reviewed again.")
        if draft.to_address != config["recipient"]:
            raise LiveRefused("Sending is limited to the operator's verified test recipient.")
    state["provider_job_count"] = state.get("provider_job_count", 0) + 1
    state["provider_job"] = {
        "id": secrets.token_hex(32), "operation": operation, "payload": payload,
        "request_id": request_id, "status": "queued", "created_at": workspace.now(),
        "sender": config["sender"], "recipient": config["recipient"],
    }
    state["requests"][request_id] = signature
    state["revision"] += 1
    store.put(handle, state, version)  # The durable pending record precedes invocation.
    dispatch(handle, state["provider_job"]["id"])
    return workspace.snapshot(state)


def run(store, journal, handle, job_id, *, client_factory=None, outbox_factory=live_outbox):
    config = configuration()
    state, version = store.get(handle)
    job = state.get("provider_job")
    if not job or job["id"] != job_id or job["status"] != "queued":
        return  # Includes Lambda retries after a process died in the running state.
    if state.get("provider_mode") != "live":
        raise LiveRefused("A synthetic session can never invoke a live provider.")
    if any(job[name] != config[name] for name in ("sender", "recipient")):
        raise LiveRefused("The operator identity changed; the old job cannot execute.")
    job.update(status="running", started_at=workspace.now())
    state["revision"] += 1
    try:
        store.put(handle, state, version)
    except Conflict:
        return  # Exactly one worker can win.
    state, version = store.get(handle)
    original = copy.deepcopy(state)
    job = state["provider_job"]
    admission = Admission(journal)
    log = DurableSendLog(journal)
    try:
        admission.grant()
        if job["operation"] == "approve":
            if job["payload"].get("live_send_consent") != "real-email":
                raise LiveRefused("The saved job has no explicit real-email consent.")
            admission.reserve(job_id + ":mail", mail=True)
            outbox = outbox_factory(
                sender=config["sender"], controlled_recipient=config["recipient"],
                authorized=True, log=log,
            )
            outbox.clock = lambda: datetime.now(UTC)
            workspace.approve(state, fingerprint=job["payload"]["fingerprint"], outbox=outbox)
        else:
            if client_factory is None:
                import boto3
                from botocore.config import Config

                def client_factory():
                    session = boto3.Session()
                    runtime = session.client(
                        "bedrock-runtime", region_name="eu-west-1",
                        config=Config(connect_timeout=5, read_timeout=60,
                                      retries={"total_max_attempts": 1}),
                    )
                    return CountingRuntime(runtime, session)
            metered = MeteredConverse(client_factory(), admission, journal, job_id)
            if job["operation"] == "intake":
                workspace.intake(
                    state, **job["payload"], reader=SourceFields(metered),
                    validate_reading=validate_reading
                )
            elif job["operation"] == "reason":
                workspace.reason(
                    state, model=model_for(metered),
                    model_label="Real Strands graph · Amazon Bedrock · model advice, ledger facts",
                    structured_composer=True,
                )
            else:
                raise LiveRefused("Unknown worker operation.")
        job.update(status="completed", finished_at=workspace.now())
    except Exception as exc:
        state = original  # A failed graph must not publish a half-created draft.
        job = state["provider_job"]
        job.update(status="failed", error=(
            str(exc) if isinstance(exc, (LiveRefused, Conflict, UnsafeDraft)) else
            "Provider operation failed. Review the durable evidence before trying a new action."
        ), finished_at=workspace.now())
    finally:
        job["calls"] = []
        for index in range(1, 21):
            call, _ = journal.read(f"call:{job_id}:{index}")
            if call:
                job["calls"].append({k: call[k] for k in (
                    "call_id", "status", "model_id", "usage", "reserved_usd", "request_hash"
                ) if k in call})
        if job["operation"] == "approve":
            saved = log.find(job["payload"]["fingerprint"])
            if saved:
                from dataclasses import asdict

                state["sends"][saved.fingerprint] = asdict(saved)
    workspace.event(state, "Real-provider job " + job["status"], job["id"])
    state.setdefault("provider_history", []).append(public_job(job))
    state["revision"] += 1
    store.put(handle, state, version)


def handler(event, context):
    bucket = os.environ["ARCHON_STATE_BUCKET"]
    run(configured_store(), Journal(S3Sessions(bucket, "provider/")),
        event["session"], event["job_id"])
    return {"accepted": True}


def public_job(job):
    if not job:
        return None
    hidden = {"payload", "sender", "recipient", "request_id"}
    safe = {k: v for k, v in job.items() if k not in hidden}
    if job["status"] == "running":
        elapsed = (datetime.now(UTC) - datetime.fromisoformat(job["started_at"])).total_seconds()
        if elapsed > 900:
            safe.update(status="unknown",
                        error="Worker interrupted. Operator reconciliation required.")
    return safe
