# WNE Phase 04 — Release readiness (v0.4.0 candidate)

Status: **CANDIDATE FIXED AND RE-VERIFIED — NOT INDEPENDENTLY RE-REVIEWED.** The single
independent Codex review of `8d93186` returned **BLOCKED** (preserved verbatim in
`WNE-P04-codex-review-8d93186.md`). All seven findings are fixed in `4b4d605` and re-verified below;
that verdict does not certify the fixed candidate. Whether a second independent review is required,
and merge/tag/release, are the user's decisions. This report does not certify publication.
Writer: Claude Code, Opus 5.5 / xHigh, HOME-PC (Windows 11, Python 3.13.12 project `.venv`).

## Git state

- Branch `feature/0.4.0-script-only-editor`. Commits this session (all pushed):
  `08f1010` Gate 02A remediation · `d248e71` Phase 02B · `5bda685` Phase 03 · `b762a6c` version
  preparation · `058610c` + `772b4dd` performance fixes (DECISIONS 081) · `8d93186` first
  candidate (reviewed: BLOCKED) · `4b4d605` review fixes (DECISIONS 082) · final candidate commit
  (this report; its SHA is given in the CLI report — a commit cannot contain its own SHA).
- `main` = `72d68ca` (v0.12.0). Tags: `v0.4.0` absent locally and remotely (checked before tagging).
- Unrelated untracked `md-instructions/plan-2-ai-editor-integration.md` preserved, never staged.

## Version surfaces

`config.toml` 0.4.0; BRIEFING `## Version: v0.4.0 — Offline Script-Only Modernization`; CHANGELOG
top entry `v0.4.0 — 2026-11-01 — Offline Script-Only Modernization` with the numbering-reset
sentence (historical `v0.4.0 — 2026-06-21` entry untouched); README publication-neutral line;
`launcher.py --version` → `Web Novel Editor 0.4.0` (verify check 5 enforces agreement).

## Verification on the committed candidate

| # | Check | Result |
|---|---|---|
| 1 | Strict offline verifier (`--require-local-corpora -rs`, keys unset, network guard in child) | **1045 passed, 0 skipped, 0 failed; all 5 checks PASS; 0 network attempts** on the fix commit `4b4d605` (`verify-04-fix.*`); the final docs-only candidate SHA is re-verified and reported in the CLI report |
| 2 | Local-corpus tests | executed inside #1 (strict; any missing corpus fails) |
| 3 | Protected terms + editorial deltas | frozen corpus 828 results, 738 changed; **contract-based attribution** (`files/run-temp/rc/contract.py`, self-tests in `contract-selftest.txt`): 22,926 validly paired quotes, 966 curly glyphs confirmed against the extracted source, 4,505 apostrophes, **0 unexplained**; second application of the new rules a no-op on all 828; mandatory invariants pass in 9 profiles × direct/PDF |
| 4 | Mixed PDF/TXT generation | 889 real The Noble Queen chapters (1 overlong title excluded in-repo), PDF + TXT: 889/889 complete pairs, 0 failed/skipped, TXT UTF-8 + LF, no form feeds, final newline; sources unchanged; manifest complete (348.9 s) |
| 5 | Crash/restart/resume/retry | on 3,095 real chapters: Pause held 3.0 s with 0 progress; cooperative Stop at exactly 500; real hard kill of the worker process at queue index 1,500 → manifest valid, 1,500 completed / 1,595 pending, 0 false completions; Resume refused until stale-lock recovery was confirmed; one injected transient publication hold failed once and Retry Failed completed it |
| 6 | Lock and collision regressions | unit/integration suites in #1 (run_lock, output_plan incl. reserved names, publication faults) |
| 7 | Settings/privacy/credential sentinels | `test_settings`, `test_gui_desktop` reset sentinels (secrets.json/siblings unchanged); session-log privacy with a real run |
| 8 | GUI/Tk and bootstrap | all Tk cases execute in fresh guarded Windows children (0 skips); bootstrap + executed `.bat` sandbox flows |
| 9 | Clean non-AI dependency/startup | real first-time setup in a sandbox copy (path with spaces, parentheses, Ü): 14 s; offline healthy check 0.8 s, 0 network attempts; no AI SDK installed; `pip check` clean; in-place repair after removing a package (no rebuild); rebuild after interpreter damage |
| 10 | Actual Windows launch | real `.bat` → offline fast path → real window (pythonw) → `WM_CLOSE` → exit 0 (3.9 s on `b762a6c`; re-run on the final candidate is reported in the CLI report); window-only capture inspected |
| 11 | PDF layout + TXT/TTS inspection | rendered page 1 of published PDFs (styled heading, justified paragraphs, “ ” ’ glyphs render); TXT sample: heading, blank-line paragraphs, LF only, UTF-8 curly glyphs; human visual/TTS acceptance pending (manual item 2) |
| 12 | Large batch (real chapters) | on `4b4d605`: 3,095 real Shadow Slave chapters (10 overlong titles excluded in-repo, see notes), PDF + debug + audit, like-for-like options with Phase 00: wall 1,830.7 s incl. stop, hard kill and two resume validations, **101.4 chapters/min vs 111.3 at Phase 00 (−9%)**; per-file median 0.516 s / p95 0.666 s (Phase 00 0.481 / 0.763); resume validation ≈60 s per resume of 3,095 sources + 9,285 outputs; memory: see notes; 0 network attempts |
| 13 | Source/output hashes, no duplicate publication | all 3,095 + 889 source SHA-256 unchanged; 9,285 recorded outputs all match their manifest hashes; 0 duplicate outputs; 0 leftover staging files; contract attribution of every debug text against Phase 00: 2,631 changed / 464 identical, **0 unexplained** (54,520 paired quotes, 413 source-confirmed curly glyphs, 793 apostrophes, 1 OCR `l`→`I`) |
| 14 | `git diff --check`, clean committed candidate | `git diff --check c6e68ed HEAD` clean; over `main..HEAD` only two Phase 00 documents are flagged (Markdown two-space hard breaks in the user's master plan, kept verbatim; a trailing blank line in a historical Plan 2b pilot report); candidate verified from a clean tracked tree |

### Large-batch notes

- In-repository output paths are long (repository root alone is 95 characters). The product's
  240-unit path preflight therefore refuses 10 of the 3,105 Shadow Slave titles when writing inside
  `files/temp/w/…`; by design names are never truncated. The same real preflight accepts **all
  3,105 + 890** queues at the default `Downloads\PDF-Editor-Outputs\…` location (no files written).
  The workload used the remaining **3,095** real chapters in the shortest contained location.
- An earlier attempt ran ~2× slower than Phase 00; it was investigated, fixed and re-measured
  (DECISIONS 081), and was also hard-terminated as a real crash test: manifest valid, 1,248
  completed with matching outputs, 1,847 pending, 0 false completions, stale lock left for
  confirmed recovery. Runs on `772b4dd` (92.1/min) were superseded by the run on `4b4d605`.
- Memory: on `4b4d605`, working set flat at 116–130 MB from item 100 to 600 of a real run (no chapter accumulation), peak 137 MB (Phase 00 peak 143 MB).
- Two workload lines first counted as unexplained were curly opening quotes present in the source
  (`“Humanity — all of you — …`); the approved spaced-dash rule had rewritten the text after them.
  The classifier gained a line-anchored source lookup and still rejects every negative self-test.

## Independent review

- Single planned review: Codex CLI 0.166.0, `gpt-6.1-sol`, reasoning high, `--sandbox read-only`,
  `--ephemeral`, of exactly `8d93186`: **BLOCKED** — four P1 (PDF later-page validation, protected
  punctuation through possessives, stale alias snapshot, over-permissive attribution) and three P2
  (malformed preferences crash, POSIX active-log pruning, `py` Store-location check).
- All seven fixed in `4b4d605` with failing-first regression tests (DECISIONS 082). The verdict is not
  transferred to the fixed candidate; a second independent review was not run (user directive: do
  not silently schedule repeated reviews).

## Release notes (draft for the GitHub release)

### Web Novel Editor v0.4.0 — Offline Script-Only Modernization

v0.4.0 is a deliberate version-number reset after v0.13.0: the editor is now an offline,
deterministic, script-only desktop app. (Version numbers are not in semantic order with the older
v0.12.0/v0.13.0 line; this release is marked Latest explicitly.)

#### Highlights
- **No AI, no network for editing.** The Ollama, Gemini and Groq passes, model pickers, API-key /
  consent / quota controls and their dependencies are gone. Editing runs entirely on your computer.
- **PDF and TXT in, PDF / TXT / both out.** Add files and whole folders (optional subfolders) into one
  ordered queue; outputs keep original names and folder structure; sources are never modified.
- **Safe, resumable runs.** Numbered run folders (default `Downloads/PDF-Editor-Outputs/<novel>-N`, or
  a folder you choose in Preferences & Data), content-hash verification, Pause/Continue/Stop at file
  boundaries, Resume in the original folder, Retry Failed, and protection against overwriting or
  aliasing existing files.
- **New compact window.** Four numbered groups (Sources, Novel & Editing, Output, Run), a resizable
  Activity pane with Summary/Detailed views, remembered Light/Dark mode, Preferences & Data, and
  session logs that never contain chapter text.
- **Self-healing launchers.** A healthy setup starts offline in seconds; re-running the launcher
  repairs missing packages or rebuilds a damaged environment. If Python is missing, Windows offers a
  user-only Python 3.13 install (with your consent); macOS links to python.org.
- **Conservative editorial improvements.** Correct curly quotes are kept; clearly paired straight
  quotes become curly; `don't`/`it's` get proper apostrophes; OCR `l'm` → `I'm` and similar attested
  cases. Protected names — e.g. *Clan Valor* always stays *Clan Valor* — and their possessives and
  surrounding punctuation never change. Uncertain cases are left exactly as written.

#### Upgrading from v0.12 / v0.13 (cloud AI versions)
- Old API keys may still be on your computer: `%LOCALAPPDATA%\WebNovelEditor\secrets.json`, a `.env`
  file in the program folder, or the `GEMINI_API_KEY` / `GROQ_API_KEY` environment variables. This
  version never reads, moves or deletes them — **delete them yourself and revoke the keys in each
  provider's console.**
- Unfinished cloud-run folders cannot be resumed; their files are left untouched. Start a new run.
- Your existing `.venv` is reused; packages that are no longer needed are not removed.

#### Known limitations
- Tested on Windows 11. The macOS launcher has not been run on a Mac for this release.
- First-time setup downloads packages (it is not an offline installer).
- Output paths longer than the conservative Windows limit (240 characters) are refused with a clear
  message instead of being shortened; choose a shorter output folder if that happens.
- Page-number removal is not included (no page-numbered sources were found).

## Limitations (honest status)

- Windows 11 (HOME-PC) is the only platform actually executed. macOS: static checks and Git Bash
  simulation of the `.command` flow only — **not run on a Mac**.
- No genuine Python-free machine (Windows Sandbox/VM) was used; missing-Python behavior is
  simulated (stripped PATH, Store-alias look-alike).
- Human visual acceptance of Light/Dark, real native dialogs, Preferences and keyboard use is
  pending the user's check (screenshots were inspected by the writer).
- Transitive dependencies other than `pdfminer.six` (pinned exactly by pdfplumber) resolve within
  ranges (e.g. Pillow, pypdfium2); direct dependencies are exact pins.
- Legacy observation kept unchanged: the single-letter rejoin glues a mid-clause lone consonant
  (`the letter l was` → `lwas`).

## Manual acceptance items for the user

1. Double-click `Setup_and_Run-Web-Novel-Editor.bat`; check both themes, Preferences & Data, Add
   Files/Add Folder native dialogs, keyboard shortcuts, a small PDF+TXT run, Clear Log/Open Log Folder.
2. Skim a few output PDFs/TXT for layout and curly-quote appearance; listen to one in the TTS tool.
3. (Optional) macOS: double-click the `.command` on a Mac before claiming macOS support.
