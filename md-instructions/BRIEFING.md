# Webnovel Editor — Project Briefing

## Version: v0.7.0

## Last Updated
2026-06-22 — Phase 7: multi-novel architecture validation

## Current Phase
Phase 7 (Multi-Novel Architecture Validation) complete. The universal-vs-profile-data split
built across Phases 1–6 was validated as a pure data exercise: every universal rule module is
genuinely novel-agnostic (no Shadow Slave hardcoding in logic), the `run_pipeline` interface
contract holds, and a stub second-novel pipeline (Lord of the Mysteries, empty placeholder
profile) was scaffolded and proven to run end-to-end on a real fixture without crashing or
mangling protected terms. No core refactor was needed. The novel-profile GUI dropdown remains
a v2 item per spec. The gate is green at 86 tests (one bash syntax test skips only when
Windows exposes an unusable WSL shim).

Phase 6 (Hardening) and the v0.6.1 independent review fixes remain in place: four Critical
data-integrity fixes and six Minor fixes covered by the suite, with header/footer removal a
logged no-op until extraction provides page-position metadata. The slash rule was finalized in
v0.6.1 to its two-case form: numeric slash -> "out of"; every other slash preserved verbatim.

## What Was Just Built or Changed (v0.7.0 — Phase 7)
- **Universal modules audited, no SS hardcoding in logic.** `unicode_cleanup`,
  `ligature_cleanup`, `junk_strip`, `spacing_cleanup`, `ocr_repair`, `chapter_titles`,
  `punctuation`, `grammar`, `em_dash`, `slash_replace` are all genuinely novel-agnostic; the
  only SS mentions are provenance comments/docstrings.
- **Stub second-novel pipeline** `scripts/pipelines/lord_of_mysteries.py` — calls the
  universal rules in the same order as `shadow_slave.py` with an empty placeholder profile
  (`scripts/profiles/lord_of_mysteries/`: `LOTM_CANONICAL_NAMES = frozenset()`,
  `LOTM_SPECIAL_FIXES = {}`). Proves a second pipeline slots in with zero core changes.
- **`scripts/tests/test_multi_novel.py`** (4) — empty-profile assertion, loader handles the
  empty `lord-of-the-mysteries.txt` placeholder cleanly, the stub runs end-to-end on a real
  fixture (no placeholder leak / no spaced em-dash), and a user-protected term survives.
- **GUI novel-profile dropdown = v2 (per spec), not built.** Batch runner stays SS-only for v1.

## What Was Just Built or Changed (v0.6.1 review fixes)
- **C1:** numeric slash ratios alone become "out of" (`6/7` -> `6 out of 7`); every other
  slash (`and/or`, `his/her`, `yes/no`, any word/word form) is preserved verbatim — final
  two-case rule, no mapping table.
- **C2:** forced special fixes now run before unmasking, so protected terms cannot be altered.
- **C3/C4:** dehyphenation preserves hyphens unless a split is explicitly safe (`sur-face`),
  and header/footer removal is a logged safe no-op pending page-position extraction.
- **M1-M6:** the WSL bash shim test now skips honestly; the macOS launcher is executable;
  both launchers require Python 3.10+; titleless headings remain `Chapter N`; comma chapter
  headings render as headings; and the README describes the shipped application.
- **Spec corrections:** build spec and editing rules now state the conservative slash behavior,
  masked special fixes, safe dehyphenation, and deferred header/footer stage.

## What This Project Is
A local desktop (Tkinter) tool that batch-cleans messy webscraped webnovel chapter PDFs into
clean, **TTS-ready** PDFs for listening as audiobooks (Kokoro / Microsoft TTS). It extracts
text, runs a deterministic rule-based editorial pipeline (no AI rewriting), and writes
`EDITED_<name>.pdf` to a user-chosen folder. Originals are never modified. First novel:
Shadow Slave; multi-novel by design. Tech stack: Python 3.10+ (built on 3.12.10), Tkinter,
pdfplumber, reportlab, pytest. (PyPDF2 was removed in Phase 6 — see Deferred Features.)

## Repo / Git State
- Under git. Phase commits chain on feature branches: `main` (`5b4ec2c`, Phase 1) →
  `phase-2-gui-shell` → `phase-3-pdf-io` → `phase-4-rule-pipeline` (`24e2771`) →
  `phase-5-novel-index` (`feeea9c`). Phase 6 work is on branch **`phase-6-hardening`**.
- The 29 MB corpus (`files/pdf-example-chapters/`) is **gitignored**; the 10 pinned fixtures
  in `test-files/shadow_slave/` are committed. `test-logs/` is gitignored (QA render outputs
  + the temp `_qa_render.py` driver live there; not shipped).

## Packaging Decision (Phase 6 — RESOLVED, do not revisit by accident)
- **Distribution = the double-click launcher (`Setup_and_Run.bat` / `.command`). NO frozen
  PyInstaller exe for v1.** The launcher already gives a non-technical user "downloaded zip
  → running GUI" with nothing installed system-wide except Python-if-missing. A frozen exe
  would *add* risk, not remove it: unsigned one-file PyInstaller binaries trip Defender/
  SmartScreen (and WatchGuard on the locked-down work machine) harder than a `.bat`;
  `sys._MEIPASS` path resolution would break the `files/novel-index/` lookup
  (`batch_runner` resolves it via `Path(__file__).parents[2]`); and reportlab + pdfminer.six
  ship data files PyInstaller misses without explicit `--collect-data`. A frozen exe is a
  *possible future option only* — if revisited, those three issues must be solved first.

## Deferred Features (intentional "not yet" — not forgotten)
- **Orphan single-heading-page removal (spec step 3k).** Not implemented: current inputs are
  single-chapter PDFs with no inter-chapter `\f`, so no orphan page is produced. **`PyPDF2`
  was removed from `requirements.txt` in Phase 6 because nothing imports it** — it (or the
  maintained `pypdf`) must be **re-added and pinned** when this feature is built. Noted in
  `scripts/requirements.txt` too.
- **Tier 2 junk-strip** is built but log-only (gated off for this clean corpus).
- **Multi-novel (Phase 7)** profile dropdown + 2nd novel profile/index/pipeline.

## What Was Just Built or Changed (Phase 6)
- **Bug hunt across every module — no Critical bugs.** Robustness against bad input
  (image-only/0-byte/corrupt/non-PDF/locked-folder/mid-batch failure) was confirmed
  empirically and then pinned with tests; it was already correct in code, not fixed.
- **Six approved Minor/Suggestion fixes:** M4 (both launchers now stop on a failed
  `pip install` with a clear message, instead of crashing into `main.py`), M3 (GUI
  auto-opens the output folder via new cross-platform `file_utils.open_in_file_manager`),
  M2 (debug sidecar renamed `DEBUG_<name>.txt` via new `file_utils.debug_text_path`,
  replacing `sibling_path`), M1 (`shadow_slave._summary` now writes a real description into
  the JSONL `replacement` field, not the rule name), S1 (deleted the dead `utils/logger.py`
  stub), S2 (removed the unused `PyPDF2` pin — see Deferred Features).
- **Tests 63 → 79:** new `test_robustness.py` (7) and `test_launchers.py` (3, incl. a
  `bash -n` check), plus rule edge cases, debug-path/open-folder, and an M1 audit-log
  regression. `verify` green throughout.

## What Was Built or Changed (Phase 5)
- **QA/TTS gate (ran first, before building):** `test-logs/_qa_render.py` (temp, gitignored)
  runs a real spread through the full batch and renders output PDFs to PNG via pypdfium2.
  Inspected Ch.1/500/1500/2500/3000 — all clean for TTS; programmatic sweep found zero
  garbage patterns. No fixes were needed before proceeding.
- **`files/novel-index/shadow-slave.txt`** reconciled with `SS_CANONICAL_NAMES`: added the 3
  missing built-in names (`Rani`, `Night`, `Kimmy`) → 352 unique terms, a complete superset
  of the built-in floor. Nothing removed.
- **`scripts/tests/test_protection.py`** (new) — the Phase-5 preservation regression guard
  (parametrized over all 10 fixtures: protected terms never lose occurrences through the
  pipeline), the spec's index-term-shields-against-a-rule acceptance test, the empty/
  comment-only/missing-index fallback contract, and an index⊇floor reconciliation check.

## What Was Built or Changed (Phase 4)
- `scripts/pipelines/shadow_slave.py` — **full `run_pipeline`**, 3-block order (see CHANGELOG
  v0.4.0). Pure rule functions; pipeline records high-value substitutions to the JSONL log.
- All `scripts/rules/` modules implemented: `unicode_cleanup` (NFC/invisibles/spaces +
  `normalize_quotes` → straight doubles, apostrophes preserved), `ligature_cleanup`,
  `junk_strip` (Tier 1 on / Tier 2 log-only, shields protected terms), `spacing_cleanup`
  (`reconstruct_paragraphs` is the core new work — re-inserts `\n\n`, hard-isolates the
  heading; plus headers/footers, dehyphenate, ported `fix_spurious_spaces`), `ocr_repair`
  (conservative insurance — only repairs that can't fire on clean prose), `chapter_titles`
  (normalize/dup/page-break/validate), `punctuation` (ellipsis+number safe), `grammar`
  (a/an only), `em_dash` (ported two-pass), `slash_replace`.
- `scripts/core/protected_lexicon.py` — implemented (this is the Phase-5 core, pulled
  forward because the pipeline can't run without it): load/expand/mask-chapter/mask-terms/
  unmask + `for_non_placeholder_segments`. Placeholder prefixes `__WE_CH_`/`__WE_P_`.
- `scripts/core/replacement_log.py` — `record` (drops no-ops) + `write_jsonl`.
- `scripts/core/batch_runner.py` — builds the lexicon once, runs the pipeline between
  extract and build, writes `EDITED_<name>_replacements.jsonl` when enabled.
- `scripts/tests/test_rules.py`, `scripts/tests/test_pipeline.py` added; two superseded
  Phase-1 assertions in `test_scaffold.py` updated.

## What Is Working (how tested)
- **`python scripts/verify.py` → PASS:** 86 tests pass and 1 skips on this machine (the
  bash syntax test runs because bash is present; it skips only on a machine with an unusable
  WSL shim), all deps are pinned, and CHANGELOG v0.7.0 matches BRIEFING.
- **Protected-term preservation proven across all 10 real fixtures:** every protected term
  present in a source chapter survives the full pipeline with its count not reduced. The
  spec's acceptance scenario passes both directions (unprotected `Half/Blood` → rewritten by
  the slash rule; the same term added to an index file → preserved verbatim).
- **All 8 novel-index files load without error:** `shadow-slave.txt` → 352 terms; the 7
  empty placeholders → the 87-term built-in floor (clean fallback).
- **Full pipeline proven on real fixtures:** on Ch.1 the heading is isolated as its own
  paragraph, 89 natural paragraphs are reconstructed from the single-`\n` wrap stream,
  `Sunny` is preserved 21× through the whole pipeline, and no spaced em-dash remains. On
  Ch.3000 (the mixed-quote outlier) all 27 curly doubles become straight and are logged.
- **Real 2-file batch:** EDITED PDFs + debug `.txt` + JSONL written; clean Ch.1 yields an
  empty (0-entry) log, Ch.3000 yields the quote-normalize entry; originals byte-for-byte
  untouched (sha256).
- Phases 1-3 still green: scaffold wiring (updated), GUI, extractor/builder round-trip.

## Skills Pulled / Used
Six skills in `.claude/skills/`: spec-to-repo, spec-driven-workflow, tdd-guide,
dependency-auditor, changelog-generator, ship-gate. Plus `.codex/skills/ui-design-system`.
- **Phase 1:** spec-to-repo, dependency-auditor, spec-driven-workflow.
- **Phase 2:** **ui-design-system** — its principles (visual hierarchy, 8pt spacing, palette/
  tokens, component state feedback) translated into native ttk (no web/CSS framework adopted);
  tdd-guide (mock-worker + construction tests).
- **Reference-only / later:** changelog-generator & ship-gate (patterns; no git Conventional-
  Commits flow here).

## What Is Broken or Incomplete
- **Nothing blocking.** The pipeline is functional and verified end-to-end on real chapters.
- Header/footer and page-number removal is intentionally disabled as a logged no-op until
  page-position data is preserved by extraction; non-positional repetition heuristics can
  delete legitimate prose. Page-boundary collision repair and `junk_strip` Tier 1/2 remain
  conservative insurance for this clean corpus.
- `ocr_repair` deliberately omits the study example's aggressive `?→fi` / `l→I` / in-word
  `slash→r` passes (they would corrupt this clean corpus). If a future source genuinely needs
  ligature-`?` recovery, add it gated behind a per-source flag — do not enable globally.
- Orphan single-heading-page removal (spec step 3k, PyPDF2) is **not** implemented: these are
  single-chapter PDFs with one heading and no inter-chapter `\f`, so no orphan page is
  produced. Revisit if multi-chapter inputs are ever batched into one PDF.

## Phase 4 Reconnaissance — RESOLVED (kept for the record)
Inspecting the real extracted fixtures this session refined the prior recon:
- **Paragraph signal is reliable:** extraction wraps each paragraph at a fixed column width
  (~73 mean, 126 max) with single `\n`; a true paragraph end is a line that ends in terminal
  punctuation AND whose next line does not start lowercase. `reconstruct_paragraphs` uses
  exactly this and rebuilds `\n\n` cleanly.
- **Quote inconsistency = doubles, not the apostrophe.** Apostrophes are consistently `’`
  (U+2019); dialogue doubles are mostly straight `"` except Ch.3000 (mixed curly+straight).
  The earlier `money�s` "junk" was a console-rendering artifact — there is **zero U+FFFD**.
  Decision: normalize doubles to straight `"`, leave `’` alone.
- **Heading** extracts as line 0 already on its own line; reconstruction force-isolates it.

## Open Items to Validate Later (do not lose)
- **reportlab 5.0.0 — RESOLVED (Phase 3).** Validated by building a real PDF on
  `reportlab==5.0.0` and inspecting rendered glyphs: Helvetica-Bold heading at exactly
  `#134252`, Times-Roman justified body, 0.5in margins, and `\f` page breaks all render
  correctly. No API regression vs. the 4.x study example. **No downgrade needed; pin stays at
  5.0.0.**

## Open Questions / Decisions Needed
- **None blocking.** Packaging is resolved (launcher, no exe — see Packaging Decision).
- The `shadow-slave.txt` term list is already rich (352 terms incl. ranks/locations/factions).
  It is user-maintained and grows freely at runtime (loaded fresh each run) — no code change
  needed to expand it further; left to the user to extend as new chapters are processed.

## Files Changed in Last Session (Phase 6)
- v0.6.1 review-fix files: `scripts/rules/slash_replace.py`,
  `scripts/rules/spacing_cleanup.py`, `scripts/rules/chapter_titles.py`,
  `scripts/pipelines/shadow_slave.py`, `scripts/pdf/builder.py`, both launchers, `README.md`,
  `md-instructions/build-spec.md`, `md-instructions/EDITING-RULES.md`, and regression tests.
- Source: `Setup_and_Run.bat`, `Setup_and_Run.command` (M4 pip-fail guard);
  `scripts/utils/file_utils.py` (M2 `debug_text_path` replaces `sibling_path`; M3 new
  `open_in_file_manager`); `scripts/core/batch_runner.py` (uses `debug_text_path`);
  `scripts/gui/app.py` (M3 auto-open on completion); `scripts/pipelines/shadow_slave.py`
  (M1 audit-log field); `scripts/requirements.txt` (S2 PyPDF2 removed + note).
- Deleted: `scripts/utils/logger.py` (S1 dead stub).
- Tests added: `scripts/tests/test_robustness.py`, `scripts/tests/test_launchers.py`;
  edits to `test_rules.py`, `test_pdf.py`, `test_pipeline.py`.
- Docs: `md-instructions/CHANGELOG.md`, `md-instructions/BRIEFING.md`.

## Next Steps
- **Phase 7 architecture validation is done** (stub pipeline + seam proof). The remaining
  multi-novel work is a **data exercise**: build the real Lord of the Mysteries (or another
  novel's) editorial profile by populating `profiles/<novel>/canonical_names.py` +
  `special_fixes.py` and `files/novel-index/<novel>.txt`, then flesh out its pipeline. No core
  refactor expected — the universal rules and the `run_pipeline` contract already hold.
- **GUI novel-profile dropdown (v2):** add the selector and a profile->pipeline registry so the
  batch runner dispatches to the chosen novel's `run_pipeline`. Deferred per spec.
- If/when **orphan single-heading-page removal** is built, re-add `PyPDF2` (or `pypdf`) to
  requirements (see Deferred Features).
- `files/study-examples/` ports are complete and confirmed reference-only (no runtime import);
  it can be deleted whenever the user is satisfied.
