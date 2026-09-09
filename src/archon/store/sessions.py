"""Opaque demo sessions: one JSON document, conditional writes, no shared books."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import sqlite3
import tempfile
from typing import Protocol


class Conflict(ValueError):
    """A newer revision exists. Re-read before making another decision."""


class MissingSession(ValueError):
    """This opaque handle is absent, invalid, or expired."""


def check_handle(handle: str) -> None:
    if not re.fullmatch(r"[a-f0-9]{64}", handle):
        raise MissingSession("Session not found. Start a new synthetic workspace.")


class SessionStore(Protocol):
    def get(self, handle: str) -> tuple[dict, str]: ...

    def put(self, handle: str, state: dict, version: str | None) -> None: ...


class SQLiteSessions:
    """Independent connections and a compare-and-swap update across processes."""

    def __init__(self, path: str):
        self.path = path

    @contextlib.contextmanager
    def connection(self):
        with contextlib.closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS demo_sessions "
                "(handle TEXT PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL)"
            )
            yield db

    def get(self, handle: str) -> tuple[dict, str]:
        check_handle(handle)
        with self.connection() as db:
            row = db.execute(
                "SELECT body, revision FROM demo_sessions WHERE handle = ?", (handle,)
            ).fetchone()
        if row is None:
            raise MissingSession("Session not found. Start a new synthetic workspace.")
        return json.loads(row[0]), str(row[1])

    def put(self, handle: str, state: dict, version: str | None) -> None:
        check_handle(handle)
        body = json.dumps(state, separators=(",", ":"), allow_nan=False)
        with self.connection() as db:
            if version is None:
                try:
                    db.execute(
                        "INSERT INTO demo_sessions VALUES (?, ?, ?)",
                        (handle, state["revision"], body),
                    )
                except sqlite3.IntegrityError as exc:
                    raise Conflict("Session already exists.") from exc
            else:
                changed = db.execute(
                    "UPDATE demo_sessions SET revision = ?, body = ? "
                    "WHERE handle = ? AND revision = ?",
                    (state["revision"], body, handle, int(version)),
                ).rowcount
                if changed != 1:
                    raise Conflict("Books changed in another tab. Refresh and review again.")


class S3Sessions:
    """Private objects. ETags make concurrent Lambda writes conditional."""

    def __init__(self, bucket: str, prefix: str = "sessions/", client=None):
        if client is None:
            import boto3

            client = boto3.client("s3")
        self.client, self.bucket, self.prefix = client, bucket, prefix

    def key(self, handle: str) -> str:
        check_handle(handle)
        return f"{self.prefix}{handle}.json"

    def get(self, handle: str) -> tuple[dict, str]:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self.key(handle))
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in {"AccessDenied", "403"}:
                logging.getLogger(__name__).warning("Session storage read unavailable: %s", code)
                raise MissingSession(
                    "Session unavailable or expired. Start a new synthetic workspace; "
                    "if that also fails, the storage service needs operator attention."
                ) from exc
            if code in {"NoSuchKey", "404"}:
                raise MissingSession("Session not found. Start a new workspace.") from exc
            raise
        with contextlib.closing(response["Body"]) as body:
            return json.loads(body.read()), response["ETag"]

    def put(self, handle: str, state: dict, version: str | None) -> None:
        condition = {"IfNoneMatch": "*"} if version is None else {"IfMatch": version}
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=self.key(handle),
                Body=json.dumps(state, separators=(",", ":"), allow_nan=False).encode(),
                ContentType="application/json",
                ServerSideEncryption="AES256",
                **condition,
            )
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in {"PreconditionFailed", "ConditionalRequestConflict", "412", "409"}:
                raise Conflict("Books changed in another tab. Refresh and review again.") from exc
            raise


def configured_store() -> SessionStore:
    bucket = os.environ.get("ARCHON_STATE_BUCKET")
    if bucket:
        return S3Sessions(bucket, os.environ.get("ARCHON_STATE_PREFIX", "sessions/"))
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        raise RuntimeError("Lambda requires ARCHON_STATE_BUCKET; ephemeral state is refused")
    default = os.path.join(tempfile.gettempdir(), "archon-sessions.sqlite3")
    return SQLiteSessions(os.environ.get("ARCHON_SESSION_DB", default))
