# Webnovel Editor — Editing Rules Reference

This is the consolidated, implementation-facing reference for the editorial pipeline.
It is populated from `build-spec.md` (Editing Rules — Shadow Slave) and kept in sync as
rules are implemented. **All rules are mechanical**: no rule rewrites prose, improves style,
changes tone, or makes judgment calls about meaning. When certainty is low, a rule leaves the
text unchanged.

The end goal is **TTS-ready output** for Kokoro / Microsoft TTS (see "TTS-Readiness Criteria"
at the bottom). Every rule exists to make a chapter read aloud cleanly as an audiobook.

Each rule is a pure function (string in → string out), living in `scripts/Universal/rules/`
(universal, reusable across novels) or driven by per-novel data in
`scripts/Universal/profiles/<novel>/`. (As of the Phase-8 reorganization all program code
lives under `scripts/Universal/`; the module names in the table below are relative to that
package. User-editable protected-term indexes and per-novel edit-details markdown ship under
`scripts/Universal/resources/` — see Stage 13 and the per-novel edit-details docs.)

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

## Stage 1.5 — Ad / URL / Fingerprint Junk Strip (IMPLEMENTED — hardened in the v0.10.0 plan)

**Status: shipped and hardened.** Built in Phase 4 (v0.4.0) and substantially hardened in the
v0.10.0 junk-strip-hardening plan (Phases 1–4) against real dirty corpora — Noble Queen and
Supreme Magus example chapters — not against guesses. This section documents intent and the
real evidence base; the exact patterns live in `scripts/Universal/rules/junk_strip.py`.

### Why this is a first-class stage
Webscraped novel PDFs are frequently littered with piracy/scraper fingerprinting that ruins a
TTS listen: ads ("read the latest chapters at…"), bare URLs/domains in the prose, and site
watermarks (often obfuscated with black-square glyphs, homoglyphs, or odd spacing to dodge
filters). A URL or "visit piratesite.net" read aloud mid-chapter is a first-class defect for an
audiobook, so removing it is a first-class stage.

### Evidence base (real, per corpus — grounded in machine scans, not hypothetical)

**A. Legacy source (from the prior editor `ss_pdf_editor-v1.py`, earlier scrape source).**
The `remove_novelbin()` pass shipped against concrete fingerprints:
- Exact markers: `@@novelbin@@`, `All ■■■■■ full.com`
- Black-square-obfuscated domains: `Free■ebnovel.c■m`, `■■■■w■■■ov■■.co■` (letters → U+25A0)
- Spaced/obfuscated promos: `Want to read more chapters? Come to p a n d a - n ovel,c.o.m`

**B. Shadow Slave corpus** (`webscraped_shadow_slave/`, 3,000 PDFs — the clean source).
A 100%-coverage Phase-1 scan found **none** of these markers, black squares, or bare URLs — it
came from a cleaner source (freewebnovel, which stripped its `<subtxt>` watermark tags at scrape
time). For *this* corpus the stage is insurance; it remains a genuine need for dirtier sources.
The 10 pinned Shadow Slave fixtures (now committed under `files/test-files/shadow_slave/`) verify
this clean-source behavior in every clone.

**C. The Noble Queen corpus** (`The_Noble_Queen-v2/`, 778 PDFs — dirty, novelfire source).
novelfire.net watermarks spliced **inline into prose** (prose on both sides of the splice) in
several shapes the original patterns could not see:
- 17+ mangled domain spellings: `n0velfire`, `Nove1Fire`, `NoveIFire`, dropped-letter variants.
- Tilde-separated `novel~fire~net` (no dot) and hyphen+truncated-TLD `novel-fire.et`.
- Degraded template skeletons down to `crs r s novelfirenet`, and **cross-line splices** where a
  template sentence ends one wrapped line and the domain opens the next (Phase 4 evidence).

**D. Supreme Magus corpus** (`Supreme_Magus-v2/`, 4,191 PDFs — dirty, multi-site source).
- Inline domain watermarks from ~8 sites (NiceNovel, NovelWell, NovelsToday, Libread,
  lightsnovel, pandasnovel scrambles, etc.).
- Spaced-out `f r e e w e b n o v e l. c o m` (5 files).
- **One confirmed homoglyph watermark** — math-script-styled `freewebnovel.com` (ch 2151) that
  NFC cannot fold; an NFKC sweep of all 7,979 files found no others.
- Support-block lines (`AN:` / discord / ko-fi / paypal).
- **3 whole-file Cloudflare error-1015 pages** (Ch. 1423, 1424, 1427) — the chapter text is
  missing entirely; these are the **detect-and-flag** class (see below), never auto-stripped.
  *(Bookkeeping: the initial Phase-1 recon estimated "4" such pages including one unconfirmed
  "+1 more"; the committed detector-backed sample `SM_ERROR_PAGES` and the Phase-5 corpus run
  both confirm the real count is **3** — see DECISIONS.md #027.)*

### Design (as implemented)
- **Tier 1 — high-confidence, default ON, near-zero false positive:** exact known markers,
  `@@…@@` markers, bare URLs (`https?://`, `www.`); a **two-layer domain matcher** (an exact list
  of every recorded mangled spelling **plus** a structural fuzzy layer — 0/1/3/I glyph folding,
  bounded Levenshtein scaled to stem length, tail-truncation — gated by an English-word guard set
  with the legitimate `webnovel.com` guard-listed; see DECISIONS.md #006); **minimum-span inline
  removal** (excise only the confirmed junk token/span, preserve adjacent prose; drop a whole line
  only when the whole line is proven junk; DECISIONS.md #004); spaced-domain and
  black-square-obfuscated tokens; and **detection-only NFKC** on a throwaway copy of styled runs
  to catch homoglyph domains without ever NFKC-rewriting the document (DECISIONS.md #003).
- **Cloudflare error-1015 pages — detect-and-flag, NEVER auto-strip** (`detect_error_page()`,
  ≥2 independent signals): both pipelines emit a GUI warning + a JSONL `integrity_flag` record
  and preserve the page as-is. The fix for a data-loss error page is a re-scrape, not an edit
  (DECISIONS.md #005).
- **Tier 2 — heuristic promo LINES, default OFF / log-only, higher false-positive risk:** lines
  like "read the latest chapters at…", translator's-note spam, donation plugs, and
  discord/ko-fi/paypal tokens. **Never** strip a segment containing a `ProtectedLexicon` term or
  canonical name.
- Runs only on non-placeholder text; **every removal is recorded to the JSONL ReplacementLog**
  (`rule="junk_strip"`) so it is fully auditable and reversible. A committed zero-false-positive
  suite over letter-sharing prose words + the shortest real defect fragments guards the patterns
  in every clone; optional `@pytest.mark.local_corpus` tests exercise the full corpora when
  present (with a `--require-local-corpora` strict mode).

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
`profiles/shadow_slave/canonical_names.py`). User additions come from the shipped
`scripts/Universal/resources/novel-index/<novel>.txt` files. Shadow Slave, Supreme Magus, and
The Noble Queen now ship real per-novel profiles + indexes; every other novel runs
universal-only (no canonical-name protection, no forced fixes).

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

## PDF Build — Orphan Heading-Only Page Handling (Stage 20 companion)

The PDF builder (`scripts/Universal/pdf/builder.py`) guards against a chapter heading being
stranded alone at the bottom of a page:
- **Prevention (active):** the chapter-heading `ParagraphStyle` sets `keepWithNext=1`, so a
  heading can never land by itself at a page bottom. This is a structural no-op for today's
  single-chapter inputs (the heading is already at the top of page 1).
- **Detection-only (active, multi-chapter builds):** `detect_heading_only_pages()` uses the
  existing `pdfplumber` to find any page whose sole content is a heading line. `batch_runner`
  runs it **only** on multi-chapter output (≥2 `\f`-separated segments) and, on a hit, emits a
  GUI warning + a JSONL `integrity_flag` record while **preserving the page**.
- **Automatic deletion — DEFERRED, not implemented.** No safe positive "this page is a genuine
  erroneous orphan" invariant exists, and the defect is not reproducible from either local
  corpus (all inputs are per-chapter single-chapter PDFs). No PDF rewrite path exists, so `pypdf`
  is **not** a dependency. See DECISIONS.md #017 / #018.

---

## TTS-Readiness Criteria (the target outcome)

Primary target playback engine: **Microsoft Edge Neural** voice (also validated against Kokoro /
Microsoft TTS generally). Output is considered "reads cleanly aloud" when:
1. The chapter title is present and clean — exactly `Chapter N: Title.` on its own line
   (a title's own terminal `?`/`!` is preserved, never given a duplicate trailing period).
2. No bare URLs or domains appear anywhere (Stage 1.5) — including mangled/homoglyph/spaced and
   inline-spliced scraper watermarks.
3. No stray symbols are voiced as words — no `■ □ �`, lone `|`/`\`, raw `/`, or bracket litter;
   spaced em/en-dashes are converted so the engine pauses rather than reading "dash".
4. Sentence/paragraph breaks are sane — false breaks rejoined, dehyphenation done, no mid-word
   splits shredding prosody.
5. Punctuation is clean — no `..`, `?!.`, or missing post-period spaces.
6. Everything is UTF-8 so smart quotes/accents are not spelled out as mojibake.

**Re-verification (v0.10.0, Phase 4).** These criteria were re-verified at 100% corpus coverage
against the new Noble Queen and Supreme Magus corpora (7,979 cached extractions). The established
garbage sweep (spaced dashes, squares/U+FFFD, `__WE_` leaks, invisibles, ligatures, double
spaces, space-before-punctuation, `word.Word` fusions, control chars) found **zero** hits — the
criteria held. The one genuine gap found was criterion 2 (a novelfire watermark class the older
patterns missed), fixed in Stage 1.5. Classes deliberately **flagged but not changed** (mechanical
inference is unsafe, so they are candidate *future* rules, not v0.10.0 changes): `*` emphasis /
censored-profanity asterisks (uncensoring is spec-excluded), unconverted `~` and raw `#` in
authored contexts, letter-tight apostrophe-misuse (`don't`/`l'm` — Edge Neural voices it
correctly today), and unspaced numeric-range dashes (`10-20`, betting odds) whose spoken form is
not inferable.
