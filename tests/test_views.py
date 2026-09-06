"""Turning six agents' prose into something a page can lay out.

The parsing is small and the failure modes are quiet, which is the combination
worth testing: a verdict read backwards or a table shown instead of a judgement
would both look fine on screen and be wrong.
"""

from __future__ import annotations

from archon.agents import views, wiring


def test_the_committed_run_has_all_six_domains():
    parsed = views.captured()
    assert {v.name for v in parsed} == set(wiring.REQUIRED_REPORTS)


def test_the_six_did_not_all_say_the_same_thing():
    """If they agreed on everything, six agents would be five too many."""
    verdicts = {v.verdict for v in views.captured()}
    assert len(verdicts) > 1, verdicts


def test_the_most_pressing_is_first():
    """A page sorted by domain buries the thing that matters."""
    parsed = views.captured()
    assert parsed[0].verdict == "URGENT"
    assert [v.rank for v in parsed] == sorted(v.rank for v in parsed)


def test_each_view_carries_the_question_it_answered():
    for view in views.captured():
        assert view.question.endswith("?"), view.name


def test_the_last_verdict_wins_not_the_first():
    """"This is not URGENT, it is something to WATCH" means WATCH."""
    assert views._verdict_of("this is not URGENT, it is something to WATCH") == "WATCH"
    assert views._verdict_of("clearly URGENT") == "URGENT"


def test_text_with_no_verdict_is_treated_as_calm_not_as_a_crisis():
    assert views._verdict_of("the tool returned nothing of note") == "FINE"


def test_the_judgement_is_taken_and_not_the_table_above_it():
    body = (
        "**What the tool returned:**\n\n"
        "| Invoice | Amount |\n|---|---|\n| PI-002 | 496.00 |\n\n"
        "It is not yet overdue and the amount is modest. WATCH"
    )
    view = views.parse("suppliers", body)
    assert view.verdict == "WATCH"
    assert "not yet overdue" in view.body
    assert "|" not in view.body, "a markdown table reached the page"


def test_bold_and_rules_are_stripped_for_a_page_that_renders_neither():
    view = views.parse("cash", "--- **Cash is thin** and could flip negative. WATCH")
    assert "**" not in view.body and "---" not in view.body
    assert view.body.startswith("Cash is thin")


def test_a_models_own_label_is_not_repeated_six_times():
    view = views.parse("trading", "Assessment: the firm made a loss this quarter. WATCH")
    assert view.body.lower().startswith("the firm made a loss")
    assert not view.body.lower().startswith("assessment")


def test_every_view_ends_as_a_sentence():
    for view in views.captured():
        assert view.body.endswith("."), view.name


def test_an_unknown_domain_in_a_transcript_is_ignored_not_shown():
    text = "### payroll\nStaff unpaid. URGENT\n\n### gardening\nThe hedge needs cutting. URGENT"
    parsed = views.from_transcript(text)
    assert [v.name for v in parsed] == ["payroll"]


def test_a_live_result_parses_into_the_same_shape_as_the_capture():
    class Outcome:
        def __init__(self, text):
            self.result = type("R", (), {"message": {"content": [{"text": text}]}})()

    class Result:
        results = {
            "payroll": Outcome("Staff unpaid for a month. URGENT"),
            "cash": Outcome("Thin but positive. WATCH"),
            "composer": Outcome("ignored, not a reader"),
        }

    parsed = views.from_graph_result(Result())
    assert [v.name for v in parsed] == ["payroll", "cash"]
    assert parsed[0].verdict == "URGENT"


def test_a_reader_that_said_nothing_is_left_out_rather_than_shown_blank():
    class Outcome:
        result = type("R", (), {"message": {"content": [{"text": "   "}]}})()

    class Result:
        results = {"payroll": Outcome()}

    assert views.from_graph_result(Result()) == []
