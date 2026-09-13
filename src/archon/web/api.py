"""Session-isolated public API. Public callers cannot select live providers."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from archon.store.sessions import Conflict, MissingSession, configured_store
from archon.web import workspace

app = FastAPI(title="ARCHON synthetic workspace", docs_url=None, redoc_url=None)
SESSION_HEADER = Annotated[str, Header(alias="X-Archon-Session")]


@lru_cache(maxsize=1)
def store():
    return configured_store()


class Mutation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=0)
    request_id: str = Field(min_length=16, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


class Intake(Mutation):
    body: str = Field(min_length=1, max_length=32000)
    replace_id: str | None = Field(default=None, max_length=40)


class ApprovalRequest(Mutation):
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class ProposalRequest(Mutation):
    invoice_id: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=4000)


class CounterRequest(ApprovalRequest):
    body: str = Field(min_length=1, max_length=4000)


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["synthetic", "live"] | None = None


class ResolutionRequest(Mutation):
    source_id: str = Field(min_length=1, max_length=40)
    decision: Literal["duplicate-payment", "resume-collection", "attest-legacy-payments"]
    note: str = Field(min_length=20, max_length=2000)
    duplicate_of: str | None = Field(default=None, max_length=40)
    identities: dict[str, str] | None = Field(default=None, max_length=50)


@app.middleware("http")
async def boundary(request: Request, call_next):
    # Bound the bytes before JSON decoding, including chunked clients. No session
    # handles, raw email bodies, or storage exceptions are included in access logs.
    size = 0
    chunks = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > 40000:
            return JSONResponse({"detail": "Request exceeds 40 KB."}, status_code=413)
        chunks.append(chunk)
    request._body = b"".join(chunks)
    try:
        response = await call_next(request)
    except Exception:
        logging.getLogger(__name__).error("Workspace request failed; no state exposed")
        response = JSONResponse(
            {"detail": "Workspace unavailable. Refresh to read durable state before retrying."},
            status_code=503,
        )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(ValueError)
async def refusal(request: Request, exc: ValueError):
    status = 401 if isinstance(exc, MissingSession) else 409 if isinstance(exc, Conflict) else 422
    return JSONResponse({"detail": str(exc)}, status_code=status)


def load(handle: str):
    state, version = store().get(handle)
    if datetime.now(UTC) - datetime.fromisoformat(state["created_at"]) > timedelta(days=7):
        raise MissingSession("This seven-day demo session expired. Start a new workspace.")
    return state, version


def mutate(handle: str, request: Mutation, operation: str, action):
    state, version = load(handle)
    payload = request.model_dump(exclude={"request_id", "revision"})
    if state.get("provider_mode") == "live":
        from archon.web import live

        if operation in live.OPERATIONS:
            return live.submit(store(), handle, state, version, operation, payload,
                               request.request_id, request.revision)
        job = state.get("provider_job")
        if job and job["status"] in {"queued", "running"}:
            raise Conflict("Wait for the durable provider job before changing these books.")
    signature = workspace.digest({"operation": operation, "payload": payload})
    previous = state["requests"].get(request.request_id)
    if previous:
        if previous != signature:
            raise Conflict("This request identifier was already used for different content.")
        return workspace.snapshot(state)
    if request.revision != state["revision"]:
        raise Conflict("Books changed in another tab. Refresh and review again.")
    if len(state["requests"]) >= 500:
        raise ValueError("This demo has reached 500 actions. Start a new synthetic workspace.")
    action(state, **payload)
    state["requests"][request.request_id] = signature
    state["revision"] += 1
    store().put(handle, state, version)
    return workspace.snapshot(state)


@app.get("/api/health")
def health():
    from archon.web import live

    if live.enabled():
        live.configuration()
        return {
            "status": "ok", "mode": "controlled-live", "live_send": True, "live_model": True,
            "commit": os.environ.get("ARCHON_COMMIT_SHA", "local-unversioned"),
            "reader": "source-checked-semantic", "model": "eu.anthropic.claude-opus-5",
            "orchestration": "Strands", "provider": "SES-controlled-recipient",
            "note": "Configuration, not proof of invocation or delivery; inspect job receipts.",
        }
    return {
        "status": "ok",
        "mode": "synthetic",
        "live_send": False,
        "live_model": False,
        "commit": os.environ.get("ARCHON_COMMIT_SHA", "local-unversioned"),
        "reader": "bounded-local-rules",
        "model": "LedgerScriptModel",
        "orchestration": "Strands",
        "provider": "SimulatedProvider",
    }


@app.get("/api/providers")
def providers():
    from archon.web import live

    return {"live": live.enabled(), "data": "fictional business examples"}


@app.post("/api/sessions", status_code=201)
def create_session(request: SessionRequest):
    handle, state = secrets.token_hex(32), workspace.fresh()
    from archon.web import live

    if request.mode == "live" and not live.enabled():
        raise ValueError("Live mode is not available in this deployment.")
    if request.mode == "live" or (request.mode is None and live.enabled()):
        config = live.configuration()
        state.update(provider_mode="live", test_recipient=config["recipient"])
    store().put(handle, state, None)
    return {"session": handle, "workspace": workspace.snapshot(state)}


@app.get("/api/workspace")
def get_workspace(handle: SESSION_HEADER):
    state, _ = load(handle)
    return workspace.snapshot(state)


@app.post("/api/intake")
def intake(request: Intake, handle: SESSION_HEADER):
    return mutate(handle, request, "intake", workspace.intake)


@app.post("/api/reason")
def reason(request: Mutation, handle: SESSION_HEADER):
    return mutate(handle, request, "reason", workspace.reason)


@app.post("/api/approve")
def approve(request: ApprovalRequest, handle: SESSION_HEADER):
    return mutate(handle, request, "approve", workspace.approve)


@app.post("/api/arrangements/propose")
def propose(request: ProposalRequest, handle: SESSION_HEADER):
    return mutate(handle, request, "propose", workspace.propose)


@app.post("/api/arrangements/approve")
def agree(request: ApprovalRequest, handle: SESSION_HEADER):
    return mutate(handle, request, "agree", workspace.agree)


@app.post("/api/arrangements/counter")
def counter(request: CounterRequest, handle: SESSION_HEADER):
    return mutate(handle, request, "counter", workspace.counter)


@app.post("/api/resolve")
def resolve(request: ResolutionRequest, handle: SESSION_HEADER):
    return mutate(handle, request, "resolve", workspace.resolve)


@app.get("/api/evidence")
def evidence(handle: SESSION_HEADER):
    from archon.web.export import evidence_bundle

    state, _ = load(handle)
    return evidence_bundle(state, os.environ.get("ARCHON_COMMIT_SHA", "local-unversioned"))
