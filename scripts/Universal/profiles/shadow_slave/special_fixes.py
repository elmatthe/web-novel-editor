"""Shadow Slave forced recurring typo substitutions.

Seeded verbatim from the build spec's Forced Recurring Typo Substitutions section.
These are always applied (corrections, not protections) and are distinct from the
novel-index protection system. The rule that applies them is finalized in Phase 4.

Note: `Obel` is a canonical name (protected); `Obers` is a misprint of `Obels`
(plural) and is force-corrected here.
"""

from __future__ import annotations

SS_SPECIAL_FIXES: dict[str, str] = {
    "Almanach": "Almanac",
    "carcassess": "carcasses",
    "threestoried": "three-storied",
    "tompost shelf": "topmost shelf",
    "Obers": "Obels",
}
