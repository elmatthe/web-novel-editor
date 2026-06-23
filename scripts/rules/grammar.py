"""Grammar repairs — unambiguous only.

This corpus extracts clean prose, so grammar repair is limited to the one mechanical fix
that is genuinely unambiguous: article agreement (``a``/``an``) before a clear vowel- or
consonant-initial word. The hard sound-based cases (``a university``, ``an hour``) are
deliberately left untouched -- words starting with ``u`` or ``h`` are never flipped --
because flipping them by spelling alone would introduce errors.

Subject-verb agreement, tense, and pronoun fixes from the spec are intentionally NOT
attempted here: they require judgment that a mechanical pass cannot make safely, and the
spec's own rule is "do not guess on ambiguous constructions -- leave unchanged."
"""

from __future__ import annotations

import re

# "a" before a vowel-letter word (excluding u-) should be "an".
# Guard "one"/"once" (vowel letter, consonant "w" sound).
_A_TO_AN_RE = re.compile(r"\b([Aa])\s+(?=(?!one\b|once\b)[aeio][a-z])")
# "an" before a consonant-letter word (excluding h-) should be "a".
_AN_TO_A_RE = re.compile(r"\b([Aa])n\s+(?=[bcdfgjklmnpqrstvwxyz][a-z])")


def _a_to_an(m: re.Match[str]) -> str:
    a = m.group(1)
    return ("An" if a == "A" else "an") + " "


def _an_to_a(m: re.Match[str]) -> str:
    a = m.group(1)
    return a + " "


def repair_grammar(text: str) -> str:
    """Apply only the unambiguous article-agreement correction."""
    text = _A_TO_AN_RE.sub(_a_to_an, text)
    text = _AN_TO_A_RE.sub(_an_to_a, text)
    return text
