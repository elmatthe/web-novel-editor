# Supreme Magus — Novel-Specific Edit Details

These edits are **unique to "Supreme Magus"** and are layered **on top of** the
universal rules in `UNIVERSAL.md`. The universal baseline still runs in full; the items
below are the Supreme Magus-only additions.

> Loaded automatically when "Supreme Magus" is the selected novel. The lookup maps the
> novel name to this file (`Supreme-Magus.md`). If this file were missing, the tool
> would fall back to universal-only editing.

---

## Forced recurring typo substitutions

Always-applied corrections (not protections), run while protected terms are still
masked so they can never touch a real name. Kept in sync with
`scripts/profiles/supreme_magus/special_fixes.py`. Ported in Phase 5b from the
legacy `sm_pdf_editor-v8.2.py` proper-noun artifact map and re-validated against
the real Supreme_Magus-v2 corpus (4,191 chapters).

| Found (incorrect)          | Replaced with   |
|----------------------------|-----------------|
| `Silven/ving` `Silvenrving`| `Silverwing`    |
| `Thn1d` `Thmd`             | `Thrud`         |
| `O1pal`                    | `Orpal`         |
| `L0crias`                  | `Locrias`       |
| `S0lus`                    | `Solus`         |
| `Phlon'a`                  | `Phloria`       |
| `Fn'ya` `F riya`           | `Friya`         |
| `lnxialot`                 | `Inxialot`      |
| `Ragnar?k` `Ragnar??k` `Ragnarfik` `Ragnarfi k` | `Ragnarök` |

> The corpus's intact spelling is the authored `Ragnarök` (o-umlaut, ~185
> occurrences survive extraction correctly), so the corrupted forms restore to
> `Ragnarök` — not the legacy editor's plain `Ragnarok`, which would have left
> the output with two spellings of the same word.

### Deliberately NOT ported from the legacy editor

- **The profanity-uncensor system** (`EXPLICIT_UNCENSOR_MAP`,
  `COMMON_CENSORED_WORDS`, censor masking/uncensor passes). Spec-excluded:
  this pipeline is mechanical cleanup and never alters content. Censored
  words pass through exactly as the source prints them.
- **Generic-word OCR artifacts** (`rnade`→`made`, `S00n`→`Soon`,
  `fiabbergasted`, `overqualifled`). Not novel-specific — they are universal
  OCR-repair candidates at best — and `rnade` is a real substring
  false-positive hazard (it occurs inside "Bernadette").
- **Possessive duplicates** (`Thn1d's`, `Thmd's`, `O1pal's`): redundant —
  substring replacement of the base form already covers them.

---

## Protected terms (Supreme Magus)

The Supreme Magus protected-term list is the built-in canonical names
(`SM_CANONICAL_NAMES`, 594 terms ported from the user's master index — the
richest of the novel indexes, a confirmed superset of all four `_legacy/`
lists) merged with the user-maintained index at
`scripts/Universal/resources/novel-index/supreme-magus.txt`. Main cast (`Lith`, `Solus`, `Kamila`,
`Phloria`, …), the full noble/military/academy rosters, places, factions, and
creature races are masked before the letter-mutating passes so they are never
altered, split, or dropped.

To protect a new Supreme Magus term, add it to
`scripts/Universal/resources/novel-index/supreme-magus.txt` (one term per line). No code change is
needed.

---

## Source-specific note

The multi-site inline watermarks this corpus carries (NiceNovel/NovelWell/
Libread/lightsnovel/pandasnovel etc., spaced-out and homoglyph domains) are
removed by the universal junk-strip stage (Phase 2 hardening). The whole-file
Cloudflare error-1015 pages in the corpus are detected and **flagged for
re-scrape, never auto-stripped** — that behaviour is universal too.
