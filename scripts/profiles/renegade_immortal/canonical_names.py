"""Renegade Immortal canonical names — deliberately an empty floor.

Unlike Shadow Slave, Supreme Magus and The Noble Queen — whose floors were ported from
hand-curated legacy master indexes — this novel's protected terms were built on
2026-07-26 by frequency analysis straight into
`scripts/Universal/resources/novel-index/renegade-immortal.txt` (837 terms, each counted
in the novel's own corpus). There is no separate hand-curated list to enshrine as a floor,
and duplicating the index here would create two sources of truth that could drift.

Keeping the floor empty also makes the 2026-07-26 promotion provably behaviour-preserving:
`resolve_dispatch` previously returned `canonical_names=frozenset()` for this novel via the
universal fallback, so the merged lexicon is byte-identical before and after.
"""

from __future__ import annotations

RI_CANONICAL_NAMES: frozenset[str] = frozenset()
