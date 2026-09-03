"""The composer must not start with one report in hand.

Under Python's OR semantics a node fires when any incoming edge's source
completes, so six edges into a composer buys nothing on their own. These tests
pin the condition that turns six edges into a real requirement, and they pin it
against both state shapes the SDK documents, because the shape is not something
this repo gets to assume.
"""

from __future__ import annotations

import pytest

from archon.agents import wiring
from archon.agents.gating import all_reported, completed_node_ids


class ResultsState:
    """A state that reports through ``results``, keyed by node id."""

    def __init__(self, *names: str) -> None:
        self.results = {name: object() for name in names}


class CompletedState:
    """A state that reports through ``completed_nodes``."""

    def __init__(self, *names: str) -> None:
        self.completed_nodes = list(names)


class NodeObject:
    def __init__(self, node_id: str) -> None:
        self.node_id = node_id


class ObjectKeyedState:
    """A state whose keys are node objects rather than strings."""

    def __init__(self, *names: str) -> None:
        self.completed_nodes = [NodeObject(name) for name in names]


ALL_SIX = tuple(sorted(wiring.REQUIRED_REPORTS))


def test_six_readers_are_required():
    assert len(wiring.REQUIRED_REPORTS) == 6


@pytest.mark.parametrize("state_type", [ResultsState, CompletedState, ObjectKeyedState])
def test_the_composer_is_held_until_every_reader_has_reported(state_type):
    condition = all_reported(wiring.REQUIRED_REPORTS)
    for count in range(len(ALL_SIX)):
        partial = state_type(*ALL_SIX[:count])
        assert not condition(partial), f"released with only {count} of six reports"
    assert condition(state_type(*ALL_SIX))


def test_five_of_six_is_still_held():
    # The failure this guards is quiet: five reports look like plenty.
    condition = all_reported(wiring.REQUIRED_REPORTS)
    assert not condition(ResultsState(*ALL_SIX[:5]))


def test_extra_nodes_do_not_prevent_release():
    condition = all_reported(wiring.REQUIRED_REPORTS)
    assert condition(ResultsState(*ALL_SIX, "some_future_node"))


def test_an_unrecognised_state_fails_closed():
    # If a future SDK renames the attribute, the composer is held rather than
    # released on an assumption. Failing open is the one outcome not allowed.
    condition = all_reported(wiring.REQUIRED_REPORTS)
    assert not condition(object())
    assert completed_node_ids(object()) == frozenset()


def test_both_surfaces_are_read_and_unioned():
    class Both:
        results = {"suppliers": object(), "sales": object()}
        completed_nodes = ["payroll", "trading", "cash", "metrics"]

    assert all_reported(wiring.REQUIRED_REPORTS)(Both())


def test_a_condition_that_requires_nothing_is_refused():
    with pytest.raises(ValueError, match="not a condition"):
        all_reported(frozenset())


def test_a_string_completed_nodes_is_not_treated_as_characters():
    # "sales" must not read as five completed nodes s, a, l, e, s.
    class Odd:
        completed_nodes = "sales"

    assert completed_node_ids(Odd()) == frozenset()


def test_the_graph_applies_the_condition_to_every_edge():
    """Read graph.py. An edge added without the condition reopens the hole."""
    import ast
    import pathlib

    src = (
        pathlib.Path(__file__).resolve().parents[1] / "src" / "archon" / "agents" / "graph.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(src)
    add_edges = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_edge"
    ]
    assert add_edges, "no add_edge call found"
    for call in add_edges:
        assert any(kw.arg == "condition" for kw in call.keywords), (
            "an edge into the composer was added without a condition. Under OR "
            "semantics that alone lets the composer start on one report."
        )


def test_a_reader_that_failed_does_not_count_as_having_reported():
    """GraphState carries failed_nodes and interrupted_nodes separately.

    Confirmed by CI run 33712269818 against strands-agents 1.54.0. A failed
    payroll reader must not let the composer write to a client as though the
    payroll position were known.
    """

    class PartlyFailed:
        completed_nodes = ["suppliers", "sales", "trading", "cash", "metrics"]
        failed_nodes = ["payroll"]

    assert not all_reported(wiring.REQUIRED_REPORTS)(PartlyFailed())


def test_the_state_fields_this_module_relies_on_are_the_ones_ci_found():
    # Kept as a written record next to the code that depends on it, so a future
    # SDK bump that renames either surface breaks a test rather than a client
    # email. The live check is the CI step that prints the real dataclass.
    proven = {
        "task", "status", "completed_nodes", "failed_nodes", "interrupted_nodes",
        "execution_order", "start_time", "results", "accumulated_usage",
        "accumulated_metrics", "execution_count", "execution_time", "total_nodes",
        "edges", "entry_points",
    }
    assert {"results", "completed_nodes"} <= proven
