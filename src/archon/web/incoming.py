"""Revocable intake-only capabilities. No mailbox access or outbound authority."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta

from archon.store.sessions import Conflict, MissingSession
from archon.web import live, workspace

RECORD_TYPE = "incoming-capability-v1"


def now():
    return datetime.now(UTC)


def connection_key(handle):
    return hashlib.sha256(("archon:incoming:key:v1:" + handle).encode()).hexdigest()


def secret_for(handle, nonce):
    return hmac.new(handle.encode(), ("archon:incoming:secret:v1:" + nonce).encode(),
                    hashlib.sha256).hexdigest()


def record_for(store, handle):
    try:
        return store.get(connection_key(handle))
    except MissingSession:
        return None, None


def active(record):
    return bool(record and record.get("enabled") and
                datetime.fromisoformat(record["expires_at"]) > now())


def status(store, handle, state):
    record, _ = record_for(store, handle)
    jobs = list(state.get("provider_history", []))
    current = live.public_job(state.get("provider_job"))
    if current:
        jobs = [job for job in jobs if job["id"] != current["id"]] + [current]
    return {
        "enabled": active(record), "expires_at": record["expires_at"] if record else None,
        "path": "/api/incoming", "scope": "fictional-intake-only",
        "events": [{"event_id": job["incoming_event"], "job_id": job["id"],
                    "status": job["status"], "created_at": job["created_at"]}
                   for job in reversed(jobs) if "incoming_event" in job],
    }


def configure(store, handle, state, action, request_id, consent=None):
    if state.get("provider_mode") != "live":
        raise ValueError("Incoming automation requires a controlled-live workspace.")
    if action == "enable":
        live.configuration()
        if consent != "fictional-intake":
            raise ValueError("Consent to metered AI intake of fictional test data is required.")
    record, version = record_for(store, handle)
    signature = workspace.digest({"action": action, "consent": consent})
    if record and request_id in record["requests"]:
        if record["requests"][request_id] != signature:
            raise Conflict("This connection request identifier has different content.")
        if record["last_request_id"] != request_id:
            raise Conflict("Connection changed. Refresh before issuing a new request.")
    else:
        requests = dict(record["requests"]) if record else {}
        if len(requests) >= 50:
            raise ValueError("This workspace reached its connection-change limit.")
        requests[request_id] = signature
        expiry = min(now() + timedelta(hours=24),
                     datetime.fromisoformat(state["created_at"]) + timedelta(days=7))
        nonce = secrets.token_hex(32)
        record = {
            "record_type": RECORD_TYPE, "revision": record["revision"] + 1 if record else 0,
            "created_at": workspace.now(), "expires_at": expiry.isoformat(),
            "enabled": action == "enable", "target": handle, "nonce": nonce,
            "secret_digest": hashlib.sha256(secret_for(handle, nonce).encode()).hexdigest(),
            "last_request_id": request_id, "requests": requests,
        }
        store.put(connection_key(handle), record, version)
    result = status(store, handle, state)
    # Deliberate reveal only in the response to the owner's explicit enable action.
    # No key is put in workspace snapshots, logs, query strings or browser storage.
    if action == "enable" and active(record):
        result["token"] = connection_key(handle) + "." + secret_for(handle, record["nonce"])
    return result


def receive(store, authorization, event_id, body, load_session):
    denied = "Incoming key is invalid, revoked or expired."
    if not re.fullmatch(r"Bearer [a-f0-9]{64}\.[a-f0-9]{64}", authorization or ""):
        raise MissingSession(denied)
    key, secret = authorization[7:].split(".")
    try:
        record, _ = store.get(key)
    except MissingSession as exc:
        raise MissingSession(denied) from exc
    if (record.get("record_type") != RECORD_TYPE or not active(record) or
            not hmac.compare_digest(record["secret_digest"],
                                    hashlib.sha256(secret.encode()).hexdigest())):
        raise MissingSession(denied)
    handle = record["target"]
    state, version = load_session(handle)
    request_id = "incoming_" + workspace.digest({"key": key, "event_id": event_id})
    # The existing compare-and-swap transaction persists the event and job before
    # scheduling. Retrying an uncertain enqueue reuses that job, not another call.
    live.submit(store, handle, state, version, "intake", {"body": body}, request_id,
                state["revision"], incoming_event=event_id)
    candidates = [state.get("provider_job")] + list(reversed(state.get("provider_history", [])))
    job = next(job for job in candidates if job and job.get("incoming_event") == event_id)
    return {"event_id": event_id, "job_id": job["id"],
            "status": live.public_job(job)["status"]}
