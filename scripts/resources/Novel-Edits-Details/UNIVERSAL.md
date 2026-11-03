# UNIVERSAL — Baseline Editor Rules

These are the **universal editor rules**. They describe the default editing behaviour the
Webnovel Editor always runs, regardless of which novel is selected. Every novel inherits
this baseline; novel-specific files in this folder (e.g. `Shadow-Slave.md`) only add the
edits that are *unique* to that novel, layered on top of these.

> This file is the shared base for all novels. Keep it novel-agnostic — anything that only
> applies to one novel belongs in that novel's own `<Novel-Name>.md`, not here.

**Terminology — "Basic Edit Mode."** The always-on universal baseline described here is what
the app calls **Basic Edit Mode**: the editing every novel gets whether or not it has a
profile. A novel with no matching profile (unknown, or an empty-placeholder index) runs Basic
Edit Mode *only* — universal cleanup, no character-name protection and no forced novel-specific
fixes. Selecting a profiled novel (Shadow Slave, Supreme Magus, The Noble Queen) layers that
novel's specific edits on top.

---

## How this layering works

1. **`UNIVERSAL.md` is always loaded and applied as the base.** It is the floor of editing
   behaviour for every run.
2. **When a specific novel is selected**, the tool also loads the matching
   `<Novel-Name>.md` (looked up by novel name) and applies those edits **on top of** the
   universal ones.
3. **If no matching novel file exists**, the tool falls back to **universal-only** editing.
   It never crashes on a missing novel file.

---

## Baseline editing behaviour (always applied)

The universal pipeline runs deterministic cleanup in three blocks, grouped by their
relationship to term-masking.

### Block A — Pre-mask cleanup
- **Unicode normalization** — NFC form; strip invisible/zero-width characters; normalize
  space-like characters to a normal space.
- **Quote normalization** — non-standard double quotes (`„ ‟ « »`, ornamental and fullwidth)
  become straight `"`; correct curly doubles `“ ”` and apostrophes are kept as written
  (v0.4.0: the old fold-everything-to-straight step is retired).
- **Ligature cleanup** — `ﬁ`, `ﬂ`, etc. expanded to their plain letters.
- **Junk strip** — remove ad lines, scraper URLs, and watermark fingerprints (Tier 1 on).
- **Scanner-junk removal** — drop replacement glyphs / stray boxes.
- **Header / footer / page-number handling** — recurring page furniture (logged no-op
  until page-position-aware extraction exists; never deletes real prose).
- **Duplicate / doubled chapter-line collapse**.
- **Page-boundary repair** and **de-hyphenation** of words wrapped across a line break
  (hyphen preserved for genuine compounds like `well-known`).
- **Paragraph reconstruction** — re-insert `\n\n` paragraph breaks and isolate the chapter
  heading onto its own line.

### Block B — Masked corrections (run shielded)
Protected terms and chapter-heading lines are masked first so letter-mutating passes can
never alter a real name:
- **OCR repair** (conservative — only repairs that cannot fire on clean prose).
- **OCR `l` for the pronoun `I`** (v0.4.0) — only `l'm`/`l'll`/`l've`/`l'd` and a
  sentence-initial `l` before a short list of verbs actually seen in the corpus
  (`l know` → `I know`). Digit `1`, mid-sentence `l`, letter names and list labels are untouched.
- **Spurious-space repair** and **multiple-space collapse**.
- Novel-specific substitutions match whole tokens only (never inside a longer word) and can
  never shorten a name (for example `Clan Valor` can never become `Valor`).
- **Slash replacement** — numeric ratios only (`6/7` → `6 out of 7`); every other slash
  (`and/or`, `his/her`, …) is preserved verbatim.
- **First spaced em/en-dash pass**.
- Forced novel-specific substitutions run here while terms are still masked (these come
  from the selected novel's file — see that novel's `<Novel-Name>.md`).

### Block C — Post-unmask editorial
- **Chapter-title normalization** (number preserved as written).
- **Punctuation repair** (ellipsis- and number-safe).
- **Grammar** — unambiguous `a`/`an` correction only.
- **Mandatory final spaced em/en-dash sweep** — no spaced em/en/bar dash survives.
- **Duplicate chapter-title removal**, blank-line tidy, and chapter page-break (`\f`)
  insertion for the PDF builder.
- **Heading validation** (log-only).
- **Typography** (v0.4.0, last step) — straight double quotes become `“…”` only when a whole
  paragraph's quotes pair up unambiguously; anything uncertain (speech running across
  paragraphs, inch marks, quotes touching a protected name) is left exactly as written.
  `don't`, `it's`, `dog's` and similar endings get `’`; leading elisions (`'em`), plural
  possessives (`dogs'`), feet marks and single quotation marks are left alone. Protected names
  — including Clan Valor, Valor Clan and Valor in every novel — and their possessives are never
  changed.

---

## Protected terms (universal floor)

Every run also loads a protected-term lexicon so names are never corrupted by the repair
passes. The universal floor is each novel's built-in canonical-name set merged with the
user-maintained list in `scripts/resources/novel-index/<novel>.txt`. A missing or empty index falls
back to the built-in floor without error.
