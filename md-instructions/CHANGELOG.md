# Webnovel Editor — Changelog

## v0.11.0 — 2026-07-19 — GUI & Batch Overhaul (Plan 1): Two-Mode Input, Auto-Numbered Mirrored Output, "Universal" Default, Pause/Continue + Condensed Log, Decorative-Run TTS Sweep

The "GUI & Batch Overhaul" plan (Plan 1, Phases 1–6) on `feature/gui-batch-overhaul`,
modernizing the GUI input/output model and batch flow. The editorial pipeline's rule
logic is unchanged except one additive junk-strip rule (Phase 5). Design reasoning is
in DECISIONS.md #028–#035.

### Added — two-mode input + natural-order folder scanning (Phase 1)
- The GUI "PDF Files" card became an **Input** card with two mutually exclusive radio
  modes: **Upload PDFs** (flat list, upload order preserved exactly) and **Select
  Folder** (recursive scan). New `core/input_scanner.py` (`scan_upload` / `scan_folder`);
  the shared listbox previews the resolved processing order.
- Folder scanning follows a pinned ordering contract: depth-first; each directory's own
  PDFs first in **natural order** (1, 2, 10 — not 1, 10, 2), then its subfolders in
  natural order; case-insensitive `.pdf` match; non-PDFs ignored. New dependency
  **`natsort==8.4.0`** (exact-pinned; verified latest stable) — numeric-aware sorting
  was deliberately not hand-rolled. (DECISIONS #028.)

### Changed — forced output location, mirroring, original filenames (Phase 2)
- The output-folder picker is **gone**: every batch writes into a fresh
  **`Downloads\<name>-x`** folder — `<name>` = kebab-cased novel selection, `x` =
  max(N)+1 over existing `<name>-N` dirs (gaps never reused; a re-run never overwrites).
  The folder is named at Start but created only when the batch runs (dry runs create
  nothing). (DECISIONS #030.)
- Downloads resolves via **`SHGetKnownFolderPath`** (`FOLDERID_Downloads`, ctypes) with
  a `~/Downloads` fallback — one function (`utils/file_utils.downloads_dir`), so macOS
  support later is that one branch. No new dependency. (DECISIONS #029.)
- Folder mode **mirrors the input tree** inside `<name>-x` (the selected folder's own
  name as the root); upload mode outputs flat. **The `EDITED_` prefix was dropped** —
  outputs keep their original filenames; collision `_2`/`_3` suffixes, `DEBUG_<name>.txt`,
  and the (now `<name>_replacements.jsonl`) sidecar remain, written beside each output.

### Changed — "Universal" default dropdown entry + profile-less markers (Phase 3)
- The roster now leads with an injected **"Universal"** entry — the **new default
  selection** (was Shadow Slave) — an explicit, named choice for universal-only editing.
  It dispatches through the existing unregistered-name fallback: **the dispatch registry
  is byte-for-byte untouched** and the LOTM-stub fallback invariant (#009/#014) holds.
  Default output folder is therefore `Downloads\universal-x`. (DECISIONS #031/#032.)
- The 5 profile-less novels (Circle of Inevitability, Lord of the Mysteries, Re Monster,
  Renegade Immortal, Reverend Insanity) carry a display-only **" — no profile yet"**
  marker; the GUI strips it via new `clean_novel_name()` before a selection reaches
  dispatch or folder naming. Authoring a real profile later auto-drops the marker.

### Added — pause/continue + condensed log (Phase 4)
- `run_batch` gained an optional **`pause_gate`** (`threading.Event`, SET = run)
  consulted only **between** files: the in-flight file always finishes, so pausing can
  never corrupt an output — the safe seam the deferred cancellation (#020) lacked.
  Session-only by design (no persistence). GUI: a **Pause ⇄ Continue** button beside
  Start, enabled only while a batch runs. (DECISIONS #033.)
- The GUI log is **condensed**: exactly one line per file (`[i/N] name — done (X edits)`
  / `— done (dry run, X edits)` / `— skipped (not found)` / `— skipped (image-only/empty)`
  / `— FAILED (Type: reason)`) plus an end-of-batch summary block (totals +
  Failed:/Skipped: lists, omitted when empty). Verbose stage chatter stays in the JSONL;
  pipeline "⚠" integrity warnings still surface. The per-file `ReplacementLog` is always
  constructed so the edit count shows even with the JSONL option off. An explicit
  "Universal" selection logs an intentional-choice line.

### Added — decorative-run TTS jargon sweep (Phase 5)
- New conservative Tier-1 junk-strip rule (`junk_strip.decorative_run`): a
  whitespace-delimited span made only of **`~ \ - = * #`** plus internal spaces,
  carrying **≥3 symbol characters** (`~~~`, `-=-=-`, `* * *`, `\ \ \`), is excised
  token-level with the existing minimum-span/emptied-line/JSONL conventions, protected
  terms shielded. Symbols glued to words (`f*ck`, `*emphasis*`, `Rule #1`,
  `well-known`), single symbols, and two-symbol spans (`**`, `--`, `~~`) always
  survive — the ~810 legitimate corpus asterisks are test-pinned untouchable. A scan of
  all 7,979 cached extractions found zero qualifying spans (corpus-no-op insurance).
  EDITING-RULES.md documents the rule. (DECISIONS #034.)

### Fixed — Phase 6 bug hunt (cross-phase integration pass)
- **No Critical bugs.** A real end-to-end run proved the full chain (folder scan →
  mirrored `universal-x` output → Universal dispatch → mid-batch pause →
  decorative-run stripping) works together. Three Minor fixes:
  - The condensed line's edit count no longer counts `integrity_flag` records (an
    error-page file now honestly reads "done (0 edits)"; regression-tested).
  - The GUI worker thread no longer reads Tk `BooleanVar`s: the three option
    checkboxes are snapshotted per batch like the rest of the batch state (Tk objects
    are not thread-safe; zero behavior change).
  - Stale docs reconciled: `junk_strip.py`'s error-page comment said 4 pages (real
    count 3, DECISIONS #027); README described the old `EDITED_`/chosen-folder model;
    DECISIONS.md's #028 entry had lost its heading line; build-spec.md gained a
    v0.11.0 reconciliation note.

### Docs
- **BRIEFING.md** updated to the new GUI/batch model and now documents the **Plan-2
  seam**: the *post-pipeline pre-build hook* in `run_batch`'s per-file loop (between
  `dispatch.run_pipeline(...)` and `build_pdf(...)`) where Plan 2's AI editing stage
  will slot, with the contract it must honor (text-in/text-out, dry-run behavior,
  pause-gate interaction, logging conventions). Documented only — not built.
- CHANGELOG v0.11.0 (this entry); DECISIONS #028–#035 appended across the phases;
  Handoff.md work/sync logs updated per phase; the plan drop deleted at completion.

### Verified
- `python scripts/verify.py` → PASS after every phase; final: **514 passed** (401 →
  514 over the plan), deps exact-pinned (incl. `natsort==8.4.0`), CHANGELOG/BRIEFING
  at v0.11.0. End-to-end integration proof run in Phase 6 (all 25 checks passed).

## v0.10.0 — 2026-07-16 — Junk-Strip Hardening, Editorial QA, New Per-Novel Profiles, PDF/GUI Alignment, Repo Reorg & Launcher Rebuild

A large multi-phase release (the "junk-strip-hardening" plan, Phases 0–10) bundling
user-visible junk-removal changes, editorial QA fixes, two new real per-novel profiles,
PDF-build and GUI alignment with the sibling `web-novel-scraper`, a full cross-platform repo
reorganization, and a rebuilt launcher per OS. The Shadow Slave editorial output is unchanged;
the branch reused the already-shipped v0.9.0 dispatch registry rather than rebuilding it.
Design reasoning for every non-obvious choice below is recorded in the new
`md-instructions/DECISIONS.md`.

### Branch/registry reconciliation (Phase 0.5)
- The v0.9.0 novel → pipeline dispatch registry was **reused** (recovered from `origin/main`),
  not rebuilt. `feature/junk-strip-hardening` was recreated from that base; the pre-reconcile
  WIP is preserved as `archive/junk-strip-hardening-pre-0.5`. (DECISIONS.md #002.)

### Added — two new real per-novel profiles (Phase 5b)
- **Supreme Magus** — `profiles/supreme_magus/` (594-term canonical floor; **16 proper-noun
  artifact special-fixes**), `pipelines/supreme_magus.py`, populated
  `resources/novel-index/supreme-magus.txt`, and `resources/Novel-Edits-Details/Supreme-Magus.md`.
  The Ragnarök family restores to the authored **"Ragnarök" (ö)**. The legacy editor's
  **profanity-uncensor map was deliberately NOT ported** (spec-excluded content alteration), and
  generic-word artifacts were excluded (e.g. `rnade` is a substring FP hazard inside
  "Bernadette"). (DECISIONS.md #013.)
- **The Noble Queen** — `profiles/the_noble_queen/` (26-term floor; **empty special-fixes by
  evidence** — a protection-only profile), `pipelines/the_noble_queen.py`, populated
  `resources/novel-index/the-noble-queen.txt`, and `resources/Novel-Edits-Details/The-Noble-Queen.md`.
  (DECISIONS.md #012.)
- **Renegade Immortal, Reverend Insanity** (and dataless placeholders) intentionally remain
  **universal-only fallbacks** — their study-examples indexes are comment-only headers with zero
  real terms. Selecting any profile-less novel runs **Basic Edit Mode** only.
- Both new profiles apply their own edits in their own mode and **not** in any other mode
  (cross-novel isolation proven both directions); **Shadow Slave output is unchanged** by their
  addition. Each new novel is a data/porting drop on the existing validated seam — no
  core/rules/pdf engine changes.

### Changed / Fixed — junk-strip hardening (Phases 1–2, 4)
- `rules/junk_strip.py` Tier 1 hardened against real fingerprint classes found by 100%-coverage
  scans of the Noble Queen (778 PDFs) and Supreme Magus (4,191 PDFs) corpora: a **two-layer
  domain matcher** (exact list of every recorded mangled spelling + a structural fuzzy layer
  gated by an English-word guard, `webnovel.com` guard-listed); **minimum-span inline removal**
  (excise only the confirmed junk span, preserve adjacent prose); spaced-out and
  black-square-obfuscated domains; **detection-only NFKC** for homoglyph domains (the document is
  never NFKC-rewritten — Stage 1 stays NFC); and **cross-line splice** handling (Phase 4).
  (DECISIONS.md #003/#004/#006.)
- **Cloudflare error-1015 pages** (whole-file, chapter text missing) are **detected and flagged**
  (GUI warning + JSONL `integrity_flag`), **never auto-stripped** — the fix is a re-scrape.
  Supreme Magus has **3** such pages (Ch. 1423/1424/1427). (DECISIONS.md #005/#027.)
- Every junk removal is logged to the JSONL `ReplacementLog` (`rule="junk_strip"`); a committed
  zero-false-positive test suite + optional `@pytest.mark.local_corpus` corpus tests (with a
  `--require-local-corpora` strict mode) guard the patterns.

### Fixed — editorial QA (Phase 3)
- Chapter titles keep their own terminal `?`/`!` and no longer gain a duplicate trailing period
  (`punctuation.py` guarded `?.`/`!.` collapse; `chapter_titles.py` + `pdf/builder.py` heading
  regex accept `[.?!]`).
- Grammar `a`→`an` rule gained an `eu`/`ew` guard (vowel-letter/consonant-sound), so
  "a euphoria" is left correct.

### Verified — TTS-readiness sweep (Phase 4)
- The "TTS-Readiness Criteria" were re-verified at 100% coverage against the new corpora and
  **held** (target engine: Microsoft Edge Neural); the one genuine gap was the novelfire
  watermark class above (fixed in Stage 1.5). Other candidate patterns (`*` emphasis, raw `#`,
  numeric-range dashes) were **flagged, not changed** — recorded as possible future rules.

### Changed — PDF build alignment (Phase 6, safety-first)
- Confirmed the editor's PDF typography already matches `web-novel-scraper` (read side by side)
  — no typography change.
- **Orphan heading-only page:** added **prevention** (`keepWithNext=1` on the heading style, so a
  heading can't be stranded at a page bottom) and **detection-only** logging
  (`detect_heading_only_pages()` via `pdfplumber`, run only on multi-chapter builds → GUI warning
  + JSONL `integrity_flag`, never deletes). **Automatic page deletion is DEFERRED** (no safe
  invariant; defect not reproducible from real data — all inputs are single-chapter). **`pypdf`
  was NOT added** (no rewrite path). (DECISIONS.md #017/#018.)

### Changed — GUI consistency with `web-novel-scraper` (Phase 7)
- Window title + header renamed **"Webnovel Editor" → "Web Novel Editor"** (pairs "Web Novel
  Scraper"); run controls moved **above** the log (log now at the bottom); the three
  diagnostic checkboxes card relabelled **"Options" → "Advanced Options."** The editor's
  `#134252`/`clam` ttk design system is fully preserved.
- **No Stop/Cancel button and no threading change** — the editor's `run_batch` has no safe
  cooperative-cancellation seam, so cancellation is recorded as a **separately deferred feature**
  (faking it by killing a worker mid-PDF-write is the corruption hazard Phase 6 guards against).
  (DECISIONS.md #019/#020.)

### Changed — cross-platform repo reorganization (Phase 8)
- All program code moved under **`scripts/Universal/`** (via `git mv`, history preserved);
  `scripts/Windows/` + `scripts/MacOS/` are `.gitkeep` **structural placeholders only** (no
  OS-exclusive code — *prepared*, not "macOS supported"). Entry point is now
  `scripts/Universal/main.py`.
- Pytest suite moved `scripts/tests/` → **`files/tests/`**; the 10 pinned Shadow Slave fixtures
  moved repo-root `test-files/` → **`files/test-files/`** (kept tracked).
- **Runtime-data relocation (Option B, user-chosen):** `novel-index/` and `Novel-Edits-Details/`
  moved from `files/` to **`scripts/Universal/resources/`**, so `files/` is now purely dev-only
  and a clean release ships only `scripts/` + launchers. Proven by a release-ZIP simulation with
  `files/` entirely absent (novel selection, protected-term loading, edit-details loading all
  work). (DECISIONS.md #021/#023.) `build-spec.md` updated to this reality.

### Changed — launcher rebuild (Phase 9)
- One hardened `Setup_and_Run.bat` + one `Setup_and_Run.command` rebuilt from the study
  templates (then the `-template` copies deleted): 4 numbered steps, self-healing venv,
  **health-gated idempotent install** (lock + `pip check` + import smoke), venv-first interpreter
  order, consent-gated base-runtime install, Windows `pythonw` windowless launch with a
  `--check` console preflight (a tiny tested flag added to `main.py`).
- **Deliberate non-alignment kept:** the Python-version gate **blocks** (does not warn) below
  **3.10** — the app uses 3.10 syntax (per v0.6.1 M3), unlike the scraper/template's warn-only
  check. (DECISIONS.md #024/#025.)

### Fixed — test-fixture commit (Phase 2)
- The 10 pinned Shadow Slave fixtures are now **actually committed** (the ignore rule was
  narrowed; a `*.pdf binary` `.gitattributes` guard prevents CRLF mangling), so fixture-backed
  tests no longer silently skip in a fresh clone. (DECISIONS.md #007/#008; closes Open Issue #1.)

### Docs
- **New `md-instructions/DECISIONS.md`** — the fourth permanent doc (append-only ADR log),
  created from the template and transcribed from the running Phase-0–9 decisions ledger
  (27 entries, newest on top).
- Re-tracked `AI-WORKSPACE.md` in-repo (deliberate exception to the gitignore-agent-config
  convention). (DECISIONS.md #001.)
- `EDITING-RULES.md` (Stage 1.5 evidence base rewritten from the real corpora; orphan-page +
  TTS-criteria notes), `build-spec.md` (Option-B paths), `BRIEFING.md`, `README.md`, and
  `handoff.md` updated to the v0.10.0 reality.

### Verified
- `python scripts/verify.py` → PASS. Suite green; corpus-backed tests skip only where the
  gitignored local corpora are absent (an explicit, visible skip, never counted as a pass).
  Shadow Slave output equivalence is pinned by both a corpus-free synthetic-text test and the
  committed fixtures. The macOS `Setup_and_Run.command` is now fully verified — real macOS
  clean-room bootstrap plus a real Finder double-click, confirmed 2026-07-16 (closing the item
  Phase 9 left open on HOME-PC, which has no macOS).

## v0.9.0 — 2026-06-24 — Phase 9: Novel-Selection Dropdown + Dispatch Registry

Promotes the previously-deferred "v2" novel-profile dropdown into v1 as a **UI + dispatch
layer only** (no new per-novel editorial profiles were authored — Shadow Slave remains the
only real profile).

### Added
- **`scripts/core/novel_registry.py`** — the single source of truth for both the dropdown
  roster and the novel → pipeline dispatch:
  - `available_novels()` derives the roster from `files/novel-index/*.txt` (one entry per
    index file, **including empty placeholders** so the full roster is visible). Display
    names are the reverse of the name → filename convention (`shadow-slave.txt` →
    "Shadow Slave"; `lord-of-the-mysteries.txt` → "Lord of the Mysteries", small words kept
    lowercase). The default novel ("Shadow Slave") is listed first.
  - `resolve_dispatch(novel_name)` returns a `NovelDispatch` (pipeline, canonical-name
    floor, index filename, `has_profile`). A **registered** novel (Shadow Slave) gets its
    real profile; **anything else** — unknown, placeholder-only, empty, or None — falls
    back to **universal-only** editing via the `lord_of_mysteries` stub pipeline (universal
    rules, no novel-specific substitutions) with an empty floor + that novel's own index.
    Documented default-to-universal path; case/separator-insensitive; never raises.
- **GUI novel dropdown** (`scripts/gui/app.py`) — a labelled, read-only `ttk.Combobox`
  ("Novel" card) populated from `available_novels()`, defaulting to "Shadow Slave". The
  selection is shown in the status bar and **always passed explicitly** to `run_batch`.

### Changed
- **`scripts/core/batch_runner.py`** — `run_batch` now dispatches via `resolve_dispatch`
  instead of hardcoding the Shadow Slave pipeline/index/canonical names. Per the user's
  decision (#3), the `novel_name` **default changed from "Shadow Slave" to universal-only**
  (`None`): no implicit Shadow Slave. The GUI always passes the selected novel. Logging now
  records the selected novel and whether a novel-specific layer applied or it fell back to
  universal-only (extends the existing log; no new logging system).

### Tests
- **`scripts/tests/test_novel_registry.py`** (new) — roster derivation (synthetic + shipped
  index dirs, placeholders included, default-first), filename ↔ display-name round-trip,
  dispatch to the real SS profile vs. the universal-only fallback, that a profile-less novel
  applies **no** other novel's special-fixes, **Shadow Slave dispatched output == direct
  pipeline output** (a corpus-free synthetic-text version plus a fixture-backed one), and
  `run_batch`'s universal-only default (#3) + explicit-novel logging.
- **`scripts/tests/test_batch.py`** — the round-trip test now passes `novel_name="Shadow
  Slave"` explicitly (it intentionally exercises the real SS pipeline under the new default).
- **`scripts/tests/test_app.py`** — asserts the dropdown exists, defaults to "Shadow Slave",
  is read-only, and offers the roster; the `gui.app` import is now lazy so the suite collects
  cleanly on a machine with no tkinter at all (skips instead of erroring).

### Docs
- **`README.md`** — GUI description mentions the novel dropdown; Status section bumped to
  v0.9.0 and describes the dropdown + universal-only fallback.
- **`md-instructions/HANDOFF.md`** — Phase-9 handoff (branch, changed-file list, verify
  result, decisions, and a "FOR CODEX REVIEW" section) for the home-PC pull + review pass.

### Verified
- `python scripts/verify.py` → PASS. Suite green (corpus-gated tests skip only where the
  gitignored `test-files/shadow_slave/` fixtures are absent — the SS-unchanged guarantee is
  *also* pinned by a corpus-free synthetic-text test that always runs). Manually exercised
  the full `run_batch` dispatch on a synthesized PDF: SS output byte-for-byte identical via
  dispatch, LOTM/other novels fall back to universal-only without applying SS fixes.

## v0.8.0 — 2026-06-22 — Phase 8: Per-Novel Edit-Details System

### Added
- **`files/Novel-Edits-Details/`** — a new, extensible per-novel edit-details layer
  (human-readable markdown that documents/specifies the editing rules):
  - **`UNIVERSAL.md`** — the universal editor rules. The baseline edit logic that applies
    to every novel regardless of selection (the default behaviour the tool always runs).
  - **`Shadow-Slave.md`** — the Shadow Slave-specific edits (forced typo substitutions and
    protected-term notes), layered on top of the universal rules. Kept in sync with
    `scripts/profiles/shadow_slave/special_fixes.py`.
- **`scripts/core/edit_details.py`** — the loader that wires this in:
  - `UNIVERSAL.md` is **always loaded/applied as the base**.
  - `load_edit_details(novel_name)` maps the selected novel name to its
    `<Novel-Name>.md` and layers it on top. The lookup (`resolve_novel_md_path`) is
    case- and separator-insensitive ("Shadow Slave" / "shadow-slave" / "Shadow_Slave"
    all resolve to `Shadow-Slave.md`); `UNIVERSAL.md` is never returned as a novel match.
  - **Fallback:** if no matching novel file exists (unknown novel, no selection, or a
    missing folder), it falls back to **universal-only** editing and never crashes.
  - `novel_md_filename()` gives the conventional `<Novel-Name>.md` name for scaffolding a
    new novel (Title-Cased, hyphen-joined).

### Changed
- **`scripts/core/batch_runner.py`** — `run_batch` takes a `novel_name` parameter
  (default "Shadow Slave"), loads the edit details once per run, and logs whether the
  novel-specific layer was applied or it fell back to universal-only. No change to the
  deterministic pipeline behaviour.

### Tests
- **`scripts/tests/test_edit_details.py`** (19 tests) — covers the novel-name → markdown
  lookup (case/separator-insensitive, never matches UNIVERSAL, unknown/empty/None name,
  missing folder), the universal-base + novel-layer composition, and — explicitly — the
  **fallback-to-universal** case. Also asserts the shipped `UNIVERSAL.md` / `Shadow-Slave.md`
  resolve and layer correctly.

### Verified
- `python scripts/verify.py` → PASS. Dependency pins exact; CHANGELOG v0.8.0 matches BRIEFING.

## v0.7.0 — 2026-06-22 — Phase 7: Multi-Novel Architecture Validation

### Validated (no core refactor — the universal/profile split held)
- **Universal rule modules confirmed novel-agnostic.** Audited every shared module
  (`unicode_cleanup`, `ligature_cleanup`, `junk_strip`, `spacing_cleanup`, `ocr_repair`,
  `chapter_titles`, `punctuation`, `grammar`, `em_dash`, `slash_replace`) for buried
  Shadow Slave hardcoding. **None found in logic** — the only SS references are provenance
  comments/docstrings (porting credit to `ss_pdf_editor-v1.py`, the corpus name, the
  `12Sunny` doc example). All rule logic is generic English / generic extraction repair.
- **Pipeline interface contract holds.** `run_pipeline(text, lexicon, *, repl_log, gui_log,
  dry_run) -> str` is clean; a second novel slots in by importing a different profile module
  with no change to any `core/`, `rules/`, or `pdf/` module.

### Added (stub second novel — proves the seams)
- **`scripts/pipelines/lord_of_mysteries.py`** — a minimal `run_pipeline` stub that calls the
  universal rules in the *same order* as `shadow_slave.py`, driven by an empty placeholder
  profile. Intentionally NOT a finished editorial profile (real LOTM data is a future
  exercise).
- **`scripts/profiles/lord_of_mysteries/`** — placeholder profile package:
  `LOTM_CANONICAL_NAMES = frozenset()`, `LOTM_SPECIAL_FIXES = {}`.
- **`scripts/tests/test_multi_novel.py`** (4 tests) — empty-profile-data assertion; the
  novel-index loader handles the empty `lord-of-the-mysteries.txt` placeholder without error
  and falls back cleanly to the (empty) floor; the stub pipeline runs end-to-end on a real
  fixture (non-empty output, no `__WE_` placeholder leak, no spaced em-dash); and a
  user-protected term (`6/7 Sequence`) survives the stub pipeline unchanged.

### GUI novel-profile dropdown — confirmed v2, not built
- The build spec lists the novel-profile dropdown under **"Future GUI Features (Not v1)"** and
  Multi-Novel Architecture step 5 marks it a **"future v2 feature."** Left unbuilt per spec.
  The batch runner stays Shadow Slave-only for v1; the stub proves a second pipeline could be
  wired without core changes when the dropdown is added in v2.

### Verified
- `python scripts/verify.py` -> PASS (86 passed, 1 skipped on this machine; the unusable-bash
  skip is expected). Dependency pins exact; CHANGELOG v0.7.0 matches BRIEFING.

## v0.6.1 — 2026-06-22 — Independent review fixes

### Fixed (Critical)
- **C1 — conservative slash replacement (final two-case rule).** `slash_replace.py` converts
  **only** numeric ratios (`6/7` -> `6 out of 7`, `10/20` -> `10 out of 20`) and preserves
  **every** other slash verbatim — `and/or`, `his/her`, `yes/no`, any word/word form — with no
  substitution and no mapping table, because the intended spoken form cannot be inferred safely.
  (Supersedes the interim Codex mapping of `and/or`/pronoun pairs to spoken phrases.) Tests
  assert numeric -> "out of" and every other slash unchanged; the Phase-5 protection probe uses
  the real `Almanach` special-fix target instead.
- **C2 — protected terms remain protected through special fixes.**
  `shadow_slave.run_pipeline()` applies `SS_SPECIAL_FIXES` while protected-term placeholders
  are still active, before unmasking. A full-pipeline regression proves a protected
  `Almanach` remains byte-for-byte unchanged.
- **C3 — safe dehyphenation.** `spacing_cleanup.dehyphenate()` preserves the hyphen when
  rejoining wrapped compounds (`well-known`, `self-aware`) and removes it only for explicit
  known-safe split `sur-face -> surface`.
- **C4 — safe header/footer handling.** `remove_headers_footers()` is now a logged no-op
  because page positions are unavailable after extraction; it cannot delete repeated prose.
  A regression preserves repeated `Come on` dialogue exactly. Header/footer removal is
  deferred until page-position-aware extraction exists.

### Fixed (Minor)
- **M1:** launcher bash syntax test probes `bash --version`; an unusable Windows WSL shim now
  skips as `No usable bash found` instead of false-failing.
- **M2:** `Setup_and_Run.command` is tracked executable (`100755`) for Finder double-click.
- **M3:** both launchers stop with a plain-language message unless Python is 3.10 or newer;
  README and build specification state the correct minimum.
- **M4:** titleless chapter headings output `Chapter N` without invented `:.` punctuation and
  are logged as malformed.
- **M5:** PDF builder recognizes comma-formatted chapter numbers such as `Chapter 1,000`.
- **M6:** README now describes the real GUI, pipeline, requirements, and current v0.6.1 state.

### Specification and tests corrected
- `build-spec.md` and `EDITING-RULES.md` now define numeric-only slash replacement, masked
  special fixes, hyphen-preserving wrap joins, and the deferred header/footer stage.
- Rule, pipeline, protection, PDF, and launcher tests add or update regressions for every
  Critical issue and practical Minor coverage.

### Verified
- `python scripts/verify.py` -> PASS (81 passed, 2 skipped; the unusable-bash skip is
  expected). Dependency pins are exact and CHANGELOG v0.6.1 matches BRIEFING.

## v0.6.0 — 2026-06-21 — Phase 6: Hardening, Robustness & Distribution

### Bug hunt (systematic, all modules)
- **No Critical bugs found.** The continue-on-failure architecture was verified
  empirically against every spec bad-input case: image-only PDF → SKIP (low-confidence,
  no output); 0-byte / corrupt / non-PDF → caught + logged + batch continues; a bad file
  between two good ones → both good files still succeed and the progress bar reaches all
  N; locked/permission-denied output → per-file failure, never a crash or freeze; a
  fatal pre-loop error → routed to `messagebox.showerror` via the thread-safe path. No
  garbage PDF is ever written. These were untested, so they are now pinned (see Added).

### Fixed (Minor/Suggestion items from the bug hunt, approved before fixing)
- **M4 — launchers no longer launch after a failed dependency install.** Both
  `Setup_and_Run.bat` and `Setup_and_Run.command` now check the `pip install` exit code
  and STOP with a plain-language message (check internet, re-run) instead of falling
  through to `python scripts/main.py` and crashing a non-technical user with a raw
  `ModuleNotFoundError`. This is the "breaks on a fresh machine" case.
- **M3 — output folder auto-opens after a batch.** New cross-platform
  `utils.file_utils.open_in_file_manager` (os.startfile / `open` / `xdg-open`, never
  raises) is called from the GUI on completion when real files were written; a failure is
  logged, not crashed (implements the spec GUI requirement).
- **M2 — debug sidecar renamed `DEBUG_<name>.txt`.** Was `EDITED_<name>.txt`; now matches
  the GUI option label and the spec. `sibling_path` was replaced by `debug_text_path`
  (keeps the same dir + numeric collision suffix, swaps the `EDITED_` prefix). The JSONL
  replacement log keeps its `EDITED_<name>_replacements.jsonl` name per spec.
- **M1 — audit-log `replacement` field now holds a real description.** `shadow_slave.
  _summary()` previously wrote the rule name into the JSONL `replacement` field for
  bulk/structural transforms; it now writes a human-readable description (`original` =
  count, `rule` = rule name), so the audit log is trustworthy.
- **S1 — removed the dead `utils/logger.py` stub** (`get_session_logger` was a no-op
  imported nowhere). Deleted rather than wired, to leave no dead code.
- **S2 — removed the unused `PyPDF2==3.0.1` pin** from `scripts/requirements.txt` (nothing
  imports it). It was reserved for the deferred orphan-page-removal feature; a note in
  requirements.txt and BRIEFING's deferred-features list records that it (or `pypdf`) must
  be re-added when that feature is built. This is a deliberate "not yet," not a forgotten dep.

### Added (tests — 79 total, up from 63)
- **`scripts/tests/test_robustness.py`** (7) — pins every bad-input case above:
  image-only skip, 0-byte/corrupt/non-PDF failure (parametrized), mid-batch continuation
  with progress reaching all N, output-write-failure via a monkeypatched builder, and an
  empty-queue no-op. Hostile inputs are synthesized in `tmp_path` (no committed binaries).
- **`scripts/tests/test_launchers.py`** (3) — assert both launchers have the pip-fail
  exit guard positioned after the requirements install and before the app launch; the
  `.command` is also run through `bash -n` for syntax. (Genuine guard, not eyeballed.)
- **`test_rules.py`** (+3) — em-dash en-dash + NBSP variants all removed (the spec's
  non-negotiable sweep); chapter-title body-fused-onto-heading split; `(Part N)` suffix preserved.
- **`test_pdf.py`** — `debug_text_path` DEBUG_ prefix; `open_in_file_manager` safe on bad
  path + success on a real dir (OS launcher monkeypatched so no window pops during tests).
- **`test_pipeline.py`** (+1) — M1 regression: bulk-transform audit row's `replacement` is
  a description, not the rule name.

### Packaging / distribution decision (RESOLVED — do not revisit by accident)
- **Ship the double-click launcher; NO frozen PyInstaller exe for v1.** The launcher
  already delivers "downloaded zip → running GUI" with nothing system-wide except
  Python-if-missing (the AI-WORKSPACE contain-in-repo philosophy). A frozen exe would
  *add* risk: unsigned one-file PyInstaller binaries trip Defender/SmartScreen (and
  WatchGuard on the locked-down work machine) harder than a `.bat`; `sys._MEIPASS` path
  resolution would break the `files/novel-index/` lookup; and reportlab + pdfminer.six
  ship data files PyInstaller misses without explicit collect-data. Recorded as a possible
  *future* option only.

### Verified
- `python scripts/verify.py` → PASS (79 tests). All deps pinned, CHANGELOG v0.6.0 matches
  BRIEFING. study-examples confirmed reference-only (no runtime import in shipping code).

## v0.5.0 — 2026-06-21 — Phase 5: Novel-Index Protection System
### Pre-phase QA / TTS gate (visual pass before building Phase 5)
- Ran a real early/mid/late spread (Ch.1, 500, 1500, 2500, 3000) through the **full**
  pipeline, rendered output PDF pages to PNG (pypdfium2), and inspected them. All clean:
  heading isolated + bold + terminal period, justified Times body, natural paragraph flow,
  straight `"` dialogue, clean page-boundary continuation, no repeated headings.
- Programmatic garbage sweep on the edited text found **zero** TTS-hostile patterns across
  all five (no spaced em/en/bar dashes, stray em-dashes, leftover `/`, `__WE_` placeholder
  leaks, U+FFFD, zero-width/invisible chars, ligature glyphs, double spaces, space-before-
  punctuation, `word.Word` fusions, or control chars). Verdict: gate clean, no fixes needed.

### Added
- **`scripts/tests/test_protection.py`** — the Phase-5 preservation regression guard:
  - `test_protected_terms_survive_full_pipeline` — parametrized over **all 10 committed
    fixtures**: asserts every protected term (with possessive/plural variants) that appears
    in the source survives the full pipeline with its occurrence count **not reduced**. This
    is the guard that masking never silently corrupts/splits/drops a protected name.
  - `test_index_term_shields_against_a_rule` — the spec's Phase-5 acceptance scenario: a
    term added to a `novel-index` file (`Half/Blood`) is preserved unchanged even though the
    slash rule would otherwise rewrite it (control run confirms the unprotected copy becomes
    `Half out of Blood`).
  - Loader fallback contract: `test_empty_index_falls_back_to_builtin`,
    `test_comments_only_index_falls_back_to_builtin`, `test_missing_index_falls_back_to_builtin`
    — empty/comment-only/missing index files load as "no user terms" over the built-in floor,
    never erroring (this is what the seven intentional empty placeholder novel files rely on).
  - `test_index_is_superset_of_builtin_floor` — keeps the index reconciled with the
    always-loaded canonical floor so the two never drift.

### Changed
- **`files/novel-index/shadow-slave.txt`** reconciled with `SS_CANONICAL_NAMES`: added the
  three built-in canonical names that were missing from the index (`Rani`, `Night`, `Kimmy`)
  so the user-facing index is a complete superset of the built-in floor (352 unique terms,
  up from 349). No term was removed. (These three were already always-loaded from the
  built-in set, so this is reference-completeness, not a behavior change.)

### Notes
- The Phase-5 loader/masking core (`load_protected_lexicon`, `mask_protected_terms`,
  `unmask_placeholders`, `expand_lexicon_variants`, empty/missing-file fallback) was already
  implemented in Phase 4 because the pipeline depends on it. Phase 5 added the dedicated
  preservation test + the index reconciliation; no loader logic changes were required.
- Universal-vs-novel-specific split kept clean: universal rules stay in `scripts/rules/`,
  novel data stays in `scripts/profiles/shadow_slave/` + `files/novel-index/shadow-slave.txt`.
  Onboarding novel #2 remains a data exercise, not a refactor.

### Verified
- `python scripts/verify.py` → PASS (63 tests). The preservation guard is green across all
  10 real fixtures; the index-term shield test passes both control and protected directions;
  all 8 novel-index files (1 populated + 7 empty placeholders) load without error.

## v0.4.0 — 2026-06-21 — Phase 4: Editorial Rule Pipeline
### Added
- **Full deterministic pipeline** `scripts/pipelines/shadow_slave.py::run_pipeline`,
  orchestrated in three blocks by relationship to masking:
  - **Block A (pre-mask cleanup):** unicode normalize → straight-quote normalization →
    ligatures → **junk_strip Stage 1.5** (Tier 1 ON, Tier 2 off) → scanner-junk → header/
    footer/page-number removal → same-line/doubled chapter contamination → page-boundary
    repair → dehyphenate → **paragraph reconstruction** (re-inserts `\n\n` and
    hard-isolates the chapter heading).
  - **Block B (masked corrections):** MASK chapter lines + protected terms → OCR repair →
    spurious-space → space-collapse → slash → first em-dash pass → UNMASK. Everything that
    mutates letters runs shielded, so protected names can never be altered.
  - **Block C (post-unmask editorial):** forced typo substitutions → chapter-title
    normalization → punctuation → grammar (a/an) → **mandatory final em-dash sweep** →
    duplicate-title removal → blank-line tidy → chapter page-break (`\f`) insertion →
    heading validation (log-only).
- **All rule modules implemented** (`scripts/rules/`): `unicode_cleanup` (incl.
  `normalize_quotes` → straight doubles, apostrophes preserved), `ligature_cleanup`,
  `junk_strip` (Tier 1 markers/URLs/promo; Tier 2 log-only, shields protected terms),
  `spacing_cleanup` (headers/footers, page-boundary, **`reconstruct_paragraphs`**,
  `dehyphenate`, ported `fix_spurious_spaces`), `ocr_repair` (conservative: only repairs
  that cannot fire on clean prose — the study example's aggressive `?→fi`/`l→I`/`slash→r`
  passes were deliberately excluded), `chapter_titles` (normalize/dup-removal/page-breaks/
  validate, number preserved as written), `punctuation` (ellipsis- and number-safe),
  `grammar` (unambiguous a/an only), `em_dash` (ported two-pass), `slash_replace`.
- `scripts/core/protected_lexicon.py` — implemented (folds in the Phase-5 core the pipeline
  depends on): `load_protected_lexicon` (built-in names + `files/novel-index/shadow-slave.txt`,
  dedup, longest-first), `expand_lexicon_variants`, `mask_chapter_lines` (`__WE_CH_`),
  `mask_protected_terms` (`__WE_P_`), `unmask_placeholders`, `for_non_placeholder_segments`.
- `scripts/core/replacement_log.py` — `ReplacementLog.record` (drops no-ops) + `write_jsonl`.
- `scripts/tests/test_rules.py` (per rule module) and `scripts/tests/test_pipeline.py`
  (lexicon mask/unmask round-trip, masking shields a term, replacement-log JSONL, and a
  full-pipeline smoke against real fixtures: heading isolated, paragraphs reconstructed,
  names preserved, no spaced em-dash).

### Changed
- `scripts/core/batch_runner.py` — builds the protected lexicon once per run and calls
  `shadow_slave.run_pipeline` between extract and build; writes
  `EDITED_<name>_replacements.jsonl` when the replacement-log option is enabled.
- `scripts/tests/test_scaffold.py` — updated the two Phase-1 stub assertions superseded by
  Phase 4 (`_STAGES` wiring constant removed; no-op-stub check replaced by a
  "clean prose is preserved by the insurance rules" invariant).

### Decisions (resolved with the user)
- **Quote style:** dialogue doubles normalized to **straight `"`** (corpus majority);
  apostrophes stay curly `’`. Single-curly dialogue left untouched (rare/ambiguous).
- **Ordering:** paragraph reconstruction sits pre-mask (stage 7) and hard-isolates the
  heading; letter-mutating corrections run masked, structural passes + final em-dash sweep
  run post-unmask. Approved before implementation.

### Verified
- `python scripts/verify.py` → PASS (48 tests). Real 2-file batch (Ch.1 clean, Ch.3000
  mixed quotes) built EDITED PDFs + debug `.txt` + JSONL; originals byte-for-byte untouched;
  Ch.3000's 27 curly doubles logged + straightened; `Sunny` preserved 21× through the full
  pipeline on Ch.1; zero spaced em-dashes in output.

## v0.3.0 — 2026-06-21 — Phase 3: PDF Extraction & Output
### Added
- `scripts/pdf/extractor.py` — real pdfplumber extraction (`x_tolerance=5`,
  `y_tolerance=3`, pages joined with `\n`), plus `is_low_confidence()` / `MIN_CHARS=100`
  so image-only or empty PDFs are skipped + logged instead of producing garbage output.
- `scripts/pdf/builder.py` — ported `create_pdf_from_text()` as `build_pdf()`: Times-Roman
  11pt justified body, Helvetica-Bold 14pt `#134252` left-aligned chapter headings, 0.5in
  letter margins, `\f` page breaks. **Validated to render correctly on reportlab 5.0.0.**
- `scripts/core/batch_runner.py` — real `run_batch()`: per-file extract -> build
  `EDITED_<name>.pdf`, continue-on-failure (each file in its own try/except), low-confidence
  skip, `dry_run` (extract only) and `write_debug_text` (`.txt` sidecar) options, and a
  summary dict `{total, succeeded, failed, skipped, output_dir, outputs}`.
- `scripts/utils/file_utils.py` — `sanitize_output_filename`, `unique_output_path`
  (EDITED_<name>.pdf with numeric-suffix collision handling: `_2`, `_3`, ...), `sibling_path`.
- `scripts/tests/test_pdf.py` — extractor, builder (re-opens its own output and checks
  fonts/`#134252` color/margins/page breaks), and file_utils tests.
- `scripts/tests/test_batch.py` — round-trip tests against the **real committed fixtures**:
  outputs named/placed correctly, originals byte-for-byte untouched (sha256 + mtime), text
  survives the round-trip, collision suffixing, dry-run writes nothing, missing-file skip.

### Changed
- `scripts/gui/app.py` — the Run button now calls the real `core.batch_runner.run_batch`
  (replacing the Phase-2 `run_mock_batch`, which was removed), preserving the daemon-thread +
  `self.after(0, ...)` non-freeze pattern; added an error path (`_on_error`) and wired the
  three option checkboxes through to the runner.
- `scripts/tests/test_app.py` — GUI smoke test no longer depends on the removed mock worker;
  it constructs the window and drives `_log` / `_set_progress` directly.

### Fixed
- **Lossy merged-heading branch in the ported builder.** The study-example builder assumes
  upstream paragraph reconstruction (Phase 4) has inserted `\n\n`/`\f`. Fed raw Phase-3 text
  (which has neither), `split("\n\n")` yields one giant paragraph; the merged-heading regex
  then matched a >500-char "heading" and the `len <= MAX_HEADING_LENGTH` guard **silently
  dropped** it, losing most of the chapter. The branch is now lossless: an over-long false
  heading match falls back to rendering the whole paragraph as body.

### Verified
- `python scripts/verify.py` → PASS (17 tests). reportlab 5.0 builder validated by glyph
  inspection (Helvetica-Bold heading at `#134252`, Times-Roman body, 0.5in margins, page
  breaks). A real 2-file batch was rendered to PNG and visually confirmed clean; originals
  untouched.

## v0.2.0 — 2026-06-21 — Phase 2: GUI Shell
### Added
- `scripts/gui/app.py` — full v1 Tkinter single window (`WebnovelEditorApp`): header,
  PDF file list (Listbox EXTENDED + scrollbar) with Add/Remove/Clear, output-folder
  picker, three option checkboxes (replacement log, debug text, dry run — all default
  off), color-tagged read-only log widget, accent progress bar, "Start Batch Processing"
  button, and a status bar.
- `run_mock_batch()` — Phase-2 placeholder worker (pure, Tk-free, unit-testable): logs
  "Would process N file(s)", advances the progress bar, returns a summary dict. **No real
  PDF processing** (that is Phase 3). Runs on a daemon thread; every UI update is posted
  via `self.after(0, ...)` so the window never freezes. Summary shown via messagebox.
- `scripts/tests/test_app.py` — worker-callback tests (deterministic, delay=0) + a Tk
  construction test that drives the real progress bar (skips cleanly if no display).
- Polished native-ttk visual system (ui-design-system principles, no web/CSS framework):
  intentional palette anchored on the `#134252` heading accent, 8pt spacing grid, type
  hierarchy, semantic log colors, button/state feedback via `ttk.Style` on the `clam` theme.

### Changed
- `scripts/main.py` — now launches the GUI (`gui.app.launch`) with a clear message if
  tkinter is missing, replacing the Phase 1 placeholder banner.

### Verified
- `python scripts/verify.py` → PASS (8 tests). GUI constructs, threaded mock worker drives
  the progress bar, and the full `mainloop` path runs and exits cleanly.

## v0.1.0 — 2026-06-21 — Phase 1: Repo Scaffold & Startup Scripts
### Added
- Full `scripts/` package tree with `__init__.py` files and stub modules for every
  component: `gui/`, `core/`, `pdf/`, `pipelines/`, `rules/`, `profiles/shadow_slave/`,
  `utils/`, `tests/`.
- **New universal rule module `scripts/rules/junk_strip.py`** (Stage 1.5) — ad/URL/
  scraper-fingerprint removal. Phase 1 stub (no-op pass-through) with full design +
  evidence documented; Tier 1 ON / Tier 2 built-but-off planned for Phase 4.
- `scripts/main.py` — Phase 1 placeholder entry point (prints scaffold banner, smoke-checks
  pipeline wiring imports).
- `scripts/pipelines/shadow_slave.py` — imports all stage modules (wiring verified, including
  junk_strip at Stage 1.5) and documents the canonical stage order; `run_pipeline()` stub.
- `scripts/requirements.txt` — exact-pinned deps (pdfplumber==0.11.10, reportlab==5.0.0,
  PyPDF2==3.0.1, pytest==9.1.1), resolved on Python 3.12.10.
- `scripts/verify.py` — phase gate (pytest + dependency-pin check + CHANGELOG-bump check).
- `scripts/conftest.py` — puts `scripts/` on sys.path for tests.
- `scripts/tests/test_scaffold.py` — Phase 1 wiring tests (imports, junk_strip pass-through,
  no-op rules, profile data, dataclass shapes).
- Seeded profile data: `SS_CANONICAL_NAMES` frozenset and `SS_SPECIAL_FIXES` dict (verbatim
  from spec).
- `test-files/shadow_slave/` — 10 representative chapter PDFs copied from the corpus as pinned
  fixtures (Ch. 1, 2, 3, 100, 500, 1000, 1500, 2000, 2500, 3000).
- `README.md` (project overview + non-technical setup instructions).
- `md-instructions/EDITING-RULES.md` (full rule reference populated from the spec, including
  the Phase-4 junk-strip placeholder section).
- `.gitignore` (`.venv/`, `__pycache__/`, build artifacts, `files/bin/`, `test-logs/`, OS cruft).

### Changed
- Adapted the on-disk launchers `Setup_and_Run.bat` / `Setup_and_Run.command` (kept, not
  replaced): entry point `scripts/launcher.py` → `scripts/main.py`; requirements path left at
  `scripts/requirements.txt`; removed the ffmpeg setup block (not needed for a text/PDF tool).
  Preserved Python detection, SmartScreen note, scope prompt, `.venv/` setup, pip-into-venv,
  and pause-at-end.
- Reconciled `md-instructions/build-spec.md` path references to the real on-disk layout:
  `markdown-instructions/` → `md-instructions/` (9×), data folders shown under `files/`,
  startup-script and requirements-location sections marked RESOLVED, structure tree rewritten,
  `sm_pdf_editor-v8_2.py` → `sm_pdf_editor-v8.2.py`, Additional Review Notes decisions recorded.

### Decisions (resolved with the user)
- Keep on-disk folder layout (`md-instructions/` plural; `novel-index`/`study-examples`/
  `pdf-example-chapters` under `files/`) and update the spec to match.
- Keep & adapt the two existing launchers rather than build the spec's 3-file scheme.
- requirements.txt → `scripts/`; venv → `.venv/`; deps exact-pinned; verify gate added.
- EDITED_ collisions → numeric suffix; empty extraction (<100 chars) → skip+log+continue.
- Junk-strip: Tier 1 ON, Tier 2 built-but-off/log-only, Stage 1.5, every removal logged to JSONL.

### Notes
- The active corpus (`files/pdf-example-chapters/webscraped_shadow_slave/`, 3,000 PDFs) was
  scanned and found **free of** ad/URL/watermark junk — it appears to be from a cleaner source.
  The junk-strip stage is therefore insurance for this corpus and a real need for other sources.
- Not yet under git. No commits made.
