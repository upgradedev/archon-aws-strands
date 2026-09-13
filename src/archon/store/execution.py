"""Durable provider journals; conditional writes happen before external effects."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from archon.store.sessions import Conflict, MissingSession
from archon.store.sqlite import PROVIDER_ACCEPTED, SendRecord


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Journal:
    """Separate private namespace, injected storage and no process-local authority."""

    def __init__(self, store):
        self.store = store

    def read(self, key):
        try:
            return self.store.get(digest(key))
        except MissingSession:
            return None, None

    def create(self, key, value):
        try:
            self.store.put(digest(key), {**value, "revision": 0}, None)
            return True
        except Conflict:
            return False

    def update(self, key, value, version):
        self.store.put(digest(key), {**value, "revision": value["revision"] + 1}, version)


class DurableSendLog:
    """A failed/unknown attempt is retained; no implicit reset or auto-resend."""

    def __init__(self, journal):
        self.journal = journal

    def find(self, fingerprint):
        row, _ = self.journal.read("send:" + fingerprint)
        return SendRecord(**row["record"]) if row else None

    def reserve(self, record):
        return self.journal.create("send:" + record.fingerprint, {"record": asdict(record)})

    def settle(self, fingerprint, message_id, error, state=PROVIDER_ACCEPTED):
        row, version = self.journal.read("send:" + fingerprint)
        if row is None:
            raise Conflict("A durable reservation is required before settling a send.")
        row["record"].update(state=state, message_id=message_id, error=error)
        self.journal.update("send:" + fingerprint, row, version)
