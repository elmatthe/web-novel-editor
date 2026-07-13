"""The Noble Queen editorial pipeline (Phase 5b).

Mirrors `pipelines/shadow_slave.py` stage-for-stage — the same three-block
masked-correction structure documented there — driven by the Noble Queen
profile data instead: `NQ_CANONICAL_NAMES` (via the registry/lexicon) and
`NQ_SPECIAL_FIXES` (empty by evidence — see the profile's special_fixes.py).
With no forced substitutions, the novel-specific value of this pipeline is
the protected-term masking of the Noble Queen floor + index.

Signature matches the profile interface contract:
    run_pipeline(text, lexicon, *, repl_log=None, gui_log=None, dry_run=False) -> str
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
from profiles.the_noble_queen.special_fixes import NQ_SPECIAL_FIXES

if TYPE_CHECKING:
    from core.protected_lexicon import ProtectedLexicon
    from core.replacement_log import ReplacementLog

# Count-only patterns for the audit summary (the transforms themselves live in the rules).
_COUNT_DOUBLE_QUOTES = re.compile("[“”„‟❝❞〝〞＂«»]")
_COUNT_SPACED_DASH = re.compile(r"\S+[\s   -   　]+[–—―⸺][\s   -   　]+\S+")


def _summary(repl_log, count: int, rule: str, category: str, note: str) -> None:
    """Record a single audit row for a bulk/structural transform (only if it fired)."""
    if repl_log is not None and count > 0:
        repl_log.record(f"{count} occurrence(s)", note, rule, category, note)


def _apply_special_fixes(text: str, repl_log) -> str:
    """Forced typo substitutions, applied longest-key-first; each logged discretely."""
    for bad, good in sorted(NQ_SPECIAL_FIXES.items(), key=lambda kv: -len(kv[0])):
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
    """Run the full Noble Queen editorial pipeline over `text` and return clean text."""
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
