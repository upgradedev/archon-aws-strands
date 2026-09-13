"""Real CommonMark parsing, local target checks and negative controls, CI only."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
PARSER = MarkdownIt("commonmark", {"html": True}).enable("table")
PAGES = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.anchors = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"a", "img"}:
            url = attrs.get("href" if tag == "a" else "src")
            if url:
                self.links.append(url)
        for attribute in ("id", "name"):
            if attrs.get(attribute):
                self.anchors.add(attrs[attribute])


def anchors(text):
    html = References()
    html.feed(PARSER.render(text))
    result = html.anchors
    counts = {}
    tokens = PARSER.parse(text)
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            title = "".join(child.content for child in tokens[index + 1].children
                            if child.type in {"text", "code_inline"})
            slug = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
            count = counts.get(slug, 0)
            counts[slug] = count + 1
            result.add(slug if not count else f"{slug}-{count}")
    return result


def check_document(source):
    text = source.read_text(encoding="utf-8")
    tokens = PARSER.parse(text)
    assert any(token.type == "heading_open" for token in tokens), source
    lines = text.splitlines()
    for token in tokens:
        if token.type == "fence":
            end = lines[token.map[1] - 1].strip()
            assert re.fullmatch(re.escape(token.markup[0]) + "{" +
                                str(len(token.markup)) + r",}\s*", end), "Unclosed fence"
    html = References()
    html.feed(PARSER.render(text))
    for link in html.links:
        url = urlsplit(link)
        if url.scheme or url.netloc:
            assert url.scheme in {"https", "http", "mailto"}, link
            continue
        target = (source.parent / unquote(url.path)).resolve() if url.path else source
        assert target.is_relative_to(ROOT), f"Escaping repository: {link}"
        assert target.exists(), f"{source.name}: missing target {link}"
        if url.fragment and target.suffix == ".md":
            assert unquote(url.fragment) in anchors(target.read_text(encoding="utf-8")), link


@pytest.mark.parametrize("source", PAGES, ids=lambda path: str(path.relative_to(ROOT)))
def test_current_markdown_parses_and_local_links_resolve(source):
    check_document(source)


def test_parser_contract_rejects_unclosed_fence_and_missing_link(tmp_path, monkeypatch):
    # Deliberately broken independent inputs prove this is not a presence-only gate.
    monkeypatch.setattr(__import__(__name__), "ROOT", tmp_path)
    document = tmp_path / "bad.md"
    document.write_text("# Broken\n\n```bash\nnever closed\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Unclosed fence"):
        check_document(document)
    document.write_text("# Broken\n\n[missing](absent.md)\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="missing target"):
        check_document(document)


def test_heading_and_html_anchor_detection():
    assert anchors('# One & two\n\n## One & two\n\n<a id="exact"></a>\n') == {
        "one--two", "one--two-1", "exact"}
