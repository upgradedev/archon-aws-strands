"""The hero claim, asserted without the SDK.

J4 says the email is not allowed out until six domains agree. That sentence is
only true if the composer cannot answer without them, so the property under test
is a negative one: **the composer holds no tools.**

An earlier version of the graph gave it a ``candidate()`` lookup. It constructed
fine, CI would have passed, and the six readers would have been decoration. A
test that only builds the graph cannot catch that, so this one reads the wiring
and the source instead.
"""

from __future__ import annotations

import ast
import pathlib

from archon.agents import wiring

GRAPH_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "archon" / "agents" / "graph.py"


def test_there_are_exactly_six_domains():
    assert len(wiring.READERS) == 6
    assert len({r.name for r in wiring.READERS}) == 6


def test_every_reader_has_its_own_tool():
    tools = [r.tool for r in wiring.READERS]
    assert len(set(tools)) == len(tools)


def test_every_reader_feeds_the_composer():
    assert set(wiring.EDGES) == {(r.name, wiring.COMPOSER) for r in wiring.READERS}


def test_the_composer_is_the_only_sink():
    sources = {src for src, _ in wiring.EDGES}
    targets = {dst for _, dst in wiring.EDGES}
    assert targets == {wiring.COMPOSER}
    assert wiring.COMPOSER not in sources


def test_the_composer_declares_no_tools():
    assert wiring.COMPOSER_TOOLS == ()


def test_the_composer_prompt_tells_it_that_the_reports_are_all_it_has():
    assert "your only view" in wiring.COMPOSER_RULES
    assert "hold no tools" in wiring.COMPOSER_RULES


def test_the_composer_is_constructed_with_an_empty_tool_list():
    """Read graph.py itself. The regression this guards is a one-word edit."""
    tree = ast.parse(GRAPH_SRC.read_text(encoding="utf-8"))
    composer_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Agent"
        and any(kw.arg == "name" and _is_composer(kw.value) for kw in node.keywords)
    ]
    assert composer_calls, "no Agent(name=COMPOSER, ...) call found in graph.py"
    for call in composer_calls:
        tools_kw = next((kw for kw in call.keywords if kw.arg == "tools"), None)
        assert tools_kw is not None, "the composer must pass tools explicitly"
        assert isinstance(tools_kw.value, ast.List) and not tools_kw.value.elts, (
            "the composer was given a tool. It would then be able to answer without "
            "reading a single domain report, and the six-domain claim would be false."
        )


def _is_composer(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == "COMPOSER") or (
        isinstance(node, ast.Attribute) and node.attr == "COMPOSER"
    )


def test_readers_are_built_from_the_wiring_not_hardcoded():
    src = GRAPH_SRC.read_text(encoding="utf-8")
    assert "wiring.READERS" in src
    assert "wiring.EDGES" in src
