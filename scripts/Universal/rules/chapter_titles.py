"""Chapter title normalization, duplicate removal, page-break insertion, validation.

Target format: ``Chapter N: Title.`` -- the exact number as written (commas preserved,
no zero-padding), a colon + single space, title ending in a period. Allowed: fix
"Chapter" casing, insert a missing colon/period, strip stray spaces, split body text
accidentally fused onto the heading line. Forbidden: invent or rephrase a title.

Adapted from `format_chapter_titles`, `remove_duplicate_chapter_titles_global`, and
`insert_chapter_page_breaks` in `ss_pdf_editor-v1.py`.
"""

from __future__ import annotations

import logging
import re

# Heading line: number keeps its exact form (commas allowed), optional separator.
_CHAPTER_TITLE_RE = re.compile(
    r"^(Chapter)\s+(\d[\d,]*)\s*[:\-–—]?\s*(.*)$",
    re.IGNORECASE,
)

# Body usually starts "Name verb ..." or "Pronoun verb ..." -- used to peel body text
# that extraction fused onto the heading line.
_TITLE_BODY_SPLIT_RE = re.compile(
    r"^(.*?)\s+([A-Z][a-z]+\s+(?:had|was|were|said|noticed|stood|gestured|thought|"
    r"realized|found|saw|heard|felt|knew|told|asked|turned|looked|moved|began)\s+)",
)

_MAX_TITLE_LEN = 120
_LOG = logging.getLogger(__name__)

# Post-normalization exact heading (for validation + dup detection). A title's
# own terminal ? or ! is as valid an ending as the appended period.
_HEADING_EXACT_RE = re.compile(r"^Chapter\s+[\d,]+:\s*.*?[.?!]\s*$", re.IGNORECASE)
_HEADING_PARAGRAPH_RE = re.compile(r"^Chapter\s+([\d,]+):", re.IGNORECASE)


def _split_title_body(rest: str) -> tuple[str, str]:
    part_match = re.match(r"^(.*?\s+\(Part\s+\d+\))\s+(.+)$", rest, re.IGNORECASE)
    if part_match:
        return part_match.group(1).strip(), part_match.group(2).strip()
    split_m = _TITLE_BODY_SPLIT_RE.match(rest)
    if split_m:
        title = split_m.group(1).strip()
        body = (split_m.group(2) + rest[split_m.end():]).strip()
        return title, body
    if len(rest) > _MAX_TITLE_LEN:
        cut = rest[:_MAX_TITLE_LEN].rfind(" ")
        if cut > 20:
            return rest[:cut].strip(), rest[cut:].strip()
    return rest, ""


def normalize_chapter_titles(text: str) -> str:
    """Normalize chapter heading lines to ``Chapter N: Title.`` (number preserved)."""
    out: list[str] = []
    for line in text.split("\n"):
        m = _CHAPTER_TITLE_RE.match(line.strip())
        if not m:
            out.append(line)
            continue
        _prefix, num_s, rest = m.groups()
        num_s = num_s.strip()
        rest = re.sub(r"^[:\-–—]+\s*", "", rest.strip())
        if not rest:
            _LOG.warning("Malformed chapter heading without title: Chapter %s", num_s)
            out.append(f"Chapter {num_s}")
            out.append("")
            continue
        title_part, body_part = _split_title_body(rest)
        title_part = title_part.rstrip(" .")
        # A title ending in its own terminal ?/! keeps it verbatim — appending a
        # period would create the "?."/"!." duplicate form Stage 15 forbids.
        terminal = "" if title_part.endswith(("?", "!")) else "."
        out.append(f"Chapter {num_s}: {title_part}{terminal}")
        out.append("")
        if body_part:
            out.append(body_part)
    return "\n".join(out)


def remove_duplicate_chapter_titles_global(text: str) -> str:
    """Drop repeated chapter-heading paragraphs, keeping the first per chapter number."""
    seen: set[str] = set()
    out: list[str] = []
    for para in text.split("\n\n"):
        m = _HEADING_PARAGRAPH_RE.match(para.strip())
        if not m:
            out.append(para)
            continue
        key = m.group(1).replace(",", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(para)
    return "\n\n".join(out)


def insert_chapter_page_breaks(text: str) -> str:
    """Insert a form feed before each chapter heading after the first (new PDF page).

    Skips the first heading so the builder does not emit a blank leading page.
    """
    out: list[str] = []
    seen_heading = False
    for line in text.split("\n"):
        if line.strip().lower().startswith("chapter "):
            if seen_heading:
                out.append("\f")
            seen_heading = True
        out.append(line)
    return "\n".join(out)


def validate_headings(text: str) -> list[str]:
    """Return chapter-heading lines that are NOT in the normalized format (for logging)."""
    bad: list[str] = []
    for para in text.split("\n\n"):
        s = para.strip()
        if s.lower().startswith("chapter ") and not _HEADING_EXACT_RE.match(s):
            bad.append(s[:120])
    return bad
