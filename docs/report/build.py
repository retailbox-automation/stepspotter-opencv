"""Build the technical report PDF from docs/REPORT.md.

    python3 docs/report/build.py            # writes report.html and the PDF next to this file

Needs: Python 3 with `markdown` (pip install markdown), Google Chrome or Chromium for the
headless print. The Markdown file is the source; this script only lays it out:
a title block with "prepared by Mikh[ai]l", Letter pages, the diagrams from
docs/diagrams/, and any {{PLACEHOLDER}} still in the text shown in amber so an unfilled
number cannot pass unnoticed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent
SRC = DOCS / "REPORT.md"
OUT_HTML = HERE / "report.html"
OUT_PDF = HERE / "StepSpotter-OpenCV26-report.pdf"

CSS = """
@page { size: letter; margin: 16mm 15mm 16mm 15mm; }
:root { --ink:#0b1030; --muted:#6b7280; --acc:#4a9fd8; --line:#d9dde7; --soft:#f4f6fa; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin:0; background:#fff; color:var(--ink);
  font: 10pt/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
.head { border-bottom: 2px solid var(--ink); padding-bottom: 10px; margin-bottom: 14px; }
.kicker { font-size: 9pt; color: var(--muted); letter-spacing: .02em; }
h1.title { font-size: 24pt; line-height: 1.15; margin: 6px 0 8px; font-weight: 750; }
.hl { background: var(--acc); color: #fff; padding: 0 .12em; }
.prep { font-size: 10pt; color: var(--muted); font-weight: 500; }
.prep .who { color: var(--ink); font-weight: 650; }
.ai { background: var(--acc); color: #fff; padding: 0 .04em; }
.links { font-size: 8.8pt; color: var(--muted); margin-top: 4px; }
h2 { font-size: 14pt; margin: 18px 0 6px; padding-top: 4px; border-top: 1px solid var(--line);
  break-after: avoid; page-break-after: avoid; }
h3 { font-size: 11pt; margin: 12px 0 4px; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
ul, ol { padding-left: 18px; margin: 4px 0 8px; }
li { margin: 2px 0; }
code { font: 8.6pt/1.3 "SF Mono", Menlo, Consolas, monospace; background: var(--soft);
  padding: 0 3px; border-radius: 3px; word-break: break-word; }
pre { background: var(--soft); border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px;
  white-space: pre-wrap; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8.2pt; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 10px; font-size: 8.8pt; }
tr { break-inside: avoid; }
td code, th code { white-space: nowrap; word-break: normal; }
th, td { border: 1px solid var(--line); padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: var(--soft); font-weight: 650; }
img { max-width: 100%; display: block; margin: 8px auto; border: 1px solid var(--line);
  border-radius: 6px; break-inside: avoid; }
blockquote { margin: 6px 0; padding: 6px 10px; border-left: 3px solid var(--acc);
  background: var(--soft); color: var(--muted); }
.ph { background: #fff1c2; color: #7a4b00; border: 1px dashed #c98a00; border-radius: 3px;
  padding: 0 3px; font-weight: 600; }
a { color: inherit; }
"""


def body_html(md_text: str) -> str:
    # The Markdown file opens with its own H1 and a by-line; the PDF has a title block.
    lines = md_text.splitlines()
    assert lines[0].startswith("# "), "REPORT.md must start with its H1"
    i = 1
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    while i < len(lines) and lines[i].strip() != "":  # the by-line paragraph
        i += 1
    rest = "\n".join(lines[i:])
    out = markdown.markdown(rest, extensions=["tables", "fenced_code", "sane_lists"])
    out = out.replace('src="diagrams/', 'src="../diagrams/')
    out = out.replace('src="screens/', 'src="../screens/')
    out = re.sub(r"\{\{([^}]+)\}\}", lambda m: f'<span class="ph">{{{{{m.group(1)}}}}}</span>', out)
    return out


def page(md_text: str) -> str:
    head = (
        '<header class="head">'
        '<div class="kicker">OpenCV AI Competition 2026, powered by AWS · technical report</div>'
        '<h1 class="title">StepSpotter: <span class="hl">OpenCV 5</span> decides what the agent does next</h1>'
        '<div class="prep">prepared by <span class="who">Mikh<span class="ai">ai</span>l</span></div>'
        '<div class="links">github.com/retailbox-automation/stepspotter-opencv · '
        'utgfmpcgxf.us-east-1.awsapprunner.com</div>'
        "</header>"
    )
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>StepSpotter OpenCV26 report</title><style>{CSS}</style></head>"
        f"<body>{head}{body_html(md_text)}</body></html>"
    )


def chrome() -> str:
    for c in (
        os.environ.get("CHROME", ""),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
    ):
        if c and Path(c).exists():
            return c
    sys.exit("Chrome or Chromium not found (set CHROME=/path/to/chrome)")


def main() -> int:
    OUT_HTML.write_text(page(SRC.read_text(encoding="utf-8")), encoding="utf-8")
    profile = HERE / ".chrome-profile"
    cmd = [
        chrome(), "--headless=new", "--disable-gpu", "--no-first-run",
        f"--user-data-dir={profile}", "--no-pdf-header-footer",
        f"--print-to-pdf={OUT_PDF}", OUT_HTML.as_uri(),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(profile, ignore_errors=True)
    data = OUT_PDF.read_bytes()
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
    box = re.findall(rb"/MediaBox\s*\[([^\]]+)\]", data)
    size = [float(v) / 72 for v in box[0].split()[2:4]] if box else None
    print(f"{OUT_PDF.name}: {len(data)} bytes, {pages} pages, page {size} in")
    left = re.findall(r"\{\{[^}]+\}\}", SRC.read_text(encoding="utf-8"))
    print(f"placeholders left in REPORT.md: {len(left)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
