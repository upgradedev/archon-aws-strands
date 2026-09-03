"""What the agents are allowed to look at.

Every tool is a read. Nothing here posts, sends or mutates, which means no
sequence of tool calls an agent invents can change the books or reach a client.
The only write in Archon goes through ``archon.agents.gate`` and needs a human
fingerprint, and that asymmetry is deliberate: the blast radius of a confused
agent is bounded by what its tools can do, not by what its prompt tells it.
"""

from __future__ import annotations

from datetime import date

from archon.domain.books import Books
from archon.domain.money import fmt
from archon.domain.reports import cashflow, metrics, profit_and_loss


def supplier_position(books: Books) -> str:
    """1. What suppliers have billed, and which of it is still owed."""
    owed = books.owed_to_suppliers()
    if not owed:
        return "Every supplier invoice on file has been paid."
    lines = [f"{len(owed)} supplier invoice(s) still open:"]
    lines += [
        f"  {s.doc_id} {s.counterparty}: {fmt(s.outstanding)} of {fmt(s.gross)}, due {s.due}"
        for s in owed
    ]
    return "\n".join(lines)


def sales_position(books: Books, as_of: date) -> str:
    """3 and 4. What was invoiced, and what has actually come in."""
    open_items = books.uncollected()
    if not open_items:
        return "Every sales invoice on file has been collected."
    lines = [f"{len(open_items)} sales invoice(s) still open:"]
    for s in open_items:
        state = f"{s.days_overdue(as_of)} days overdue" if s.is_overdue(as_of) else f"due {s.due}"
        received = f", {fmt(s.settled)} received so far" if s.settled else ""
        lines.append(
            f"  {s.doc_id} {s.counterparty}: {fmt(s.outstanding)} outstanding, {state}{received}"
        )
    return "\n".join(lines)


def payroll_position(books: Books) -> str:
    """5. Whether the staff have been paid."""
    unpaid = books.payroll_unpaid()
    if not unpaid:
        return "Staff are paid up to date."
    lines = ["Payroll not yet paid:"]
    lines += [
        f"  {run.doc_id} {run.period}: {fmt(run.gross)}, run on {run.run_on}" for run in unpaid
    ]
    return "\n".join(lines)


def trading_position(books: Books, frm: date, to: date) -> str:
    """6a. The P&L for a window."""
    pnl = profit_and_loss(books, frm, to)
    margin = "no sales, so no margin" if pnl.margin is None else f"margin {pnl.margin:.2%}"
    return (
        f"From {frm} to {to}: sales {fmt(pnl.sales)}, purchases {fmt(pnl.purchases)}, "
        f"wages {fmt(pnl.wages)}, profit {fmt(pnl.profit)} ({margin})."
    )


def cash_position(books: Books, frm: date, to: date) -> str:
    """6b. What actually moved through the bank, which is not profit."""
    cf = cashflow(books, frm, to)
    return (
        f"From {frm} to {to}: opening {fmt(cf.opening)}, in {fmt(cf.inflow)}, "
        f"out {fmt(cf.outflow)}, closing {fmt(cf.closing)}."
    )


def headline_metrics(books: Books, as_of: date) -> str:
    """6c. The handful of numbers the owner actually looks at."""
    m = metrics(books, as_of)
    staff = "staff are paid" if m.staff_paid else f"{fmt(m.owed_to_staff)} of wages unpaid"
    return (
        f"As at {as_of}: bank {fmt(m.bank)}, owed by clients {fmt(m.owed_by_clients)}, "
        f"owed to suppliers {fmt(m.owed_to_suppliers)}, {staff}. "
        f"{m.overdue_count} invoice(s) overdue totalling {fmt(m.overdue_amount)}, "
        f"the oldest by {m.oldest_overdue_days} days. "
        f"Working capital {fmt(m.working_capital)}."
    )


def chase_candidate(books: Books, as_of: date) -> str:
    """The single receivable a chase would be about, or nothing.

    Deliberately returns the worst one rather than a list. An agent handed a
    list will pick, and picking is the judgment this tool exists to remove: the
    oldest unpaid debt is not a matter of opinion.
    """
    worst = books.worst_overdue(as_of)
    if worst is None:
        return "Nothing is overdue. There is no chase to write."
    return (
        f"{worst.doc_id} to {worst.counterparty}: {fmt(worst.outstanding)} outstanding "
        f"of {fmt(worst.gross)}, {worst.days_overdue(as_of)} days overdue, "
        f"{fmt(worst.settled)} received so far."
    )
