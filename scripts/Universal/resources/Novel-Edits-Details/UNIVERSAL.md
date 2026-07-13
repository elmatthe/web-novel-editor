# UNIVERSAL — Baseline Editor Rules

These are the **universal editor rules**. They describe the default editing behaviour the
Webnovel Editor always runs, regardless of which novel is selected. Every novel inherits
this baseline; novel-specific files in this folder (e.g. `Shadow-Slave.md`) only add the
edits that are *unique* to that novel, layered on top of these.

> This file is the shared base for all novels. Keep it novel-agnostic — anything that only
> applies to one novel belongs in that novel's own `<Novel-Name>.md`, not here.

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
- **Quote normalization** — curly double quotes (`“ ” „ ‟ « »`) become straight `"`;
  apostrophes are left as-is.
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
- **Spurious-space repair** and **multiple-space collapse**.
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

---

## Protected terms (universal floor)

Every run also loads a protected-term lexicon so names are never corrupted by the repair
passes. The universal floor is each novel's built-in canonical-name set merged with the
user-maintained list in `scripts/Universal/resources/novel-index/<novel>.txt`. A missing or empty index falls
back to the built-in floor without error.
