"""Opt-in packaging component; the deployed handler/AR3-pinned src are unchanged."""

from __future__ import annotations

import json
import os
import re
from contextvars import ContextVar

PREFIX = "ARCHON_X1 "
SCHEMA = "archon-x1-invocation-v1"
PATTERNS = {
    "request_id": r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}",
    "source_sha": r"[a-f0-9]{40}",
    "function_arn": r"arn:aws:lambda:[a-z0-9-]{1,32}:[0-9]{12}:function:"
                    r"[A-Za-z0-9_-]{1,64}(?::[A-Za-z0-9_$-]{1,64})?",
    "function_version": r"(?:\$LATEST|[0-9]{1,12})",
    "log_group": r"/aws/lambda/[A-Za-z0-9_/-]{1,128}",
    "log_stream": r"[A-Za-z0-9_/$\[\].-]{1,256}",
}
HEADERS = {
    "x-archon-lambda-request-id": "request_id",
    "x-archon-backend-commit": "source_sha",
    "x-archon-lambda-version": "function_version",
}
_current: ContextVar[dict | None] = ContextVar("archon_x1_runtime", default=None)


def application_handler(event, context):
    # Lazy import keeps the offline correlation CLI standard-library-only.
    from archon.web.lambda_handler import handler as original

    return original(event, context)


def valid(field, value):
    return isinstance(value, str) and re.fullmatch(PATTERNS[field], value) is not None


def current_context():
    """A copy, isolated to this invocation; never event headers or caller request_id."""
    value = _current.get()
    return dict(value) if value is not None else None


def identity(context):
    values = {
        "request_id": getattr(context, "aws_request_id", None),
        "source_sha": os.getenv("ARCHON_COMMIT_SHA"),
        "function_arn": getattr(context, "invoked_function_arn", None),
        "function_version": getattr(context, "function_version", None),
        "log_group": getattr(context, "log_group_name", None),
        "log_stream": getattr(context, "log_stream_name", None),
    }
    return {key: value if valid(key, value) else None for key, value in values.items()}


def emit(record):
    # One bounded line, no URL/path/query/event/body/session/token/exception text.
    line = PREFIX + json.dumps(record, sort_keys=True, separators=(",", ":"))
    if len(line.encode("utf-8")) > 2048:
        return
    try:
        print(line, flush=True)
    except (OSError, ValueError):
        # Observability must not break the API. Exporter refuses a missing log receipt.
        pass


def handler(event, context):
    runtime = identity(context)
    token = _current.set(runtime)
    status = None
    outcome = "raised"
    try:
        response = application_handler(event, context)
        observed = response.get("statusCode")
        status = observed if type(observed) is int and 100 <= observed <= 599 else None
        # Additive response metadata only; never change body/status/cookies/contracts.
        headers = {k: v for k, v in response.get("headers", {}).items()
                   if k.lower() not in HEADERS}
        headers.update({name: runtime[field] for name, field in HEADERS.items()
                        if runtime[field] is not None})
        outcome = "returned"
        return {**response, "headers": headers}
    finally:
        _current.reset(token)
        emit({"schema": SCHEMA, **runtime, "status": status, "outcome": outcome,
              "identity_status": "known" if all(runtime.values()) else "unknown"})
