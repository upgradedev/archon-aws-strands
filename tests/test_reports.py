"""P&L, cashflow and metrics, checked against arithmetic done by hand.

Every expected number below was computed from the fixture by hand and is written
out in the comment above it. A test that asserts whatever the code returned is
not a test.
"""

from datetime import date
from decimal import Decimal

from archon.domain.accounts import Account
from archon.domain.reports import cashflow, metrics, profit_and_loss

FRM = date(2026, 7, 1)
TO = date(2026, 9, 3)


def test_profit_and_loss_over_the_quarter(books):
    # Sales in window: SI-002 net 800 (20 Jul) + SI-003 net 1500 (25 Aug) = 2300.
    # SI-001 was issued 10 Jun and falls outside, which is the point of a window.
    # Purchases: PI-001 net 1000 (4 Jul) + PI-002 net 400 (1 Aug) = 1400.
    # Wages: 1100 (31 Aug). Costs 2500. Profit 2300 - 2500 = -200.
    pnl = profit_and_loss(books, FRM, TO)
    assert pnl.sales == Decimal("2300.00")
    assert pnl.purchases == Decimal("1400.00")
    assert pnl.wages == Decimal("1100.00")
    assert pnl.costs == Decimal("2500.00")
    assert pnl.profit == Decimal("-200.00")


def test_pnl_excludes_vat_because_vat_was_never_ours(books):
    # SI-002 grossed 992 and only 800 of it is income. A P&L that showed 992
    # would be reporting the tax authority's money as turnover.
    pnl = profit_and_loss(books, FRM, TO)
    assert pnl.sales == Decimal("2300.00") != Decimal("2852.00")


def test_margin_is_none_when_nothing_was_sold(books):
    quiet = profit_and_loss(books, date(2026, 1, 1), date(2026, 1, 31))
    assert quiet.sales == Decimal("0.00")
    assert quiet.margin is None


def test_cashflow_over_the_quarter(books):
    # In: RC-002 480 (1 Aug) + RC-001 992 (20 Aug) = 1472.
    # Out: PAY-001 1240 (2 Aug). Net 232. Opening 0, so closing 232.
    cf = cashflow(books, FRM, TO)
    assert cf.opening == Decimal("0.00")
    assert cf.inflow == Decimal("1472.00")
    assert cf.outflow == Decimal("1240.00")
    assert cf.net == Decimal("232.00")
    assert cf.closing == Decimal("232.00")


def test_cash_and_profit_disagree_and_that_is_the_point(books):
    # Profit is -200 while cash rose 232. A firm can be profitable and broke, or
    # loss-making and liquid, and the owner needs to see both numbers.
    pnl = profit_and_loss(books, FRM, TO)
    cf = cashflow(books, FRM, TO)
    assert pnl.profit != cf.net


def test_closing_cash_equals_the_bank_account(books):
    # The cashflow statement and the ledger must not be able to disagree.
    cf = cashflow(books, FRM, TO)
    assert cf.closing == books.ledger.balance_as_read(Account.BANK, upto=TO)


def test_metrics(books):
    # Owed to suppliers: PI-002 496. Owed by clients: SI-001 2000 + SI-003 1860
    # = 3860. Overdue: SI-001 alone, 2000, 55 days. Wages owed 1100. Bank 232.
    m = metrics(books, TO)
    assert m.owed_to_suppliers == Decimal("496.00")
    assert m.owed_by_clients == Decimal("3860.00")
    assert m.overdue_amount == Decimal("2000.00")
    assert m.overdue_count == 1
    assert m.oldest_overdue_days == 55
    assert m.staff_paid is False
    assert m.owed_to_staff == Decimal("1100.00")
    assert m.bank == Decimal("232.00")


def test_working_capital_counts_the_wages_not_yet_paid(books):
    # 232 + 3860 - 496 - 1100 = 2496. Leaving payroll out would report 3596 and
    # flatter the firm in the month it has not paid its people.
    m = metrics(books, TO)
    assert m.working_capital == Decimal("2496.00")
