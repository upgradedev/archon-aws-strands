"""Exact money.

A float cannot hold 0.10 and a business cannot hold a rounding error, so every
amount in this package is a two-place ``Decimal``. The constructor refuses a
float outright rather than quietly converting one, because a converted float is
already wrong by the time it is stored.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CURRENCY = "EUR"
PLACES = Decimal("0.01")
ZERO = Decimal("0.00")


class MoneyError(ValueError):
    """An amount that cannot be represented exactly."""


def money(value: str | int | Decimal) -> Decimal:
    """Return ``value`` as an exact two-place Decimal.

    A ``float`` is rejected on sight. ``money(0.1 + 0.2)`` would otherwise store
    0.30 while the caller believes it stored the sum it wrote.
    """
    if isinstance(value, float):
        raise MoneyError(
            f"refusing to build money from the float {value!r}. "
            "Pass a string, an int or a Decimal."
        )
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise MoneyError(f"not an amount: {value!r}") from exc
    if not amount.is_finite():
        raise MoneyError(f"not a finite amount: {value!r}")
    return amount.quantize(PLACES, rounding=ROUND_HALF_UP)


def total(amounts: object) -> Decimal:
    """Sum an iterable of amounts, returning exact zero when it is empty."""
    running = ZERO
    for amount in amounts:  # type: ignore[attr-defined]
        running += amount
    return running.quantize(PLACES, rounding=ROUND_HALF_UP)


def fmt(amount: Decimal) -> str:
    """Render an amount for a human, currency included."""
    return f"{amount:,.2f} {CURRENCY}"
