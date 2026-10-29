"""Stages 4-7 — header/footer/page-number removal, page-boundary repair, paragraph
reconstruction (false line-break repair, dehyphenation), and pdfplumber single-letter
spurious-space repair.

The load-bearing stage here is `reconstruct_paragraphs`. Extraction of this corpus yields
one block of single-`\\n` line-wraps with zero paragraph breaks; this stage rebuilds the
paragraph structure (`\\n\\n`) the PDF builder needs, joining layout-wrapped lines with a
space and starting a new paragraph only at a true sentence-ending boundary. It also
hard-isolates any chapter-heading line into its own paragraph regardless of punctuation,
so heading styling never depends on the generic break heuristic.

`fix_spurious_spaces` is ported from `ss_pdf_editor-v1.py`. It mutates letters, so the
pipeline runs it inside the masked region (Stage 10), not here in the pre-mask block.
"""

from __future__ import annotations

import logging
import re

from core.protected_lexicon import CHAPTER_LINE_START_RE

# A line "ends a sentence" if it ends in terminal punctuation, allowing trailing
# closing quotes/brackets after it (e.g. `bitter!"` or `end.)`).
_ENDS_SENTENCE_RE = re.compile(r"""[.!?…:]["'’”)\]]*$""")

# Standalone page-number line (just digits, optionally spaced).
_PAGE_NUMBER_LINE_RE = re.compile(r"^\s*\d{1,4}\s*$")

# Layout-wrap hyphen: a word split across a line end, continued lowercase.
_DEHYPHEN_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]+)-\n([a-z][A-Za-z]*)")
_KNOWN_SAFE_WRAP_SPLITS = {("sur", "face"): "surface"}
_LOG = logging.getLogger(__name__)


def remove_headers_footers(text: str) -> str:
    """Return text unchanged until extraction retains page-position metadata.

    Header/footer removal needs per-page top/bottom position data. The extraction stream
    does not retain it, so a positional implementation would be unsafe.
    """
    _LOG.info("Header/footer removal skipped: requires page-position data to be safe.")
    return text


def repair_page_boundaries(text: str) -> str:
    """Repair the one safely-detectable page-join artifact: a word hyphen-split across
    the boundary (handled by `dehyphenate`) and a number fused to the start of a word
    (`12Sunny` -> `Sunny`) left by a page-number colliding with body text.

    Broader fused/split-word repair is intentionally NOT attempted: after extraction the
    page boundaries are gone, so guessing would introduce false positives into clean
    prose. Layout-wrap splits are recovered by `reconstruct_paragraphs` instead.
    """
    # A standalone 1-4 digit run glued to the front of a capitalized word at a line
    # start is almost always a page number that collided with the next paragraph.
    return re.sub(r"(?m)^\s*\d{1,4}(?=[A-Z][a-z])", "", text)


def dehyphenate(text: str) -> str:
    """Rejoin words split by layout hyphenation: ``sur-\\nface`` -> ``surface``.

    Hyphens are preserved by default; only explicit known-safe split pairs are stripped.
    """
    def rejoin(match: re.Match[str]) -> str:
        first, second = match.groups()
        return _KNOWN_SAFE_WRAP_SPLITS.get((first.lower(), second.lower()), f"{first}-{second}")

    return _DEHYPHEN_RE.sub(rejoin, text)


def reconstruct_paragraphs(text: str) -> str:
    """Rebuild paragraph structure from single-`\\n` line-wrapped extraction text.

    Joins layout-wrapped continuation lines with a space; starts a new paragraph
    (`\\n\\n`) only when the previous line ended a sentence AND the next line does not
    begin lowercase. Blank lines are honored as explicit paragraph breaks. Any
    chapter-heading line is forced into its own isolated paragraph.
    """
    paragraphs: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            joined = " ".join(current).strip()
            if joined:
                paragraphs.append(joined)
            current.clear()

    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            flush()
            continue
        if CHAPTER_LINE_START_RE.match(line):
            flush()
            paragraphs.append(line)  # heading: always its own paragraph
            continue
        if not current:
            current.append(line)
            continue
        prev = current[-1]
        if _ENDS_SENTENCE_RE.search(prev) and not line[:1].islower():
            flush()
            current.append(line)
        else:
            current.append(line)
    flush()

    return "\n\n".join(paragraphs)


# --- Repeated chapter-title contamination (Stage 5, line-based, pre-mask) ----
_CHAPTER_ANY_RE = re.compile(r"Chapter\s+(\d+)", re.IGNORECASE)


def collapse_same_line_duplicate_chapters(text: str) -> str:
    """Cut a line at a second 'Chapter N' occurrence on the same line (scrape glitch)."""
    new_lines: list[str] = []
    for line in text.split("\n"):
        matches = list(_CHAPTER_ANY_RE.finditer(line))
        if len(matches) < 2:
            new_lines.append(line)
            continue
        by_number: dict[str, list[re.Match]] = {}
        for m in matches:
            by_number.setdefault(m.group(1), []).append(m)
        cut_line = line
        for _num, m_list in by_number.items():
            if len(m_list) >= 2:
                cut_line = line[: m_list[1].start()].rstrip()
                break
        new_lines.append(cut_line)
    return "\n".join(new_lines)


def remove_doubled_chapter_lines(text: str) -> str:
    """Drop exact-duplicate 'Chapter ...' lines (keep the first occurrence)."""
    seen: set[str] = set()
    out: list[str] = []
    for line in text.split("\n"):
        s = line.strip()
        if s.lower().startswith("chapter "):
            if s in seen:
                continue
            seen.add(s)
        out.append(line)
    return "\n".join(out)


# --- pdfplumber single-letter spurious-space repair (Stage 10, ported) -------
def fix_spurious_spaces(text: str) -> str:
    """Fix broken words from pdfplumber inserting spurious spaces.

    ``d efending`` -> ``defending``, ``r espectively`` -> ``respectively``. Skips the
    article ``a `` so ``a spell`` is not merged into ``aspell``. Ported from
    ``ss_pdf_editor-v1.py``.
    """

    def rejoin_single_letter_splits(t: str) -> str:
        rejoin_re = re.compile(r"(?<=\s)([bcdefghjklmnopqrstuvwxyz])\s([a-z])")
        fixed: list[str] = []
        for line in t.split("\n"):

            def repl_line(mm: re.Match[str]) -> str:
                st = mm.start()
                if st >= 2 and line[:st].endswith("a "):
                    return mm.group(0)
                return mm.group(1) + mm.group(2)

            fixed.append(rejoin_re.sub(repl_line, line))
        return "\n".join(fixed)

    def rejoin_a_splits(t: str) -> str:
        return re.sub(r"\ba\s([bcdfghjklmnpqrstvwxyz])\1", r"a\1\1", t)

    split_fixes = [
        (r"\bi\s+gnored\b", "ignored"), (r"\br\s+espectively\b", "respectively"),
        (r"\bc\s+ontestants\b", "contestants"), (r"\bw\s+ould\b", "would"),
        (r"\bc\s+ould\b", "could"), (r"\bs\s+hould\b", "should"),
        (r"\bi\s+nto\b", "into"), (r"\bi\s+ts\b", "its"), (r"\bi\s+t\b", "it"),
        (r"\bi\s+n\b", "in"), (r"\bi\s+s\b", "is"), (r"\bo\s+nly\b", "only"),
        (r"\ba\s+bout\b", "about"), (r"\ba\s+gain\b", "again"),
        (r"\ba\s+fter\b", "after"), (r"\ba\s+ll\b", "all"),
        (r"\be\s+very\b", "every"), (r"\be\s+ven\b", "even"),
        (r"\ba\s+ny\b", "any"), (r"\bk\s+now\b", "know"),
    ]
    text = rejoin_single_letter_splits(text)
    text = rejoin_a_splits(text)
    for pat, repl in split_fixes:
        text = re.sub(pat, repl, text)
    return text
