"""What the agents are shown.

These strings are the agent's entire view of the business, so a wrong one is a
wrong decision. They are asserted on content, not merely on not raising.
"""

from datetime import date

from archon.agents import tools
from archon.domain.books import Books

TODAY = date(2026, 9, 3)
FRM = date(2026, 7, 1)


def test_supplier_position_names_the_open_invoice(books):
    out = tools.supplier_position(books)
    assert "PI-002" in out and "Van Leasing B" in out and "496.00 EUR" in out
    assert "PI-001" not in out  # paid, so not "still open"


def test_supplier_position_when_everything_is_paid():
    assert "has been paid" in tools.supplier_position(Books())


def test_sales_position_separates_overdue_from_merely_due(books):
    out = tools.sales_position(books, TODAY)
    assert "SI-001" in out and "55 days overdue" in out
    assert "SI-003" in out and "due 2026-09-24" in out
    assert "SI-002" not in out  # collected in full


def test_sales_position_shows_what_was_already_received(books):
    assert "480.00 EUR received so far" in tools.sales_position(books, TODAY)


def test_sales_position_when_nothing_is_owed():
    assert "has been collected" in tools.sales_position(Books(), TODAY)


def test_payroll_position(books):
    out = tools.payroll_position(books)
    assert "PR-2026-08" in out and "1,100.00 EUR" in out


def test_payroll_position_when_staff_are_paid():
    assert "paid up to date" in tools.payroll_position(Books())


def test_trading_position_carries_the_profit(books):
    out = tools.trading_position(books, FRM, TODAY)
    assert "-200.00 EUR" in out and "margin" in out


def test_trading_position_says_so_when_there_were_no_sales():
    out = tools.trading_position(Books(), FRM, TODAY)
    assert "no sales, so no margin" in out


def test_cash_position_carries_the_closing_balance(books):
    out = tools.cash_position(books, FRM, TODAY)
    assert "closing 232.00 EUR" in out


def test_headline_metrics_carries_every_number_the_owner_asked_for(books):
    out = tools.headline_metrics(books, TODAY)
    for expected in (
        "bank 232.00 EUR",
        "owed by clients 3,860.00 EUR",
        "owed to suppliers 496.00 EUR",
        "1,100.00 EUR of wages unpaid",
        "2,000.00 EUR",
        "55 days",
        "Working capital 2,496.00 EUR",
    ):
        assert expected in out, f"missing {expected!r} in: {out}"


def test_headline_metrics_says_staff_are_paid_when_they_are():
    assert "staff are paid" in tools.headline_metrics(Books(), TODAY)


def test_chase_candidate_returns_the_one_debt_not_a_list(books):
    out = tools.chase_candidate(books, TODAY)
    assert "SI-001" in out and "Cafe on the corner" in out
    assert "SI-003" not in out  # not overdue, so not a candidate


def test_chase_candidate_refuses_to_invent_a_target():
    assert "no chase to write" in tools.chase_candidate(Books(), TODAY)
