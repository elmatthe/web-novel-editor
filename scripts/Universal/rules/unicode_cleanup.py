"""Stage 1 + Stage 3 — Unicode cleanup, quote normalization, scanner-junk removal.

Stage 1: NFC-normalize; strip invisibles (U+200B/C/D, U+FEFF, control/format chars,
keeping newline/CR/tab/form-feed); convert space-like chars (U+00A0, U+2009, U+2002/3,
U+202F, U+205F, U+3000, the U+2000-200A range, U+1680) to a plain U+0020.

Quote normalization (project decision: dialogue uses STRAIGHT doubles): curly/odd
DOUBLE quotes are folded to ASCII ``"``. Single quotes / apostrophes (U+2019 ``'``,
U+2018) are left untouched -- U+2019 is the consistent apostrophe in this corpus and
must be preserved.

Stage 3: remove stray squares (U+25A0/25A1) and replacement glyphs (U+FFFD), and
collapse runs of spaces to one (without touching paragraph/newline structure).
"""

from __future__ import annotations

import re
import unicodedata

# Space-like characters that function as a plain space in prose.
_SPACE_LIKE_RE = re.compile(
    "[   -    　]"
)

# Visible scanner junk: black square, white square, replacement glyph.
_SCANNER_JUNK_RE = re.compile("[■□�]")

# DOUBLE-quote variants folded to ASCII '"' (single quotes intentionally excluded):
# curly/low/reversed doubles, ornamental doubles, fullwidth, and guillemets.
_DOUBLE_QUOTE_RE = re.compile(
    "[“”„‟❝❞〝〞＂«»]"
)

# Collapse 2+ spaces/tabs (but never newlines) to a single space.
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")


def normalize_unicode(text: str) -> str:
    """NFC-normalize, strip invisibles, and fold space-like chars to U+0020."""
    text = "".join(
        ch
        for ch in text
        if not (unicodedata.category(ch) in ("Cc", "Cf") and ch not in "\n\r\t\f")
    )
    text = unicodedata.normalize("NFC", text)
    text = _SPACE_LIKE_RE.sub(" ", text)
    return text


def normalize_quotes(text: str) -> str:
    """Fold curly/odd DOUBLE quotes to ASCII '"'; leave single quotes/apostrophes."""
    return _DOUBLE_QUOTE_RE.sub('"', text)


def remove_scanner_junk(text: str) -> str:
    """Strip black squares and replacement glyphs left by extraction."""
    return _SCANNER_JUNK_RE.sub("", text)


def collapse_spaces(text: str) -> str:
    """Collapse runs of spaces/tabs to one space; trim trailing line whitespace."""
    text = _MULTISPACE_RE.sub(" ", text)
    text = re.sub(r"[ \t]+(\n)", r"\1", text)
    return text
