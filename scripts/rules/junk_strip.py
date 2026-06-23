"""Ad / URL / scraper-fingerprint removal (Stage 1.5).

WHY THIS MODULE EXISTS
----------------------
Webscraped webnovel PDFs are frequently littered with piracy/scraper fingerprinting
that ruins a text-to-speech listen: advertisements ("read the latest chapters at..."),
bare URLs and domain names embedded in prose, and site watermarks inserted to trace
pirated copies (often obfuscated with black-square glyphs or odd spacing to dodge
filters). For a TTS audiobook, a URL or "visit piratesite.net" read aloud mid-chapter
is a first-class defect, so removing this junk is a first-class stage.

EVIDENCE THIS IS REAL (not a guess)
-----------------------------------
The prior editor `files/study-examples/ss_pdf_editor-v1.py` shipped a `remove_novelbin()`
pass targeting concrete fingerprints from an earlier scrape source (exact markers,
black-square-obfuscated domains, spaced/obfuscated promos). The CURRENT
`webscraped_shadow_slave/` corpus was scanned and contains NONE of these -- it is from a
cleaner source. This module is therefore insurance for this corpus and a genuine need for
dirtier sources / future novels.

TIERS
-----
* Tier 1 (default ON, near-zero false positive): exact known markers, `@@...@@` markers,
  bare URLs (http(s)://, www.), and the spaced/obfuscated panda-novel promo. Token-level
  removal -- strip the junk, leave surrounding prose intact. Every removal is recorded to
  the ReplacementLog (rule="junk_strip", category="fingerprint").
* Tier 2 (default OFF / log-only): heuristic promo LINES ("read the latest chapters
  at...", donation plugs). Higher false-positive risk, so when off it only logs candidate
  lines (it never removes them), and it never flags a line containing a protected term.

PLACEMENT: Stage 1.5 -- after unicode normalize (Stage 1) and ligature normalization
(Stage 2), but BEFORE scanner-junk square removal (Stage 3) and masking, so
square-obfuscated markers are still intact and matchable. Runs on non-placeholder text.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.protected_lexicon import ProtectedLexicon
    from core.replacement_log import ReplacementLog

# --- Tier 1: exact known markers (ported from ss_pdf_editor-v1.py) -----------
_MARKERS_TO_REMOVE = [
    "@@novelbin@@",
    "Free■ebnovel.c■m",
    "Free■ebn■vel.c■m",
    "All ■■■■■ full.com",
    "■■■■w■■■ov■■.co■",
]

# Generic @@...@@ scraper markers.
_AT_MARKER_RE = re.compile(r"@@[^@\n]{1,40}@@")

# Bare URLs and www. domains embedded in prose.
_URL_RE = re.compile(r"\bhttps?://\S+", re.IGNORECASE)
_WWW_RE = re.compile(r"\bwww\.[^\s,;)]+", re.IGNORECASE)

# Spaced/obfuscated panda-novel promo (any spacing variant), ported verbatim.
_PANDA_NOVEL_PROMO_RE = re.compile(
    r"(?:Do\s+you\s+)?"
    r"Want\s+to\s+(?:read|see)\s+more\s+chapters\??\s*"
    r"(?:(?:Come\s+to|Please\s+visit)\s+)?"
    r"p\s*a\s*n\s*d\s*a\s*[\s\-\.\,]+n\s*o\s*v\s*e\s*l\s*[\s\-\.\,]*c\s*\.?\s*o\s*\.?\s*m",
    re.IGNORECASE,
)

# --- Tier 2: heuristic promo lines (log-only by default) ---------------------
_TIER2_PROMO_LINE_RE = re.compile(
    r"(read\s+(?:the\s+)?(?:latest|more|full)\s+chapter|"
    r"visit\s+(?:us|our\s+site)|"
    r"support\s+(?:the|us\s+on)|"
    r"translator'?s?\s+note|donat)",
    re.IGNORECASE,
)


def _record(repl_log, original: str, rule: str, context: str) -> None:
    if repl_log is not None and original.strip():
        repl_log.record(original, "", rule, "fingerprint", context)


def strip_junk(
    text: str,
    *,
    lexicon: "Optional[ProtectedLexicon]" = None,
    enable_tier2: bool = False,
    repl_log: "Optional[ReplacementLog]" = None,
) -> str:
    """Remove ad/URL/fingerprint junk from ``text`` (Tier 1 always; Tier 2 if enabled).

    Tier 1 removals are recorded to ``repl_log``. Tier 2 lines are only logged (or,
    when ``enable_tier2`` is True, removed) and are never touched if they contain a
    protected term from ``lexicon``.
    """
    # --- Tier 1 -------------------------------------------------------------
    for marker in _MARKERS_TO_REMOVE:
        if marker in text:
            _record(repl_log, marker, "junk_strip.marker", marker)
            text = text.replace(marker, "")

    for regex, rule in (
        (_AT_MARKER_RE, "junk_strip.at_marker"),
        (_PANDA_NOVEL_PROMO_RE, "junk_strip.promo"),
        (_URL_RE, "junk_strip.url"),
        (_WWW_RE, "junk_strip.url"),
    ):
        for m in regex.finditer(text):
            _record(repl_log, m.group(0), rule, m.group(0))
        text = regex.sub("", text)

    # --- Tier 2 (heuristic lines) -------------------------------------------
    term_lowers = lexicon.term_set_lower if lexicon is not None else frozenset()
    out_lines: list[str] = []
    for line in text.split("\n"):
        if _TIER2_PROMO_LINE_RE.search(line):
            low = line.lower()
            if any(t in low for t in term_lowers):
                out_lines.append(line)  # shields a protected term: never touch
                continue
            if enable_tier2:
                _record(repl_log, line.strip(), "junk_strip.tier2_line", line)
                continue  # drop the line
            # log-only (default): keep the line untouched. Tier 2 is gated off for
            # this clean corpus; removal only happens when enable_tier2 is True.
        out_lines.append(line)
    return "\n".join(out_lines)
