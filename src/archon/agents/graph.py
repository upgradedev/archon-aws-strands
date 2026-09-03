"""The Strands graph: six domains that have to agree before a chase is drafted.

This is the only module in Archon that imports the SDK, and it is where the
SDK either earns its place or does not. Six readers run over the same books, one
per question the owner asked, and fan into a composer that decides whether a
chase is warranted and how to put it. Remove Strands and there is no agent left,
only six queries and a template.

The composer never sends. It proposes a draft; ``archon.agents.gate`` re-derives
every fact and demands a human fingerprint. Safety that depends on a model
behaving is not safety, so the gate is plain code and stays that way.

**Unverified until CI says otherwise.** Nothing in this module has been executed
on this machine, because the SDK is not installed here. The CI job asserts the
imports, the builder surface and that this graph constructs.
"""

from __future__ import annotations

from datetime import date

from strands import Agent, tool
from strands.multiagent import GraphBuilder

from archon.domain.books import Books

from . import tools

COMPOSER = "composer"

_READER_RULES = (
    "You report only what your tool returns. You never estimate, round or infer "
    "a figure the tool did not give you. If the tool says nothing is outstanding, "
    "you say so plainly rather than looking for something to report."
)

_COMPOSER_RULES = (
    "You decide whether a collection chase is worth sending, and if so you write "
    "only the opening line and the closing line. You never write a number: every "
    "figure is added by a claim the ledger has already confirmed, and your text is "
    "refused outright if it contains a digit. Judge the tone from the whole "
    "position, not from the debt alone. A client who has part paid is treated as "
    "someone settling in stages, not as a defaulter. If nothing is overdue, you "
    "say there is no chase to write and stop."
)


def _readers(books: Books, as_of: date, frm: date, to: date) -> list[tuple[str, Agent]]:
    """One agent per question, each with exactly the tool it needs.

    Tools are bound to these books by closure rather than passed as arguments,
    so an agent cannot ask about a different set of books than the one the run
    was started for.
    """

    @tool
    def suppliers_owed() -> str:
        """What suppliers have billed, and which invoices are still open."""
        return tools.supplier_position(books)

    @tool
    def sales_open() -> str:
        """What was invoiced to clients, and what remains uncollected."""
        return tools.sales_position(books, as_of)

    @tool
    def payroll_state() -> str:
        """Whether the staff have been paid."""
        return tools.payroll_position(books)

    @tool
    def trading() -> str:
        """The profit and loss for the period."""
        return tools.trading_position(books, frm, to)

    @tool
    def cash() -> str:
        """What actually moved through the bank in the period."""
        return tools.cash_position(books, frm, to)

    @tool
    def headline() -> str:
        """The headline metrics as at the reporting date."""
        return tools.headline_metrics(books, as_of)

    specs = (
        ("suppliers", "what this firm owes its suppliers", suppliers_owed),
        ("sales", "what this firm's clients owe it", sales_open),
        ("payroll", "whether this firm has paid its people", payroll_state),
        ("trading", "whether this firm traded at a profit", trading),
        ("cash", "what actually moved through the bank", cash),
        ("metrics", "the headline position", headline),
    )
    return [
        (
            name,
            Agent(
                name=name,
                system_prompt=f"You report on {duty}. {_READER_RULES}",
                tools=[fn],
            ),
        )
        for name, duty, fn in specs
    ]


def _composer(books: Books, as_of: date) -> Agent:
    @tool
    def candidate() -> str:
        """The single overdue receivable a chase would be about, if any."""
        return tools.chase_candidate(books, as_of)

    return Agent(name=COMPOSER, system_prompt=_COMPOSER_RULES, tools=[candidate])


def build(books: Books, as_of: date, frm: date, to: date):
    """Wire the graph. Construction only; nothing runs until it is called."""
    builder = GraphBuilder()
    readers = _readers(books, as_of, frm, to)
    for name, agent in readers:
        builder.add_node(agent, name)
    builder.add_node(_composer(books, as_of), COMPOSER)
    for name, _ in readers:
        builder.add_edge(name, COMPOSER)
    return builder.build()
