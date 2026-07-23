# Webnovel Editor — Project Briefing

## Version: v0.11.0

## Last Updated
2026-07-23 — v0.11.0 remains the shipped baseline. Plan 1 is merged into `main`;
provider-neutral Plan 2a foundation work is in progress on
`feature/plan-2a-provider-foundation` (no AI stage integrated yet).

## Current State (v0.11.0)
The "GUI & Batch Overhaul" plan (Plan 1, Phases 1–6) is complete and merged into
`main` by `ce96359`. Provider-neutral Plan 2a groundwork is in progress from
`origin/main` `9ca90fd`; no provider, GUI, batch-runner, or user-visible AI feature
has been implemented. Headlines:
- **Provider-neutral Plan 2a foundation (in progress):** `scripts/Universal/ai/` now
  defines frozen provider request/result/capability models, a cloud-ready typed error
  taxonomy, the four-method provider protocol, and lazy factory construction. Root
  `config.toml` is committed and secret-free with AI disabled; per-user settings use
  atomic JSON outside the repository. Python 3.10 remains supported through
  `tomli==2.4.1`. Versioned prompt assembly renders the canonical protected lexicon
  at runtime; gate v1.0 validates structure, protected terms, placeholders, truncation,
  minimal diffs, and canonical spaced-em-dash behavior without mutating candidates.
  Chunker v1.0 splits only between complete paragraphs, preserves headings and explicit
  newline boundaries, and asserts byte-exact unchanged reassembly. Provider-neutral
  `AIEditor` now implements both explicit protection strategies: default Strategy M masks
  with the canonical lexicon before chunk planning and unmasks only after exact reassembly;
  Strategy V verifies exact spelling plus paragraph/sentence/word position. Gate/malformed/
  truncated retries use versioned stricter prompt `1.0-retry.1`; transient transport retries
  retain prompt `1.0`, with one total retry maximum. Attempt provenance includes lexicon,
  strategy, chunk, chunker, attempt, status, and error metadata while never storing complete
  text. Provider construction/availability is cached for the run: script-only constructs
  nothing, prefer-AI falls back honestly after outages, and AI-required raises instead of
  degrading. No provider adapter or SDK is present, and none of this foundation is wired
  into the batch runner or GUI.
- **Two-mode input (Phase 1):** the GUI's Input card offers mutually exclusive
  **Upload PDFs** / **Select Folder** radio modes. Folder mode runs
  `core/input_scanner.scan_folder` — a depth-first recursive scan where each
  directory's own PDFs come first in **natural order** (1, 2, 10 — `natsort==8.4.0`,
  case-insensitive) followed by its subfolders in natural order; the listbox previews
  the resolved processing order. Upload mode preserves the user's upload order exactly.
- **Forced, mirrored output (Phase 2):** no output-folder picker. Every batch writes
  into a fresh **`Downloads\<name>-x`** folder (`<name>` = kebab-cased novel selection,
  `x` = max(N)+1 over existing `<name>-N` dirs — never reused, never overwritten).
  Downloads resolves via `SHGetKnownFolderPath` (ctypes) with a `~/Downloads` fallback
  (`utils/file_utils.downloads_dir`). Folder mode mirrors the selected folder's tree
  (its own name as the root) inside `<name>-x`; upload mode is flat. **Original
  filenames are kept** (the `EDITED_` prefix is gone); collision `_2`/`_3` suffixes,
  `DEBUG_<name>.txt`, and `<name>_replacements.jsonl` sidecars remain.
- **"Universal" default (Phase 3):** the dropdown roster leads with an injected
  **"Universal"** entry — the default selection — dispatching through the existing
  unregistered-name fallback (universal-only editing; registry untouched). The 5
  profile-less novels carry a display-only " — no profile yet" marker, stripped by
  `clean_novel_name()` in the GUI before any name reaches dispatch or folder naming
  (default output is therefore `Downloads\universal-x`).
- **Pause/continue + condensed log (Phase 4):** `run_batch` takes an optional
  `pause_gate` `threading.Event` consulted only BETWEEN files — the in-flight file
  always finishes, so pausing can never corrupt an output (the safe seam DECISIONS
  #020's deferred cancellation lacked; session-only, no persistence — #033). The GUI
  has a Pause ⇄ Continue button enabled only while running. The log is condensed: one
  line per file (`[i/N] name — done (X edits)` / `— skipped (…)` / `— FAILED (…)`)
  plus an end-of-batch summary block; verbose stage chatter lives only in the JSONL;
  "⚠" integrity warnings still surface. The per-file `ReplacementLog` is always
  constructed (feeds the edit count); `integrity_flag` records never count as edits.
- **Decorative-run TTS sweep (Phase 5):** `rules/junk_strip.py` Tier 1 removes
  whitespace-delimited runs of `~ \ - = * #` (≥3 symbols, internal spaces allowed —
  `* * *`, `-=-=-`, `~~~`) that TTS would voice character by character. Everything
  glued to a word, single symbols, and two-symbol spans survive — the corpus's ~810
  legitimate asterisks (censored profanity, authored emphasis, footnotes) are
  test-pinned untouchable (DECISIONS #034). Corpus-no-op insurance on current data.
- **Phase 6 bug hunt:** no Critical bugs. Fixed: edit counts no longer include
  `integrity_flag` records; GUI worker no longer reads Tk variables off-thread
  (per-batch snapshots); stale docs/comments reconciled. A real end-to-end run
  proved the full chain (folder scan → mirrored `universal-x` → Universal dispatch →
  mid-batch pause → decorative-run stripping) works together.

## Architecture — per-file batch loop and the Plan-2 seam
`core/batch_runner.run_batch` processes files sequentially; per file:
**extract** (`pdf/extractor.extract_text_from_pdf`, low-confidence skip) →
**editorial rule pipeline** (`dispatch.run_pipeline` via `core/novel_registry`) →
**build** (`pdf/builder.build_pdf` into the mirrored/flat output path). Each file is
wrapped in its own try/except (continue-on-failure), and the pause gate is consulted
only between files.

**The post-pipeline pre-build hook (Plan 2's insertion seam).** There is exactly one
clean structural seam for a future AI editing stage: inside the per-file loop of
`scripts/Universal/core/batch_runner.py`, **after** `text = dispatch.run_pipeline(...)`
returns (currently lines ~185–187) and **before** `build_pdf(text, out_path)`
(currently line ~214). At that point the file's fully rule-edited text exists as a
plain string, its `ReplacementLog` is live, and nothing has been written to disk.
Plan 2's Ollama/Qwen stage slots in there as a text-in/text-out call — ideally
immediately after the rule pipeline and **before the edit count / dry-run check**, so
its edits appear in the condensed "X edits" count and dry runs exercise the full text
path without writing PDFs. The hook is **documented only — deliberately not built**
(no empty callback exists in the code). A Plan-2 implementation must honor this
contract:
- **Text-in/text-out, no I/O:** transform the string; never touch the input file;
  `build_pdf` stays the only writer, so output naming/mirroring/collision handling
  are inherited unchanged.
- **Dry-run:** with `dry_run=True` the loop skips PDF output but still runs the text
  path — an AI stage placed at the seam runs in dry runs too (in-memory only), which
  is the intended preview behavior.
- **Pause-gate interaction:** the Phase-4 gate holds only BETWEEN files, so the AI
  stage runs to completion for the in-flight file — AI latency lengthens the "current
  file will finish first" window; do not add a mid-file hold without a superseding
  DECISIONS entry.
- **Logging conventions:** record every AI change into the same per-file
  `ReplacementLog` (own rule prefix, e.g. `ai_editor.*`) so JSONL provenance and the
  edit count work; keep the GUI log condensed (one line per file) — verbose detail
  goes to the JSONL; surface problems as `⚠`-prefixed `gui_log` lines (the runner's
  filter forwards only `⚠` lines to the GUI); `category="integrity_flag"` records are
  excluded from edit counts by design.
- **Failure semantics:** raising inside the seam marks that one file FAILED and the
  batch continues (existing per-file try/except); a graceful skip-AI fallback must be
  logged honestly, not silently.
- **Protected terms:** the run's `ProtectedLexicon` is in scope at the seam — AI
  editing must preserve protected terms (mask before / verify counts after), matching
  the pipeline's guarantee.

## Prior: v0.10.0
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
text, runs a deterministic rule-based editorial pipeline (no AI rewriting), and writes each
edited PDF **under its original filename** into a fresh auto-numbered
`Downloads\<novel>-x` folder (v0.11.0 — mirrored tree in folder-input mode, flat in
upload mode). Originals are never modified. First novel: Shadow Slave (plus Supreme Magus
and The Noble Queen as of v0.10.0); multi-novel by design; "Universal" (universal-only
editing) is the default dropdown choice as of v0.11.0.
Tech stack: Python 3.10+ (built on 3.12.10), Tkinter, pdfplumber, reportlab, natsort, pytest.
(`PyPDF2`/`pypdf` is intentionally NOT a dependency — see Deferred Features.)

## Repo / Git State
- Under git. Current work is on branch **`feature/gui-batch-overhaul`** (the v0.11.0
  GUI & Batch Overhaul plan — Plan 1, Phases 1–6 complete), branched off `main` @
  `c424d30` after the junk-strip-hardening plan (v0.10.0) was merged into `main`
  (`94999a8`). Awaiting the user's end-of-plan sign-off before any merge to `main`.
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
- **Cooperative Stop/Cancel in the GUI**: still deferred (DECISIONS.md #020) — but as of
  v0.11.0 the **pause/continue** feature built exactly the safe between-files checkpoint
  that discussion described (`run_batch`'s `pause_gate`, DECISIONS #033). A future Stop
  can reuse that same seam; killing a worker mid-PDF-write remains the hazard to avoid.
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
- **v0.11.0 (Plan 1 — GUI & Batch Overhaul) is complete and pushed on
  `feature/gui-batch-overhaul`, awaiting the user's end-of-plan sign-off before merge
  to `main`.** The plan drop has been deleted per its Definition of Done.
- **Plan 2 (AI editor integration, `plan-2-ai-editor-integration.md`) is next.** It was
  drafted against a much earlier repo state and must be **rewritten/reconciled against
  the real v0.11.0 tree first** (same as Plan 1's v2 reconciliation). Its stage slots
  into the documented **post-pipeline pre-build hook** (see Architecture above) and
  must honor that seam's contract.
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
