"""The journey a judge runs. If this breaks, the quickstart in the README lies.

It is asserted on content rather than on exit code, because a demo that finishes
cleanly while printing the wrong number is the failure worth catching.
"""

from __future__ import annotations

import pytest

pytest.importorskip("strands", reason="the journey runs the real graph")

from archon import demo  # noqa: E402


def _run(capsys) -> str:
    assert demo.main([]) == 0
    return capsys.readouterr().out


def test_the_journey_completes_offline(capsys):
    out = _run(capsys)
    assert "scripted, offline" in out
    assert "in-memory outbox" in out


def test_it_says_a_scripted_run_does_not_judge(capsys):
    # The discrepancy this guards: a scripted run reading like an agentic one.
    out = _run(capsys)
    assert "it does not judge" in out


def test_the_books_balance_on_screen(capsys):
    out = _run(capsys)
    assert "trial balance 0.00" in out


def test_all_six_domains_are_shown(capsys):
    out = _run(capsys)
    for expected in ("supplier invoice", "sales invoice", "Payroll", "profit", "closing", "bank"):
        assert expected in out, expected


def test_the_composer_runs_after_all_six_readers(capsys):
    out = _run(capsys)
    line = next(ln for ln in out.splitlines() if "ran in order:" in ln)
    order = [name.strip() for name in line.split(":", 1)[1].split(",")]
    assert order[-1] == "composer", order
    assert len(order) == 7


def test_the_email_carries_only_verified_figures(capsys):
    out = _run(capsys)
    assert "2,000.00 EUR" in out
    assert "It fell due 55 days ago." in out
    assert "480.00 EUR against it" in out


def test_the_gate_releases_the_correct_chase(capsys):
    out = _run(capsys)
    assert "release: SI-001 is open, overdue" in out


def test_an_edit_after_approval_is_shown_being_refused(capsys):
    out = _run(capsys)
    assert "one word edited after approval -> held:" in out
    assert "approved different bytes" in out


def test_a_client_paying_at_lunchtime_is_shown_being_refused(capsys):
    out = _run(capsys)
    assert "the client pays at lunchtime -> held:" in out
    assert "settled since the draft was written" in out


def test_the_send_is_evidenced_and_not_repeated(capsys):
    out = _run(capsys)
    assert "message id offline-0001" in out
    assert "replayed=True, same id=True" in out
    assert "read back from the outbox: offline-0001" in out


def test_the_post_is_wholly_invented():
    """S11 forbids customer data. The fixture is where that promise is kept."""
    names = " ".join(
        str(getattr(d, "supplier", "")) + str(getattr(d, "client", "")) for d in demo.the_post()
    )
    assert "Cafe on the corner" in names and "Wholesaler A" in names


def test_two_lines_survives_a_one_line_reply():
    opening, closing = demo.two_lines("Just the one line.")
    assert opening == "Just the one line."
    assert closing


def test_two_lines_refuses_an_empty_reply():
    from archon.agents.draft import UnsafeDraft

    with pytest.raises(UnsafeDraft, match="wrote nothing"):
        demo.two_lines("   \n  \n")


def test_the_summary_line_a_video_needs():
    books = demo.keep_the_books(demo.the_post())
    line = demo.summary(books)
    assert "profit" in line and "overdue" in line and "EUR" in line
