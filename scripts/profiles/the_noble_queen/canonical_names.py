"""The Noble Queen canonical names — the built-in protected-name floor.

Ported in Phase 5b from the user's hand-curated master index at
files/study-examples/noble_queen_master_index.txt (26 unique terms; the _legacy/ lists
are confirmed subsets). This is the always-loaded built-in set;
`scripts/Universal/resources/novel-index/the-noble-queen.txt` adds user-maintained terms on top of it
(and must remain a superset of this floor).
"""

from __future__ import annotations

NQ_CANONICAL_NAMES: frozenset[str] = frozenset({
    "Queen Bee",
    "Noble Queen",
    "Mongrel",
    "Lady Morgan",
    "Brock",
    "Honey",
    "Noble",
    "Fort",
    "Mordret",
    "Dreamscape",
    "The Dreamscape",
    "Dream Realm",
    "Awakened",
    "Aspect",
    "Blood Aspect",
    "Valor",
    "Sleeper",
    "Master",
    "Nightmare",
    "Memory",
    "Trial",
    "Echo",
    "Flaw",
    "Spell",
    "Sovereign",
    "Dread Lord",
})
