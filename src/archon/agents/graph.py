"""The Strands graph: six domain readers that must finish before a chase is drafted.

This is the only module in Archon that imports the SDK, and it is where the
SDK either earns its place or does not. Six readers run over the same books, one
per question the owner asked, and fan into a composer that decides whether a
chase is warranted and how to put it. Remove Strands and there is no agent left,
only six queries and a template.

The composer never sends. It proposes a draft; ``archon.agents.gate`` re-derives
every fact and demands a human fingerprint. Safety that depends on a model
behaving is not safety, so the gate is plain code and stays that way.

**Proven, and by two versions.** `tests/test_graph_runs.py` runs this graph
against a scripted model and asserts the six readers all execute before the
composer. That suite passes locally on `strands-agents 1.53.0` and in CI on
1.54.0. What is still not proven here is judgment: a scripted model walks the
graph, it does not decide anything.
"""

from __future__ import annotations

from datetime import date

from strands import Agent, tool
from strands.multiagent import GraphBuilder

from archon.adapters import bedrock
from archon.domain.books import Books

from . import gating, tools, wiring

COMPOSER = wiring.COMPOSER



def _readers(
    books: Books, as_of: date, frm: date, to: date, model: object | None, suffix: str = ""
) -> list[tuple[str, Agent]]:
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
                model=model,
                system_prompt=reader.system_prompt + ("\n\n" + suffix if suffix else ""),
                tools=[bound[reader.tool]],
                # Silent. The SDK's default handler streams every reply to stdout,
                # which makes this graph unusable inside anything that has its own
                # output. A caller who wants the text reads it off the result.
                callback_handler=None,
            ),
        )
        for reader in wiring.READERS
    ]


def _composer(books: Books, as_of: date, model: object | None, suffix: str = "") -> Agent:
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
    if suffix:
        brief += "\n\n" + suffix
    return Agent(
        name=COMPOSER, model=model, system_prompt=brief, tools=[], callback_handler=None
    )


def build(books: Books, as_of: date, frm: date, to: date, model: object | None = None,
          *, composer_suffix: str = "", reader_suffix: str = ""):
    """Wire the graph. Construction only; nothing runs until it is called.

    ``model`` is injected rather than reached for. Passing ``None`` uses the
    configured Archon Bedrock factory, passing ``bedrock_model()`` runs on Bedrock,
    and passing a ``ScriptedModel`` walks the whole graph with no AWS account,
    which is how S9 is satisfied by the architecture instead of by a promise.
    """
    if model is None:
        model = bedrock.bedrock_model()
    builder = GraphBuilder()
    readers = _readers(books, as_of, frm, to, model, reader_suffix)
    for name, agent in readers:
        builder.add_node(agent, name)
    builder.add_node(_composer(books, as_of, model, composer_suffix), COMPOSER)
    gate = gating.all_reported(wiring.REQUIRED_REPORTS)
    for source, target in wiring.EDGES:
        builder.add_edge(source, target, condition=gate)
    return builder.build()
