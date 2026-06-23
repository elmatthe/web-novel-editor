"""Shadow Slave canonical names — the built-in protected-name floor.

Seeded verbatim from the build spec's Canonical Name Normalization section. This is
the always-loaded built-in set; `files/novel-index/shadow-slave.txt` adds user-
maintained terms on top of it (merged in Phase 5 via load_protected_lexicon). The
name-normalization rule that consumes this set is finalized in Phase 4.
"""

from __future__ import annotations

SS_CANONICAL_NAMES: frozenset[str] = frozenset({
    # Main cast
    "Sunny", "Sunless", "Nephis", "Neph", "Cassie", "Cassia",
    "Kai", "Night", "Effie", "Jet", "Rain", "Rani",
    # Supporting
    "Ananke", "Gunlaug", "Caster", "Hector", "Athena", "Harper",
    "Bloodwave", "Tyris", "Roan", "Obel", "Dale", "Naomi", "Verne",
    "Luster", "Kim", "Kimmy", "Morgan", "Winter", "Samara", "Belle",
    "Dorn", "Quentin", "Seishan", "Beastmaster",
    "Dire Fang", "Silent Stalker", "Blood Sage", "Hollow", "Nightmare",
    "Song Seer", "Song Hunter", "Song Knight", "Mordret", "Asterion",
    "Anvil", "Broken Sword", "Smile of Heaven", "Weaver",
    "The Forgotten God", "War God", "Storm God", "Sun God", "Beast God",
    "Shadow God", "Saint", "Scavenger", "Goliath", "White Feather",
    "Iron Hand", "Black Lion", "Silver Fang", "Silent Blade",
    "Fallen Grace", "Mountain King", "Crimson Terror", "Winter Beast",
    "Fallen Devil", "Stone Saint", "Dread Lord", "Nightmare Steed",
    "Soul Devourer",
    "Felix", "Rin", "Mark", "Lucas", "Elliot", "Theo", "Noah",
    "Grace", "Iris", "Paul", "Mia", "Victor", "Leon", "Eric",
})
