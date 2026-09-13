"""Render repository Markdown for CI visual review; never publish it automatically."""
from __future__ import annotations

import re
import shutil
import sys
from html import escape
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
PARSER = MarkdownIt("commonmark", {"html": True}).enable("table")
STYLE = """
body{margin:0;background:#f6f8fa;color:#172d44;font:16px/1.65 system-ui,sans-serif}
main{box-sizing:border-box;max-width:1000px;margin:auto;padding:36px 24px;overflow-wrap:anywhere}
h1,h2,h3{line-height:1.3;color:#13334c}h2{border-bottom:1px solid #cedbdc;padding-bottom:8px}
a{color:#096c77}img,svg{max-width:100%;height:auto}pre{overflow:auto;padding:18px;background:#e9eef3}
table{display:block;max-width:100%;overflow:auto;border-collapse:collapse}
th,td{padding:9px 12px;border:1px solid #c9d6db;text-align:left}
blockquote{border-left:4px solid #d8a647;margin-left:0;padding-left:18px;color:#49566c}
summary{cursor:pointer;padding:12px 0}code{font-size:.9em}
"""


def pages(root=ROOT):
    return [root / "README.md", *sorted((root / "docs").glob("*.md"))]


def render(target, root=ROOT):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for source in pages(root):
        relative = source.relative_to(root).with_suffix(".html")
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        body = PARSER.render(source.read_text(encoding="utf-8"))
        body = re.sub(r'(href="[^"#]+)\.md(?=["#])', r'\1.html', body)
        output.write_text(
            f'<!doctype html><html lang="en"><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(source.name)} review</title><style>{STYLE}</style>'
            f'<main>{body}</main></html>', encoding="utf-8")
    for folder, suffix in (("docs", "*.svg"), ("graphics", "*.jpg")):
        for asset in (root / folder).glob(suffix):
            output = target / asset.relative_to(root)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(asset, output)


if __name__ == "__main__":
    render(sys.argv[1])
