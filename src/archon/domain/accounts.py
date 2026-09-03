"""The chart of accounts.

Small on purpose. Every account here is one a sole trader would recognise on a
bank statement or an accountant's letter, and nothing is present that the six
questions in the product scope do not need.
"""

from __future__ import annotations

from enum import Enum


class Side(Enum):
    """Which way an account increases."""

    DEBIT = "debit"
    CREDIT = "credit"


class Account(Enum):
    """The accounts Archon posts to.

    The value is what a human sees; the ``natural`` side is what decides whether
    a positive balance reads as an asset or as a debt.
    """

    BANK = "Bank"
    RECEIVABLES = "Trade debtors"
    PAYABLES = "Trade creditors"
    PAYROLL_PAYABLE = "Wages owed to staff"
    VAT_INPUT = "VAT on purchases"
    VAT_OUTPUT = "VAT on sales"
    SALES = "Sales"
    PURCHASES = "Purchases"
    WAGES = "Wages"

    @property
    def natural(self) -> Side:
        return _NATURAL[self]

    @property
    def is_profit_and_loss(self) -> bool:
        """True for accounts that close into the P&L rather than carry forward."""
        return self in _PROFIT_AND_LOSS


_NATURAL: dict[Account, Side] = {
    Account.BANK: Side.DEBIT,
    Account.RECEIVABLES: Side.DEBIT,
    Account.PURCHASES: Side.DEBIT,
    Account.WAGES: Side.DEBIT,
    Account.VAT_INPUT: Side.DEBIT,
    Account.PAYABLES: Side.CREDIT,
    Account.PAYROLL_PAYABLE: Side.CREDIT,
    Account.VAT_OUTPUT: Side.CREDIT,
    Account.SALES: Side.CREDIT,
}

_PROFIT_AND_LOSS: frozenset[Account] = frozenset(
    {Account.SALES, Account.PURCHASES, Account.WAGES}
)
