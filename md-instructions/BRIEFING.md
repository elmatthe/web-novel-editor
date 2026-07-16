# Webnovel Editor — Project Briefing

## Version: v0.10.0

## Last Updated
2026-07-16 — v0.10.0: junk-strip hardening, new profiles (Noble Queen + Supreme Magus),
PDF/GUI alignment, cross-platform repo reorg, launcher rebuild, docs pass (Phase 10)

## Current State (v0.10.0)
The "junk-strip-hardening" plan (Phases 0–10) is complete. Headlines:
- **Two new real per-novel profiles: Supreme Magus and The Noble Queen** (Phase 5b), joining
  Shadow Slave. Each is selectable in the dropdown, applies only its own edits, and does not
  change Shadow Slave's output. Every other novel runs **Basic Edit Mode** (universal-only).
- **Junk-strip Tier 1 hardened** (Phases 1–4) against real fingerprint classes found in the
  Noble Queen / Supreme Magus corpora (mangled/spaced/homoglyph/inline-spliced scraper
  domains; Cloudflare error pages are detect-and-flag, never stripped).
- **Editorial QA fixes** (Phase 3: chapter-title terminal `?`/`!`; grammar `eu`/`ew` guard) and
  a **TTS-readiness re-verification** (Phase 4, Edge Neural target) that held.
- **PDF-build alignment** (Phase 6): orphan heading-only-page **prevention** (`keepWithNext`) +
  **detection-only** logging; automatic deletion deferred; no `pypdf` added.
- **GUI consistency** (Phase 7): renamed to **"Web Novel Editor"**, log at the bottom,
  "Advanced Options" grouping; design system preserved; no Stop button (deferred).
- **Cross-platform repo reorganization** (Phase 8): all code under `scripts/Universal/`; tests →
  `files/tests/`; fixtures → `files/test-files/`; **runtime data (novel-index +
  Novel-Edits-Details) relocated to `scripts/Universal/resources/`** so `files/` is dev-only
  (Option B).
- **One hardened launcher per OS** (Phase 9): `scripts/Universal/main.py` entry point,
  self-healing venv, health-gated idempotent install, blocking 3.10 gate.
- **New `DECISIONS.md`** permanent doc (append-only ADR log, 27 entries).

The dispatch registry (`novel_registry.py`) and the edit-details markdown layer
(`edit_details.py`, `UNIVERSAL.md` + `<Novel-Name>.md`) from v0.9.0/v0.8.0 are reused
unchanged; v0.10.0 layers new profiles + hardening on top. The dropdown is populated from
`scripts/Universal/resources/novel-index/*.txt`.

## Prior: v0.9.0 (Phase 9 — Novel-Selection Dropdown + Dispatch Registry)
The GUI gained a labelled, read-only **novel dropdown** (`ttk.Combobox`, defaults to "Shadow
Slave") populated from the novel-index roster. The selection drives `run_batch`'s `novel_name`,
which dispatches through a **single registry** (`novel_registry.py`): a registered novel runs
its real profile pipeline; any other novel falls back to **universal-only** editing. Logging
records the selected novel and which layer applied. (Registry + dropdown reused as-is in
v0.10.0; Supreme Magus and The Noble Queen are now registered real profiles alongside Shadow
Slave.) Covered by `test_novel_registry.py`.

## Phase 8 (prior)
Phase 8 (Per-Novel Edit-Details System) complete. Added `files/Novel-Edits-Details/` with a
`UNIVERSAL.md` baseline (always applied) and per-novel `<Novel-Name>.md` files layered on
top (`Shadow-Slave.md` is the first). `scripts/core/edit_details.py` resolves the selected
novel name to its markdown (case/separator-insensitive) and falls back to universal-only
when no file matches, never crashing. `batch_runner.run_batch` takes a `novel_name`,
loads the edit details, and logs which layer was applied. Covered by
`scripts/tests/test_edit_details.py` (19 tests). Each new novel is a drop-in
`<Novel-Name>.md` — no code change.

## Previous Phase
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
Shadow Slave (plus Supreme Magus and The Noble Queen as of v0.10.0); multi-novel by design.
Tech stack: Python 3.10+ (built on 3.12.10), Tkinter, pdfplumber, reportlab, pytest.
(`PyPDF2`/`pypdf` is intentionally NOT a dependency — see Deferred Features.)

## Repo / Git State
- Under git. Current work is on branch **`feature/junk-strip-hardening`** (the v0.10.0
  junk-strip-hardening plan, Phases 0–10). The registry work was reused from `origin/main`
  (v0.9.0) rather than rebuilt; the pre-reconcile WIP is archived as
  `archive/junk-strip-hardening-pre-0.5`.
- **Layout (post Phase-8 reorg):** all program code under `scripts/Universal/`; shipped
  runtime data under `scripts/Universal/resources/{novel-index,Novel-Edits-Details}/`;
  `scripts/requirements.txt` + `scripts/verify.py` at the `scripts/` root;
  `scripts/Windows/` + `scripts/MacOS/` are `.gitkeep` structural placeholders. `files/` is
  now **dev-only**: `files/tests/` (pytest suite), `files/test-files/shadow_slave/` (the 10
  committed pinned fixtures), and the gitignored `pdf-example-chapters/` corpora,
  `study-examples/`, `test-logs/`, and `qa-tools/` scratch.

## Packaging Decision (RESOLVED, do not revisit by accident)
- **Distribution = the double-click launcher (`Setup_and_Run.bat` / `.command`). NO frozen
  PyInstaller exe for v1.** The launcher already gives a non-technical user "downloaded zip
  → running GUI" with nothing installed system-wide except Python-if-missing. A frozen exe
  would *add* risk, not remove it: unsigned one-file PyInstaller binaries trip Defender/
  SmartScreen (and WatchGuard on the locked-down work machine) harder than a `.bat`;
  `sys._MEIPASS` path resolution would break the shipped-resource lookups (the novel roster,
  protected-term indexes, and edit-details resolve from `scripts/Universal/resources/` via
  `Path(__file__).parents[1] / "resources"`); and reportlab + pdfminer.six ship data files
  PyInstaller misses without explicit `--collect-data`. A frozen exe is a *possible future
  option only* — if revisited, those three issues must be solved first.

## Deferred Features (intentional "not yet" — not forgotten)
- **Automatic orphan heading-only-page deletion.** As of v0.10.0 (Phase 6) the builder does
  **prevention** (`keepWithNext=1` so a heading can't be stranded at a page bottom) and
  **detection-only** logging (`detect_heading_only_pages()` on multi-chapter builds → GUI
  warning + JSONL `integrity_flag`, never deletes). **Automatic deletion stays deferred** — no
  safe positive "this page is a genuine orphan" invariant exists, and the defect is not
  reproducible (all inputs are single-chapter). No PDF-rewrite path exists, so **`pypdf` is not
  a dependency**; it would be re-added + pinned only if deletion is ever built. (DECISIONS.md
  #017/#018.)
- **Cooperative Stop/Cancel in the GUI** (Phase 7): deferred — `run_batch` has no safe
  cancellation seam; killing a worker mid-PDF-write risks a corrupt output. (DECISIONS.md #020.)
- **Tier 2 junk-strip** is built but log-only / default-off (heuristic promo lines).
- **Real per-novel profiles beyond the three shipped** (Shadow Slave, Supreme Magus, The Noble
  Queen). Renegade Immortal / Reverend Insanity and other dataless novels remain universal-only
  (Basic Edit Mode) placeholders; authoring another real profile is a data/porting exercise on
  the validated seam. **Universal-seam caveat:** the universal-only fallback still reuses the
  `lord_of_mysteries` stub (empty special-fixes); if a real LOTM profile is ever authored, the
  fallback must get its own dedicated neutral pipeline first (pinned by test). (DECISIONS.md
  #009/#014.)

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
- **`python scripts/verify.py` → PASS (v0.10.0):** the committed suite is green (CHANGELOG
  v0.10.0 matches BRIEFING, all deps pinned). Corpus-backed tests skip only where the
  gitignored local corpora are absent — an explicit, visible skip, never counted as a pass.
- **Local QA evidence (gitignored corpora, HOME-PC).** The junk-strip hardening + QA + TTS +
  dual-mode work was proven against three real corpora under
  `files/pdf-example-chapters/`: `webscraped_shadow_slave/` (3,000 PDFs, clean source),
  `The_Noble_Queen-v2/` (778 PDFs, novelfire watermarks), and `Supreme_Magus-v2/` (4,191 PDFs,
  multi-site watermarks + 3 Cloudflare error pages). These are **local evidence only** — not
  fixtures guaranteed to exist in a clone. The committed guarantees ride on the 10 pinned
  Shadow Slave fixtures + synthetic-text tests.
- **Protected-term preservation proven across all 10 committed fixtures:** every protected term
  present in a source chapter survives the full pipeline with its count not reduced; the
  index-term-shields-a-rule acceptance test passes both directions.
- **Dual-mode dispatch proven at the registry/provenance level:** Shadow Slave / Supreme Magus /
  The Noble Queen resolve to their real profiles and apply only their own edits; every other
  novel resolves to the universal-only fallback (Basic Edit Mode) — proven by spy/bait-string
  tests, not just by inspecting output. No `__WE_` placeholder leaks in either mode.
- **Junk-strip hardening proven zero-false-positive** over letter-sharing prose + a full
  old-vs-new corpus diff (exactly the watermark chapters changed, every span manually reviewed).
- **Shadow Slave output equivalence intact:** pinned by both a corpus-free synthetic-text test
  and the fixture-backed tests; originals are never modified (sha256).
- **macOS launcher verified 2026-07-16:** real macOS clean-room bootstrap + a real Finder
  double-click (closing the item Phase 9 left open — HOME-PC has no macOS).

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
- Orphan heading-only-page **prevention** (`keepWithNext`) and **detection-only** logging are
  implemented (Phase 6); **automatic deletion is deferred** (no safe invariant; not reproducible
  — all inputs are single-chapter). No `pypdf` dependency. See Deferred Features / DECISIONS.md
  #017.

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
- **v0.10.0 is complete and committed on `feature/junk-strip-hardening` (local only — not
  pushed; awaiting the user's review before it hits origin).** The instruction drop
  (`Instructions_Phase10_JunkStrip_And_QA.md`) is Phase 11's to delete + final-verify + the
  user's end-of-plan sign-off before any merge to `main`.
- **Authoring more real per-novel profiles** is a data/porting exercise on the validated seam:
  populate `scripts/Universal/profiles/<novel>/canonical_names.py` + `special_fixes.py` and
  `scripts/Universal/resources/novel-index/<novel>.txt`, add a `<Novel-Name>.md`, register in
  `novel_registry.py`. **If Lord of the Mysteries is ever authored, give the universal-only
  fallback its own dedicated pipeline first** (it currently reuses the LOTM stub — DECISIONS.md
  #009/#014).
- If/when **automatic orphan heading-only-page deletion** is built, add + pin `pypdf` and
  establish a safe positive orphan invariant first (see Deferred Features / DECISIONS.md #017).
- `files/study-examples/` ports are complete and reference-only (no runtime import); it can be
  deleted whenever the user is satisfied.
