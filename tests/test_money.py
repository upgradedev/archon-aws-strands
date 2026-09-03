"""Money is exact or it is refused."""

from decimal import Decimal

import pytest

from archon.domain.money import MoneyError, ZERO, fmt, money, total


def test_a_float_is_refused_rather_than_converted():
    # 0.1 + 0.2 is 0.30000000000000004. Converting it quietly is how a ledger
    # acquires an error nobody can later find.
    with pytest.raises(MoneyError, match="refusing to build money from the float"):
        money(0.1 + 0.2)


def test_strings_and_ints_and_decimals_are_accepted():
    assert money("12.5") == Decimal("12.50")
    assert money(7) == Decimal("7.00")
    assert money(Decimal("0.005")) == Decimal("0.01")


def test_rounding_is_half_up_not_bankers():
    # Python's default is banker's rounding, which would make this 0.00.
    assert money(Decimal("0.005")) == Decimal("0.01")
    assert money(Decimal("0.015")) == Decimal("0.02")


def test_nonsense_is_refused():
    with pytest.raises(MoneyError):
        money("not an amount")
    with pytest.raises(MoneyError):
        money(Decimal("NaN"))


def test_total_of_nothing_is_exact_zero():
    assert total([]) == ZERO
    assert str(total([])) == "0.00"


def test_fmt_shows_currency():
    assert fmt(money("1234.5")) == "1,234.50 EUR"
