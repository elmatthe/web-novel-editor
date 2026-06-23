"""Punctuation repairs — mechanical and conservative only.

Fixes clear extraction artifacts without touching style: collapse a doubled comma or a
two-dot run (ellipsis ``...`` is preserved), insert a missing space after a comma or a
sentence-ending ``. ! ?`` when it was clearly dropped, and remove a space wrongly placed
before ``, ; : ! ?``. Never adds stylistic commas; never alters numbers (``1,000``,
``3.14``) or ellipses.
"""

from __future__ import annotations

import re

# Exactly two dots (not part of a longer ellipsis) -> one period.
_DOUBLE_DOT_RE = re.compile(r"(?<!\.)\.\.(?!\.)")
_DOUBLE_COMMA_RE = re.compile(r",,+")
# Space after a comma when a letter follows directly (skips 1,000 -> digit follows).
_COMMA_SPACE_RE = re.compile(r",(?=[A-Za-z])")
# Sentence boundary lost: lowercase + .!? + Uppercase (skips decimals, ellipsis, e.g.).
_SENTENCE_SPACE_RE = re.compile(r"(?<=[a-z])([.!?])(?=[A-Z])")
# Space wrongly inserted before closing punctuation.
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,;:!?])")


def repair_punctuation(text: str) -> str:
    """Apply only mechanical, unambiguous punctuation corrections."""
    text = _DOUBLE_COMMA_RE.sub(",", text)
    text = _DOUBLE_DOT_RE.sub(".", text)
    text = _COMMA_SPACE_RE.sub(", ", text)
    text = _SENTENCE_SPACE_RE.sub(r"\1 ", text)
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    return text
