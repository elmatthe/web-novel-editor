"""PDF output via reportlab (Phase 3).

Port of `create_pdf_from_text()` from the study example `sm_pdf_editor-v8.2.py`,
**validated against reportlab 5.0.0** (Times-Roman justified body, Helvetica-Bold
#134252 headings, 0.5in margins, and PageBreak all confirmed to render correctly).

Formatting:
  - Body: Times-Roman 11pt, 15pt leading, justified, 6pt space before/after.
  - Headings ("Chapter N: Title."): Helvetica-Bold 14pt, left-aligned, color #134252.
  - Page geometry: US letter, 0.5in margins all sides.
  - Pages are split on form-feed ("\\f"); paragraphs on blank lines ("\\n\\n").
  - Merged "heading + body" paragraphs are split so the heading renders as a heading.

The builder is structural only: deciding what is a heading is layout formatting, not an
editorial rule, so it lives here and runs even in Phase 3 where the rule pipeline is a
no-op pass-through.

Phase 6 (scraper alignment, safety-first): headings carry `keepWithNext` so a chapter
heading can never be stranded alone at the bottom of a page (orphan prevention at
layout time), and `detect_heading_only_pages()` reports heading-only pages for review.
Detection is LOG-ONLY — unlike the scraper's `remove_single_heading_pages()`, nothing
here ever deletes a page: "this page contains only a heading" is not positive proof
the page is an erroneous orphan (a legitimate title-only chapter looks identical).
"""

from __future__ import annotations

import re

import pdfplumber
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

HEADING_COLOR = "#134252"
MAX_HEADING_LENGTH = 500  # Allow long chapter titles, but cap runaway paragraphs.

# "Chapter N: Title." on its own (a title's own terminal ? or ! also ends it).
CHAPTER_HEADING_EXACT_RE = re.compile(r"^Chapter\s+\d[\d,]*:\s*.*?[.?!]\s*$", re.IGNORECASE)
# Merged "Chapter N: Title" immediately followed by dialogue (a quote mark).
CHAPTER_MERGED_QUOTE_RE = re.compile(
    r"^(Chapter\s+\d+:\s*[^\"'“‘\n]+)\s+([\"'“‘].*)", re.IGNORECASE
)
# Fallback: merged "Chapter N: Title" followed by a new sentence (space + capital).
CHAPTER_MERGED_CAPITAL_RE = re.compile(
    r"^(Chapter\s+\d+:\s*.+?)\s+([A-Z][^.]+\.\s+.*)", re.IGNORECASE
)
# Heading-only page detection (Phase 6, log-only). Looser than the exact heading
# match on purpose: terminal punctuation optional, so a flag is never missed on a
# heading a rendering quirk left unterminated. Over-flagging costs a log line;
# nothing is ever deleted based on this.
HEADING_ONLY_PAGE_RE = re.compile(r"^Chapter\s+\d[\d,]*:\s*.*?[.?!]?\s*$", re.IGNORECASE)


def _escape_html(text: str) -> str:
    """Escape text for safe use in a reportlab Paragraph (HTML-like markup)."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _is_chapter_heading(text: str) -> bool:
    """True if a paragraph is a 'Chapter N: Title.' heading (title may be empty)."""
    stripped = text.strip()
    if len(stripped) > MAX_HEADING_LENGTH:
        return False
    return bool(CHAPTER_HEADING_EXACT_RE.match(stripped))


def build_pdf(text: str, output_path: str) -> None:
    """Render text to a formatted PDF at output_path.

    Splits on '\\f' into pages, then on blank lines into paragraphs; classifies each
    paragraph as heading vs. body and renders accordingly.
    """
    styles = getSampleStyleSheet()

    body_style = ParagraphStyle(
        "CustomBody", parent=styles["BodyText"], fontName="Times-Roman",
        fontSize=11, leading=15, alignment=TA_JUSTIFY, spaceBefore=6, spaceAfter=6,
    )
    chapter_style = ParagraphStyle(
        "ChapterHeading", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=14, leading=18, spaceBefore=18, spaceAfter=12,
        textColor=HEADING_COLOR, alignment=TA_LEFT,
        # Phase 6 orphan prevention: keep the heading on the same page as the
        # start of whatever follows it, so it can't be stranded at a page bottom.
        keepWithNext=1,
    )

    doc = SimpleDocTemplate(
        str(output_path), pagesize=letter,
        rightMargin=0.5 * inch, leftMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )

    story: list = []
    pages = [p for p in text.split("\f") if p.strip()]

    for i, page_text in enumerate(pages):
        if i > 0:
            story.append(PageBreak())

        for para in (p for p in page_text.split("\n\n") if p.strip()):
            clean_text = " ".join(para.split())  # collapse whitespace so text flows
            if not clean_text:
                continue

            if _is_chapter_heading(clean_text):
                story.append(Paragraph(_escape_html(clean_text), chapter_style))
                continue

            merged = (CHAPTER_MERGED_QUOTE_RE.match(clean_text)
                      or CHAPTER_MERGED_CAPITAL_RE.match(clean_text))
            heading_part = merged.group(1).rstrip() if merged else ""
            if not heading_part.endswith((".", "?", "!")):
                heading_part += "."
            if merged and len(heading_part) <= MAX_HEADING_LENGTH:
                # A genuine merged "heading + body": split them so the heading styles.
                story.append(Paragraph(_escape_html(heading_part), chapter_style))
                body_part = merged.group(2).strip()
                if body_part:
                    story.append(Paragraph(_escape_html(body_part), body_style))
            else:
                # Not a heading (no match, or an over-long false match on an
                # un-segmented paragraph). Render the whole paragraph as body so no
                # text is ever dropped. Proper paragraph segmentation is Phase 4's job.
                story.append(Paragraph(_escape_html(clean_text), body_style))

    if not story:
        # Never emit a totally empty document; surface a single visible marker instead.
        story.append(Paragraph("(no extractable text)", body_style))

    doc.build(story)


def detect_heading_only_pages(pdf_path: str) -> list[int]:
    """Return the 1-based page numbers whose only content is one heading line.

    Detection-only (Phase 6): the caller may warn/log, but the page is NEVER
    removed — a heading-only page is either a legitimate title-only chapter or
    upstream data loss, and neither may be silently deleted. Mirrors the page
    scan of the scraper's `remove_single_heading_pages()` without its rewrite.
    """
    flagged: list[int] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if len(lines) == 1 and HEADING_ONLY_PAGE_RE.match(lines[0]):
                flagged.append(page_no)
    return flagged
