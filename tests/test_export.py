"""The static walkthrough. If these break, a judge sees a page that lies."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="the walkthrough renders the screen")

from archon.web import export  # noqa: E402


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    target = tmp_path_factory.mktemp("site")
    export.write(target)
    return {p.stem: p.read_text(encoding="utf-8") for p in target.glob("*.html")}


def test_all_three_states_are_written(pages):
    assert set(pages) == {"index", "paid", "sent"}


def test_every_page_says_it_is_static(pages):
    for name, html in pages.items():
        assert "A static walkthrough" in html, name
        assert "not interactive" in html, name


def test_no_page_carries_a_form_a_static_host_cannot_post(pages):
    for name, html in pages.items():
        assert "<form" not in html, name
        assert "<button disabled" in html, name


def test_the_first_page_shows_a_released_chase(pages):
    assert "Released" in pages["index"]
    assert "2,000.00 EUR" in pages["index"]


def test_the_second_page_shows_the_approval_no_longer_matching(pages):
    html = pages["paid"]
    assert "books moved while this page was open" in html
    assert "1,000.00 EUR" in html, "the debt should be halved, not gone"


def test_the_third_page_shows_one_receipt(pages):
    assert "message id" in pages["sent"]
    assert "offline-0001" in pages["sent"]


def test_the_pages_link_to_each_other(pages):
    for html in pages.values():
        for target in ("index.html", "paid.html", "sent.html"):
            assert target in html


def test_the_figures_are_computed_not_written(pages):
    """Each state is built by doing what a visitor would do."""
    from archon.domain.reports import metrics
    from archon.web.app import TODAY

    fresh = export._state("index")
    paid = export._state("paid")
    assert metrics(paid.books, TODAY).owed_by_clients < metrics(fresh.books, TODAY).owed_by_clients


def test_the_walkthrough_needs_no_external_asset(pages):
    for name, html in pages.items():
        assert "cdn" not in html.lower(), name
        assert "<script" not in html.lower(), name
