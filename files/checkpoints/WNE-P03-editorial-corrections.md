# WNE Phase 03 — Approved small corrections and protection hardening

Status: **PASS (internal Gate 03, 2026-11-01)** — every frozen-corpus difference is attributed to an
authorized rule; zero unexplained deltas; mandatory rulings verbatim in every profile.
Scope: Master Plan §8 / Phase 03 within the Gate 00 dispositions (DECISIONS 080).
Writer: Claude Code, Opus 5.5 / xHigh, HOME-PC. Independent reviewer: the single final Codex review
(DECISIONS 078); none scheduled here.

## Git state

- Branch `feature/0.4.0-script-only-editor`; input = Phase 02B `d248e71` (local = live origin).
  Unrelated untracked `md-instructions/plan-2-ai-editor-integration.md` preserved, never staged.

## Approval basis (no invented approval)

The repository does not hold the verbatim Gate 00 answers for D5–D7. Phase 01 was explicitly
conditional on approval of D1–D10 (P00 report §13) and proceeded; the 2026-11-01 directive lists
conservative curly quotes/apostrophes and bounded, evidence-supported OCR as Phase 03 work. D5 and D6
are therefore implemented exactly as proposed in the P00 report, D7 stays deferred, and `Asa result`
stays excluded. Anything broader than those proposals is not implemented.

## Changes by group

1. **Protection floor (§8.2).** `profiles/loader.py` now refuses word-deleting corrections
   (`Clan Valor` -> `Valor` style shortening), NFC-equivalent duplicate keys and — via
   `validate_against_protection`, called by `run_batch` before any run folder exists — any key that
   equals or shares a token span with a protected term. Profile corrections apply only on token
   boundaries (never inside a longer word), longest key first with a deterministic tie-break.
   Corpus effect: none (see evidence).
2. **D5 typography (`rules/typography.py`, last stage).** `TYPO-DQ-PAIR`: straight doubles become
   “…” only on a line where every quote is in an unambiguous open/close position, strictly
   alternating, even count, no existing curly double, no empty pair, no digit before a quote (inch
   marks) and no quote touching a protected name; otherwise the line is left as written and one
   `integrity_flag` audit row counts the uncertain lines. `TYPO-APOS`: `'` becomes ’ only between a
   letter and a word-final `s/t/re/ve/ll/d/m` ending. Leading elisions, plural possessives, feet
   marks, other in-name apostrophes and single quotation marks are preserved. Protected names plus a
   **mandatory rulings floor** (Clan Valor, Valor Clan, Valor, Grey Wolf Tribe, Ember Queen, God of
   Peace, Demon of Desire, War God, Goddess of Life) are masked for this stage in every profile, so
   their spelling, possessives and touching punctuation never change — including in Universal.
   `normalize_quotes` no longer flattens correct “ ” (only non-standard variants are folded); the
   three character classes that inspected `"` (`junk_strip` boundary/trailing sets, `spacing_cleanup`
   sentence end) now list “ ” too, so every earlier decision is glyph-independent. The legacy
   `quote_normalize` audit row now counts only folded non-standard variants.
3. **D6 OCR (`ocr_repair.repair_pronoun_l`).** Evidence scan (counts only): lowercase `l` for the
   pronoun occurs only in Supreme Magus — `l'm` 17, `l'll` 5, `l've` 1, `l'd` 1, and clause-initial
   `l` before 37 attested words (one Shadow Slave `l asked`). Repaired: those contractions anywhere
   (never valid English) and clause-initial `l` before an attested word. Not repaired: digit `1`
   (`1 foot`, `1 inch`, mid-clause `1 was` are real numbers), mid-clause `l`, capital `L`, split words
   (`l ife`, `l ike`, `l ost`), letter names, list labels, identifiers, protected terms. The rule runs
   before the legacy single-letter rejoin, which had glued `left. l hope` into `left. lhope`.
4. **Unchanged by design:** the two-pass spaced-dash algorithm and unspaced dashes (existing coverage
   plus the frozen `quotes_dashes` input), grammar/punctuation rules, no pronoun/gender automation.
5. **Deferred / excluded:** §8.4 positional page-number adapter (0 standalone digit lines in 12,818
   chapters and 0 page-edge numbers in 210 sampled pages — no evidence); `Asa result` (0 occurrences;
   `Asa` is a real name); digit-`1` OCR (no safe bounded form).

## Evidence

- Group 1 corpus attribution (`files/test-logs/rc/p03-g1-attribution.json`): **828 results, 0 changed
  beyond the 18 approved Phase 01 deltas, 0 unexplained, invariants all pass.**
- Groups 2+3 corpus attribution (`files/test-logs/rc/p03-g23-attribution.json`, every character
  of every result classified against the Phase 00 text + approved Phase 01 deltas): **828 results,
  738 changed, 24,130 double-quote glyph changes (TYPO-DQ-PAIR / preserved curly) and 4,505
  apostrophes (TYPO-APOS), 0 unexplained, 0 input changes, second application of the new rules a
  no-op on all 828, mandatory invariants pass in all 9 profiles × direct/PDF.** Per profile,
  quotes 2,646–2,694 and apostrophes 444–517; profiles with larger lexicons convert slightly fewer
  because quotes touching protected names stay as written. The frozen sample contains no attested
  `l`-pronoun context; on the raw local corpora the rule makes 88 repairs in 32 Supreme Magus
  chapters, 1 in Shadow Slave and 0 in the other three novels (matching the evidence scan).
- Focused tests: `test_protection_rulings.py` (49), `test_typography.py` (44), `test_ocr_pronoun.py`
  (31) — positive, clean negative, protected-term and full-pipeline cases for every new rule;
  idempotence; PDF + TXT glyph round-trip (Times-Roman renders and pdfplumber extracts “ ” ’).
- Legacy behavior recorded, not changed (needs a named approval to change):
  `spacing_cleanup.fix_spurious_spaces` glues a mid-clause lone consonant to the next word
  (`the letter l was` -> `the letter lwas`), pinned by `test_legacy_single_letter_rejoin_is_recorded_not_changed`.

## Test disposition (Phase 03)

| Node | Disposition |
|---|---|
| `test_rules::test_normalize_quotes_doubles_only` | Adapted to D5: “ ” preserved, non-standard doubles folded |
| `test_pipeline::test_audit_log_replacement_field_is_a_description_not_rule_name` | Input uses non-standard doubles to trigger the fold row |
| `test_universal_engine::test_the_three_legacy_profiles_keep_their_audit_summary_rows[*]` (3) | Same input adaptation; row policy unchanged |

## Remaining risks

- Typography leaves uncertain lines straight, so a chapter can mix straight and curly doubles where
  speech spans paragraphs or quotes touch protected names. This is the conservative contract.
- Representative before/after review by the user is collected for the final release gate.
