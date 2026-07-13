"""Stage 8 — OCR repair (targeted, conservative).

Applies only outside placeholder tokens (the pipeline wraps it in
`for_non_placeholder_segments`). The `webscraped_shadow_slave` corpus extracts cleanly,
so this stage is INSURANCE: it deliberately includes only repairs that cannot fire on
valid English prose, so it never corrupts already-clean text.

INCLUDED (safe on clean text):
  - whole-word OCR typos that are non-words (`tbe`->`the`, `0f`->`of`, ...)
  - digit-0-inside-word repair (`b0dy`->`body`) -- valid words never contain `0`
  - dotted-word repair (`h.i.p.s`->`hips`)
  - pipe/backslash-in-word repair (`V|adion`->`Vladion`)
  - glued contraction / possessive repair (`Lith'swill`->`Lith's will`, `aspell`->`a spell`)

DELIBERATELY EXCLUDED (would corrupt clean text in this corpus): the study example's
`?`->`fi` ligature guesser (mangles a question mark followed by a letter) and `l`->`I`
guesser, and the `/`->`r` in-word rule (would turn `and/or` into `andror`). Slash handling
belongs entirely to `slash_replace`; this corpus has no ligature-`?` artifacts.
"""

from __future__ import annotations

import re

# Apostrophe variants (ASCII + curly + modifier).
_APOS = r"['’‘ʼ´`]"

# Whole-word OCR typos (all non-words, so matching them is safe).
_OCR_WORD_FIXES: dict[str, str] = {
    "tbe": "the", "tiie": "the", "tlie": "the", "tihe": "the",
    "bis": "his", "liis": "his",
    "0f": "of", "0n": "on", "0ff": "off", "0nly": "only",
    "t0": "to", "0r": "or", "0ne": "one", "0ut": "out", "0wn": "own",
}


def _fix_ocr_words(text: str) -> str:
    for bad, good in _OCR_WORD_FIXES.items():
        text = re.sub(rf"\b{re.escape(bad)}\b", good, text)
    return text


def _fix_zero_to_o(text: str) -> str:
    """Digit 0 used in place of the letter o inside a word (valid words have no 0)."""
    text = re.sub(r"(?<=[a-zA-Z])0(?=[a-zA-Z'’])", "o", text)
    text = re.sub(r"(?<=[a-zA-Z])00(?=[a-zA-Z])", "oo", text)
    return text


def _fix_dotted_words(text: str) -> str:
    """`h.i.p.s` -> `hips`: collapse runs of 2+ letter-dot pairs into one word."""
    return re.sub(r"((?:[A-Za-z]\.){2,}[A-Za-z])",
                  lambda m: m.group(1).replace(".", ""), text)


def _fix_pipe_backslash_in_word(text: str) -> str:
    """`V|adion` -> `Vladion`, `Sve\\nsson` style backslash -> r (valid words have neither)."""
    text = re.sub(r"(?<=[a-zA-Z])\|(?=[a-zA-Z])", "l", text)
    text = re.sub(r"(?<=[a-zA-Z])\\(?=[a-zA-Z])", "r", text)
    return text


def _fix_glued_contractions(text: str) -> str:
    """Restore a missing space after a possessive/contraction glued to the next word.

    Only fires on extraction artifacts (no valid word follows a contraction with no
    space), so it is safe: `Lith'swill`->`Lith's will`, `can'tallow`->`can't allow`,
    `I'mhere`->`I'm here`, `aspell`->`a spell`, `alot`->`a lot`.
    """
    text = re.sub(rf"([A-Za-z]+{_APOS}s)([a-zA-Z]{{2,}})", r"\1 \2", text)
    text = re.sub(rf"(n{_APOS}t)([a-zA-Z]{{2,}})", r"\1 \2", text)
    text = re.sub(rf"({_APOS}ll)([a-zA-Z]{{2,}})", r"\1 \2", text)
    text = re.sub(rf"({_APOS}ve)([a-zA-Z]{{2,}})", r"\1 \2", text)
    text = re.sub(rf"({_APOS}re)([a-zA-Z]{{2,}})", r"\1 \2", text)
    text = re.sub(
        rf"\b([Ii]|[Ww]e|[Yy]ou|[Tt]hey|[Hh]e|[Ss]he|[Ii]t){_APOS}(m|ve|re|ll|d)([a-zA-Z]{{2,}})\b",
        r"\1'\2 \3",
        text,
    )
    for pat, repl in (
        (r"\baspell\b", "a spell"), (r"\baline\b", "a line"),
        (r"\balot\b", "a lot"), (r"\bafew\b", "a few"),
        (r"\balittle\b", "a little"),
    ):
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    return text


def repair_ocr(text: str) -> str:
    """Apply the conservative OCR-artifact corrections to non-placeholder text."""
    text = _fix_dotted_words(text)
    text = _fix_pipe_backslash_in_word(text)
    text = _fix_zero_to_o(text)
    text = _fix_ocr_words(text)
    text = _fix_glued_contractions(text)
    return text
