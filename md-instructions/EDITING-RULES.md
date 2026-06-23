# Webnovel Editor — Editing Rules Reference

This is the consolidated, implementation-facing reference for the editorial pipeline.
It is populated from `build-spec.md` (Editing Rules — Shadow Slave) and kept in sync as
rules are implemented. **All rules are mechanical**: no rule rewrites prose, improves style,
changes tone, or makes judgment calls about meaning. When certainty is low, a rule leaves the
text unchanged.

The end goal is **TTS-ready output** for Kokoro / Microsoft TTS (see "TTS-Readiness Criteria"
at the bottom). Every rule exists to make a chapter read aloud cleanly as an audiobook.

Each rule is a pure function (string in → string out), living in `scripts/rules/` (universal,
reusable across novels) or driven by per-novel data in `scripts/profiles/<novel>/`.

---

## Canonical Stage Order

Apply in exactly this order. Earlier stages expose issues that later stages fix.

| # | Stage | Module | Phase |
|---|-------|--------|-------|
| 1 | Unicode cleanup (invisibles, zero-width, NFC, space-likes, quotes) | `rules/unicode_cleanup.py` | 4 |
| 2 | Ligature normalization (ﬁ→fi, ﬂ→fl, …) | `rules/ligature_cleanup.py` | 4 |
| **1.5** | **Ad / URL / fingerprint junk strip** *(runs here — see below)* | **`rules/junk_strip.py`** | **4** |
| 3 | Non-standard spacing + scanner-junk (■/□/�) removal, space collapse | `rules/unicode_cleanup.py` | 4 |
| 4 | Header/footer/page-number removal (deferred safe no-op) | `rules/spacing_cleanup.py` | 4 |
| 5 | Repeated chapter-title contamination removal | `rules/spacing_cleanup.py` | 4 |
| 6 | Page-boundary collision repair | `rules/spacing_cleanup.py` | 4 |
| 7 | Paragraph reconstruction (false line-break, dehyphenation, spurious spaces) | `rules/spacing_cleanup.py` | 4 |
| 8 | MASK chapter lines + protected terms | `core/protected_lexicon.py` | 5 |
| 9 | OCR repair dictionary pass | `rules/ocr_repair.py` | 4 |
| 10 | Spurious-space / contraction repair (within masked text) | `rules/spacing_cleanup.py` | 4 |
| 11 | UNMASK placeholders | `core/protected_lexicon.py` | 5 |
| 12 | Chapter title format normalization | `rules/chapter_titles.py` | 4 |
| 13 | Canonical name normalization | `profiles/shadow_slave/canonical_names.py` | 4 |
| 14 | Forced recurring typo substitutions | `profiles/shadow_slave/special_fixes.py` | 4 |
| 15 | Punctuation repairs | `rules/punctuation.py` | 4 |
| 16 | Grammar repairs (+ American-English variant) | `rules/grammar.py` | 4 |
| 17 | Slash replacement (`/` → " out of ") | `rules/slash_replace.py` | 4 |
| 18 | Final spaced em-dash sweep (mandatory 2nd pass) | `rules/em_dash.py` | 4 |
| 19 | Duplicate chapter title removal | `rules/spacing_cleanup.py` | 4 |
| 20 | Chapter page-break insertion (for PDF builder) | `pdf/builder.py` | 3/4 |
| 21 | Chapter heading validation (log only, no auto-fix) | `rules/chapter_titles.py` | 4 |

> **Why Stage 1.5 sits where it does:** junk-strip must run **after** unicode normalization and
> ligature folding (so text is consistent) but **before** Stage 3 strips the ■ black-square
> glyphs — because scraper watermarks *use* those squares to obfuscate domains
> (`Free■ebnovel.c■m`). If the squares were stripped first, the marker would collapse into
> unmatchable garbage. Junk-strip removes the intact marker; Stage 3 then mops up any residue.

---

## ⚠ Stage 1.5 — Ad / URL / Fingerprint Junk Strip (PLACEHOLDER — finalized in Phase 4)

**Status: STUB in Phase 1. The full stripping logic is built in Phase 4, against real corpus
samples — not guesses.** This section documents intent and the evidence base; the exact
patterns are finalized when implementing the module.

### Why this is a first-class stage
Webscraped novel PDFs are frequently littered with piracy/scraper fingerprinting that ruins a
TTS listen: ads ("read the latest chapters at…"), bare URLs/domains in the prose, and site
watermarks (often obfuscated with black-square glyphs or odd spacing to dodge filters). A URL
or "visit piratesite.net" read aloud mid-chapter is a first-class defect for an audiobook, so
removing it is a first-class stage.

### Evidence base (real, not hypothetical)
The prior editor `files/study-examples/ss_pdf_editor-v1.py` already shipped a `remove_novelbin()`
pass against concrete fingerprints from an earlier scrape source:
- Exact markers: `@@novelbin@@`, `All ■■■■■ full.com`
- Black-square-obfuscated domains: `Free■ebnovel.c■m`, `■■■■w■■■ov■■.co■` (letters → U+25A0)
- Spaced/obfuscated promos: `Want to read more chapters? Come to p a n d a - n ovel,c.o.m`

### Important finding about the current corpus
The active corpus `files/pdf-example-chapters/webscraped_shadow_slave/` (3,000 PDFs) was scanned
during Phase 1 planning (250+ chapters, forced-UTF-8) and contains **none** of these markers,
black squares, or bare URLs — it appears to come from a cleaner source. So for *this* corpus the
stage is insurance; it remains a genuine need for dirtier sources and future novels.

### Design (to implement in Phase 4)
- **Tier 1 — high-confidence, default ON, near-zero false positive:** exact known markers (port
  `MARKERS_TO_REMOVE` + the panda-promo regex from `ss_pdf_editor-v1.py`), `@@…@@` markers, bare
  URLs (`https?://`, `www.`), and standalone obfuscated-domain tokens (■-substituted and
  space-spread `d o m a i n . c o m`). **Token-level** removal — strip the URL/marker, leave the
  surrounding prose intact.
- **Tier 2 — heuristic promo LINES, default OFF / log-only, higher false-positive risk:** lines
  like "read the latest chapters at…", "translator's note:" spam, donation plugs. **Never** strip
  a segment containing a `ProtectedLexicon` term or canonical name.
- Runs only on non-placeholder text; **every removal is recorded to the JSONL ReplacementLog**
  (`rule="junk_strip"`) so it is fully auditable and reversible.

---

## Stage 1 — Unicode Cleanup
Remove invisibles (U+200B/C/D, U+FEFF, control/format chars). NFC-normalize. Convert space-likes
(U+00A0, U+2009, U+2002/3, U+202F, U+205F, U+3000) to U+0020. Normalize corrupted/mismatched
apostrophes and quotes; preserve valid consistent curly quotes.

## Stage 2 — Ligature Normalization
`ﬁ`→fi, `ﬂ`→fl, `ﬀ`→ff, `ﬃ`→ffi, `ﬄ`→ffl, `ﬅ`/`ﬆ`→st. Global, before any other processing.

## Stage 3 — Non-Standard Spacing & Scanner Junk
Remove stray black squares (U+25A0/25A1), replacement glyphs (U+FFFD), and control bytes
(U+0000–U+001F except newline/CR). Collapse 2+ spaces to one (except at paragraph boundaries).
Strip only — never guess the intended character.

## Stage 4 — Header/Footer/Page-Number Removal (Deferred)
This stage is currently a logged no-op: extraction discards page-position data, so it cannot
safely distinguish a repeated header/footer from repeated prose. Header/footer removal is
deferred pending page-position-aware extraction. No content is removed by this stage.

## Stage 5 — Repeated Chapter-Title Contamination
Remove chapter-title recurrences after the first canonical instance
(`remove_duplicate_chapter_titles_global()`, ported from `ss_pdf_editor-v1.py`).

## Stage 6 — Page-Boundary Collision Repair
Repair words fused or split across a page transition when the intended word is obvious; leave
ambiguous cases alone.

## Stage 7 — Paragraph Reconstruction
- **False line-break repair:** a break not following terminal punctuation and followed by a
  lowercase letter is joined with a space; breaks after terminal punctuation or before a capital
  (new sentence / chapter heading) are preserved.
- **Dehyphenation:** preserve the hyphen by default when rejoining a wrapped word
  (`well-\nknown` → `well-known`). Remove it only for an explicit known-safe wrap such as
  `sur-\nface` → `surface`; preserve legitimate compound hyphens (`three-storied`,
  `hand-to-hand`).
- **Single-letter split repair:** `d efending` → `defending` (`fix_spurious_spaces()`), with the
  article-`a` exception (do not merge `a spell` → `aspell`).

## Stage 8 — Masking
Mask `Chapter` + digit lines as `__WE_CH_NNNNN__`; mask protected lexicon terms as
`__WE_P_NNNNN__` (longest-first; letter-boundary match for single words; `\s+` between
multi-word terms; expand possessive/plural variants). Store maps for restoration. (Phase 5.)

## Stage 9 — OCR Repair
Apply only outside placeholders. Dictionary (`tbe`→the, `bis`→his, `0f`→of, …), zero-to-O in
words (`b0dy`→body), dotted-word repair (`h.i.p.s`→hips), pipe/backslash-in-word
(`V|adion`→Vladion). Dictionary is extendable without changing logic.

## Stage 12 — Chapter Title Normalization
Target: `Chapter N: Title.` — exact number as written (no zero-pad), colon + single space, title
ends with a period. Allowed: fix `Chapter` casing, insert missing colon/period, strip stray
spaces, fix obvious typos where the intended word is already present. **Forbidden:** invent a
missing title, rename/rephrase a title.
Detection: `^Chapter\s+(\d[\d,]*)\s*[:\-–—]?\s*(.+?)\.?\s*$` (IGNORECASE | MULTILINE).

## Stage 13 — Canonical Name Normalization
Correct obvious misspellings to the built-in `SS_CANONICAL_NAMES` floor (in
`profiles/shadow_slave/canonical_names.py`). User additions come from `files/novel-index/`.

## Stage 14 — Forced Recurring Typo Substitutions
`SS_SPECIAL_FIXES` applies while protected terms are still masked, so it corrects only
unprotected text:
`Almanach`→Almanac, `carcassess`→carcasses, `threestoried`→three-storied,
`tompost shelf`→topmost shelf, `Obers`→Obels. Easy to extend.

## Stage 15 — Punctuation Repairs
Collapse duplicate punctuation (`..`→`.`, `?!.`→`?!`); insert missing space after
`, . ; : ! ?`; remove space before punctuation; repair fused sentence ends (`word.Word`→`word.
Word`). No stylistic commas. Balance only clearly-broken closing punctuation.

## Stage 16 — Grammar Repairs
Unambiguous only: article agreement (`a explosion`→`an explosion`), clear subject-verb agreement,
obvious pronoun/tense fixes. American-English variant only when a correction already requires
choosing one (`centre`→center, `armour`→armor). Do not mass-replace British spellings.

## Stage 17 — Slash Replacement
**Numeric slash → "out of"; all other slashes preserved verbatim.** Convert a digit/digit
ratio only (`6/7` → `6 out of 7`, `10/20` → `10 out of 20`). Every other slash — `and/or`,
`his/her`, `yes/no`, any word/word form — is left exactly as written (no substitution, no
mapping table). Apply only outside placeholder tokens.

## Stage 18 — Spaced Em-Dash Removal (Mandatory Two-Pass)
A `—` with spaces on both sides must **never** appear in output. Replace by context:
parenthetical → `, `; related clauses → `; `; sentence boundary (next word capitalized) → `. `.
Also handle NBSP+dash combos, spaced en-dash (U+2013), horizontal bar (U+2015), two-em-dash
(U+2E3A). Unspaced dashes (`word—word`) are untouched. A dedicated second pass runs for **every**
file. Port `remove_spaced_em_dashes()` from `ss_pdf_editor-v1.py`.

## Stage 21 — Chapter Heading Validation
After normalization, scan for any `Chapter …` line not matching the expected format. **Log a
warning only — no auto-fix, no crash.**

---

## TTS-Readiness Criteria (the target outcome)

Output is considered "reads cleanly aloud" for Kokoro / Microsoft TTS when:
1. The chapter title is present and clean — exactly `Chapter N: Title.` on its own line.
2. No bare URLs or domains appear anywhere (Stage 1.5).
3. No stray symbols are voiced as words — no `■ □ �`, lone `|`/`\`, raw `/`, or bracket litter;
   spaced em/en-dashes are converted so the engine pauses rather than reading "dash".
4. Sentence/paragraph breaks are sane — false breaks rejoined, dehyphenation done, no mid-word
   splits shredding prosody.
5. Punctuation is clean — no `..`, `?!.`, or missing post-period spaces.
6. Everything is UTF-8 so smart quotes/accents are not spelled out as mojibake.
