"""The condition that makes six domains a requirement rather than a request.

**Why this module exists.** The Strands graph fires a node under OR semantics in
Python: a target runs when *any* incoming edge's source completes. Six readers
feeding a composer therefore does not mean the composer waits for six. It means
it starts as soon as the first one finishes, with one report in hand and five
still running.

That is not a style problem. J4 requires all six domain readers to finish before
the composer can draft, and under OR semantics that requirement was false in the
graph even though it appeared in the prompt. Putting the requirement in the
composer's system prompt does not fix it either: a prompt is a request, and the
node has already started.

So every edge into the composer carries the same condition, and the condition is
satisfied only when all six readers have reported. Under OR semantics, no single
edge becomes traversable until that holds, which gives AND behaviour through the
mechanism the SDK actually provides.

**The state shape, printed by CI run 33712269818 against strands-agents 1.54.0
rather than assumed here.** ``GraphState`` carries ``task``, ``status``,
``completed_nodes``, ``failed_nodes``, ``interrupted_nodes``, ``execution_order``,
``start_time``, ``results``, ``accumulated_usage``, ``accumulated_metrics``,
``execution_count``, ``execution_time``, ``total_nodes``, ``edges`` and
``entry_points``. Both surfaces this module reads are confirmed present.

**A reader that fails or is interrupted does not count as having reported**, and
that is the behaviour we want rather than an oversight: it lands in
``failed_nodes`` or ``interrupted_nodes``, never in the two sets read here, so
the composer stays held. A graph that quietly composes a client email while the
payroll domain errored is the outcome worth refusing, and the cost of refusing it
is a run that ends with no draft, which is visible and safe.

The union of both surfaces is still read rather than one, because either alone
demonstrates a node ran and neither is documented as authoritative. Failing open
is the one thing this module must not do.
"""

from __future__ import annotations

from collections.abc import Callable


def _node_id(candidate: object) -> str:
    """A node's id, whether the SDK hands back a string or a node object."""
    if isinstance(candidate, str):
        return candidate
    for attribute in ("node_id", "id", "name"):
        value = getattr(candidate, attribute, None)
        if isinstance(value, str):
            return value
    return str(candidate)


def completed_node_ids(state: object) -> frozenset[str]:
    """Which nodes have finished, read from whichever surface the state offers.

    ``results`` is documented as a mapping of node id to result and is the
    primary source. ``completed_nodes`` is the secondary. Both are read and the
    union is taken, because a node present in either has demonstrably run.
    """
    found: set[str] = set()

    results = getattr(state, "results", None)
    if hasattr(results, "keys"):
        found.update(_node_id(key) for key in results.keys())  # noqa: SIM118

    completed = getattr(state, "completed_nodes", None)
    if completed is not None and not isinstance(completed, (str, bytes)):
        try:
            found.update(_node_id(node) for node in completed)
        except TypeError:
            pass

    return frozenset(found)


def all_reported(required: frozenset[str]) -> Callable[[object], bool]:
    """An edge condition: traversable only once every ``required`` node has run.

    Fails closed. An unrecognised state shape yields an empty completed set,
    which yields False, which holds the composer rather than releasing it on an
    assumption about an attribute name.
    """
    if not required:
        raise ValueError("a condition that requires nothing is not a condition")

    def condition(state: object) -> bool:
        return required.issubset(completed_node_ids(state))

    condition.__name__ = "all_reported"
    condition.__doc__ = f"True once all of {sorted(required)} have reported."
    return condition
