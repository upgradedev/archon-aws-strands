"""Score the methods and print the number the README is allowed to quote.

Two outcomes are counted apart because they cost differently. **Wrong money** is
an email demanding a figure that is not owed: it reaches a client and it cannot
be recalled. **A missed chase** is silence where money was owed: it costs the
firm without embarrassing it.

Both are always reported together, because a method that never sends scores zero
wrong money and reporting either alone would let any of the three look perfect.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from archon.domain.money import ZERO

from .methods import METHODS, Answer
from .scenarios import Scenario, all_scenarios


@dataclass(frozen=True, slots=True)
class Tally:
    """How one method did over the whole set."""

    method: str
    n: int
    wrong_money: int
    missed: int
    refused: int
    correct: int

    @property
    def wrong_money_rate(self) -> float:
        return self.wrong_money / self.n if self.n else 0.0

    @property
    def missed_rate(self) -> float:
        return self.missed / self.n if self.n else 0.0


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """A 95% interval that behaves at the edges, where the textbook one does not.

    With twenty cases and a count of zero, the normal-approximation interval is
    zero to zero, which would let this project publish a certainty it has not
    earned. Wilson gives an honest upper bound instead, and that upper bound is
    what the README quotes next to any zero.
    """
    if n == 0:
        return (0.0, 1.0)
    phat = successes / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    margin = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def judge(scenario: Scenario, answer: Answer) -> str:
    """One of: wrong-money, missed, refused, correct."""
    owed = scenario.truth > ZERO
    if answer.refused:
        return "refused"
    if not answer.sends:
        return "missed" if owed else "correct"
    if not owed:
        return "wrong-money"
    if answer.invoice != scenario.chase_invoice:
        return "wrong-money"
    return "correct" if answer.amount == scenario.truth else "wrong-money"


def score(
    method: str,
    fn: Callable[[Scenario], Answer],
    scenarios: tuple[Scenario, ...] | None = None,
) -> Tally:
    cases = scenarios or all_scenarios()
    counts = {"wrong-money": 0, "missed": 0, "refused": 0, "correct": 0}
    for case in cases:
        counts[judge(case, fn(case))] += 1
    return Tally(
        method=method,
        n=len(cases),
        wrong_money=counts["wrong-money"],
        missed=counts["missed"],
        refused=counts["refused"],
        correct=counts["correct"],
    )


def score_all(scenarios: tuple[Scenario, ...] | None = None) -> list[Tally]:
    return [score(name, fn, scenarios) for name, fn in METHODS.items()]


def report(tallies: list[Tally] | None = None, title: str = "one firm's post") -> str:
    """The table, with the count taken from the tallies rather than written in.

    The heading said "twenty months" while a fifteen-case run was printed beneath
    it, which is the shape of mistake this whole file exists to catch elsewhere.
    """
    rows = tallies or score_all()
    n = rows[0].n if rows else 0
    header = (
        f"{'method':<24}{'wrong money':>13}{'missed':>9}{'refused':>9}"
        f"{'correct':>9}   95% CI, wrong money"
    )
    lines = [
        f"{n} months of {title}. Every answer is known by construction.",
        "",
        header,
        "-" * len(header),
    ]
    for row in rows:
        low, high = wilson(row.wrong_money, row.n)
        lines.append(
            f"{row.method:<24}{row.wrong_money:>8} /{row.n:<3}{row.missed:>9}"
            f"{row.refused:>9}{row.correct:>9}   {low:.1%} to {high:.1%}"
        )
    lines += [
        "",
        "Wrong money is an email demanding a figure that is not owed. It reaches a client",
        "and cannot be recalled. A missed chase is silence where money was owed: it costs",
        "the firm without embarrassing it. Both are shown, because a method that never",
        "sends anything scores zero on the first and would otherwise look perfect.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    import sys

    if "--hard" in sys.argv:
        from .hard import all_hard_scenarios

        print(report(score_all(all_hard_scenarios()), "the awkward month"))
    else:
        print(report())
