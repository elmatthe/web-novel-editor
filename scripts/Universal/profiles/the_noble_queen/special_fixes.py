"""The Noble Queen forced typo substitutions — intentionally empty.

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
`files/novel-index/the-noble-queen.txt`). Add entries here only with the same
corpus evidence standard used for `profiles/shadow_slave/special_fixes.py`.
"""

from __future__ import annotations

NQ_SPECIAL_FIXES: dict[str, str] = {}
