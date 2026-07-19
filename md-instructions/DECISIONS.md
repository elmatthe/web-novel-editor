# Web Novel Editor — Decisions (ADR Log)

Append-only record of non-obvious design decisions and their reasoning. Newest on top.
See AI-WORKSPACE.md for how this fits alongside Briefing, CHANGELOG, and handoff.

This log was transcribed in Phase 10 from the running decisions ledger kept in gitignored
scratch (`files/qa-tools/scratch/decisions-ledger.md`) during Phases 0–9; each entry keeps
its original decision date. New decisions continue to be appended here (newest on top).

---

## 033 — Plan 1 Phase 4: session-only pause/continue via a between-files Event gate (the safe seam DECISIONS #020's deferred cancellation lacked) — 2026-07-18 — Claude Code

**Status:** Accepted
**Context:** DECISIONS #020 deferred Stop/Cancel because `run_batch` had no cooperative
seam — killing the daemon worker mid-PDF-write risks a corrupt output, and the scraper's
cancellation machinery was out of scope to port. The plan's pause feature builds exactly
the between-files checkpoint that discussion described: pause is safe where cancellation
wasn't, because it only ever holds *between* files — the file in flight always finishes
and is fully written before the loop can stop moving.
**Decision:** `run_batch` gains an optional `pause_gate: threading.Event` (SET = run,
cleared = pause requested), consulted only at the top of each iteration for files 2..N —
never before the first file or after the last. On a cleared gate it logs "Paused after
chapter N of M." and blocks on `pause_gate.wait()` until Continue sets it. The GUI owns
one gate per app (`self.pause_gate`) wired to a Pause ⇄ Continue button that is enabled
only while a batch runs; `_start_batch` re-sets the gate so a new batch always starts
un-paused. **Pause state is session-only — deliberately no persistence across GUI
restarts:** the gate is in-memory only, and closing the app while paused simply ends the
daemon worker with the partial batch's completed outputs intact (re-running later is a
fresh `<name>-x` folder by the Phase-2 numbering, so nothing is overwritten). The batch
also gained the always-constructed per-file `ReplacementLog` so the condensed log line
can show an edit count even when the JSONL option is off (the JSONL file itself is still
written only when enabled).
**Alternatives considered:** A polling loop on a "paused" flag — rejected: `Event.wait()`
blocks without busy-waiting and needs no poll interval. Persisting pause/queue state to
disk for resume-after-restart — rejected: heavy machinery for a session tool, and the
numbered-output contract already makes a re-run safe. Extending pause into full
cancellation — rejected: still out of scope; #020's corruption analysis stands, and a
future Stop can now reuse this same between-files seam as its checkpoint.
**Consequences:** No threading-model change (same daemon worker + `after(0, ...)`
marshalling); headless callers that pass no gate are byte-identical in behavior. The
condensed-log rewrite in the same phase means pipeline "⚠" integrity warnings
(DECISIONS #005/#017) are explicitly forwarded to the GUI while verbose stage chatter
stays in the JSONL.

## 032 — Plan 1 Phase 3: default dropdown selection changed Shadow Slave → "Universal" — 2026-07-18 — Claude Code

**Status:** Accepted
**Context:** Since v0.9.0 the GUI dropdown pre-selected "Shadow Slave", making one novel's
full profile the implicit default for every batch. The plan promotes universal-only
editing — which every novel receives anyway as its baseline — to an explicit, named,
default choice, so a user who just wants generic cleanup never accidentally runs Shadow
Slave's forced substitutions on another novel's text.
**Decision:** `novel_registry.DEFAULT_NOVEL` is now `"Universal"`; the GUI pre-selects it.
Shadow Slave stays in the roster (alphabetical with the other index-derived novels), just
no longer pre-selected. This also finalizes the DECISIONS #030 provisional note: the
default output folder is now `Downloads\universal-x`, produced by the existing Phase-2
`kebab_case(<selection>)` with zero Phase-2 code change (pinned by test).
**Alternatives considered:** Keeping Shadow Slave as default — rejected: a novel-specific
profile is the wrong implicit choice for a multi-novel tool, and the plan's goal is
universal-first. A `None`/blank default — rejected: the dropdown must never be empty and
"Universal" names the behavior honestly.
**Consequences:** Tests asserting the Shadow Slave default were updated in place
(`test_app`, `test_novel_registry`, `test_novel_profiles`). Selecting Shadow Slave (or any
real profile) behaves exactly as before — only the pre-selection changed.

## 031 — Plan 1 Phase 3: "Universal" roster entry injected outside the registry + display-only "no profile yet" markers stripped in the GUI — 2026-07-18 — Claude Code

**Status:** Accepted
**Context:** The plan requires "Universal" as a first-class roster entry and a visible
marker on the 5 profile-less novels (Circle of Inevitability, Lord of the Mysteries,
Re Monster, Renegade Immortal, Reverend Insanity), without rebuilding the shipped v0.9.0
dispatch registry or disturbing the LOTM-stub universal-fallback invariant (#009/#014).
**Decision:** `available_novels()` injects `"Universal"` as the first entry (it is not
index-derived and has **no** `_REGISTRY` entry) and appends `NO_PROFILE_MARKER`
(" — no profile yet") to any index-derived name not in `_REGISTRY`. "Universal"
dispatches through `resolve_dispatch`'s **existing** unregistered-name fallback —
universal pipeline, empty floor — so the dispatch layer is byte-for-byte untouched. The
marker is **display-only**: `_norm_key` would not strip it, so a new
`clean_novel_name()` (same module) maps display → clean name and the **GUI calls it in
`_start_batch`** before the selection reaches `run_batch` or the output-folder
kebab-casing (a marked selection can never leak `-no-profile-yet` into a folder name;
pinned by test both at the registry and GUI-spy level).
**Alternatives considered:** Registering "Universal" in `_REGISTRY` — rejected: the
registry is for real per-novel profiles, and the fallback already does exactly this.
Stripping markers inside `resolve_dispatch`/`_norm_key` — rejected: it would push GUI
display concerns into the dispatch layer and mask genuine lookup mismatches. A separate
marker-to-name dict in the GUI — rejected: two sources of truth for one convention;
keeping marker + stripper beside the roster builder in `novel_registry` keeps it one.
**Consequences:** Roster length is now index-file count + 1; `available_novels()`'s
missing/empty-folder fallback returns `["Universal"]`. Adding a real profile later
automatically drops that novel's marker (the roster consults `_REGISTRY`). The 5 marked
novels still dispatch universal-only exactly as before.

## 030 — Plan 1 Phase 2: forced output naming `Downloads\<name>-x` (kebab-case, max(N)+1) with original filenames — EDITED_ prefix dropped — 2026-07-18 — Claude Code

**Status:** Accepted (folder-name source is provisional pending Phase 3)
**Context:** The plan removes the user-chosen output folder entirely: every batch writes
into a fresh folder in the user's Downloads, mirroring the input structure in folder mode
(the selected folder's own name is the root inside it) and flat in upload mode. The old
`EDITED_<name>.pdf` naming becomes redundant once outputs live in their own clearly-named
folder, and it broke the "original filenames kept" mirroring contract.
**Decision:** Output folder = `Downloads\<name>-x` where `<name>` is the kebab-cased novel
selection (`kebab_case` in `utils/file_utils.py`) and `x` = max(N of existing `<name>-N`
dirs, case-insensitive, numeric-suffix-only) + 1, starting at 1 — gaps are never reused, so
a re-run never collides with or overwrites an earlier batch. `next_numbered_output_dir`
only *names* the folder; `run_batch` creates it when the batch actually starts (dry runs
create nothing). Output PDFs keep their original filenames; the per-file collision suffix
(`_2`, `_3`, ...) stays; sidecars are now `<name>_replacements.jsonl` and `DEBUG_<name>.txt`
beside each output (the JSONL name follows automatically since it derives from the output
path). **Provisional note:** `<name>` currently kebab-cases the live dropdown selection
(default "Shadow Slave" → `shadow-slave-x`); Phase 3 makes "Universal" the default entry,
which will produce `universal-x` with no further code change here — deliberately NOT
hardcoded ahead of that phase.
**Alternatives considered:** Keeping the `EDITED_` prefix alongside the new folders —
rejected: redundant marking, and mirrored trees must keep original names for 1:1
correspondence with the source. Reusing numbering gaps (first free N) — rejected: max+1 is
the plan's contract and keeps batch folders chronologically ordered. Creating the folder at
selection time — rejected: an abandoned session would litter Downloads with empty folders.
**Consequences:** The GUI's "Choose Output Folder" control and state are gone; `run_batch`
gains an optional `mirror_root` param (folder mode) that routes each output into the
mirrored subfolder. Tests asserting `EDITED_` names were updated in place
(`test_pdf`/`test_batch`), and the Phase-1 folder-mode-deferred GUI test was replaced by
tests pinning the real folder-mode batch wiring.

## 029 — Plan 1 Phase 2: Downloads resolved via `SHGetKnownFolderPath` (ctypes) with `~/Downloads` fallback, behind one function — 2026-07-18 — Claude Code

**Status:** Accepted
**Context:** The forced output location writes into the user's Downloads. Assuming
`%USERPROFILE%\Downloads` is wrong on Windows when the user has relocated the folder
(Explorer's "Location" tab / OneDrive folder moves) — the plan explicitly requires proper
known-folder resolution.
**Decision:** `utils.file_utils.downloads_dir()` is the single resolution point. On Windows
it calls `SHGetKnownFolderPath` with `FOLDERID_Downloads` (`{374DE290-123F-4565-9164-39C4925E467B}`)
via `ctypes` — the canonical Win32 API for known folders, verified live on HOME-PC
(resolves `C:\Users\ematthew\Downloads`, HRESULT 0) — freeing the returned buffer with
`CoTaskMemFree`. Any failure (or a non-Windows platform) falls back to
`Path.home()/"Downloads"`, which on macOS *is* the standard location — so macOS support
later is exactly this one existing branch, per the plan.
**Alternatives considered:** Registry `Shell Folders` `{374DE290-...}` value — viable (the
plan offers it) but it's the legacy mechanism; `SHGetKnownFolderPath` is the API Microsoft
documents as authoritative and needs no registry-layout assumptions. Third-party
`platformdirs`/`knownpaths` packages — rejected: one small ctypes call doesn't justify a
new pinned dependency.
**Consequences:** No new dependency; pure-stdlib. The fallback branch is test-pinned
(`test_output_layout.py`), and the Windows branch is asserted against the real machine
(absolute, existing directory).

**Status:** Accepted
**Context:** The GUI & Batch Overhaul plan (target v0.11.0) adds a Select-Folder input mode
with a recursive scan whose ordering contract is depth-first traversal with natural
(numeric-aware) ordering at every level — `1, 2, 10`, not `1, 10, 2` — so chapter files
numbered by a person process in reading order. Numeric-aware sorting has real edge cases
(multi-number names, mixed case, embedded text), and the plan explicitly forbids
hand-rolling it.
**Decision:** Add **`natsort==8.4.0`** to `scripts/requirements.txt` — the latest stable
release, verified live against PyPI on 2026-07-17 (8.4.0, published 2023; the project is
mature and stable, not stale) rather than pinned from training memory. The scanner
(`scripts/Universal/core/input_scanner.py`) uses one shared `natsort_keygen(alg=ns.IGNORECASE)`
key so ordering is case-insensitive (matching Windows filename semantics) and identical for
files and directories. The ordering contract is pinned by `files/tests/test_input_scanner.py`.
**Alternatives considered:** Hand-rolled `re.split`-based numeric key — rejected: the plan
forbids it and natsort's handling of edge cases (multiple numbers, unicode digits, case
folding) is well-tested upstream. `os_sorted` (natsort's OS-file-explorer emulation) —
rejected: it varies by platform/locale, while the ordering contract must be identical on
Windows and macOS.
**Consequences:** One new pinned runtime dependency (pure-Python, no binaries — no launcher
change needed; installed via the existing `requirements.txt` flow). Both input modes route
through `input_scanner` (`scan_upload` preserves upload order; `scan_folder` applies the
contract), giving Phase 2's output mirroring a single ordered-list source of truth.

## 027 — Phase 10: Supreme Magus Cloudflare error-page count reconciled to 3 (committed/detected truth), not the Phase-1 recon estimate of 4 — 2026-07-16 — Claude Code

**Status:** Accepted
**Context:** A carried-forward doc discrepancy: the Phase-1 addendum recon note recorded
"ch 1423, 1424, 1427 (+1 more; 4 files)" whole-file Cloudflare error-1015 pages in
Supreme_Magus-v2, and the Phase-4 findings propagated "4". But the committed, tested artifact
`SM_ERROR_PAGES` in `files/tests/test_junk_strip_corpus.py` records exactly **3** filenames
(1423, 1424, 1427), and the Phase-5 real `run_batch` pass over the corpus reported "3/3 error
pages integrity-flagged not stripped." The "+1 more" was an unconfirmed recon estimate never
pinned to a fourth filename by the detector-backed sample.
**Decision:** Treat the **code as the source of truth**: the real count is **3**. Fix the
forward-looking docs (EDITING-RULES Stage-1.5 evidence base and the handoff carried-forward
item) to state 3; do **not** change `SM_ERROR_PAGES` or `detect_error_page()` to chase a
possibly-wrong recon number. Historical handoff Work Log entries that say "4" are append-only
history and are left as written; the reconciliation is recorded here and closed in the handoff
Current Focus.
**Alternatives considered:** Editing the code to add a hypothetical 4th error page — rejected:
no 4th filename was ever identified, the detector flags 3/3, and inventing a corpus file to
match a recon note inverts the evidence hierarchy. Silently leaving the discrepancy — rejected:
the standing instruction (#005) explicitly flagged it for Phase-10 reconciliation.
**Consequences:** Docs now agree with the committed detector behavior (3). If a genuine 4th
error page is ever found in a re-scan, it is added to `SM_ERROR_PAGES` with evidence and a new
superseding entry — the count stays code-driven, not doc-driven.

## 026 — Phase 10: release version is v0.10.0 (minor bump), not a patch v0.9.1 — 2026-07-16 — Claude Code

**Status:** Accepted
**Context:** Phase 10 finalizes the docs for the whole junk-strip-hardening plan. Everything
since v0.9.0 (Phases 1–9) bundles user-visible change: hardened junk-strip patterns, Phase-3
editorial QA fixes, the Phase-4 TTS sweep + novelfire-watermark fix, **two new real per-novel
profiles** (Noble Queen + Supreme Magus), Phase-6 PDF-build alignment (orphan-page prevention
+ detection), Phase-7 GUI consistency + rename to "Web Novel Editor", a full Phase-8 repo
reorganization (cross-platform `scripts/Universal/` layout + runtime-data relocation to
`resources/`), and Phase-9 launcher hardening. The project has no documented semver policy
beyond "one 0.x.0 bump per phase/version" in the CHANGELOG history.
**Decision:** Bump to **v0.10.0**. The plan explicitly recommends v0.10.0 over a patch-level
v0.9.1, and the breadth of user-visible change (new features + structural reorg) matches a
minor bump under the CHANGELOG's established 0.x.0 cadence. (0.10.0 > 0.9.0 in semver — 10 > 9.)
**Alternatives considered:** v0.9.1 (patch) — rejected: this is far more than a bug-fix; it
adds selectable novel profiles and reorganizes the whole repo. v1.0.0 — rejected: no
first-stable-release milestone was declared; the project is still pre-1.0 per its own history.
**Consequences:** `CHANGELOG.md`, `BRIEFING.md`, and `README.md` all read v0.10.0; the
`verify.py` gate (CHANGELOG-top == BRIEFING version) is satisfied at 0.10.0.

## 025 — Phase 9: added a `--check` preflight mode to `scripts/Universal/main.py` as the windowless-launch startup-error mechanism — 2026-07-13 — Claude Code

**Status:** Accepted
**Context:** Phase 9 §6 requires launching the GUI with `pythonw.exe` (no console) so the
user sees only the app window, and §8 requires guarding against a fatal startup exception
vanishing silently behind that windowless launch. The plan offers three options: a
console preflight import before detaching to `pythonw`; a launcher wrapper that catches
startup exceptions; or another existing startup-error mechanism. `main.py` already owns
the startup import chain (the tkinter presence check + the friendly not-found message +
`from gui.app import launch`).
**Decision:** Add a `--check` flag to `main.main()` that runs the exact startup import
chain (tkinter → `gui.app`) and exits 0 with "Startup check passed." *without* opening a
window. The launchers call `python "<main>" --check` with the CONSOLE interpreter as a
preflight; only if it exits 0 do they detach to `pythonw` (Windows) / launch the GUI
(macOS). This reuses `main.py`'s existing friendly-error handling (DRY) instead of
duplicating an import list in shell, and confirmed side-effect-free because importing
`gui.app` does not construct a Tk root (already relied on by the test suite).
**Alternatives considered:** A pure-shell import smoke (`python -c "import gui.app"`) —
rejected: it would bypass `main.py`'s friendly tkinter-missing message and duplicate the
startup chain in two places. A try/except wrapper module — rejected as heavier than a flag
on the entry point that already does this work.
**Consequences:** One tiny, tested addition to app code inside an otherwise launcher-only
phase, justified as the startup-error mechanism the plan calls for. Both launchers preflight
before the windowless launch; a startup crash is always visible in the setup console. The
`--check` contract is pinned by `test_main_check_flag.py`.

## 024 — Phase 9: one hardened launcher per OS built from the study templates; scraper *structural* patterns adopted, editor behavioral choices preserved; `-template` copies deleted — 2026-07-13 — Claude Code

**Status:** Accepted
**Context:** The repo carried both the shipped `Setup_and_Run.bat`/`.command` (a simpler
Phase-1/6 launcher: linear, always-reinstall, `python` launch, blocking 3.10 gate) and the
untracked `Setup_and_Run-template.*` study copies (the AI-WORKSPACE scaffolder sources:
numbered steps, self-healing venv, `py`-launcher detection, warn-only version check). Phase 9
directs building ONE correct launcher per OS from the template pattern, targeting the
post-Phase-8 entry point `scripts/Universal/main.py`, then deleting the templates. No local
`web-novel-scraper` clone exists on HOME-PC, so the templates (priority-1 reference) + the
live launchers (priority-2) were the sources; the scraper was already studied at commit
`5127b384…` in Phases 6/7.
**Decision:** Rebuild both launchers with a 4-step structure (`[Step N of 4]`: Python/env
check → venv → dependencies → preflight+launch; no ffmpeg step — text/PDF tool). Adopt the
templates'/scraper's **structural** patterns: numbered step banners; self-healing venv
(detect missing `activate`, rebuild, with the Windows ".venv still held open → close windows
/ check Task Manager" guidance); `py -3`→`python` detection order on Windows; consent-gated
winget/Homebrew base-runtime install defaulting to user scope. **Strengthened beyond the
templates** per §4/§5: idempotent install is health-GATED, not just a lock byte-match — skip
only when ALL of {complete venv, `requirements.lock` == `requirements.txt`, venv Python
≥3.10, `pip check` clean, `import pdfplumber, reportlab` succeeds} hold; the lock is written
ONLY after a successful install AND validation; the venv's own interpreter is preferred on a
healthy repeat launch (system Python searched only when the venv must be (re)built); the
version gate validates the interpreter that will actually build/run the venv.
**Deliberate NON-alignments (kept, not oversights):** (a) **the Python-version gate BLOCKS,
does not warn** — the templates/scraper warn-and-continue below their minimum; the editor
STOPS below 3.10 (per CHANGELOG v0.6.1 M3, the app uses 3.10 syntax). (b) The floor stays
**3.10** (the app's real minimum), even though a from-scratch install pulls
`Python.Python.3.11`. (c) macOS `.command` has no `pythonw` equivalent, so it launches with
`python` (console visible) — the Windows-only windowless launch uses `pythonw` with a
`python` fallback.
**Alternatives considered:** Keeping the simpler shipped launcher (fails the plan's
self-healing/health-check/numbered-step requirements); copying a template verbatim (would
regress the editor's blocking version gate to warn-only and drop the health gate); adding an
ffmpeg step from the template (irrelevant to a text/PDF tool).
**Consequences:** Exactly one launcher per OS in the root; the untracked `-template` study
copies deleted (never tracked, so `rm` not `git rm`). `.gitattributes` (Phase 8) already
enforces `*.bat eol=crlf` / `*.command eol=lf`; the `.command` keeps mode `100755`. Verified:
clean-room bootstrap (fresh venv → pinned install → `pip check` → import smoke → `--check`)
and a real `cmd.exe` run of the `.bat` (first run built the lock; repeat run took the
idempotent skip path and launched windowless). The `.command` was NOT executed end-to-end
(no macOS on HOME-PC) — verified by `bash -n` + static structure + logic-parity with the
proven `.bat`; user should confirm it on a Mac. 12 new launcher assertions in
`files/tests/test_launchers.py` (numbered-step order, self-healing, block-not-warn, consent
gate, health-checked install, preflight-before-windowless-launch, subroutine resolution).

## 023 — Phase 8 follow-up: user chose Option B — runtime data relocated to `scripts/Universal/resources/`; `files/` is now purely dev-only (Supersedes #022) — 2026-07-13 — Claude Code

**Status:** Accepted
**Context:** #022 escalated the build-spec-vs-AI-WORKSPACE conflict over where the two
runtime-required data folders live. The user chose **Option B**: relocate them under the
shipped `scripts/` tree so `files/` becomes purely dev-only with no exceptions, accepting
the extra work/risk of updating every path reference + re-verifying the release-ZIP proof.
**Decision:** `git mv files/novel-index → scripts/Universal/resources/novel-index` and
`git mv files/Novel-Edits-Details → scripts/Universal/resources/Novel-Edits-Details`
(history preserved). Chose `scripts/Universal/resources/` (the plan's suggested location;
no prior resources convention existed) since the data is shared/universal, not OS-specific.
Updated: the two runtime resolvers (`novel_registry.NOVEL_INDEX_DIR`,
`edit_details.EDIT_DETAILS_DIR`) from `parents[3]/"files"/…` to `parents[1]/"resources"/…`;
3 test path literals (`test_multi_novel`, `test_pipeline`, `test_protection`); and all
concrete-path mentions in shipped code comments/docstrings **and** the shipped edit-details
`.md` resources (they now say `scripts/Universal/resources/novel-index/…`). No packaging
manifest exists to update (distribution is the launcher). **Verified:** `verify` green
(369); release-ZIP proof re-run with **`files/` entirely absent** — roster 8, SS profile +
352 protected terms, edit-details layered, universal fallback intact → app fully functional
shipping only `scripts/` + launchers.
**Alternatives considered:** Option A (keep under `files/`, document the exception) —
rejected by the user in favour of a clean no-exceptions split.
**Consequences:** `files/` now holds only dev-only content (`tests/`, `test-files/`, and the
gitignored corpora/scratch); a clean release excludes all of `files/` with zero runtime
impact. Narrative doc files (BRIEFING/CHANGELOG/README/build-spec, incl. build-spec's
deliberate `files/novel-index` placement note) are updated in Phase 10 — this relocation is
exactly the build-spec change the Phase-10 doc pass formalizes.

## 022 — Phase 8: runtime data (`files/novel-index/` + `files/Novel-Edits-Details/`) NOT relocated — blocked on a genuine build-spec vs. AI-WORKSPACE conflict, escalated to the user — 2026-07-13 — Claude Code

**Status:** Superseded by #023 (user chose Option B — data relocated to `scripts/Universal/resources/`)
**Context:** `AI-WORKSPACE.md` defines `files/` as development-only and excluded from a
clean release; by that rule the two folders the running app loads at runtime
(`files/novel-index/` → roster + protected-term lexicons via `novel_registry.py`;
`files/Novel-Edits-Details/` → per-novel edit details via `edit_details.py`) "should" move
to the shipped tree (`scripts/Universal/resources/…`). **But `build-spec.md` lines ~87–89
deliberately document `novel-index/` (and study-examples/pdf-example-chapters) as living
under `files/`** — an intentional on-disk layout choice RESOLVED with the user in Phase 1.
Two of the user's own specs are in direct conflict. Phase 8 §5 and the session kickoff both
explicitly say: this is the one Phase-8 spot where stopping to ask is correct — do not
silently relocate data the build-spec deliberately placed.
**Decision:** Leave both runtime-required folders under `files/` for this phase. The package
move still fixes the resolver depth (`parents[2]`→`[3]`, see #021) so the moved code keeps
finding them at repo-root `files/…`. Present the user 2–3 concrete options and let them
decide: (A) keep them under `files/` and document the exception in build-spec + AI-WORKSPACE;
(B) relocate both to `scripts/Universal/resources/` and update resolvers + packaging +
docs + tests; (C) something else. A release-ZIP simulation proved the app loads novel
selection, protected-term indexes (352 SS terms), and edit-details with the entire *dev-only*
`files/` tree absent **as long as these two data folders ship** — which is exactly why the
where-they-live question must be settled before a release is packaged.
**Alternatives considered:** Relocating unilaterally to satisfy AI-WORKSPACE (rejected — it
overrides a deliberate, user-resolved build-spec choice on a data-handling matter, exactly
what "stop and ask" is for); leaving it undocumented (rejected — the conflict is real and
would resurface at packaging time).
**Consequences:** Phase 8 is otherwise complete; the novel-index/Novel-Edits-Details piece
is the only deferred item, pending the user's call. Whatever they choose becomes a formal
`DECISIONS.md` entry in Phase 10.

## 021 — Phase 8: cross-platform reorg — all program code under `scripts/Universal/`, tests → `files/tests/`, fixtures → `files/test-files/`; OS folders are structural placeholders only — 2026-07-13 — Claude Code

**Status:** Accepted
**Context:** The repo did not follow `AI-WORKSPACE.md`'s cross-platform layout
(`scripts/Universal|Windows|MacOS`), kept its pytest suite at `scripts/tests/` (dev-only,
mis-located), and its pinned fixtures at repo-root `test-files/`. The sibling
`web-novel-scraper` already uses the target layout (read locally as the reference).
A grep for OS-branching found only *runtime* platform selection
(`utils/file_utils.open_in_file_manager` → `os.startfile`/`open`/`xdg-open`) and no
OS-exclusive modules.
**Decision:** Mechanical structural pass (no behavior change), all via `git mv` to preserve
history: (a) every package + `main.py` → `scripts/Universal/`; `verify.py` +
`requirements.txt` stay at `scripts/` root. (b) `scripts/Windows/` + `scripts/MacOS/` are
`.gitkeep` placeholders — *structurally prepared only*, NOT "macOS supported" (nothing
OS-exclusive to put there yet). (c) `scripts/tests/` → `files/tests/`; the moved
`conftest.py` now bootstraps `scripts/Universal/` onto `sys.path` (mirroring the scraper's
`files/tests/conftest.py`) while **preserving** the editor's `local_corpus` marker +
`--require-local-corpora` flag (the scraper conftest lacks these — merged, not overwritten).
(d) repo-root `test-files/` → `files/test-files/` (10 pinned fixtures kept tracked through
the move; `.gitignore` negation rules repointed). (e) runtime resolvers
`novel_registry.py`/`edit_details.py` `parents[2]`→`parents[3]` so they still reach
repo-root `files/…` from the deeper `scripts/Universal/core/`. (f) `verify.py`
`TESTS_DIR` → `files/tests`; test fixture-path literals `test-files`→`files/test-files`
(the `_REPO_ROOT` computations stay valid — both `scripts/tests/` and `files/tests/` are 2
dirs below root). (g) launchers' `MAIN_SCRIPT` → `scripts/Universal/main.py`;
`.gitattributes` gains the scraper's launcher line-ending rules (`*.bat`/`*.cmd`→CRLF,
`*.command`→LF) preserving the existing `*.pdf binary` rule.
**Alternatives considered:** A pure `git mv`-only commit with zero edits (impossible — the
moved tree can't import or find its data without the resolver/conftest/verify path edits, so
a broken intermediate commit would be worse; edits are minimal and move-driven only);
splitting real code into `Windows/`/`MacOS/` (rejected — no OS-exclusive code exists).
**Consequences:** Layout now matches AI-WORKSPACE + the scraper. `verify` green post-move
(369 passed, unchanged from baseline) and proven from repo root, an arbitrary cwd, a
spaced-path cwd, and a stripped release-ZIP simulation. `.claude/` left as-is; `.codex/`
absent and not created (per-machine gitignored agent config, out of a mechanical-move
scope). Import mechanism unchanged: all imports are top-level package imports resolved by
putting the package root on `sys.path`, so `main.py` itself needed no edit. Runtime data
relocation was the one open item (see #022, resolved by #023).

## 020 — Phase 7: Stop/cancellation deliberately NOT added (no safe seam); editor keeps its own daemon-thread lifecycle; scraper threading NOT ported — 2026-07-13 — Claude Code

**Status:** Accepted
**Context:** The sibling `web-novel-scraper` GUI
(`scripts/Universal/app.py` @ scraper commit `5127b384f48d1496bab4a34af79264ced97a98b5`)
has a Start/Stop pair with a real cooperative-cancellation seam: a `threading.Event`
the pipeline honours between chapters, a **non-daemon** worker, and a
`WM_DELETE_WINDOW` poll-until-worker-exits close sequence (so pipeline teardown always
runs). The editor's `run_batch` has **no** cancellation seam — it is a synchronous
per-file loop with no cooperative check point — and its GUI worker is `daemon=True`.
Phase 7 §3/§4 forbid porting the scraper's threading/cancellation/lifecycle and forbid
faking cancellation by killing a worker mid-PDF-write.
**Decision:** Do **not** add a Stop/Cancel button and do **not** touch the editor's
threading model. Keep the single accent "Start Batch Processing" button and the existing
`daemon=True` worker + `self.after(0, ...)` marshalling exactly as-is. A real cooperative
cancellation feature (a `threading.Event` checked between files + a graceful window-close
poll, mirroring the scraper) is recorded as a **separately deferred feature**, not built
under cover of a visual-alignment phase. Also confirmed the "daemon vs non-daemon"
comment/behaviour mismatch the plan warned about is already reconciled at this scraper
commit (its docstring now says "non-daemon"), so nothing was copied from stale prose.
**Alternatives considered:** (a) Porting the scraper's Event + non-daemon + close-poll
pattern — rejected: it is an architectural change explicitly out of scope, and the editor
has no between-unit checkpoint to honour an Event without a pipeline redesign. (b) A Stop
button that kills the daemon thread — rejected: risks a corrupt/partial `EDITED_*.pdf`
mid-write, the exact hazard Phase 6's atomicity discussion exists to prevent.
**Consequences:** Zero lifecycle/threading change; the editor's tested non-freeze worker
is preserved. The GUI reads as paired with the scraper visually/structurally without
inheriting its cancellation machinery. If cancellation is ever wanted, it is a scoped,
independently-tested future change (add the seam in `batch_runner` first, then the button).

## 019 — Phase 7: GUI aligned to `web-novel-scraper` structurally/behaviorally while PRESERVING the editor's ttk design system — 2026-07-13 — Claude Code

**Status:** Accepted
**Context:** Phase 7 asks the editor GUI to read as a visible product family with the
scraper, but the editor already has a deliberately-built, tested ttk design system
(CHANGELOG v0.2.0/v0.6.0): `#134252` accent, `clam` theme, card/`Labelframe` sections,
semantic log colors, 8pt grid, type hierarchy. The scraper uses plainer default ttk.
Cataloguing both `scripts/gui/app.py` (editor) and `scripts/Universal/app.py` (scraper)
side by side, two of the plan's alignment items were **already satisfied** (novel/source
selection first; input/output controls before options) and did not need changing.
**Decision:** Apply **only** terminology/layout/workflow alignment, changing nothing about
the visual design system: (a) **paired naming** — window title + header H1
"Webnovel Editor" → **"Web Novel Editor"** (pairs the scraper's "Web Novel Scraper"); the
internal code name "Webnovel Editor" in non-GUI docstrings/log-prefix constants is left
untouched (not user-facing). (b) **log at the bottom** — reordered so the run controls
(progress bar + Start button) sit *above* the log, which is now the last large widget
(above only the thin status strip), mirroring the scraper's Start/Stop → progress → log
order; purely a grid-row swap (log row 5→6, run row 6→5, weighted row 5→6), no widget or
style change. (c) **grouping** — the three advanced/diagnostic checkboxes (replacement
log / debug text / dry run) card relabelled "Options" → **"Advanced Options"** so they
read as secondary. Did **not** add scraper-only controls (site/browser/delay/range/output
modes) or remove editor-only controls (file list, the three option checkboxes).
"Start Batch Processing" kept verbatim (already Start-prefixed, accurately describes the
action, and there is no Stop — see #020); renaming to bare "Start" was rejected as a
low-value cosmetic change against the "leave unchanged when certainty is low" principle.
**Alternatives considered:** Restyling the editor toward the scraper's plainer default-ttk
look — rejected outright: the plan says preserve the tested design work, and matching down
to a plainer look is a regression, not an alignment.
**Consequences:** The two apps share window-title convention, control order, log position,
and advanced-control grouping while the editor keeps its distinct polished theme. Changes
are confined to `scripts/gui/app.py` (+ `test_app.py` coverage); no core/rules/pdf/pipeline
code touched. Structural order is pinned by new grid-row assertions in `test_app.py`.

## 018 — Phase 6: `pypdf` NOT added — the deferred-feature precondition (a PDF rewrite path) was deliberately not met — 2026-07-12 — Claude Code

**Status:** Accepted
**Context:** BRIEFING's Deferred Features and `scripts/requirements.txt` both note that
`PyPDF2`/`pypdf` must be "re-added and pinned when [orphan single-heading-page removal] is
built." The scraper's `remove_single_heading_pages()` uses `pypdf` (`PdfReader`/`PdfWriter`)
to rewrite the file. Phase 6 §11 says add `pypdf` **only** if a rewrite/copy/metadata path
is actually implemented.
**Decision:** Do not add `pypdf`. Phase 6 implements prevention (`keepWithNext`) and
detection-only logging (`detect_heading_only_pages()` via the already-present `pdfplumber`)
— no page-removal, no PDF rewrite, no metadata-preservation copy. So the deferred-feature
precondition ("this feature is built") is unmet and the dependency stays absent. The
requirements-note and BRIEFING deferred entry remain accurate as written (the Phase 10 doc
pass updates the deferred note to reflect that prevention/detection landed while deletion is
still deferred).
**Alternatives considered:** Adding `pypdf` speculatively "to be ready" — rejected: an
unused pinned dependency violates the plan's "add only when genuinely required" and the
project's lean-dependency posture.
**Consequences:** Zero new dependencies this phase; Phase 6 §7–9 (metadata/atomicity/
file-lock tests) are N/A by construction and explicitly skipped. If automatic deletion is
ever justified by a positive invariant (see #017), `pypdf` must be added and pinned to the
scraper's version at that time.

## 017 — Phase 6 orphan-page handling: prevention (`keepWithNext`) + detection-only logging; automatic page deletion DEFERRED because the defect is not reproducible from real data — 2026-07-12 — Claude Code

**Status:** Accepted
**Context:** The sibling `web-novel-scraper`
(`scripts/Universal/webnovel_scraper/pdf_builder.py` @ scraper commit
`5127b384f48d1496bab4a34af79264ced97a98b5`) ships `remove_single_heading_pages()`, which
DELETES any page whose sole extracted line matches the chapter-heading regex. Phase 6
forbids porting this verbatim: a heading-only page is indistinguishable from a legitimate
title-only/empty-body chapter, the only page of a document, or (degenerately) every page.
A 100%-coverage scan of all 7,979 Phase-1 cached extractions
(`phase6_orphan_scan.py` → `phase6-orphan-scan-report.txt`) found **zero** multi-chapter/
combined documents (every file has exactly one chapter-heading-shaped line; the lone
0-heading file, SM ch. 3362, is a filename-underscore artifact, still single-chapter) and
**zero** heading-only files. The orphan defect is therefore **not reproducible from either
local corpus** — the editor's inputs are all per-chapter single-chapter PDFs, exactly as
BRIEFING assumed when it deferred this.
**Decision:** (a) **Prevention at layout time** — add `keepWithNext=1` to the builder's
chapter-heading `ParagraphStyle` so a heading can never be stranded alone at a page bottom
(a synthetic RED test found stranding at filler counts 18 and 37 with the old builder;
both, plus neighbours, now pass). Chose `keepWithNext` over wrapping the heading+first-body
paragraph in `KeepTogether` (plan's fallback) — it's the plan's preferred mechanism, native,
and doesn't risk the "chapter exceeds one page" breakage `KeepTogether` warns about.
(b) **Detection-only** — `pdf.builder.detect_heading_only_pages()` returns 1-based page
numbers of heading-only pages using the existing `pdfplumber`; `batch_runner` calls it
**only for multi-chapter builds** (≥2 `\f`-separated segments in the edited text — today's
single-chapter case skips it entirely) and, on a hit, emits a GUI warning + a JSONL
`integrity_flag` record (`rule="pdf.heading_only_page_flag"`) while **preserving the page**.
(c) **Automatic deletion DEFERRED** — no positive "this page is a genuine erroneous orphan"
invariant exists (the rejected "preceding page lacks this chapter's body" heuristic is
explicitly unreliable), and the defect isn't even reproducible, so building deletion would
be a speculative fix. A zero-page-guard test pins that a single heading-only-content
document is preserved as one page, never emptied.
**Alternatives considered:** Porting `remove_single_heading_pages()` verbatim (deletes
legitimate title-only chapters, can zero-page a document — disqualifying and explicitly
forbidden); `KeepTogether` on the whole chapter (breaks multi-page-chapter layout).
**Consequences:** Real single-chapter output is byte-content-unchanged (proven: 10/10
fixtures semantically identical pre/post via `phase6_equivalence_proof.py`, page count and
dimensions included — `keepWithNext` is a structural no-op when the heading is already at
page-1 top). Multi-chapter output (if the editor ever ingests scraper Chunked/Single-mode
PDFs) gets stranding prevention + a loud, non-destructive review flag. Deletion stays
available as a future option gated on a proven invariant + `pypdf` (see #018). Docs (Phase
10) describe this as prevention/detection-only, NOT as active deletion.

## 016 — Phase-5 provenance tests re-pointed to the two intentionally-unauthored placeholders — 2026-07-12 — Claude Code

**Status:** Accepted
**Context:** Phase 5's committed provenance tests used "The Noble Queen" as the
universal-only exemplar and pinned NQ/SM as unregistered. Phase 5b registers both, which
flips those assertions. Phase 5 §2 of the plan anticipated exactly this: the fallback
proof must always run against a novel that genuinely has no profile at that moment.
**Decision:** Swap the universal-mode exemplar in `test_dual_mode_provenance.py` to
"Renegade Immortal" (and parametrize the fallback-resolution test over Renegade
Immortal + Reverend Insanity), updating docstrings to record the history.
**Alternatives considered:** Deleting the tests (loses the fallback proof); keeping NQ
and expecting failure (wrong — the registration is deliberate).
**Consequences:** The dual-mode proof stays permanently valid because it now rides on the
two novels the user decided stay placeholders; if those are ever authored, the tests
must move to another unregistered name (same pattern, next candidate).

## 015 — One pipeline module per novel (copy of shadow_slave.py), not a shared parameterized pipeline — 2026-07-12 — Claude Code

**Status:** Accepted
**Context:** Authoring NQ/SM pipelines duplicates ~140 lines of `shadow_slave.py`
stage-ordering code per novel (4 near-identical pipeline modules now exist). A shared
`run_profile_pipeline(profile)` would remove the duplication.
**Decision:** Mirror `pipelines/shadow_slave.py` verbatim per novel (own
`_apply_special_fixes` bound to the profile's dict), exactly as the plan directs
("model it on pipelines/shadow_slave.py"); do not refactor the seam mid-plan.
**Alternatives considered:** A parameterized shared pipeline — cleaner, but it is a core
architecture change inside a phase scoped as "data/porting exercise, no core/rules/pdf
changes", and it would invalidate the per-module provenance the Phase-5 JSONL run-header
records (`pipeline: pipelines.<novel>`).
**Consequences:** Adding a novel stays a mechanical copy + registry line. A future
deliberate refactor (post-plan) can collapse the duplication; until then any stage-order
fix must be applied to all four pipeline modules.

## 014 — Universal-seam caveat NOT triggered in Phase 5b: fallback keeps reusing the LOTM stub — 2026-07-12 — Claude Code

**Status:** Accepted
**Context:** The standing v0.9.0 caveat: the universal-only fallback reuses
`pipelines.lord_of_mysteries.run_pipeline`, which is universal-rules-only *only because*
`LOTM_SPECIAL_FIXES` is empty. The plan's trigger for giving the fallback its own
dedicated pipeline is "a real LOTM profile is authored". Phase 5b authored The Noble
Queen and Supreme Magus — not LOTM (its study-examples data doesn't exist).
**Decision:** Confirmed the trigger is unmet and left the fallback on the LOTM stub;
`test_universal_fallback_applies_no_special_fixes` continues to pin
`LOTM_SPECIAL_FIXES == {}` so any future LOTM authoring is caught loudly.
**Alternatives considered:** Building `pipelines/universal.py` now anyway — rejected as
out of 5b scope (a dispatch-seam change, not data porting) and as relitigating a
settled, test-pinned design.
**Consequences:** Zero behavior change for profile-less novels. Whoever authors LOTM
must create the dedicated universal pipeline first (the pinning test forces the
conversation).

## 013 — Supreme Magus special fixes: proper-noun artifacts only; restore to the authored "Ragnarök"; profanity map and generic-word fixes excluded — 2026-07-12 — Claude Code

**Status:** Accepted
**Context:** The legacy `sm_pdf_editor-v8.2.py` carries `PROPER_NOUN_ARTIFACTS`,
Ragnarok regex fixes, a large profanity-uncensor system, and generic-word OCR fixes.
Our special-fix mechanism is plain longest-key-first `str.replace` on masked text, so
every key must be impossible in legitimate prose. All candidates were re-validated
codepoint-exactly against the real Supreme_Magus-v2 corpus (4,191 cached extractions).
**Decision:** Port only the novel-specific proper-noun corruption fixes (Silverwing/
Thrud/Orpal/Locrias/Solus/Phloria/Friya/Inxialot + the Ragnarök family). Map the
Ragnarök keys to **"Ragnarök" (o-umlaut)**, not the legacy "Ragnarok": the corpus's
~185 intact occurrences are the authored ö spelling, and NFC preserves ö, so the legacy
target would have produced a mixed-spelling output. Keep only ASCII-apostrophe forms
(curly variants have zero corpus hits). Drop possessive duplicates (substring replace of
the base form covers them). EXCLUDE: (a) the entire profanity-uncensor machinery —
spec-excluded content alteration, reconfirmed user decision; (b) generic-word artifacts
`rnade`/`S00n`/`fiabbergasted`/`overqualifled` — not novel-specific (universal
ocr_repair candidates at best) and `rnade` is a real substring false-positive hazard
(occurs inside "Bernadette"). Keep the digit-0 forms (`S0lus`, `L0crias`) as zero-risk
backstops even though universal `ocr_repair._fix_zero_to_o` normally repairs them first
(proven in the corpus run: they rarely reach stage 11).
**Alternatives considered:** Porting the legacy dict wholesale (imports the FP hazard
and non-novel-specific edits); word-boundary regex fixes (deviates from the established
SS special-fix mechanism for no corpus-evidenced need).
**Consequences:** 16 keys, all corpus- or legacy-evidenced, zero-FP by construction;
committed tests pin the exclusions (censored `f*ck` passes through verbatim;
"Bernadette" survives). The `rnade`/`S00n` class stays visible as a possible future
*universal* word-boundary OCR rule (Phase-10 note), not a profile fix.

## 012 — Noble Queen profile ships an EMPTY special-fixes dict (protection-only profile) — 2026-07-12 — Claude Code

**Status:** Accepted
**Context:** Phase 5b requires porting "only genuine, evidence-backed novel-specific
edits". The NQ study-examples scrapers contain exactly one replacement table —
`V2_DECORATIVE_REPLACEMENTS`, the webnovel.com decorative-Unicode/homoglyph watermark
map — and Phases 1–4 QA of the 778-chapter corpus surfaced no recurring NQ-specific
misspelling.
**Decision:** `NQ_SPECIAL_FIXES = {}` with a docstring explaining it is empty *by
evidence*; the profile's substance is its 26-term protected floor + index. The
decorative-Unicode class stays in universal junk-strip (Phase 2) per the plan's explicit
"don't duplicate it into the profile".
**Alternatives considered:** Inventing plausible fixes to make the profile look
substantial (violates the evidence bar); duplicating the homoglyph table into the
profile (universal junk would then behave differently per selected novel — wrong layer).
**Consequences:** Selecting "The Noble Queen" adds name protection and its own
edit-details doc, nothing else — which is what the evidence supports.

## 011 — Per-novel floors ported verbatim from the user's curated indexes; index file == floor superset — 2026-07-12 — Claude Code

**Status:** Accepted
**Context:** NQ (26 terms) and SM (594 terms, confirmed superset of all four `_legacy/`
lists) master indexes include common capitalized words ("Master", "Red", "Dawn",
"Noble"). Should the port prune them?
**Decision:** Port verbatim (generated programmatically with a round-trip check — no
hand transcription of 594 terms incl. "Arjîn", "Jǫrmungrandr"). The floors ARE the
user's curated do-not-touch lists; over-protection only shields a word from the
conservative letter-mutating passes, which is the safe direction, and SS already
protects the same class ("Night", "Winter", "Rain") across 3,000 chapters without harm.
`files/novel-index/<novel>.txt` ships the same terms (with the source's section
comments) so the SS "index ⊇ floor" reconciliation invariant holds for all three
profiled novels, pinned by tests. (Index files later moved to
`scripts/Universal/resources/novel-index/` in Phase 8 / #023.)
**Alternatives considered:** Pruning generic words (substitutes my judgment for the
user's curation — exactly what "when certainty is low, don't change it" forbids);
floor ⊂ index split like SS's historical 87/352 (SS's split is an artifact of its spec
seeding, not a design goal).
**Consequences:** Term additions remain a user-editable index exercise; the built-in
floor keeps protection alive even if an index file is emptied.

## 010 — Phase 5 provenance = JSONL run-metadata HEADER + summary fields, not per-event fields — 2026-07-11 — Claude Code

**Status:** Accepted
**Context:** Phase 5 required run-level dispatch metadata (novel/mode/pipeline) recorded
somewhere provable for both modes. `ReplacementLog` entries had a fixed 5-field schema.
**Decision:** Optional `ReplacementLog.metadata` dict; when set, `write_jsonl` emits one
`{"record": "run_metadata", ...}` header line before the entries. `run_batch` stamps it
per file and also returns `novel` + `profile_applied` in its summary. Entry schema and
`len()` unchanged; header omitted when unset (backward-compatible).
**Alternatives considered:** Adding novel/mode to every replacement event (bloats every
line with run-constant data, breaks the entry schema); a separate sidecar metadata file
(a second artifact to keep in sync).
**Consequences:** Every JSONL log self-describes which novel/pipeline/mode produced it;
old logs and tests remain valid. The plan's "run header, not per-event" guidance is
satisfied literally.

## 009 — Universal-seam coupling caveat recorded as a standing constraint (v0.9.0) — 2026-07-11 — Claude Code

**Status:** Accepted (still in force; see #014 for the Phase-5b non-trigger)
**Context:** The v0.9.0 registry's universal-only fallback reuses
`pipelines.lord_of_mysteries.run_pipeline` — universal-rules-only *only because*
`LOTM_SPECIAL_FIXES` is empty. A future real LOTM profile would silently give every
profile-less novel LOTM's fixes.
**Decision:** Keep the reuse (no dedicated universal pipeline yet) but pin the emptiness
with `test_universal_fallback_applies_no_special_fixes` and document the promotion rule:
authoring LOTM requires giving the fallback its own dedicated neutral pipeline first.
**Alternatives considered:** Building the dedicated pipeline speculatively (dead code
until LOTM exists; the reuse is correct today and test-guarded).
**Consequences:** Zero duplication now; a loud test failure is the tripwire later.

## 008 — .gitattributes `*.pdf binary` guard (core.autocrlf protection) — 2026-07-10 — Claude Code

**Status:** Accepted
**Context:** Committing the 10 pinned fixture PDFs on a Windows machine with
`core.autocrlf=true` risks CRLF mangling of binary PDF bytes on checkout/commit,
silently corrupting the fixtures the whole test layer trusts.
**Decision:** Add `.gitattributes` with `*.pdf binary` before committing the fixtures,
and verify the staged blobs are byte-identical to the on-disk files.
**Alternatives considered:** Relying on git's binary auto-detection (usually right,
but "usually" is not a guarantee the test corpus deserves).
**Consequences:** Fixture integrity is explicit and machine-independent; any future
committed PDF inherits the guard.

## 007 — Commit the 10 pinned Shadow Slave fixtures (approved exception to "no corpus PDFs in git") — 2026-07-10 — Claude Code

**Status:** Accepted
**Context:** `test-files/` was gitignored, so the 10 fixtures BRIEFING claimed were
committed never actually were — fixture-backed tests silently skipped in every fresh
clone (Open Issue #1). The corpora are copyrighted and stay local by rule.
**Decision:** Narrow the ignore rule and commit exactly these 10 small chapter PDFs, as
the one user-approved exception; everything else under `files/pdf-example-chapters/`
stays gitignored and hash-baselined.
**Alternatives considered:** Keeping them ignored + documenting the skip (leaves the
protection/equivalence guarantees unverifiable off this machine); synthetic-only
fixtures (lose real-extraction regressions).
**Consequences:** The suite's corpus-gated tests run everywhere; the copyright posture
is unchanged for the bulk corpora (they remain local-only). They moved to
`files/test-files/` in Phase 8, staying tracked.

## 006 — Junk-strip fuzzy domain matcher: structural anchors + bounded edit distance + English-word guard (zero-FP bar) — 2026-07-10 — Claude Code

**Status:** Accepted
**Context:** Phase 1 recorded 17+ mangled novelfire spellings (n0velfire, Nove1Fire,
NoveIFire, dropped letters) — an exact-string list can't cover the next mangling, but a
loose fuzzy match would eat prose. `webnovel.com` is also the *legitimate* official
site and a literal tail of "freewebnovel".
**Decision:** Two-layer matcher: an exact list of every recorded spelling, plus a
structural fuzzy layer (0/1/3/I glyph folding, Levenshtein bounded and scaled to stem
length, tail-truncation tolerance) that only fires on domain-shaped tokens and is gated
by an English-word guard set with `webnovel.com` explicitly guard-listed. A committed
zero-FP suite over letter-sharing prose words is part of the contract.
**Alternatives considered:** One permissive regex (uncontrollable FP surface); Tier-2
(log-only) for the mangled class (leaves proven junk in TTS output).
**Consequences:** New manglings within the structural envelope are caught without
touching prose; anything outside it must be added to the exact list with evidence
(sequential-thinking caught the webnovel-tail FP at design time — the guard is
load-bearing).

## 005 — Cloudflare error-1015 pages: detect-and-flag, NEVER auto-strip — 2026-07-10 — Claude Code

**Status:** Accepted
**Context:** Supreme_Magus-v2 contains whole-file Cloudflare error pages — the chapter
text is simply missing. "Cleaning" one would emit an empty/garbage chapter that looks
like a successful edit.
**Decision:** `junk_strip.detect_error_page()` requires ≥2 independent signals and both
pipelines flag (GUI warning + `integrity_flag` JSONL record) without altering the text.
The fix is a re-scrape, not an edit.
**Alternatives considered:** Auto-stripping the error boilerplate (produces an empty
"chapter" and hides the data loss); skipping the file silently (hides it differently).
**Consequences:** Data-loss cases surface loudly in logs and JSONL; no pipeline ever
manufactures an empty chapter. (Count bookkeeping: Phase-1/4 recon notes estimated 4 such
SM files, the committed `SM_ERROR_PAGES` sample records 3 — reconciled to **3** in Phase
10, see #027, as the committed/detected truth.)

## 004 — Minimum-span inline watermark removal, not whole-line drops — 2026-07-10 — Claude Code

**Status:** Accepted
**Context:** novelfire splices sit INSIDE prose lines (prose on both sides). Any
line-level removal deletes real narration; the spec's old "token-level only" wording
conversely blocked removing confirmed whole-line promos.
**Decision:** Remove the smallest provably-junk span: inline tokens excised with
surrounding prose preserved; a full line dropped only when the whole line is proven
junk; leftward template-vocabulary expansion only from a confirmed domain-token anchor,
stopping at real prose/sentence punctuation; a line is dropped only when the removal
itself empties it. Blank-line behavior explicit and pinned.
**Alternatives considered:** Whole-line removal on any marker hit (destroys prose —
disqualifying); token-only removal (leaves template-sentence fragments around the
domain).
**Consequences:** Zero prose loss by construction (Phase-4 full-corpus diff: exactly the
21 watermark chapters changed, every span manually reviewed); the expansion logic is
more complex but each step is anchored and testable.

## 003 — Homoglyph watermark domains: detection-only NFKC on a throwaway copy — never NFKC-rewrite the document — 2026-07-10 — Claude Code

**Status:** Accepted
**Context:** One SM chapter carries a math-alphanumeric-styled `freewebnovel.com`
watermark that NFC cannot fold (NFKC can). But switching the whole pipeline to NFKC
would rewrite legitimate typography corpus-wide (ligatures, styled letters, fractions)
— a global content change to fix one watermark class.
**Decision:** Stage 1 stays NFC (pinned by test). Junk-strip NFKC-folds a *throwaway
copy* of suspicious math-alphanumeric runs purely to detect a domain match, then removes
the original styled run from the real text.
**Alternatives considered:** Global NFC→NFKC (over-normalizes prose the spec says to
preserve); an explicit homoglyph translation table (endless maintenance vs. one
standard fold used detection-only).
**Consequences:** The homoglyph class is caught with zero normalization side effects;
any future styled-run watermark inherits the same detect-only path.

## 002 — Reuse the recovered v0.9.0 registry — rebase the feature branch, do NOT rebuild the dispatch layer — 2026-07-06 — Claude Code

**Status:** Accepted
**Context:** The local clone (release-main @ v0.8.0) had no `novel_registry.py`, but the
public GitHub main's README described v0.9.0 as shipped. `git fetch` confirmed
origin/main @ 319f523 contains the full registry + dropdown + tests (PR #2).
**Decision:** Recreate `feature/junk-strip-hardening` from origin/main @ 319f523
(old branch preserved as `archive/junk-strip-hardening-pre-0.5`), carry forward the
baseline scratch, and demote Phase 5 from "build dual-mode" to "confirm/prove
dual-mode". User-confirmed base.
**Alternatives considered:** Building a fresh registry on the stale base (a conflicting
parallel implementation of already-merged, reviewed work); merging the stale branch
into origin/main (inverts which side is authoritative).
**Consequences:** No duplicate dispatch implementations; Phase 5 became a proof phase;
the archive branch preserves the pre-0.5 WIP for forensics.

## 001 — Re-track AI-WORKSPACE.md in this repo (exception to the gitignore-agent-config rule) — 2026-07-06 — ematthew / Claude Code

**Status:** Accepted
**Context:** The workspace convention gitignores `AI-WORKSPACE.md` (scaffolder writes it
per-machine). The GitHub web-UI curation commits on main deleted it; the user's expanded
version needed to survive the Phase-0.5 branch recreation and ride the repo.
**Decision:** Restore and re-track the expanded `AI-WORKSPACE.md` on the feature branch,
user-directed.
**Alternatives considered:** Keeping it untracked per convention (risks losing the
expanded content the plan itself depends on).
**Consequences:** This repo deviates from the workspace default; the deviation is
deliberate and recorded (this entry is the formal DECISIONS.md record promised in Phase 0.5).
