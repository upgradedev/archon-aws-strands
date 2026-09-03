"""The agent layer.

The split this package exists to enforce: **the agent decides, the code
calculates, and the code verifies.** An agent chooses which receivable is worth
chasing and how firmly to put it. It never computes a number that reaches a
client, and it never asserts a fact the ledger has not confirmed.
"""
