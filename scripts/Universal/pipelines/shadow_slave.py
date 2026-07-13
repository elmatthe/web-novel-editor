"""Shadow Slave editorial pipeline.

`run_pipeline` orchestrates the deterministic rule stages in the approved order. The order
is grouped into three blocks by relationship to masking, which is the load-bearing
structure:

  BLOCK A  Pre-mask cleanup (raw single-\\n line stream)
    1   unicode_cleanup.normalize_unicode     NFC, invisibles, space-likes
    1a  unicode_cleanup.normalize_quotes      curly DOUBLE quotes -> straight "
    2   ligature_cleanup.normalize_ligatures
    1.5 junk_strip.strip_junk                 ad/URL/fingerprint (Tier 1 on, Tier 2 off)
    3   unicode_cleanup.remove_scanner_junk    squares / replacement glyphs
    4   spacing_cleanup.remove_headers_footers page numbers / recurring lines
    5   spacing_cleanup.collapse_same_line_duplicate_chapters + remove_doubled_chapter_lines
    6   spacing_cleanup.repair_page_boundaries
    7   spacing_cleanup.dehyphenate + reconstruct_paragraphs   <-- inserts \\n\\n, isolates heading

  BLOCK B  Masked corrections (letter-mutating passes run shielded)
    8   MASK chapter lines + protected terms
    9   ocr_repair.repair_ocr                  (non-placeholder segments)
    10  spacing_cleanup.fix_spurious_spaces + collapse_spaces
    10a slash_replace + first em_dash pass
    11  SS_SPECIAL_FIXES while protected terms remain masked
    12  UNMASK (terms first, then chapter lines)

  BLOCK C  Post-unmask editorial (needs real text back)
    13  chapter_titles.normalize_chapter_titles
    14  punctuation.repair_punctuation
    15  grammar.repair_grammar
    16  em_dash.remove_spaced_em_dashes        MANDATORY final sweep
    17  chapter_titles.remove_duplicate_chapter_titles_global
    18  tidy blank lines
    19  chapter_titles.insert_chapter_page_breaks   \\f for the PDF builder
    20  chapter_titles.validate_headings       log-only

Letter-mutating corrections (OCR, spurious-space) run inside the mask so protected names
can never be altered; structural passes (punctuation, grammar, the final em-dash sweep,
title/dup/page-break handling) run post-unmask because they need real sentence text and
headings. Rule functions are pure (str -> str); high-value substitutions are recorded to
`repl_log` here in the pipeline.
"""

from __future__ import annotations

import re
from typing import Callable, Optional, TYPE_CHECKING

from core.protected_lexicon import (
    for_non_placeholder_segments,
    mask_chapter_lines,
    mask_protected_terms,
    unmask_placeholders,
)
from rules import (
    chapter_titles,
    em_dash,
    grammar,
    junk_strip,
    ligature_cleanup,
    ocr_repair,
    punctuation,
    slash_replace,
    spacing_cleanup,
    unicode_cleanup,
)
from profiles.shadow_slave.special_fixes import SS_SPECIAL_FIXES

if TYPE_CHECKING:
    from core.protected_lexicon import ProtectedLexicon
    from core.replacement_log import ReplacementLog

# Count-only patterns for the audit summary (the transforms themselves live in the rules).
_COUNT_DOUBLE_QUOTES = re.compile("[“”„‟❝❞〝〞＂«»]")
_COUNT_SPACED_DASH = re.compile(r"\S+[\s   -   　]+[–—―⸺][\s   -   　]+\S+")


def _summary(repl_log, count: int, rule: str, category: str, note: str) -> None:
    """Record a single audit row for a bulk/structural transform (only if it fired).

    `original` carries the count of affected spots; `replacement` carries a real
    human-readable description of the change (NOT the rule name — that lives in `rule`),
    so the JSONL audit can be read and trusted at a glance.
    """
    if repl_log is not None and count > 0:
        repl_log.record(f"{count} occurrence(s)", note, rule, category, note)


def _apply_special_fixes(text: str, repl_log) -> str:
    """Forced typo substitutions, applied longest-key-first; each logged discretely."""
    for bad, good in sorted(SS_SPECIAL_FIXES.items(), key=lambda kv: -len(kv[0])):
        if bad in text:
            if repl_log is not None:
                repl_log.record(bad, good, "special_fixes", "forced_substitution", bad)
            text = text.replace(bad, good)
    return text


def run_pipeline(
    text: str,
    lexicon: "ProtectedLexicon",
    *,
    repl_log: "Optional[ReplacementLog]" = None,
    gui_log: "Optional[Callable[[str], None]]" = None,
    dry_run: bool = False,
) -> str:
    """Run the full Shadow Slave editorial pipeline over `text` and return clean text."""
    log = gui_log or (lambda *_a, **_k: None)

    # Whole-file CDN error page? Flag for re-scrape and leave the text alone —
    # the chapter content is missing, so stripping would yield an empty chapter.
    error_reason = junk_strip.detect_error_page(text)
    if error_reason:
        log(f"  ⚠ {error_reason} — chapter text missing; file needs re-scrape")
        if repl_log is not None:
            repl_log.record(
                error_reason,
                "[FLAGGED: whole-file error page - re-scrape needed]",
                "junk_strip.error_page_flag",
                "integrity_flag",
                text.split("\n", 1)[0],
            )

    # --- BLOCK A — pre-mask cleanup ----------------------------------------
    n_quotes = len(_COUNT_DOUBLE_QUOTES.findall(text))
    text = unicode_cleanup.normalize_unicode(text)
    text = unicode_cleanup.normalize_quotes(text)
    text = ligature_cleanup.normalize_ligatures(text)
    text = junk_strip.strip_junk(text, lexicon=lexicon, repl_log=repl_log)
    text = unicode_cleanup.remove_scanner_junk(text)
    text = spacing_cleanup.remove_headers_footers(text)
    text = spacing_cleanup.collapse_same_line_duplicate_chapters(text)
    text = spacing_cleanup.remove_doubled_chapter_lines(text)
    text = spacing_cleanup.repair_page_boundaries(text)
    text = spacing_cleanup.dehyphenate(text)

    n_dash = len(_COUNT_SPACED_DASH.findall(text))
    text = spacing_cleanup.reconstruct_paragraphs(text)
    _summary(repl_log, n_quotes, "quote_normalize", "quote", "curly doubles -> straight")
    log("  ✓ Block A: cleanup + paragraph reconstruction")

    # --- BLOCK B — masked corrections --------------------------------------
    text, ch_map = mask_chapter_lines(text)
    text, prot_map = mask_protected_terms(text, lexicon)
    text = for_non_placeholder_segments(text, ocr_repair.repair_ocr)
    text = for_non_placeholder_segments(text, spacing_cleanup.fix_spurious_spaces)
    text = for_non_placeholder_segments(text, unicode_cleanup.collapse_spaces)
    slash_count_before = text.count("/")
    text = for_non_placeholder_segments(text, slash_replace.replace_slashes)
    n_slash = slash_count_before - text.count("/")
    text = for_non_placeholder_segments(text, em_dash.remove_spaced_em_dashes)
    text = _apply_special_fixes(text, repl_log)
    text = unmask_placeholders(text, prot_map, ch_map)
    _summary(repl_log, n_slash, "slash_replace", "slash", "numeric ratio -> out of")
    log(f"  ✓ Block B: masked repair ({len(prot_map)} terms, {len(ch_map)} headings)")

    # --- BLOCK C — post-unmask editorial -----------------------------------
    text = chapter_titles.normalize_chapter_titles(text)
    text = punctuation.repair_punctuation(text)
    text = grammar.repair_grammar(text)
    text = em_dash.remove_spaced_em_dashes(text)  # mandatory final sweep
    _summary(repl_log, n_dash, "em_dash", "dash", "spaced em/en dash -> , or .")
    text = chapter_titles.remove_duplicate_chapter_titles_global(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = chapter_titles.insert_chapter_page_breaks(text)

    for bad in chapter_titles.validate_headings(text):
        log(f"  ⚠ Non-normalized chapter line: {bad}...")
    log("  ✓ Block C: editorial normalization")

    return text
