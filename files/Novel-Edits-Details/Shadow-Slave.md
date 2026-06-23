# Shadow Slave — Novel-Specific Edit Details

These edits are **unique to the "Shadow Slave" novel** and are layered **on top of** the
universal rules in `UNIVERSAL.md`. The universal baseline still runs in full; the items
below are the Shadow Slave-only additions.

> Loaded automatically when "Shadow Slave" is the selected novel. The lookup maps the
> novel name to this file (`Shadow-Slave.md`). If this file were missing, the tool would
> fall back to universal-only editing.

---

## Forced recurring typo substitutions

These are always-applied corrections (not protections), run while protected terms are
still masked so they can never touch a real name. Kept in sync with
`scripts/profiles/shadow_slave/special_fixes.py`.

| Found (incorrect) | Replaced with    |
|-------------------|------------------|
| `Almanach`        | `Almanac`        |
| `carcassess`      | `carcasses`      |
| `threestoried`    | `three-storied`  |
| `tompost shelf`   | `topmost shelf`  |
| `Obers`           | `Obels`          |

> Note: `Obel` is a canonical (protected) name; `Obers` is a misprint of the plural
> `Obels` and is force-corrected here. The two do not conflict because the substitution
> runs against the masked text.

---

## Protected terms (Shadow Slave)

The Shadow Slave protected-term list is the built-in canonical names
(`SS_CANONICAL_NAMES`) merged with the user-maintained index at
`files/novel-index/shadow-slave.txt`. These names — main cast (`Sunny`, `Nephis`,
`Cassie`, `Kai`, …), factions, locations, and unique terminology — are masked before the
letter-mutating passes so they are never altered, split, or dropped.

To protect a new Shadow Slave term, add it to `files/novel-index/shadow-slave.txt`
(one term per line). No code change is needed.

---

## Adding more novels

Each additional novel gets its own `<Novel-Name>.md` in this folder describing its
specific edits, while `UNIVERSAL.md` remains the shared base. The selected novel name is
mapped to its file (e.g. "Lord of the Mysteries" → `Lord-Of-The-Mysteries.md`); if no
file matches, editing falls back to universal-only.
