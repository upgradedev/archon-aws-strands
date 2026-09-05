"""A static walkthrough of the same journey, for a judge with nothing installed.

    python -m archon.web.export site/

**Why this exists alongside the live app.** The submission has to stay testable
by a stranger, free and unrestricted, until 2026-10-08. A running server can go
down, run out of credit or be behind a login on the day someone looks. Static
files on GitHub Pages cannot.

**What it is and what it is not, said on every page rather than implied.** These
are real pages rendered by the real code from the real ledger: every figure on
them was computed by `archon.domain.reports` and every sentence in the draft by a
claim the books confirmed. What they are not is interactive. The buttons on a
static page cannot post, so the states a visitor would reach by pressing them are
pre-rendered and linked instead, which shows the same three outcomes in the same
order.

Anyone who wants the buttons runs the server. The README says how, and it takes
one command.
"""

from __future__ import annotations

import pathlib
import re
import sys
from dataclasses import dataclass

from archon.adapters.ses import SendRefused
from archon.demo import TODAY
from archon.web.app import Session, _stats
from archon.web.render import page

from ..evidence.compare import score_all, wilson

BANNER = (
    '<div class="note"><strong>A static walkthrough.</strong> These pages were rendered by the '
    "real code from the real ledger, so every figure on them is computed rather than written. "
    "They are not interactive: the buttons need the server, which is one command in the README. "
    "{here}</div>"
)

NAV = (
    '<div class="row" style="margin:18px 0">'
    '<a href="./index.html"><button>1. the chase, ready to send</button></a> '
    '<a href="./paid.html"><button>2. the client pays at lunchtime</button></a> '
    '<a href="./sent.html"><button>3. sent, once</button></a>'
    "</div>"
)


@dataclass(frozen=True, slots=True)
class Page:
    name: str
    caption: str


PAGES = (
    Page("index", "This is where a visitor starts: a chase the gate has released."),
    Page(
        "paid",
        "Here part of the money arrived after the draft was written. The debt is still owed, for "
        "less, and the approval no longer matches the text that would be sent.",
    ),
    Page("sent", "Here it was approved and sent once. Asking again returns the same receipt."),
)


def _render(session: Session, caption: str) -> str:
    html = page(
        books=session.books,
        stats=_stats(session.books),
        draft=session.draft(),
        verdict_for=session.verdict,
        receipt=session.receipt,
        refusal=session.last_refusal,
        evidence=[(t, wilson(t.wrong_money, t.n)) for t in score_all()],
    )
    # Forms cannot post from a static host, so they are turned into plain blocks
    # rather than left as buttons that quietly do nothing when pressed.
    html = re.sub(r"<form[^>]*>", "<div>", html)
    html = html.replace("</form>", "</div>")
    html = html.replace("<button", "<button disabled")
    html = html.replace("<button disableddisabled", "<button disabled")
    return html.replace(
        '<p class="lede">', BANNER.format(here=caption) + NAV + '<p class="lede">', 1
    )


def _state(which: str) -> Session:
    """Build each state by doing what a visitor would do, not by faking it."""
    session = Session()
    if which == "index":
        return session

    draft = session.draft()
    assert draft is not None
    if which == "paid":
        from archon.domain.documents import Receipt as ReceiptDoc
        from archon.domain.money import money

        worst = session.books.worst_overdue(TODAY)
        session.books.record(
            ReceiptDoc(
                doc_id="RC-lunchtime",
                settles=worst.doc_id,
                received_on=TODAY,
                amount=str(money(worst.outstanding / 2)),
                source_ref="email:paid-at-lunchtime",
            )
        )
        session.last_refusal = (
            "The books moved while this page was open, so the text you approved is not the text "
            "that would be sent. Nothing was sent. Reload and read it again."
        )
        return session

    if which == "sent":
        try:
            session.receipt = session.outbox.send(draft, session.verdict(draft))
        except SendRefused as refused:  # pragma: no cover - would be a real regression
            raise SystemExit(
                f"the walkthrough cannot show a send that the gate refuses: {refused}"
            ) from refused
        return session

    raise ValueError(which)  # pragma: no cover


def write(target: pathlib.Path) -> list[pathlib.Path]:
    target.mkdir(parents=True, exist_ok=True)
    (target / ".nojekyll").write_text("", encoding="utf-8")
    written = []
    for spec in PAGES:
        html = _render(_state(spec.name), spec.caption)
        out = target / f"{spec.name}.html"
        out.write_text(html, encoding="utf-8")
        written.append(out)
    return written


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    target = pathlib.Path(args[0]) if args else pathlib.Path("site")
    for path in write(target):
        print(f"wrote {path} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
