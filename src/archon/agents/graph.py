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

from . import gating, tools, wiring

COMPOSER = wiring.COMPOSER



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

    bound = {
        "supplier_position": suppliers_owed,
        "sales_position": sales_open,
        "payroll_position": payroll_state,
        "trading_position": trading,
        "cash_position": cash,
        "headline_metrics": headline,
    }
    return [
        (
            reader.name,
            Agent(
                name=reader.name,
                system_prompt=reader.system_prompt,
                tools=[bound[reader.tool]],
            ),
        )
        for reader in wiring.READERS
    ]


def _composer(books: Books, as_of: date) -> Agent:
    """The composer, deliberately toolless.

    It had a ``candidate()`` tool and that was a hole: it could answer from its
    own lookup and never read a single reader, which would make the six domains
    decoration and the claim about them false. Its whole view now arrives along
    the edges.

    Which invoice to chase is still not a matter of opinion, so it is decided
    here in code and stated to the composer as a given rather than left for the
    model to pick out of a list.
    """
    given = tools.chase_candidate(books, as_of)
    brief = wiring.COMPOSER_RULES + "\n\n" + "The debt in question: " + given
    return Agent(name=COMPOSER, system_prompt=brief, tools=[])


def build(books: Books, as_of: date, frm: date, to: date):
    """Wire the graph. Construction only; nothing runs until it is called."""
    builder = GraphBuilder()
    readers = _readers(books, as_of, frm, to)
    for name, agent in readers:
        builder.add_node(agent, name)
    builder.add_node(_composer(books, as_of), COMPOSER)
    gate = gating.all_reported(wiring.REQUIRED_REPORTS)
    for source, target in wiring.EDGES:
        builder.add_edge(source, target, condition=gate)
    return builder.build()
