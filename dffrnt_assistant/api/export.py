"""Render an assistant answer (Markdown) to a downloadable PDF, fully locally:
mistune turns Markdown into HTML, and PyMuPDF's Story API (already a dependency
via PDF ingestion) paginates that HTML into a PDF."""

import io

import fitz  # PyMuPDF
import mistune

# Minimal print stylesheet (PyMuPDF's Story supports a subset of CSS).
_CSS = """
body { font-family: sans-serif; font-size: 11pt; line-height: 1.5; color: #111; }
h1 { font-size: 20pt; margin: 0 0 8pt; }
h2 { font-size: 16pt; margin: 14pt 0 6pt; }
h3 { font-size: 13pt; margin: 12pt 0 6pt; }
p { margin: 0 0 8pt; }
ul, ol { margin: 0 0 8pt 18pt; }
li { margin: 0 0 3pt; }
code { font-family: monospace; background: #f2f2f2; }
pre { font-family: monospace; font-size: 9.5pt; background: #f2f2f2;
      padding: 6pt; margin: 0 0 8pt; }
blockquote { margin: 0 0 8pt; padding-left: 10pt; border-left: 3px solid #ccc;
             color: #555; }
a { color: #1a4fb4; }
h1.doc-title { font-size: 22pt; margin: 0 0 12pt; }
"""

# US Letter with 0.5" margins, in points (72pt = 1in).
_PAGE = fitz.paper_rect("letter")
_CONTENT = _PAGE + (36, 36, -36, -36)


def markdown_to_pdf(markdown_text: str, title: str = "") -> bytes:
    """Render ``markdown_text`` to PDF bytes, with an optional heading title."""
    body = mistune.html(markdown_text or "")
    heading = f"<h1 class='doc-title'>{mistune.escape(title)}</h1>" if title else ""
    html = f"<html><head><style>{_CSS}</style></head><body>{heading}{body}</body></html>"

    story = fitz.Story(html=html)
    buffer = io.BytesIO()
    writer = fitz.DocumentWriter(buffer)
    # Story.place returns (more, filled); loop until it reports no overflow, one
    # page per iteration.
    more = 1
    while more:
        device = writer.begin_page(_PAGE)
        more, _ = story.place(_CONTENT)
        story.draw(device)
        writer.end_page()
    writer.close()
    return buffer.getvalue()
