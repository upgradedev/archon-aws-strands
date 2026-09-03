"""The shape of the graph, as data rather than as SDK objects.

Split out for one reason: the claim that six domains are load-bearing has to be
testable, and it cannot be tested through ``GraphBuilder`` without the SDK
installed. Here the wiring is a plain structure, so a test with no dependencies
can assert the property the README will claim.

The property, stated once so a test can enforce it: **the composer has no tools
of its own.** Its entire view of the business arrives along the six edges. Give
it a shortcut tool and the readers become decoration, the graph becomes a
diagram, and the sentence about six domains agreeing stops being true.
"""

from __future__ import annotations

from dataclasses import dataclass

COMPOSER = "composer"

READER_RULES = (
    "You report only what your tool returns. You never estimate, round or infer "
    "a figure the tool did not give you. If the tool says nothing is outstanding, "
    "you say so plainly rather than looking for something to report."
)

COMPOSER_RULES = (
    "Six colleagues have each reported on one part of this business, and their "
    "reports are your only view of it. You hold no tools and can look nothing up, "
    "so if a fact is not in front of you, you do not have it.\n\n"
    "Decide whether a collection chase is worth sending. Write only an opening "
    "line and a closing line. You never write a number: every figure is added by "
    "a claim the ledger has already confirmed, and your text is refused outright "
    "if it contains a digit.\n\n"
    "Judge the tone from the whole position and not from the debt alone. A client "
    "who has part paid is settling in stages, not defaulting. If the reports show "
    "nothing overdue, say there is no chase to write and stop."
)


@dataclass(frozen=True, slots=True)
class Reader:
    """One domain, one agent, one tool."""

    name: str
    duty: str
    tool: str

    @property
    def system_prompt(self) -> str:
        return f"You report on {self.duty}. {READER_RULES}"


READERS: tuple[Reader, ...] = (
    Reader("suppliers", "what this firm owes its suppliers", "supplier_position"),
    Reader("sales", "what this firm's clients owe it", "sales_position"),
    Reader("payroll", "whether this firm has paid its people", "payroll_position"),
    Reader("trading", "whether this firm traded at a profit", "trading_position"),
    Reader("cash", "what actually moved through the bank", "cash_position"),
    Reader("metrics", "the headline position", "headline_metrics"),
)

EDGES: tuple[tuple[str, str], ...] = tuple((reader.name, COMPOSER) for reader in READERS)

#: The composer is deliberately toolless. See the module docstring.
COMPOSER_TOOLS: tuple[str, ...] = ()
