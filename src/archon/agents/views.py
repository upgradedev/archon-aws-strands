"""The six views, and how the screen gets hold of them.

A reader returns prose ending in URGENT, WATCH or FINE. This turns that into
something a page can lay out without the page having to parse a model's writing,
and it does the parsing in one place so there is one answer to "what did payroll
think" rather than one per caller.

**Offline it serves a captured run rather than inventing one.** The scripted
model walks the graph; it does not judge, and six identical placeholder
paragraphs on screen would be a lie about what the product does. So the offline
screen shows what the six agents actually said on a real run, dated, labelled as
captured, and committed to the repository so anyone can read the whole thing.
Running with Bedrock replaces it with today's.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass

from . import wiring

#: A real run, committed so the offline screen shows judgement rather than a stub.
CAPTURED = pathlib.Path(__file__).resolve().parents[3] / "evidence" / "SIX-VIEWS-2026-09-05.txt"
CAPTURED_ON = "2026-09-05"

_VERDICT = re.compile(r"\b(URGENT|WATCH|FINE)\b")
_PARAGRAPH = re.compile(r"\n\s*\n")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_SPACES = re.compile(r"\s+")
_LABEL = re.compile(r"^(assessment|verdict|view|conclusion)\s*[:\-]\s*", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class View:
    """What one reader made of its domain."""

    name: str
    question: str
    body: str
    verdict: str

    @property
    def rank(self) -> int:
        """URGENT first. A page sorted by domain buries the thing that matters."""
        return {"URGENT": 0, "WATCH": 1, "FINE": 2}.get(self.verdict, 3)


def _verdict_of(text: str) -> str:
    """The last verdict word in the text.

    The last rather than the first: a reader that writes "this is not URGENT but
    something to WATCH" means the second one, and taking the first inverts it.
    """
    found = _VERDICT.findall(text)
    return found[-1] if found else "FINE"


def _assessment(text: str) -> str:
    """The judgement, not the restatement.

    A reader answers in two parts and the screen already shows the first: the
    tool's own output is on the page beside this. What is wanted here is the
    last paragraph, which is the view, with the markdown a model reaches for
    stripped off so a page can lay it out without rendering tables nobody asked
    for.
    """
    body = _VERDICT.sub("", text)
    paragraphs = [p.strip() for p in _PARAGRAPH.split(body) if p.strip()]
    # A view is prose. Skip the tables and headings a model puts above it.
    prose = [p for p in paragraphs if p.count("|") < 3 and not p.lstrip().startswith("#")]
    last = (prose or paragraphs or [""])[-1]
    last = _BOLD.sub(r"\1", last).replace("---", "").replace("*", "").strip()
    last = _SPACES.sub(" ", last)
    # Models label their own conclusion. The page already says these are views,
    # so "Assessment:" in front of every one of six is noise.
    last = _LABEL.sub("", last).strip()
    return (last.rstrip(" .,;:") + ".") if last else ""


def parse(name: str, body: str) -> View:
    reader = next((r for r in wiring.READERS if r.name == name), None)
    return View(
        name=name,
        question=reader.question if reader else "",
        body=_assessment(body),
        verdict=_verdict_of(body),
    )


def from_transcript(text: str) -> list[View]:
    """Read the committed capture, or a fresh run written in the same shape."""
    views: list[View] = []
    for block in text.split("### ")[1:]:
        head, _, body = block.partition("\n")
        name = head.strip()
        if name in wiring.REQUIRED_REPORTS:
            views.append(parse(name, body.strip()))
    return sorted(views, key=lambda view: view.rank)


def captured() -> list[View]:
    """The six views from the committed run. Empty if it is not there."""
    if not CAPTURED.exists():  # pragma: no cover - the file is committed
        return []
    return from_transcript(CAPTURED.read_text(encoding="utf-8"))


def from_graph_result(result: object) -> list[View]:
    """The six views from a live run, in the same shape as the capture."""
    views: list[View] = []
    for node, outcome in (getattr(result, "results", {}) or {}).items():
        name = str(getattr(node, "node_id", node))
        if name not in wiring.REQUIRED_REPORTS:
            continue
        message = getattr(getattr(outcome, "result", None), "message", None)
        text = ""
        if isinstance(message, dict):
            text = " ".join(
                block.get("text", "") for block in message.get("content", []) if "text" in block
            )
        if text.strip():
            views.append(parse(name, text.strip()))
    return sorted(views, key=lambda view: view.rank)
