"""The HTML, hand-written and self-contained.

No template engine and no CDN. Every byte the browser needs is in this file, so
the page renders for someone with no network beyond this host. That is not
minimalism for its own sake: the judging window runs to 2026-10-08 and a page
that depends on somebody else's asset host is a page that can go dark without
anyone noticing.

The colours follow the viewer's own light or dark setting, because a finance
screen someone opens on a Sunday night should not burn their eyes.
"""

from __future__ import annotations

from collections.abc import Callable
from html import escape

from archon.adapters.inbound import Reading
from archon.adapters.ses import Receipt
from archon.agents.draft import ChaseDraft
from archon.agents.gate import Release
from archon.domain.books import Books
from archon.domain.money import fmt
from archon.evidence.compare import Tally

from .. import __version__
from ..agents import wiring
from ..demo import TODAY

CSS = """
:root {
  color-scheme: light dark;
  --bg: #f6f7f9; --card: #ffffff; --ink: #14171f; --muted: #5c6472;
  --line: #e3e6ec; --accent: #1c5d99; --good: #14714a; --bad: #a4262c;
  --warn-bg: #fdf6e3; --warn-line: #e6d5a8;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14161a; --card: #1c1f25; --ink: #e8eaee; --muted: #99a1af;
    --line: #2b2f38; --accent: #7db3e0; --good: #4cc38a; --bad: #f2708a;
    --warn-bg: #2a2418; --warn-line: #4a3f24;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.wrap { max-width: 1120px; margin: 0 auto; padding: 28px 20px 60px; }
header { display: flex; flex-wrap: wrap; gap: 12px; align-items: baseline; margin-bottom: 4px; }
h1 { font-size: 22px; margin: 0; letter-spacing: -0.01em; }
.tag { color: var(--muted); font-size: 13px; }
.lede { color: var(--muted); margin: 6px 0 24px; max-width: 78ch; font-size: 15px; }
.grid { display: grid; gap: 14px; grid-template-columns: repeat(3, 1fr); }
@media (max-width: 860px) { .grid { grid-template-columns: repeat(2, 1fr); } }
/* Two across on a phone, not one. Six full-height cards stacked means scrolling
   past everything before reaching anything that can be acted on, and this is a
   screen someone opens standing up. */
@media (max-width: 520px) {
  .grid { gap: 10px; }
  .tile { padding: 11px 12px; }
  .tile .v { font-size: 18px; }
  .tile .s { font-size: 11px; }
  .wrap { padding: 18px 14px 44px; }
  h1 { font-size: 20px; }
  .lede { font-size: 14px; }
  .card { padding: 14px 15px; }
}
@media (max-width: 340px) { .grid { grid-template-columns: 1fr; } }
.tile { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.tile .k { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }
.tile .v { font-size: 21px; font-weight: 600; margin: 4px 0 2px; font-variant-numeric: tabular-nums; }
.tile .s { color: var(--muted); font-size: 12px; }
.cols { display: grid; gap: 18px; grid-template-columns: 1fr 1fr; margin-top: 22px; }
@media (max-width: 860px) { .cols { grid-template-columns: 1fr; } }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 18px 20px; }
.card h2 { font-size: 15px; margin: 0 0 4px; }
.card .why { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
pre { margin: 0; white-space: pre-wrap; font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.domain { border-top: 1px solid var(--line); padding: 10px 0; }
.domain:first-of-type { border-top: 0; }
.domain .n { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.mail { border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; background: var(--bg); }
.mail .hdr { color: var(--muted); font-size: 12px; border-bottom: 1px solid var(--line);
  padding-bottom: 8px; margin-bottom: 10px; }
.claim { display: flex; gap: 10px; align-items: flex-start; padding: 6px 0; }
.check { color: var(--good); font-weight: 700; flex: none; }
.free { color: var(--muted); font-style: italic; }
.verdict { border-radius: 8px; padding: 12px 14px; margin: 14px 0; font-size: 14px; }
.ok { background: color-mix(in srgb, var(--good) 12%, transparent); border: 1px solid var(--good); }
.held { background: color-mix(in srgb, var(--bad) 10%, transparent); border: 1px solid var(--bad); }
.note { background: var(--warn-bg); border: 1px solid var(--warn-line); border-radius: 8px;
  padding: 12px 14px; margin: 14px 0; font-size: 13px; }
button { font: inherit; border-radius: 8px; padding: 9px 15px; cursor: pointer; border: 1px solid var(--line);
  background: var(--card); color: var(--ink); }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
.row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-top: 6px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; margin-top: 8px; }
th, td { text-align: right; padding: 8px 10px; border-bottom: 1px solid var(--line); font-variant-numeric: tabular-nums; }
th:first-child, td:first-child { text-align: left; }
thead th { color: var(--muted); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }
tr.us td { font-weight: 600; }
.scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
@media (max-width: 520px) {
  th, td { padding: 7px 8px; font-size: 12px; }
  /* Let it overflow its own box and scroll, rather than squeezing "Cafe on the
     corner" onto three lines and "55 days late" onto two. A cramped table is
     harder to read than one you slide. */
  .scroll table { min-width: 460px; }
  td { white-space: nowrap; }
}
footer { color: var(--muted); font-size: 12px; margin-top: 30px; border-top: 1px solid var(--line); padding-top: 14px; }
textarea { width: 100%; font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: var(--bg); color: var(--ink); border: 1px solid var(--line); border-radius: 8px;
  padding: 12px; resize: vertical; }
input[type=file] { font: 13px inherit; color: var(--muted); max-width: 100%; }
.view { display: flex; gap: 12px; align-items: flex-start; padding: 12px 0;
  border-top: 1px solid var(--line); font-size: 13.5px; line-height: 1.5; }
.view:first-of-type { border-top: 0; }
.badge { flex: none; font-size: 10px; font-weight: 700; letter-spacing: .06em; padding: 3px 7px;
  border-radius: 5px; margin-top: 2px; }
.badge.urgent { background: color-mix(in srgb, var(--bad) 18%, transparent); color: var(--bad);
  border: 1px solid var(--bad); }
.badge.watch { background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--accent);
  border: 1px solid var(--accent); }
.badge.fine { background: color-mix(in srgb, var(--good) 14%, transparent); color: var(--good);
  border: 1px solid var(--good); }
.vn { font-weight: 600; font-size: 13px; }
.vq { color: var(--muted); font-size: 12px; margin-bottom: 6px; font-style: italic; }
details.card > summary { cursor: pointer; font-size: 15px; list-style: none; }
details.card > summary::-webkit-details-marker { display: none; }
details.card > summary::before { content: "▸ "; color: var(--muted); }
details.card[open] > summary::before { content: "▾ "; }
details.card > summary strong { font-weight: 600; }
code { font: 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: var(--bg); padding: 1px 5px; border-radius: 4px; border: 1px solid var(--line); }
"""


def _tiles(stats: list[tuple[str, str, str]]) -> str:
    cells = "".join(
        f'<div class="tile"><div class="k">{escape(k)}</div>'
        f'<div class="v">{escape(v)}</div><div class="s">{escape(s)}</div></div>'
        for k, v, s in stats
    )
    return f'<section class="grid">{cells}</section>'


def _delivery(record) -> str:
    """What is actually known about the one email, and what is not.

    Five states, kept apart on purpose. A provider handing back an identifier is
    acceptance by that provider; it is not evidence that anything arrived in
    anybody's inbox. Collapsing the two would let this screen tell its owner a
    debt was chased when all that happened was an API said "received".
    """
    if record is None:
        return ""

    said = {
        "queued": (
            "held",
            "Written down and not yet sent.",
            "The record exists so that a process dying here cannot lose the attempt.",
        ),
        "unknown": (
            "held",
            "Sent, and nobody knows whether it arrived.",
            "The connection did not answer. It may well have gone. Nothing is tried again "
            "on its own, because a second demand for money cannot be recalled. Check the "
            "mailbox, then clear this deliberately.",
        ),
        "provider-accepted": (
            "sent",
            "Accepted by Amazon SES.",
            "That is the provider saying it has the message. It is not evidence that anyone "
            "received it, and this screen will not pretend otherwise.",
        ),
        "delivered": (
            "sent",
            "Delivered, with evidence.",
            "Nothing here can produce this today. It exists so the difference from provider "
            "acceptance stays visible rather than being quietly assumed.",
        ),
        "failed": (
            "held",
            "Refused by the provider.",
            "SES answered and said no, so nothing was sent and trying again is safe.",
        ),
    }
    tone, headline, detail = said.get(
        record.state, ("held", f"State {record.state!r}.", "This state has no explanation, which is itself worth looking at.")
    )
    return (
        f'<div class="verdict {tone}" style="margin-top:14px">'
        f"<strong>{escape(headline)}</strong>"
        f'<div class="why" style="margin-top:6px">{escape(detail)}</div>'
        f'<div class="why" style="margin-top:8px">'
        f"invoice {escape(record.invoice_id)} &middot; {escape(record.amount)} &middot; "
        f"to {escape(record.to_address)}"
        + (f" &middot; provider id {escape(record.message_id)}" if record.message_id else "")
        + "</div></div>"
    )


def _queue(q) -> str:
    """What to do next, and what nobody can do yet.

    Both halves are on the page. The second is the one tools like this leave out,
    and leaving it out is what makes them untrustworthy: an invoice with no reply
    address quietly disappears, the owner never learns it exists, and the screen
    looks tidy while the money sits there.
    """
    def row(item, blocked=False):
        late = (
            f'<span class="late">{item.days_overdue} days late</span>'
            if item.days_overdue and not blocked
            else f"{item.days_overdue} days late"
            if item.days_overdue
            else "not late"
        )
        tail = (
            f'<td class="why">{escape(item.reason)}</td>'
            if blocked
            else f"<td>{escape(item.recipient)}</td>"
        )
        return (
            f"<tr><td>{escape(item.invoice_id)}</td><td>{escape(item.client)}</td>"
            f"<td>{fmt(item.outstanding)}</td><td>{late}</td>{tail}</tr>"
        )

    ready = "".join(row(i) for i in q.ready) or (
        '<tr><td colspan="5" class="why">Nothing can be chased today.</td></tr>'
    )
    blocked = "".join(row(i, blocked=True) for i in q.blocked)
    blocked_block = (
        '<p class="why" style="margin-top:18px"><strong>Waiting on somebody, not on Archon.</strong> '
        "These are not chased and not forgotten. Each line says the one thing that has to change, "
        "and none of it is guessed at.</p>"
        '<div class="scroll"><table><thead><tr><th>invoice</th><th>client</th><th>amount</th>'
        f"<th>age</th><th>what is missing</th></tr></thead><tbody>{blocked}</tbody></table></div>"
        if blocked
        else ""
    )
    return (
        '<div class="card" style="margin-top:18px"><strong>What is worth doing next</strong>'
        f'<p class="why">{fmt(q.at_stake)} can be chased today, oldest first. '
        "The order is arithmetic on the ledger: age, then size. No model ranks this, because a "
        "ranking nobody can check against the books is not a ranking.</p>"
        '<div class="scroll"><table><thead><tr><th>invoice</th><th>client</th><th>amount</th>'
        f"<th>age</th><th>chase goes to</th></tr></thead><tbody>{ready}</tbody></table></div>"
        f"{blocked_block}</div>"
    )


def _reasoning(reasoning) -> str:
    """Say what produced the tone, in the three states it can be in.

    The screen used to show a constant and let a visitor assume six agents had
    reasoned about their books. Whatever else is true, this must not be.
    """
    if reasoning.is_live:
        rows = "".join(
            f'<div class="row" style="align-items:flex-start;gap:10px;margin-top:10px">'
            f'<span class="pill {v.verdict.lower()}">{escape(v.verdict)}</span>'
            f"<div><strong>{escape(v.name)}</strong>"
            f'<div class="why">{escape(v.body[:240])}</div></div></div>'
            for v in reasoning.views
        )
        return (
            '<div class="card" style="margin-top:18px"><strong>What the six of them made of it</strong>'
            '<p class="why">Six agents reasoned about these books on Bedrock just now. They are asked '
            "what only a reader of that domain can judge, and they disagree.</p>"
            f"{rows}</div>"
        )
    if reasoning.failed:
        return (
            '<div class="verdict held" style="margin-top:18px">'
            "<strong>A live run was asked for and Bedrock could not be reached.</strong>"
            f'<div class="why" style="margin-top:6px">{escape(reasoning.error or "")}</div>'
            '<div class="why">The tone below is the scripted one this page already had. '
            "Nothing reasoned. It is said here rather than left for you to assume.</div></div>"
        )
    return (
        '<div class="card" style="margin-top:18px"><strong>No model has reasoned yet</strong>'
        '<p class="why">The two lines of tone below are a constant, not an agent\'s judgement. '
        "The books, the figures and the refusals are all real and computed; only the wording is "
        "canned. Ask the six agents to look, and they will run on Bedrock, which takes about "
        "thirteen seconds and costs money, which is why it is a button.</p>"
        '<form method="post" action="/reason"><button class="primary" type="submit">'
        "Ask the six agents, on Bedrock</button></form></div>"
    )


def _provenance(books: Books) -> str:
    """Where every figure came from, laid out so the claim can be checked.

    The ledger has always carried this: an entry cannot be posted without naming
    the document it came from, and `Ledger.by_source` walks it back. It has never
    been on screen, so "every number walks back to the email that produced it"
    was a sentence a reader had to take on trust from a project whose entire
    argument is that nobody should have to.
    """
    rows = ""
    for entry in books.ledger.entries:
        postings = ", ".join(
            f"{p.account.value} {fmt(abs(p.amount))} {p.side.value[:2]}" for p in entry.postings
        )
        rows += (
            f"<tr><td><code>{escape(entry.source_ref)}</code></td>"
            f"<td>{escape(entry.entry_id)}</td>"
            f"<td>{entry.on}</td>"
            f"<td>{escape(entry.narrative)}</td>"
            f"<td>{escape(postings)}</td></tr>"
        )
    return (
        '<details class="card" style="margin-top:18px"><summary><strong>Where every figure came '
        'from</strong></summary>'
        f'<p class="why">{len(books.ledger.entries)} entries, each naming the email it arrived in. '
        "An entry cannot be posted without one, and debits and credits have to agree before it is "
        f"posted at all: the trial balance below is {books.ledger.trial_balance()}, and any other "
        "value would mean this table is lying.</p>"
        '<div class="scroll"><table><thead><tr><th>from</th><th>entry</th><th>on</th>'
        "<th>what</th><th>posted</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div></details>"
    )


def _open_items(books: Books) -> str:
    """The actual lines, which is what someone scans for.

    The tiles say how much is owed; this says by whom and when. Replacing the
    old monospace dump with the six views alone lost that, and "you are owed
    3,860.00" without a name is a number nobody can act on.
    """
    rows = ""
    for item in books.uncollected():
        late = item.days_overdue(TODAY)
        state = (
            f'<span style="color:var(--bad)">{late} days late</span>'
            if late
            else f"due {item.due}"
        )
        part = f"{fmt(item.settled)} received" if item.settled else ""
        rows += (
            f"<tr><td>owed to you</td><td>{escape(item.counterparty)}</td>"
            f"<td>{fmt(item.outstanding)}</td><td>{state}</td><td>{part}</td></tr>"
        )
    for item in books.owed_to_suppliers():
        rows += (
            f"<tr><td>you owe</td><td>{escape(item.counterparty)}</td>"
            f"<td>{fmt(item.outstanding)}</td><td>due {item.due}</td><td></td></tr>"
        )
    for run in books.payroll_unpaid():
        rows += (
            f"<tr><td>wages</td><td>{escape(run.period)}</td><td>{fmt(run.gross)}</td>"
            f"<td>run {run.run_on}</td><td>not paid</td></tr>"
        )
    if not rows:
        return ""
    return (
        '<div class="card" style="margin-top:18px"><h2>What is actually open</h2>'
        '<p class="why">Every line came from a document, and every document named the email it '
        "arrived in.</p>"
        '<div class="scroll"><table><thead><tr><th></th><th>who</th><th>amount</th>'
        "<th>when</th><th></th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div></div>"
    )


def _views(views: list, captured_on: str | None) -> str:
    """The six judgements, most pressing first.

    This card used to be the tools' own output in monospace, which is what the
    stat tiles above already say in numbers. The interesting thing the product
    does is the reading of it, so that is what is on screen.
    """
    if not views:
        return ""
    rows = ""
    for view in views:
        rows += (
            f'<div class="view"><span class="badge {view.verdict.lower()}">'
            f"{escape(view.verdict)}</span>"
            f'<div><div class="vn">{escape(view.name)}</div>'
            f'<div class="vq">{escape(view.question)}</div>'
            f"<div>{escape(view.body)}</div></div></div>"
        )
    provenance = (
        f"Captured from a real Bedrock run on {escape(captured_on)} and committed to the "
        "repository, because the offline model walks the graph and does not judge, and six "
        "identical placeholders would say something untrue about what this does."
        if captured_on
        else "From this run, just now."
    )
    return (
        '<div class="card"><h2>What the six of them made of it</h2>'
        f'<p class="why">One agent per domain, each asked something only a reader of that '
        f"domain can answer, each told a colleague may disagree. {provenance}</p>"
        f"{rows}</div>"
    )


def _mail(draft: ChaseDraft, verdict: Release) -> str:
    claims = "".join(
        f'<div class="claim"><span class="check">&#10003;</span>'
        f"<span>{escape(claim.sentence())}</span></div>"
        for claim in draft.claims
    )
    verdict_class = "ok" if verdict.allowed else "held"
    reasons = "".join(f"<div>{escape(reason)}</div>" for reason in verdict.reasons)
    action = (
        f'<form method="post" action="/approve" class="row">'
        f'<input type="hidden" name="fingerprint" value="{escape(draft.fingerprint())}">'
        f'<button class="primary" type="submit">Approve and send this exact text</button>'
        f"</form>"
        if verdict.allowed
        else '<div class="row"><button disabled>Held. Nothing will be sent.</button></div>'
    )
    return f"""
    <div class="card">
      <h2>The one thing it will do</h2>
      <p class="why">The greeting and the sign-off are the agent's. Every figure is a claim the ledger
      confirmed, and the draft is refused outright if the agent's own words contain a digit.</p>
      <div class="mail">
        <div class="hdr">To: {escape(draft.to_address)}<br>Subject: {escape(draft.subject)}</div>
        <div class="free">{escape(draft.opening)}</div>
        <div style="margin:10px 0">{claims}</div>
        <div class="free">{escape(draft.closing)}</div>
      </div>
      <div class="verdict {verdict_class}"><strong>{"Released" if verdict.allowed else "Held"}</strong>
        <div style="margin-top:6px">{reasons}</div></div>
      {action}
      <div class="row">
        <form method="post" action="/pay"><button type="submit">The client pays at lunchtime</button></form>
        <form method="post" action="/reset"><button type="submit">Start the month again</button></form>
      </div>
      <p class="why" style="margin-top:10px">Press <em>the client pays at lunchtime</em> and part of the
      money arrives after this draft was written. The chase is still owed, for less. Then try to send
      the one you were reading.</p>
    </div>
    """


def _sent(receipt: Receipt) -> str:
    return f"""
    <div class="card">
      <h2>Sent</h2>
      <p class="why">One email left, to the address on the invoice, after a human approved that exact text.</p>
      <div class="verdict ok">
        <div>to {escape(receipt.to_address)}</div>
        <div>message id <code>{escape(receipt.message_id)}</code></div>
        <div>fingerprint <code>{escape(receipt.fingerprint[:24])}...</code></div>
      </div>
      <p class="why">Asking again returns this same receipt rather than sending a second time. A client
      who receives the same demand for money twice in a minute is a client who telephones.</p>
      <form method="post" action="/reset" class="row"><button type="submit">Start the month again</button></form>
    </div>
    """


def _nothing_due() -> str:
    return """
    <div class="card">
      <h2>Nothing is overdue</h2>
      <p class="why">So there is no chase to write, and saying nothing is the right answer. That is a
      result, not an absence: chasing a client who has paid is the expensive mistake.</p>
      <form method="post" action="/reset" class="row"><button type="submit">Start the month again</button></form>
    </div>
    """


def _evidence(rows: list[tuple[Tally, tuple[float, float]]]) -> str:
    body = ""
    for tally, (low, high) in rows:
        cls = ' class="us"' if tally.method == "Archon" else ""
        body += (
            f"<tr{cls}><td>{escape(tally.method)}</td><td>{tally.wrong_money}</td>"
            f"<td>{tally.missed}</td><td>{tally.correct}</td>"
            f"<td>{low:.0%} to {high:.0%}</td></tr>"
        )
    body += (
        '<tr><td>a real Claude model, one pass, no ledger</td><td>0</td><td>3</td><td>17</td>'
        "<td>0% to 16%</td></tr>"
    )
    return f"""
    <div class="card" style="margin-top:18px">
      <h2>Twenty months of one firm's post, every answer known in advance</h2>
      <p class="why">Wrong money is an email demanding a figure that is not owed; it reaches a client and
      cannot be recalled. A missed chase is silence where money was owed. Both are shown, because a
      method that never sends anything scores zero on the first.</p>
      <div class="scroll"><table>
        <thead><tr><th>method</th><th>wrong money</th><th>missed</th><th>correct</th>
          <th>95% CI, wrong money</th></tr></thead>
        <tbody>{body}</tbody>
      </table></div>
      <p class="why" style="margin-top:12px">The live row is the one that is not ours. A frontier model
      reading the same post gets no figure wrong and goes quiet on three months where money was owed,
      and <strong>nothing in its answer tells you which three</strong>. Re-run it yourself with
      <code>python -m archon.evidence.compare</code>.</p>
    </div>
    """


def _inbox(sample: str, reading: Reading | None, error: str | None) -> str:
    """Where a visitor does the thing the owner would actually do."""
    if error:
        outcome = (
            f'<div class="verdict held"><strong>Not posted</strong>'
            f'<div style="margin-top:6px">{escape(error)}</div>'
            "<div style=\"margin-top:6px\">The ledger checks the reader, not the other way "
            "round. Nothing that does not add up reaches the books.</div></div>"
        )
    elif reading is not None:
        doc = reading.document
        hidden = ", ".join(reading.redacted_categories) or "nothing"
        outcome = (
            f'<div class="verdict ok"><strong>Posted</strong>'
            f"<div style=\"margin-top:6px\">{escape(type(doc).__name__)} "
            f"<code>{escape(doc.doc_id)}</code></div>"
            f"<div>hidden before the reader saw it: {reading.redactions} items, {escape(hidden)}</div>"
            "</div>"
        )
    else:
        outcome = ""
    return f"""
    <div class="card" style="margin-top:18px">
      <h2>Forward it an email</h2>
      <p class="why">Redacted on this machine first, then read for fields only, then checked by the
      ledger. Offline the reading is done by rules and no model is called, which the result says.
      Try changing a figure so the total stops adding up.</p>
      <form method="post" action="/post">
        <textarea name="body" rows="9" spellcheck="false">{escape(sample)}</textarea>
        <div class="row"><button class="primary" type="submit">Put this in the books</button></div>
      </form>
      <form method="post" action="/upload" enctype="multipart/form-data" class="row"
            style="margin-top:14px; border-top:1px solid var(--line); padding-top:14px">
        <input type="file" name="attachment" accept=".pdf,.txt,.eml">
        <button type="submit">Read an attached invoice</button>
      </form>
      <p class="why" style="margin-top:8px">A PDF is opened here, not sent. The text is pulled out and
      redacted on this machine, and only the redacted text goes to the model, because redaction cannot
      reach inside a file. A scan is refused rather than guessed at.</p>
      {outcome}
    </div>
    """


def broke(detail: str) -> str:
    """The page when something unexpected failed.

    Same shell, same colours, so it reads as this product rather than as the
    web server underneath it. It says what failed and what did not happen,
    because a blank "Internal Server Error" on a demonstration says neither.
    """
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Archon</title><style>{CSS}</style></head>
<body><div class="wrap">
  <header><h1>Archon</h1><span class="tag">something went wrong, and here is what</span></header>
  <div class="verdict held" style="margin-top:18px">
    <strong>The screen failed. Nothing was sent and nothing was written.</strong>
    <div style="margin-top:8px"><code>{escape(detail)}</code></div>
  </div>
  <p class="lede">The books are unchanged: every route that changes them commits or fails as a whole,
  and the one write needs a human approval that no failure can supply. Start the month again below, or
  reload; if it keeps happening the fault is in the code rather than in what you did.</p>
  <form method="post" action="/reset" class="row"><button class="primary" type="submit">Start the month again</button></form>
  <footer>This page shows the fault because it is a demonstration running against an invented firm.
  A deployment holding real books would log it and tell you only that something failed.</footer>
</div></body></html>"""


def page(
    *,
    reasoning,
    queue,
    delivery=None,
    books: Books,
    stats: list[tuple[str, str, str]],
    draft: ChaseDraft | None,
    verdict_for: Callable[[ChaseDraft], Release],
    receipt: Receipt | None,
    refusal: str | None,
    views: list | None = None,
    captured_on: str | None = None,
    reading: Reading | None = None,
    reading_error: str | None = None,
    sample: str = "",
    evidence: list[tuple[Tally, tuple[float, float]]],
) -> str:
    if receipt is not None:
        right = _sent(receipt)
    elif draft is None:
        right = _nothing_due()
    else:
        right = _mail(draft, verdict_for(draft))

    note = f'<div class="note">{escape(refusal)}</div>' if refusal else ""
    overdue = books.worst_overdue(TODAY)
    hero = (
        f"{escape(overdue.counterparty)} owes {fmt(overdue.outstanding)}, "
        f"{overdue.days_overdue(TODAY)} days late, and has already paid {fmt(overdue.settled)} of it."
        if overdue
        else "Every invoice on file is settled or not yet due."
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Archon</title><style>{CSS}</style></head>
<body><div class="wrap">
  <header><h1>Archon</h1><span class="tag">the back office that lives in an inbox</span></header>
  <p class="lede">{hero} Nine documents arrived this quarter. Nobody typed any of this in.</p>
  {note}
  {_tiles(stats)}
  {_open_items(books)}
  <div class="cols">{_views(views, captured_on)}{right}</div>
  {_inbox(sample, reading, reading_error)}
  {_delivery(delivery)}
  {_queue(queue)}
  {_reasoning(reasoning)}
  {_provenance(books)}
  {_evidence(evidence)}
  <footer>
    Archon {escape(__version__)} &middot; six Strands agents, one per domain, and the composer holds no
    tools: every edge into it waits for all {len(wiring.REQUIRED_REPORTS)} reports.
    Running offline against an invented firm; no customer data is present anywhere in this repository.
  </footer>
</div></body></html>"""
