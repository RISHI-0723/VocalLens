"""Render docs/technical_report.md to a self-contained, print-ready HTML.

Usage:
    python scripts/build_report_html.py

Output:
    docs/technical_report.html  (open in a browser -> Ctrl/Cmd+P -> "Save as PDF")

The CSS is tuned (A4, compact type, tight margins) so the rendered PDF fits the
hackathon's six-page limit. Verify the page count in the print preview. No
network access and no heavy PDF engine are required; the markdown source stays
canonical.
"""
from __future__ import annotations

from pathlib import Path

import markdown  # pure-Python; a build-time tool only (not a runtime dependency)

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "docs" / "technical_report.md"
OUT = REPO / "docs" / "technical_report.html"

CSS = """
@page { size: A4; margin: 13mm 14mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: "Segoe UI", Arial, sans-serif; color: #15181d;
  font-size: 10.3px; line-height: 1.34; max-width: 820px; margin: 0 auto; padding: 18px;
}
h1 { font-size: 20px; margin: 0 0 4px; color: #0b1020; }
h2 { font-size: 13.5px; margin: 11px 0 4px; border-bottom: 1px solid #d7dbe2;
     padding-bottom: 2px; color: #0b1020; page-break-after: avoid; }
h3 { font-size: 11.3px; margin: 8px 0 3px; color: #222; page-break-after: avoid; }
p { margin: 3px 0; }
ul, ol { margin: 3px 0 3px 18px; padding: 0; }
li { margin: 1px 0; }
code { font-family: Consolas, "Courier New", monospace; font-size: 9.2px;
       background: #f1f3f6; padding: 0 2px; border-radius: 2px; }
pre { background: #f6f8fa; border: 1px solid #e2e6ec; border-radius: 4px;
      padding: 6px 8px; overflow-x: auto; page-break-inside: avoid; margin: 4px 0; }
pre code { background: none; font-size: 8.9px; line-height: 1.3; }
blockquote { margin: 4px 0; padding: 3px 9px; border-left: 3px solid #6b7cff;
             background: #f4f5ff; color: #2a2f45; }
table { border-collapse: collapse; width: 100%; margin: 4px 0; font-size: 9.2px;
        page-break-inside: avoid; }
th, td { border: 1px solid #d0d5dd; padding: 2px 5px; text-align: left; vertical-align: top; }
th { background: #eef1f6; }
hr { border: none; border-top: 1px solid #d7dbe2; margin: 8px 0; }
a { color: #3341c4; text-decoration: none; }
"""

HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VocalLens — Technical Report</title>
<style>{css}</style></head>
<body>{body}</body></html>
"""


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    OUT.write_text(HTML.format(css=CSS, body=body), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(REPO)} ({OUT.stat().st_size:,} bytes).")
    print("Open it in a browser and Save as PDF (A4). Verify the PDF is <= 6 pages.")


if __name__ == "__main__":
    main()
