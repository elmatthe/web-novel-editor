"""The Noble Queen forced typo substitutions.

One entry, added 2026-07-26 on the author's ruling. Phase 5b originally left this
map empty; that audit is preserved below because it still explains why nothing
else is here.

Phase 5b audited every Noble Queen study-examples script for novel-specific
forced edits and found none to port:

  * `scrape_noble_queen-v2/v3.py` carry only `V2_DECORATIVE_REPLACEMENTS` — the
    webnovel.com decorative-Unicode/homoglyph watermark table. That is a
    *universal* junk-strip class (handled by `rules/junk_strip.py` since
    Phase 2), not a Noble-Queen-specific edit, and the plan explicitly says
    not to duplicate it into the profile.
  * No recurring-typo or proper-noun-artifact map exists for this novel, and
    the Phase 1–4 corpus QA of The_Noble_Queen-v2 surfaced no recurring
    novel-specific misspelling to force-correct.

The profile's substance is its protected-term data (`canonical_names.py` +
`scripts/Universal/resources/novel-index/the-noble-queen.txt`). Add entries here only with the same
corpus evidence standard used for `profiles/shadow_slave/special_fixes.py`.

The one entry — "Kraii" -> "Kraai" (the tyrant king):
  * The source text is inconsistent about this character's name. Counted over
    all 890 extracted chapters of the-noble-queen-1 on 2026-07-26: "Kraai"
    appears 30 times across 9 chapters (241-244, 260-264) including the
    character's first appearance, "Kraii" 5 times across 3 (242, 266, 276).
    Both occur in chapter 242.
  * The author ruled on 2026-07-26 that "Kraai" is canonical, so this
    normalizes the 5 stragglers rather than freezing them.
  * Safe as a plain substring key: every "Kraii" in the corpus sits inside
    "Kraii" (3) or "Kraii's" (2) and nothing else, so substring replacement
    also fixes the possessive without a separate entry.
  * "Kraii" must NOT be added to the novel-index. The pipeline masks protected
    terms before applying special fixes, so an indexed "Kraii" would be a
    placeholder by the time this map is consulted and the fix could never fire.
    The canonical "Kraai" IS indexed, which is what protects the result.
"""

from __future__ import annotations

NQ_SPECIAL_FIXES: dict[str, str] = {
    # Kraai (the tyrant king) — source-text spelling drift, author-ruled 2026-07-26
    "Kraii": "Kraai",
}
