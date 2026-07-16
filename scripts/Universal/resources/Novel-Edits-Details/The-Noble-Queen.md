# The Noble Queen — Novel-Specific Edit Details

These edits are **unique to "The Noble Queen"** (the Shadow Slave fanfic) and are layered
**on top of** the universal rules in `UNIVERSAL.md`. The universal baseline still runs in
full; the items below are the Noble Queen-only additions.

> Loaded automatically when "The Noble Queen" is the selected novel. The lookup maps the
> novel name to this file (`The-Noble-Queen.md`). If this file were missing, the tool
> would fall back to universal-only editing.

---

## Forced recurring typo substitutions

**None.** Phase 5b audited the Noble Queen study-examples scrapers
(`scrape_noble_queen-v2/v3.py`) and the Phase 1–4 QA of the real
The_Noble_Queen-v2 corpus: no recurring novel-specific misspelling exists to
force-correct. The scrapers' only replacement table is the webnovel.com
decorative-Unicode/homoglyph watermark map — that is a **universal** junk-strip
concern (`scripts/rules/junk_strip.py`, hardened in Phase 2), deliberately not
duplicated into this profile.

`scripts/profiles/the_noble_queen/special_fixes.py` is therefore an empty dict
by evidence, not by omission.

---

## Protected terms (The Noble Queen)

The Noble Queen protected-term list is the built-in canonical names
(`NQ_CANONICAL_NAMES`, 26 terms ported from the user's master index) merged with
the user-maintained index at `scripts/Universal/resources/novel-index/the-noble-queen.txt`. These —
`Queen Bee`, `Noble Queen`, `Mongrel`, `Lady Morgan`, the Dreamscape/Aspect
terminology, and the Shadow Slave parent-series canon terms the fanfic reuses —
are masked before the letter-mutating passes so they are never altered, split,
or dropped.

To protect a new Noble Queen term, add it to
`scripts/Universal/resources/novel-index/the-noble-queen.txt` (one term per line). No code change is
needed.

---

## Source-specific note

The novelfire.net inline watermark splices this corpus carries (template
sentences + mangled domains spliced into prose) are removed by the universal
junk-strip stage (Phases 2/4 hardening), not by this profile — they would be
junk in any novel scraped from that site.
