"""Renegade Immortal profile.

Promoted from profile-less to a registered profile on 2026-07-26 for one reason: the
novel needs a forced substitution (`RI_SPECIAL_FIXES`), and forced substitutions are
per-profile data. The universal fallback resolves its substitution map from
`profiles/lord_of_mysteries`, which is shared by every profile-less novel and is pinned
empty by test, so there was no way to give this novel a novel-specific fix without
registering it.

The canonical-name floor is deliberately empty: this novel's 837 protected terms live in
`scripts/Universal/resources/novel-index/renegade-immortal.txt`, which the registry loads
on top of the floor exactly as before. Protection is therefore byte-identical to the
pre-promotion universal-fallback behaviour — the only change is that special fixes now
fire.
"""
