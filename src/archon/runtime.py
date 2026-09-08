"""One path from raw post to a decision, used by everything that has one.

There were three. `demo.py` built the graph from documents constructed in code,
`web/app.py` skipped the graph entirely and returned a constant, and the
evaluation handed Archon a set of books somebody had already posted correctly.
Three call sites is why they drifted, and each drift flattered the product in a
different way:

* the screen a judge actually uses never ran a single agent;
* the demo never read an email, so the reader was never exercised end to end;
* Archon's column in the comparison started from books it did not have to build,
  while the method it was compared against started from raw text.

This is the one path. Raw post in, a decision out, and **the mode is a required
argument** rather than a default, because the difference between a run that
reasons on Bedrock and one that walks a script is the difference between a claim
and a demonstration, and it must never be decided by what happens to be
importable.

**There is no fallback.** If a live run cannot reach Bedrock it raises. A screen
that quietly served a scripted answer when the model was unreachable would be
lying at precisely the moment somebody was watching.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from archon.adapters.inbound import LocalReader, Reading, UnreadablePost, read_email
from archon.agents.draft import ChaseDraft
from archon.domain.books import Books

#: Where the reading comes from.
RULES, BEDROCK = "rules", "bedrock"
#: Where the tone comes from.
SCRIPTED = "scripted"


class NotLive(RuntimeError):
    """A live run was asked for and the model could not be reached.

    Raised rather than handled. The caller may present it; nothing may swallow
    it and continue with a scripted answer.
    """


@dataclass(frozen=True, slots=True)
class Mode:
    """Which reader, which composer. Stated at every call site."""

    reader: str
    composer: str
    label: str

    @property
    def live_reading(self) -> bool:
        return self.reader == BEDROCK

    @property
    def live_reasoning(self) -> bool:
        return self.composer == BEDROCK


#: Reads with rules and composes from a script. Runs anywhere, proves the wiring,
#: and is not evidence that anything reasoned.
OFFLINE = Mode(reader=RULES, composer=SCRIPTED, label="offline, no model reasoned")
#: Reads and reasons on Bedrock. Costs money and needs credentials.
LIVE = Mode(reader=BEDROCK, composer=BEDROCK, label="live on Bedrock")
#: Reads on Bedrock, composes from a script. Used where the reading is the thing
#: under test and the tone is not worth paying for.
LIVE_READING = Mode(reader=BEDROCK, composer=SCRIPTED, label="live reading, scripted tone")


@dataclass(frozen=True, slots=True)
class Close:
    """What one pass over a month's post produced, and what it refused."""

    mode: Mode
    books: Books
    readings: tuple[Reading, ...] = ()
    refusals: tuple[str, ...] = ()
    draft: ChaseDraft | None = None
    views: tuple = ()

    @property
    def redactions(self) -> int:
        return sum(r.redactions for r in self.readings)

    @property
    def read_count(self) -> int:
        return len(self.readings)


def _reader(mode: Mode):
    """The client `read_email` should use. None means real Bedrock."""
    return None if mode.live_reading else LocalReader()


def read_the_post(raw_post: list[str], mode: Mode, *, prefix: str = "email") -> Close:
    """Turn raw emails into books, refusing rather than guessing.

    Every method compared in `archon.evidence` now starts here, from the same
    strings, so no column begins with books somebody else posted for it.
    """
    books = Books()
    readings: list[Reading] = []
    refusals: list[str] = []
    client = _reader(mode)

    for index, raw in enumerate(raw_post):
        source_ref = f"{prefix}:{index:03d}"
        try:
            reading = read_email(raw, source_ref, client=client)
            books.record(reading.document)
        except (UnreadablePost, ValueError) as refused:
            # SettlementError and UnbalancedEntry are both ValueError, so one
            # clause covers a document that will not read and one the books
            # refuse to accept. Both are refusals; neither is a crash.
            # A refusal is part of the result, not an error to be hidden. A month
            # where two documents were refused is a different month from one
            # where none were, and a caller that cannot see the difference cannot
            # report it.
            refusals.append(f"{source_ref}: {refused}")
            continue
        readings.append(reading)

    return Close(mode=mode, books=books, readings=tuple(readings), refusals=tuple(refusals))


@dataclass(frozen=True, slots=True)
class Reasoning:
    """What produced the tone on screen, and whether anything reasoned at all.

    Kept as a value rather than a flag because a page has to be able to say three
    different things: nothing has reasoned yet, six agents did and here is what
    each thought, or a live run was asked for and could not be reached. The third
    is the one that matters. A screen that answers an unreachable model with the
    scripted line it already had, without saying so, is lying at the moment
    somebody is watching.
    """

    reply: str
    source: str
    views: tuple = field(default_factory=tuple)
    error: str | None = None

    @classmethod
    def scripted(cls, reply: str | None = None) -> Reasoning:
        from archon.demo import SCRIPTED_REPLY

        return cls(reply=reply or SCRIPTED_REPLY, source="scripted")

    @classmethod
    def live(cls, reply: str, views: tuple) -> Reasoning:
        return cls(reply=reply, source="bedrock", views=views)

    @classmethod
    def unreachable(cls, error: str) -> Reasoning:
        """Live was asked for and failed. The tone stays scripted and says so."""
        from archon.demo import SCRIPTED_REPLY

        return cls(reply=SCRIPTED_REPLY, source="unreachable", error=error)

    @property
    def is_live(self) -> bool:
        return self.source == "bedrock"

    @property
    def failed(self) -> bool:
        return self.source == "unreachable"

    @property
    def label(self) -> str:
        if self.is_live:
            return "six agents reasoned on Bedrock"
        if self.failed:
            return "a live run was asked for and Bedrock could not be reached"
        return "no model has reasoned; this tone is a constant"
