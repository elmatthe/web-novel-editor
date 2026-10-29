"""Shadow Slave forced recurring typo substitutions.

Originally seeded verbatim from the build spec's Forced Recurring Typo Substitutions
section. These are always applied (corrections, not protections) and are distinct from the
novel-index protection system.

Phase 01C (Gate 00 decision, DECISIONS 075): only approved name/term corrections remain
here (`Almanach`, `Obers`). `carcassess` -> `carcasses` was promoted to the universal
engine as a bounded whole-word fix; `threestoried` and `tompost shelf` were retired (a
style choice and a phrase-specific typo, neither with any corpus evidence).

Note: `Obel` is a canonical name (protected); `Obers` is a misprint of `Obels`
(plural) and is force-corrected here.
"""

from __future__ import annotations

from profiles.loader import load_corrections

#: Approved literal corrections; the data lives in profiles/corrections/shadow-slave.toml.
SS_SPECIAL_FIXES: dict[str, str] = load_corrections("shadow-slave")
