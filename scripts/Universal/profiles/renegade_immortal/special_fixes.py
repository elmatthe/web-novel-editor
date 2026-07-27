"""Renegade Immortal forced typo substitutions (proper-noun artifacts).

Added 2026-07-26 on the author's ruling that "Liguo" is the canonical spelling for the
devil Xu Liguo. Applied with plain longest-key-first `str.replace` while protected terms
are masked, exactly like `profiles/supreme_magus/special_fixes.py` — so every key must be
a token that cannot occur in legitimate prose as a substring.

Corpus evidence, counted over all 2,082 extracted chapters of renegade-immortal-1 on
2026-07-26:
  * "Liguo"  — 928 substring hits: "Liguo" (768), "Liguo's" (159), "Liguos" (1). Canonical.
  * "Ligou"  —  38 substring hits, all inside "Ligou" (35) or "Ligou's" (3). Source typo.
  * "Ligo"   —  39 substring hits, of which **38 are inside "Ligou"** and exactly one is a
    standalone "Ligo" ("...the devil Xu Liguo came out. The moment Xu Ligo saw the Nascent
    Soul..." — the same sentence pair, so unambiguously the same character).

ORDERING IS LOAD-BEARING. "Ligo" is a prefix of "Ligou", so replacing "Ligo" first would
turn every "Ligou" into "Liguou". `_apply_special_fixes` sorts keys longest-first, which
replaces all 38 "Ligou" before "Ligo" is considered; the resulting "Liguo" does not contain
"Ligo" as a substring, so the second key cannot re-fire on the first key's output. This is
pinned by test_renegade_immortal_ligo_prefix_does_not_double_apply — do not reorder or
switch this map to insertion order.

Substring replacement also covers the possessives ("Ligou's" -> "Liguo's") without separate
entries, matching the Supreme Magus convention.

The variant spellings are deliberately NOT in the novel-index. The pipeline masks protected
terms BEFORE applying special fixes, so an indexed "Ligou" would already be a placeholder
when this map is consulted and the fix could never fire. Only the canonical "Liguo" and
"Xu Liguo" are indexed, which is what protects the normalized result from the AI pass.
"""

from __future__ import annotations

RI_SPECIAL_FIXES: dict[str, str] = {
    # Xu Liguo (the devil sealed in Wang Lin's body) — author-ruled canonical 2026-07-26.
    # Longest key first is enforced by the applier, not by this ordering.
    "Ligou": "Liguo",
    "Ligo": "Liguo",
}
