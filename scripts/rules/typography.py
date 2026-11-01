"""Phase 03 conservative typography (Master Plan §8.3; Gate 00 D5).

Two narrowly bounded rules, applied once at the very end of the pipeline so no earlier stage
(paragraph reconstruction, titles, punctuation, dashes) ever sees a different glyph than before:

``TYPO-DQ-PAIR`` (``typography.paired_double_quotes``)
    Within ONE paragraph (one line), straight double quotes become “…” only when the whole
    line is reliably bounded: an even number of straight quotes, no curly double already on
    the line, every quote in an unambiguous opening or closing position, strictly alternating
    open/close, no empty pair, no quote after a digit (inch marks), and no quote touching a
    protected name. Otherwise every quote on that line is left exactly as written (uncertain).
    There is no cross-line or global alternating counter. Existing curly quotes are never changed.

``TYPO-APOS`` (``typography.apostrophe_contraction``)
    A straight apostrophe becomes ’ only between a letter and a contraction/possessive ending
    (``n't``, ``'s``, ``'re``, ``'ve``, ``'ll``, ``'d``, ``'m``) that ends the word. Leading
    elisions ('em), plural possessives (dogs'), feet marks (5'), other in-name apostrophes
    (Xi'an, O'Brien's first apostrophe) and single quotation marks stay as written.

Protected names (the profile's lexicon plus the mandatory rulings floor) are masked first, so
their spelling, their possessives and the punctuation touching them are never changed.
"""

from __future__ import annotations

import re

from core.protected_lexicon import (
    ProtectedLexicon,
    load_protected_lexicon,
    mask_protected_terms,
    unmask_placeholders,
)

RULE_DOUBLE = "typography.paired_double_quotes"
RULE_APOSTROPHE = "typography.apostrophe_contraction"
RULE_UNCERTAIN = "typography.uncertain_double_quotes"

#: Mandatory rulings protected in every profile, even where a novel's index lacks them
#: (Master Plan §8.2; 2026-11-01 directive). Masking only shields them from typography.
RULINGS_FLOOR = frozenset({
    "Clan Valor", "Valor Clan", "Valor", "Grey Wolf Tribe", "Ember Queen", "God of Peace",
    "Demon of Desire", "War God", "Goddess of Life",
})

STRAIGHT, OPEN, CLOSE = '"', "“", "”"
_OPEN_BEFORE = frozenset(" \t\f([{—–-/")
_CLOSE_AFTER = frozenset(" \t.,;:!?)]}—–-…'’")
_PLACEHOLDER_EDGE = re.compile(r"__WE_(?:P|CH)_\d{5}__")
_APOSTROPHE_RE = re.compile(r"(?<=[^\W\d_])'(?=(?:[sStTdDmM]|re|RE|ve|VE|ll|LL)(?![^\W_]))")


def _role(line: str, i: int) -> str | None:
    """'open', 'close' or None (ambiguous) for the straight quote at ``line[i]``."""
    prev = line[i - 1] if i > 0 else None
    nxt = line[i + 1] if i + 1 < len(line) else None
    if prev is not None and prev.isdigit():
        return None  # inch mark / measurement
    opening = (prev is None or prev in _OPEN_BEFORE) and nxt is not None and not nxt.isspace() \
        and nxt not in ',;:!?)]}"'
    closing = prev is not None and not prev.isspace() and prev not in "([{" \
        and (nxt is None or nxt in _CLOSE_AFTER)
    if opening == closing:
        return None
    return "open" if opening else "close"


def _touches_placeholder(line: str, i: int) -> bool:
    for match in _PLACEHOLDER_EDGE.finditer(line):
        if match.end() == i or match.start() == i + 1:
            return True
    return False


def pair_line(line: str) -> tuple[str, int, bool]:
    """Return (line, quotes converted, uncertain?) for one paragraph line."""
    positions = [i for i, ch in enumerate(line) if ch == STRAIGHT]
    if not positions:
        return line, 0, False
    if OPEN in line or CLOSE in line or len(positions) % 2:
        return line, 0, True
    chars = list(line)
    for n, i in enumerate(positions):
        expected = "open" if n % 2 == 0 else "close"
        if _role(line, i) != expected or _touches_placeholder(line, i):
            return line, 0, True
        if expected == "close" and positions[n - 1] == i - 1:
            return line, 0, True  # empty pair
        chars[i] = OPEN if expected == "open" else CLOSE
    return "".join(chars), len(positions), False


def curl_double_quotes(text: str) -> tuple[str, int, int]:
    """Apply TYPO-DQ-PAIR line by line. Returns (text, converted quotes, uncertain lines)."""
    converted = uncertain = 0
    lines = text.split("\n")
    for index, line in enumerate(lines):
        new, count, unsure = pair_line(line)
        lines[index] = new
        converted += count
        uncertain += unsure
    return "\n".join(lines), converted, uncertain


def curl_apostrophes(text: str) -> tuple[str, int]:
    """Apply TYPO-APOS. Returns (text, apostrophes converted)."""
    return _APOSTROPHE_RE.subn("’", text)


def protection_lexicon(lexicon: ProtectedLexicon | None) -> ProtectedLexicon:
    terms = frozenset(lexicon.terms) if lexicon is not None else frozenset()
    return load_protected_lexicon("", terms | RULINGS_FLOOR)


def apply_typography(text: str, lexicon: ProtectedLexicon | None, repl_log=None) -> str:
    """Mask protected names, apply both rules, unmask, and record one audit row per rule."""
    masked, mapping = mask_protected_terms(text, protection_lexicon(lexicon))
    masked, quotes, uncertain = curl_double_quotes(masked)
    masked, apostrophes = curl_apostrophes(masked)
    result = unmask_placeholders(masked, mapping, {})
    if repl_log is not None:
        if quotes:
            repl_log.record(f"{quotes} straight double quote(s)", "paired curly quotes", RULE_DOUBLE,
                            "quote", "TYPO-DQ-PAIR: clearly paired quotes within one paragraph")
        if apostrophes:
            repl_log.record(f"{apostrophes} straight apostrophe(s)", "’", RULE_APOSTROPHE, "quote",
                            "TYPO-APOS: contraction/possessive ending after a letter")
        if uncertain:
            repl_log.record(f"{uncertain} paragraph(s)", "[quotes preserved as written - uncertain pairing]",
                            RULE_UNCERTAIN, "integrity_flag", "TYPO-DQ-PAIR left these lines unchanged")
    return result
