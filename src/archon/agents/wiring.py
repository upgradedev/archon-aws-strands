"""The shape of the graph, as data rather than as SDK objects.

Split out for one reason: the claim that six domains are load-bearing has to be
testable, and it cannot be tested through ``GraphBuilder`` without the SDK
installed. Here the wiring is a plain structure, so a test with no dependencies
can assert the property the README will claim.

Two properties live here, and each answers a question a reader of the code will
otherwise ask.

**The composer has no tools of its own.** Its entire view of the business arrives
along the six edges. Give it a shortcut tool and the readers become decoration,
the graph becomes a diagram, and the statement that all six reports are required
stops being true.

**Each reader is asked for a judgement, not a restatement.** An earlier version
told them to report what their tool returned and nothing else, which is a model
call that adds nothing: a judge is right to ask what six agents are for, and
"they relay a string" is not an answer. Each one now answers a question only
somebody looking at that domain can answer, and they are told plainly that a
colleague may disagree. The disagreement is what the composer is for.
"""

from __future__ import annotations

from dataclasses import dataclass

COMPOSER = "composer"

READER_RULES = (
    "Call your tool, then do two things with what it returns.\n\n"
    "First, state it. Never estimate, round or infer a figure the tool did not "
    "give you; if it says nothing is outstanding, say so plainly rather than "
    "looking for something to report.\n\n"
    "Second, and this is the part only you can do: say whether it is a problem "
    "and how pressing, in one sentence. You are looking at one part of a very "
    "small firm whose owner does everything alone, so say what someone who had "
    "read only your part would want said. End with URGENT, WATCH or FINE.\n\n"
    "Do not soften it and do not dramatise it. Five colleagues are reading five "
    "other parts and one of them may reasonably disagree with you."
)

COMPOSER_RULES = (
    "Six colleagues have each read one part of this business and given you their "
    "reading and their view. Those reports are your only view of it: you hold no "
    "tools and can look nothing up, so if a fact is not in front of you, you do "
    "not have it.\n\n"
    "They will not always agree, and the disagreement is the useful part. Cash "
    "may be pressing while this particular client is settling in stages. Payroll "
    "may be due while the debt is small. Weigh them rather than following the "
    "loudest.\n\n"
    "Write only an opening line and a closing line for one collection chase. You "
    "never write a number: every figure is added by a claim the ledger has "
    "already confirmed, and your text is refused outright if it contains a "
    "digit.\n\n"
    "Let the tone follow what the six of them together describe, not the size of "
    "the debt. A client who has part paid is settling in stages, not defaulting. "
    "If the reports show nothing overdue, say there is no chase to write and stop."
)


@dataclass(frozen=True, slots=True)
class Reader:
    """One domain, one agent, one tool, and one question worth asking."""

    name: str
    duty: str
    tool: str
    #: The judgement only somebody looking at this domain can make. Without it a
    #: reader restates its tool, and a restatement is not worth a model call.
    question: str

    @property
    def system_prompt(self) -> str:
        return (
            f"You report on {self.duty}. The question you answer for your "
            f"colleagues is: {self.question}\n\n{READER_RULES}"
        )


READERS: tuple[Reader, ...] = (
    Reader(
        "suppliers",
        "what this firm owes its suppliers",
        "supplier_position",
        "is anything owed out about to become a problem, and can it wait?",
    ),
    Reader(
        "sales",
        "what this firm's clients owe it",
        "sales_position",
        "which client should be pushed, and is any of them settling in stages "
        "rather than avoiding payment?",
    ),
    Reader(
        "payroll",
        "whether this firm has paid its people",
        "payroll_position",
        "can this firm pay its people this month, and if not, by when must that change?",
    ),
    Reader(
        "trading",
        "whether this firm traded at a profit",
        "trading_position",
        "is this firm making money, or busy?",
    ),
    Reader(
        "cash",
        "what actually moved through the bank",
        "cash_position",
        "will this firm run out of cash, and how soon?",
    ),
    Reader(
        "metrics",
        "the headline position",
        "headline_metrics",
        "what is the one number the owner should be worried about this month?",
    ),
)

EDGES: tuple[tuple[str, str], ...] = tuple((reader.name, COMPOSER) for reader in READERS)

#: The composer is deliberately toolless. See the module docstring.
COMPOSER_TOOLS: tuple[str, ...] = ()

#: Every reader the composer must have heard from before it may run at all.
#: Enforced by an edge condition, not by the prompt. See ``agents.gating``.
REQUIRED_REPORTS: frozenset[str] = frozenset(reader.name for reader in READERS)

#: What a reader is asked to end its view with, so a caller can tell an urgent
#: report from a calm one without parsing prose.
VERDICTS: tuple[str, ...] = ("URGENT", "WATCH", "FINE")
