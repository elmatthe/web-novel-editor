"""Spaced em-dash removal — mandatory two-pass rule.

A long dash (em/en/horizontal-bar/two-em) with whitespace on BOTH sides must never appear
in output: it is replaced by ``. `` when the following word is capitalized (sentence
boundary) or ``, `` otherwise. Unspaced dashes (``word<emdash>word``) are left untouched.

Ported from `remove_spaced_em_dashes()` in `ss_pdf_editor-v1.py` (confirmed working). The
pipeline calls this twice: once inside the masked region and again as the mandatory final
sweep, so no spaced dash can survive into the PDF.
"""

from __future__ import annotations

import re

# Whitespace around the dash: ASCII + NBSP + Unicode space separators.
_WS = r"[\s   -   　]+"
# Em dash U+2014, en dash U+2013, horizontal bar U+2015, two-em dash U+2E3A.
_DASH = r"[–—―⸺]"
_SPACED_DASH_RE = re.compile(rf"(\S+){_WS}{_DASH}{_WS}(\S+)")

_NBSP = " "
_EM = "—"
_EN = "–"
_LITERAL_FALLBACKS = (
    (" " + _EM + " ", ", "),
    (_NBSP + _EM + _NBSP, ", "),
    (_NBSP + _EM + " ", ", "),
    (" " + _EM + _NBSP, ", "),
    (" " + _EN + " ", ", "),
    (_NBSP + _EN + _NBSP, ", "),
)


def _repl(m: re.Match[str]) -> str:
    before, after = m.group(1), m.group(2)
    if after and after[0].isupper():
        return before + ". " + after
    return before + ", " + after


def remove_spaced_em_dashes(text: str) -> str:
    """Replace every whitespace-flanked long dash with ``. `` or ``, `` by context."""
    text = _SPACED_DASH_RE.sub(_repl, text)
    text = _SPACED_DASH_RE.sub(_repl, text)
    for _ in range(4):
        old = len(text)
        for src, dst in _LITERAL_FALLBACKS:
            text = text.replace(src, dst)
        if len(text) == old:
            break
    return text
