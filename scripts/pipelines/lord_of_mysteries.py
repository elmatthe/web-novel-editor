"""Lord of the Mysteries editorial pipeline — Phase 7 architecture stub.

This proves the multi-novel seam holds: a second novel slots in by importing a different
profile module (empty placeholder data here) and reusing the universal rule modules in the
*same order* as `shadow_slave.py`. No core module changes are required to add it — the
batch runner could swap which pipeline it imports, nothing more.

It is intentionally NOT a finished editorial profile. Building the real LOTM canonical
names and forced substitutions is a future data exercise once that corpus is in hand. The
canonical-name floor is empty (`LOTM_CANONICAL_NAMES`) and there are no forced
substitutions (`LOTM_SPECIAL_FIXES`), so this pipeline applies only the universal,
novel-agnostic rules. Protected terms a user adds to
`files/novel-index/lord-of-the-mysteries.txt` are still masked and survive untouched,
exactly as in the Shadow Slave pipeline.

The signature matches the profile interface contract from the build spec:
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
from profiles.lord_of_mysteries.special_fixes import LOTM_SPECIAL_FIXES

if TYPE_CHECKING:
    from core.protected_lexicon import ProtectedLexicon
    from core.replacement_log import ReplacementLog


def _apply_special_fixes(text: str, repl_log) -> str:
    """Forced typo substitutions from the profile (none in the placeholder)."""
    for bad, good in sorted(LOTM_SPECIAL_FIXES.items(), key=lambda kv: -len(kv[0])):
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
    """Run the universal editorial rules over `text`, in the Shadow Slave order."""
    log = gui_log or (lambda *_a, **_k: None)

    # --- BLOCK A — pre-mask cleanup ----------------------------------------
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
    text = spacing_cleanup.reconstruct_paragraphs(text)
    log("  ✓ Block A: cleanup + paragraph reconstruction")

    # --- BLOCK B — masked corrections --------------------------------------
    text, ch_map = mask_chapter_lines(text)
    text, prot_map = mask_protected_terms(text, lexicon)
    text = for_non_placeholder_segments(text, ocr_repair.repair_ocr)
    text = for_non_placeholder_segments(text, spacing_cleanup.fix_spurious_spaces)
    text = for_non_placeholder_segments(text, unicode_cleanup.collapse_spaces)
    text = for_non_placeholder_segments(text, slash_replace.replace_slashes)
    text = for_non_placeholder_segments(text, em_dash.remove_spaced_em_dashes)
    text = _apply_special_fixes(text, repl_log)
    text = unmask_placeholders(text, prot_map, ch_map)
    log(f"  ✓ Block B: masked repair ({len(prot_map)} terms, {len(ch_map)} headings)")

    # --- BLOCK C — post-unmask editorial -----------------------------------
    text = chapter_titles.normalize_chapter_titles(text)
    text = punctuation.repair_punctuation(text)
    text = grammar.repair_grammar(text)
    text = em_dash.remove_spaced_em_dashes(text)  # mandatory final sweep
    text = chapter_titles.remove_duplicate_chapter_titles_global(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = chapter_titles.insert_chapter_page_breaks(text)

    for bad in chapter_titles.validate_headings(text):
        log(f"  ⚠ Non-normalized chapter line: {bad}...")
    log("  ✓ Block C: editorial normalization")

    return text
