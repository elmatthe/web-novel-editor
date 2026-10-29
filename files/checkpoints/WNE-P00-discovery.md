# WNE Phase 00 — checkpoint (discovery, safety preparation, baseline capture)

Status: **READY FOR USER ACCEPTANCE — STOP AT GATE 00** (no hard blocker; 13 decisions listed in §13)
Scope: Master Plan Revision 2, Phase 00 only. Release target fixed at `0.4.0`. No Phase 01 work started.
Writer: Claude Code, model Sonnet 5.5, effort high (selected via `/model` in this session). The plan anticipated Codex Sol 6.1 / High; the user directed this session to execute Phase 00, so the selection differs and is reported as such.
Independent reviewer: none yet. Phase 00 mandates none; Gate 01 does. Planning-chat review of this pushed report is not a local test rerun.
Machine: HOME-PC (Windows 11 Pro 10.0.26300, 16 logical cores, 1.9 TB volume with ample free space).

## 1. Git state

| Item | Value |
|---|---|
| Working branch | `feature/plan-2b-cloud-providers` (not `main`) |
| Input HEAD | `c8a52595dd1f46f5b07f15d63798cc09e76c1145` — equals the historical SHA in the plan, rechecked live, not assumed |
| Upstream | `origin/feature/plan-2b-cloud-providers` @ `c8a5259…` (in sync before this checkpoint) |
| `origin/main` | `72d68caa3588856c063c62b9b39588fd965db603` — equals the historical SHA |
| Ahead / behind `main` | 33 ahead / 0 behind (`git rev-list --left-right --count origin/main...HEAD` = `0 33`) |
| Remote | `origin` = `https://github.com/elmatthe/web-novel-editor.git` (fetch+push) |
| Fetch | `git fetch --prune origin` succeeded; `git ls-remote` confirmed both branch tips and the tag list |
| Tags | Remote: `v0.12.0` only (peels to `72d68ca`). Local: `v0.12.0` and a local-only `stale-local-main-backup` (→ `5b4ec2c`, an old Phase 1 commit, never pushed). **`v0.4.0` is absent locally and remotely.** |
| Tree at start | Clean except two untracked paths that predate this session: `files/plans/` (the Master Plan) and `md-instructions/plan-2-ai-editor-integration.md` (an older AI drop — **left untouched and unstaged**, see decision D11) |
| Stash | none |
| Trusted script-only authority | HEAD `c8a5259`; `git status` for `scripts/`, `config.toml`, `files/tests/` was clean against HEAD when the baseline was captured. `scripts/Universal` tree `1e037a05efaa4bcf6f65a11dc2a036920c7cdf88`, `scripts` tree `8570345997ea9b1417d20d595fc23af4e9f5c2ce`. No local code differs from origin. |
| Commit of this checkpoint | A commit cannot hold its own SHA. Resolved afterwards via `git rev-parse HEAD` and `git ls-remote`; reported in the final CLI report. |

## 2. Instruction sources actually used

- `AI-WORKSPACE.md` at the repo root (present, gitignored by the existing rule). Read in full.
- The user's global/project instruction file at `MyProjects/Home-PC/.claude/CLAUDE.md` (applies to the whole Home-PC workspace). Read.
- **Absent:** `AGENTS.md`, `.claude/CLAUDE.md` inside this repo, `.ai/`, and `Vibe-Coding_Chat_Workflow.md` (searched the Home-PC workspace to depth 3; not found). Their contents were not invented.
- Orientation docs live under `md-instructions/` with tracked upper-case names (`HANDOFF.md`, `BRIEFING.md`, `CHANGELOG.md`, `DECISIONS.md`) but the working tree shows mixed-case names (`Handoff.md`, …) because of `core.ignorecase=true`. Harmless; not renamed.
- The one material conflict: the global instructions say "if I haven't specified a branch, ask before committing". The user's prompt specified the standing feature-branch policy, so the commit/push below follows that and is on the existing feature branch.

## 3. Changed files (this checkpoint)

| Path | Change |
|---|---|
| `.gitignore` | **+9 lines, 0 removed.** Anchored: `/files/checkpoints/baselines/`, `/files/runtime-data/`, `/files/temp/`, `/files/run-temp/`, `/files/test-logs/`. Credentials block untouched. |
| `files/plans/Web-Novel-Editor-Master-Implementation-Plan.md` | Added (Revision 2, saved locally as the plan instructs; unchanged content). |
| `files/checkpoints/WNE-P00-discovery.md` | This report. |
| `md-instructions/HANDOFF.md` | Short Phase 00 block added at the top; the old "Current Focus" heading renamed to mark it as prior focus. |
| `md-instructions/DECISIONS.md` | Entry **074** (0.4.0 fixed; plan-2c superseded; storage contract). Additive. |
| `md-instructions/plan-2c-installer-bootstrap.md` | 6-line SUPERSEDED notice under the title; history unchanged. |

Not changed: product code, tests, dependencies, `config.toml`, launchers, source chapters, completed outputs, credentials, version fields (`config.toml`, BRIEFING, top CHANGELOG heading and README all remain **v0.13.0**).

## 4. Ignore-safety evidence (done before any baseline text existed)

- Added the five anchored rules above; did **not** ignore `files/checkpoints/` as a whole.
- `git check-ignore -v --no-index` confirms ignored: `files/checkpoints/baselines/script-only/x.txt`, `…/MANIFEST.json`, `files/runtime-data/a`, `files/temp/a`, `files/run-temp/a`, `files/test-logs/a.log`.
- Confirmed **trackable**: `files/checkpoints/WNE-P00-discovery.md`, `files/checkpoints/WNE-P01-ai-removal.md`, `files/plans/…Master-Implementation-Plan.md`.
- `git ls-files files/checkpoints files/runtime-data files/temp files/run-temp files/test-logs test-logs` → **0** tracked private files.
- Credential block: 0 lines removed from `.gitignore`; `.env`, `.env.local`, `x.key`, `x.pem`, `secrets.json` all still ignored.
- No `.env` exists in the repo. Both provider key variables **are set** in the user's shell; values were never read or printed (names only), and were removed from the child environment only.

## 5. Validation — existing verifier, offline development harness

Command: `.venv/Scripts/python.exe files/test-logs/p00/run_offline_verify.py <venv-python>` which runs the **unmodified** `scripts/verify.py` once.
Harness (ignored, stdlib only): removes `GEMINI_API_KEY` / `GROQ_API_KEY` from the child environment; puts a `sitecustomize` network guard on `PYTHONPATH` (refuses and logs `socket.connect`, `connect_ex`, `create_connection`, `sendto` in every Python child, including pytest's); adds `PYTEST_ADDOPTS="-rs -p no:cacheprovider --junitxml=…"` so skip node IDs come from the same run. Guard self-tested before use.

| Fact | Result |
|---|---|
| Interpreter / OS | Python 3.13.12 (project `.venv`), Windows-11-10.0.26300 |
| Exit code / wall time | **0** / 34.7 s (run 1) |
| pytest, run 1 (the baseline run; JUnit/ledger source) | **1,267 passed, 8 skipped, 0 failed, 0 errors** (1,275 collected, 33 modules) |
| pytest, final-tree rerun after the doc edits | exit 0, but **1,265 passed, 10 skipped** — two Tk tests skipped; see "Intermittent Tk skips" below |
| Other verifier checks | pins all `==` PASS; CHANGELOG v0.13.0 = BRIEFING PASS; `config.toml` v0.13.0 PASS |
| Network-guard attempts | **0** logged (also 0 during the baseline freeze and workload runs) |
| `pip check` | "No broken requirements found" (read-only) |
| Real Tk | `tkinter.Tk()` and `WebnovelEditorApp()` construct fine in isolation (45/45 constructions). In run 1 `test_app` ran 19/19 with no Tk skips; **not guaranteed on every run** (below) |

### Skip inventory (all 8, node ID → reason)

All eight are `local_corpus` skips with the same cause: the tests look for corpus directories named `Supreme_Magus-v2`, `The_Noble_Queen-v2` and `webscraped_shadow_slave` under `files/pdf-example-chapters/`, but the local directories are `supreme-magus-1`, `the-noble-queen-1`, `shadow-slave-1` (plus `renegade-immortal-1`, `reverend-insanity-1`).

| Node ID | Reason |
|---|---|
| `test_junk_strip_corpus::test_no_confirmed_marker_survives_strip_junk[The_Noble_Queen-v2]` | corpus `The_Noble_Queen-v2` not present |
| `test_junk_strip_corpus::test_no_confirmed_marker_survives_strip_junk[Supreme_Magus-v2]` | corpus `Supreme_Magus-v2` not present |
| `test_junk_strip_corpus::test_error_page_files_are_flagged_and_never_stripped_empty` | corpus `Supreme_Magus-v2` not present |
| `test_junk_strip_corpus::test_corpus_asterisks_and_hashes_survive_strip_junk[The_Noble_Queen-v2]` | corpus `The_Noble_Queen-v2` not present |
| `test_junk_strip_corpus::test_corpus_asterisks_and_hashes_survive_strip_junk[Supreme_Magus-v2]` | corpus `Supreme_Magus-v2` not present |
| `test_junk_strip_corpus::test_clean_shadow_slave_sample_is_untouched` | corpus `webscraped_shadow_slave` not present |
| `test_novel_profiles::test_sm_corpus_artifact_chapters_are_fixed_in_sm_mode` | corpus `Supreme_Magus-v2` not present |
| `test_novel_profiles::test_nq_corpus_chapter_protected_terms_survive_profile_mode` | corpus `The_Noble_Queen-v2` not present |

**This matters:** corpus-backed regression checks for three novels are silently not running even though larger current corpora exist locally. The `-1` corpora are *not* byte-identical successors (e.g. Supreme Magus 4,191 → 4,407 chapters; Noble Queen 778 → 890), so pointing the tests at them may need re-pinning. Not changed here (decision D3).

### Intermittent Tk skips (new finding — affects the "Tk tests must execute" requirement)

Six full-suite runs on the unchanged tree: **1,267/8, 1,265/10, 1,267/8, 1,266/9, 1,265/10, 1,267/8** (passed/skipped), exit code 0 every time, 0 failures. The varying extra skips are Tk tests (`test_app::test_app_constructs_and_has_widgets`, `test_app.py:71`, `test_ai_gui_controls.py:418`, `test_cloud_gui.py:1082`, …), each printing "no display available for Tk". A temporary ignored pytest plugin that logged the real exception shows this is **not a display problem**: `tkinter.Tk()` intermittently raised `TclError: Can't find a usable init.tcl … couldn't read file …/tcl8.6/init.tcl: No error` and, once, `couldn't read file …/tk8.6/ttk/spinbox.tcl: no such file or directory` — files that exist and read fine moments later. Every Tk test converts *any* `TclError` into that same skip message, so the real cause is hidden and `verify` still passes.

- Cause: **unproven**. The pattern (sporadic read failures on files inside the base Python install's `tcl` folder) is typical of antivirus/indexer interference, or a filesystem filter, but no such component was inspected and nothing was changed. The workload run had just written ~9,300 files, which may or may not be related.
- Consequence: the Phase 02 requirement that meaningful Tk tests *actually execute* cannot be satisfied by an exit code or a skip count on this machine. Mitigations for 01A/02B (test change, so not done here): make Tk-construction skips fail on HOME-PC (e.g. a `--require-tk` flag analogous to `--require-local-corpora`), and print the real `TclError`.
- Any Phase 01 comparison must therefore be against **1,267 passed / 8 skipped** (clean-Tk runs), with a rerun whenever a Tk skip appears — not against a bare skip count.

### Reconciliation with other reports (kept separate)

- **Handoff (historical):** 1,265 passed / 8 skipped. **This run: 1,267 / 8.** The +2 equals the two tests `b1ded4e` added to `test_scaffold.py` (`test_config_toml_version_matches_the_changelog`, `test_verify_gate_actually_checks_the_config_version`); the Handoff figure appears to predate that commit. This is an inference from `git show`, not a rerun of the older state.
- **Supplied audit (Linux, reviewer-reported):** 1,203 passed / 67 skipped / 5 failed. **Not reproduced on HOME-PC**: 0 failures here. The audit's attribution (Windows-path expectations, missing Tk) is consistent with a Linux container but was not independently confirmed; the HOME-PC result shows the suite is green on a real Windows desktop with Tk.
- Evidence limits: single interpreter (3.13.12); no macOS; no Python 3.10 interpreter exists on this machine; corpus-backed checks for three novels did not run (above).

## 6. Frozen script-only baseline (ignored: `files/checkpoints/baselines/script-only/`)

**Authority:** the existing script-only pipeline at HEAD `c8a5259`, AI disabled (`ai_editor=None`), imported read-only. Tool: `files/test-logs/p00/freeze_baselines.py` (`write` / `verify` modes). Text files are written with `newline=""`, so `\f` and `\n` are byte-exact.

| Identity | Value |
|---|---|
| Code/config aggregate SHA-256 (93 tracked files under `scripts/` plus `config.toml` and `files/tests/conftest.py`) | `c9bd7480739dc23fa19d99c4e541b91c54b05eb4f70c5acbc62c283331e51856` |
| `BASELINE-INDEX.json` SHA-256 | `57fa825dc6ebd915a850e6f8dbb1487a3df0f43a8f25fdb512bf635256d27256` |
| Master Plan SHA-256 | `6d13564fbd70b2522bb62205245272a060f63b4150ee5ceb17ce52b9862d4b03` |
| Inputs | **92**: 11 synthetic direct + 11 synthetic PDF round-trips + 10 pinned tracked Shadow Slave PDFs + 60 private corpus PDFs (12 per corpus, evenly spaced in natural order) |
| Results | **828** = 92 inputs × 9 profiles; each is the exact post-pipeline (pre-render) text with SHA-256, rule/category counts and captured ⚠ warnings |
| Determinism | every (profile, input) run **twice in-process: 0 differences** |
| Reproducibility | `freeze_baselines.py verify` recomputed everything in a fresh process (separate temp dir): **828/828 output hashes and all input hashes identical, 0 mismatches**, 0 network attempts |
| Render samples | 10 pinned fixtures rendered with the existing builder under Shadow Slave; PDF-bytes hash, page count and re-extracted-text hash recorded (PDF bytes carry metadata, so the extracted-text hash is the comparison key per §8.1) |
| Source immutability | every source PDF SHA-256 recorded; no source was opened for writing |

Roster (9 effective profiles — one Universal, four registered, four index-only):

| Profile | Pipeline module | Registered profile | Protected terms loaded |
|---|---|---|---|
| Universal | `pipelines.lord_of_mysteries` | no | 0 (no index file) |
| Circle of Inevitability | `pipelines.lord_of_mysteries` | no | 0 (placeholder index) |
| Lord of the Mysteries | `pipelines.lord_of_mysteries` | no | 0 (placeholder index) |
| Re:Monster | `pipelines.lord_of_mysteries` | no | 0 (placeholder index) |
| Reverend Insanity | `pipelines.lord_of_mysteries` | no | 1,429 |
| Renegade Immortal | `pipelines.renegade_immortal` | yes | 861 |
| Shadow Slave | `pipelines.shadow_slave` | yes | 540 |
| Supreme Magus | `pipelines.supreme_magus` | yes | 890 |
| The Noble Queen | `pipelines.the_noble_queen` | yes | 370 |

Finding: Universal and every index-only novel dispatch to the same universal pipeline (`lord_of_mysteries`, an empty-profile stub); Universal and Circle of Inevitability produce identical text on **92/92** inputs.

### Mandatory protection invariant — PASSED on all 9 profiles, direct text and PDF round-trip

The synthetic `protected_valor` case contains every mandatory sentence from §8.2: `Clan Valor`, `Valor Clan`, `Valor`, possessives (`Valor Clan's`, `Clan Valor's`), `Grey Wolf Tribe`, `ember` / `amber` / `Ember Queen`, `the God of Peace`, `Demon of Desire`, `War God` with female pronouns, and `War God, the Goddess of Life`. For **every** profile and both input paths each sentence survives **verbatim** (`all_pass: true`), and both `Clan Valor` and `Valor Clan` remain. No `Clan Valor` → `Valor` substitution exists anywhere in current code or data (`git grep`/profile read). Index facts: `shadow-slave.txt` protects `Clan Valor`, `Valor Clan`, `Valor Group`, `Warden of Valor`, `Anvil of Valor`, `Morgan of Valor`, `Knights of Valor`; bare `Valor` is a **commented-out unresolved candidate** there (`# Valor  # capitalized 1323x in 587 chapters, but also lowercase 23x`). `the-noble-queen` protects `Valor` and `Clan Valor` (and `Princess of Valor`). Supreme Magus has `# Valor` commented out. Do not activate commented candidates silently.

### Special-fix scoping observed (same synthetic input through each profile)

Shadow Slave alone applies `Almanach→Almanac`, `carcassess→carcasses`, `threestoried→three-storied`, `tompost shelf→topmost shelf`, `Obers→Obels`; Supreme Magus alone the Silverwing/Thrud/Orpal/Ragnarök set; Noble Queen alone `Kraii→Kraai`; Renegade Immortal alone `Ligou/Ligo→Liguo`; Universal applies none (universal `ocr_repair` still fixed `S0lus→Solus`, `L0crias→Locrias`).

## 7. Large-batch workload baseline (task 7)

Real `run_batch` (script-only, `ai_editor=None`, no checkpoint — as today's GUI runs a non-cloud job), Shadow Slave profile, folder mode over `shadow-slave-1`, `write_debug_text` and `write_replacement_log` on. Run as a durable background process (explicit executable, working directory, PID file, stdout/stderr logs under `files/test-logs/p00/`). Runner: `workload_runner.py` (ignored). Network guard active; key variables removed from the child only.

| Measure | Result |
|---|---|
| Corpus / profile | `shadow-slave-1`, Shadow Slave (540 protected terms) |
| Outcome | **3,105 / 3,105 done, 0 failed, 0 skipped**; 0 warnings in the log |
| Wall time | 1,674.4 s (27.9 min) |
| Throughput | 111.3 chapters/min |
| Per-file time | median 0.481 s, p95 0.763 s, max 0.999 s, mean 0.539 s |
| Peak working set | 143.2 MB (peak only; memory growth over the run was not sampled, so boundedness is not claimed) |
| Source identity | all 3,105 source SHA-256 recorded before the run and **unchanged after** (`sources_unchanged: true`) |
| Produced | 9,315 files = 3,105 PDFs + 3,105 debug-text + 3,105 replacement JSONL, each SHA-256 recorded (identity files hash `6757c9f5…` produced, `72bda9f6…` sources; kept ignored) |
| Process | worker PID 22772 under launcher stub PID 33388, started 21:19:33, finished 21:47:32; network guard logged **0** attempts (no guard log was created) |
| Not baselined | interruption / resume / retry (script-only persistent resume does not exist yet, §2.2 item 2), checkpoint and hash overhead, resume-validation time |

Timing caveat: a 32 s evidence scan and an 11 min reproducibility check (single-threaded, other cores) overlapped part of this run. The machine has 16 cores, so any distortion should be small, but treat the throughput as a reference with a few percent of noise, not a laboratory figure. Later phases compare against this as the like-for-like reference for the plan's 20% regression threshold.

Process note: the first launch of this run was mis-quoted by `Start-Process` (the space in `Shadow Slave` split the argument), so it wrote to a stray `Slave/` directory at the repo root under the wrong profile. It was stopped via its two recorded PIDs after verifying their command lines (no other Python process was touched), the stray directory (3,796 files, all generated by that run, nothing tracked) was removed, the runner now rejects unknown novels and non-absolute output paths, and the run was repeated correctly. Its output is not used anywhere.

## 8. Inventory

### 8.1 AI / shared-utility boundary (what must be extracted before `ai/` is deleted)

| Non-`ai/` module | Imports from `ai/` | Needed generically? |
|---|---|---|
| `core/batch_runner.py` | `ai.editor.AIEditor`; `ai.models.{ProviderRunState, RunPolicy}`; `ai.provenance.text_hash` | `text_hash` → `hashlib` directly. The rest is the AI seam to remove (`ai_editor`, `use_ai_in_dry_run`, `ai_*` run-metadata, `ai_status` checkpoint arg). |
| `core/run_manifest.py` | `ai.redaction.{redact, redact_obj}`; `ai.settings.write_settings_atomic` | Atomic writer: keep (→ `utils/`). Redaction: keep only bounded diagnostic sanitization if still called. |
| `gui/app.py` | `ai.redaction.redact` (L42); lazy `ai.secrets.default_secrets_file` (L649) and `DEFAULT_DOTENV_PATH` (L662) | `redact` possibly; the two secrets lookups belong to key-location UI → remove. |
| `gui/ai_settings.py`, `gui/cloud_ui.py` | many | **Remove** (provider/key/consent/quota UI); first extract any general settings/resume presentation. |
| `main.py` | none | — |

`ai/` has 23 tracked Python files (matches the plan's inventory). Direct pins to remove: `ollama==0.6.2`, `google-genai==2.14.0`, `groq==1.6.0` (the three are lazily imported). The existing `.venv` also carries their transitive packages (`httpx`, `pydantic`, `google-auth`, `cryptography`, `websockets`, `tenacity`, …); per §7.2 these are **not** purged from a healthy environment. `config.toml` has `[ai]`, `[ai.gemini]`, `[ai.groq]` and eight `[[ai.approved_models]]` blocks to remove in Phase 01 (the `[project]` block stays). `resources/Novel-Edits-Details/UNIVERSAL-AI.md` is referenced only by `ai/prompt.py:36`.

### 8.2 Path dependencies of the `scripts/Universal` → `scripts` move

- Launchers: `Setup_and_Run-Web-Novel-Editor.bat` line 36 and `.command` line 38 hard-code `scripts\Universal\main.py` (both keep `requirements.txt` at `scripts/`).
- `files/tests/conftest.py` inserts `scripts/Universal` on `sys.path` (4 refs). Other tests mentioning the path: `test_novel_registry` (18), `test_pause_and_condensed_log` (6), `test_app` (6), `test_run_manifest` (3), `test_output_layout` (3), `test_ollama_provider` (3), a few others with 1–2.
- Resource anchors use `Path(__file__).resolve().parents[1] / "resources" / …` (`core/edit_details.py:31`, `core/novel_registry.py:66`) and survive the move provided `resources/` moves with `core/`. `gui/ai_settings.py:55` uses `parents[3]` but is deleted.
- `README.md` (5 refs) and `main.py` docstring mention the old path.

### 8.3 Pipeline differences (stage order is identical across all five)

A line-level diff of the five modules shows the same three-block sequence, same call order, same two dash passes and the same `_apply_special_fixes` (longest-key-first, applied while protected terms are masked). They differ only in: (a) which profile map is imported; (b) docstrings; (c) **audit summary rows**.

| Pipeline | Special-fix map (entries) | Emits `quote_normalize` / `slash_replace` / `em_dash` summary rows |
|---|---|---|
| `shadow_slave` | `SS_SPECIAL_FIXES` (5) | yes |
| `supreme_magus` | `SM_SPECIAL_FIXES` (13) | yes |
| `the_noble_queen` | `NQ_SPECIAL_FIXES` (1) | yes |
| `renegade_immortal` | `RI_SPECIAL_FIXES` (2) | **no** |
| `lord_of_mysteries` (= Universal and 4 index-only novels) | `LOTM_SPECIAL_FIXES` (0) | **no** |

Across the 70 private+pinned inputs, each of the three row-emitting pipelines recorded 21 quote, 1 slash and 22 dash summary rows in total, where the other two recorded 0. Those rows have category `quote`/`slash`/`dash`, so they **count as edits in the condensed log** (`category != "integrity_flag"`). Final text is identical either way, but consolidating to one orchestrator changes audit/edit counts for five of nine profiles unless summary emission stays conditional (decision D9).

### 8.4 Special-fix classification and frequency (raw extracted text, five current corpora)

| Profile | Key → target | Class (proposal) | Raw hits in own corpus; hits in other corpora |
|---|---|---|---|
| Shadow Slave | `Obers` → `Obels` | name correction (profile) | 0; 0 |
| Shadow Slave | `Almanach` → `Almanac` | term correction; keep in profile data | 1; 0 |
| Shadow Slave | `carcassess` → `carcasses` | universally-safe literal (promotion candidate) | 1; 0 |
| Shadow Slave | `threestoried` → `three-storied` | literal + style choice (hyphenation) | 0; 0 |
| Shadow Slave | `tompost shelf` → `topmost shelf` | phrase-specific typo | 0; 0 |
| Supreme Magus | 13 artifact keys (`Silven/ving`, `Thn1d`, `Thmd`, `O1pal`, `L0crias`, `S0lus`, `Phlon'a`, `Fn'ya`, `F riya`, `lnxialot`, `Ragnar??k`, `Ragnar?k`, `Ragnarfik`…) | name/term corrections (profile); fire only in Supreme Magus (`Ragnar?k` 253, `Ragnar??k` 32) | see `special-fix-frequency.json` (ignored) |
| Noble Queen | `Kraii` → `Kraai` | name correction | 5; 0 |
| Renegade Immortal | `Ligou` / `Ligo` → `Liguo` | name correction | 38 / 39; 0 |

No key fires in any *other* novel's corpus, so promoting a generic entry would change no output on today's data — and there is equally no evidence base for promotion. All five Shadow Slave entries are unclassifiable beyond this; none is blocking, but Gate 01 stays blocked on this item per §4.3 until D4 is answered.

### 8.5 Test-disposition ledger (proposal; nothing deleted or rewritten)

Full per-node ledger (1,275 node IDs, old responsibility, proposed disposition, reason/replacement) is the ignored machine-readable companion `files/test-logs/p00/test-disposition-ledger.csv` (SHA-256 `22038104d1a3a5cb29f425286cbbef38ca4b5da6b392759e8eb4df43dc2c69ee`), generated from the JUnit node IDs of the single verifier run. It is a Phase 00 *proposal*: every removal still needs the case-level confirmation in 01A.

| Proposed disposition | Nodes |
|---|---:|
| KEEP (editorial/protection/PDF/profile; root-path update only) | 398 |
| KEEP-ADAPT (no AI references; batch/GUI/IO API or root updates) | 149 |
| ADAPT (AI wording removed, launcher/scaffold path changes) | 38 |
| EXTRACT (generic behaviour to re-home before its module goes) | 15 |
| EXTRACT-REVIEW (stop/pause/checkpoint cases; confirm already covered) | 15 |
| REMOVE-CANDIDATE (AI/provider/cloud-only) | 660 |
| **Total** | **1,275** |

Per module: AI-only modules (`test_ai_editor`, `test_ai_foundation`, `test_ai_gui_controls`, `test_ai_validation`, `test_cloud_gui`, `test_cloud_keys_and_consent`, `test_gemini_provider`, `test_groq_provider`, `test_ollama_provider`, `test_rate_limiting`, `test_spend_guard`, `test_dual_mode_provenance`) → REMOVE-CANDIDATE except the named extracts below. Mixed modules are reviewed per case: `test_plan2a_phase5` (18 remove / 8 adapt), `test_run_manifest` (9 remove — quota seam; 5 adapt; 52 keep-adapt), `test_launchers` (16 adapt — they are installer/bootstrap checks, including the "consent gates base runtime install" pair, which are **not** AI tests and survive into 02B), `test_scaffold` (7 adapt: path move and the `tomllib` fix), `test_main_check_flag` (2 adapt).

Named generic tests to extract **before** their module is removed (each needs a replacement node ID recorded in 01A):

| Old node (module::function) | Responsibility | Re-home |
|---|---|---|
| `test_ai_foundation::test_per_user_paths` | per-user settings path contract | settings test using `PureWindowsPath` / `PurePosixPath` |
| `test_ai_foundation::test_atomic_settings_write_and_no_leftover` | atomic write, no temp residue | shared atomic-I/O test |
| `test_ai_foundation::test_import_has_no_filesystem_or_sdk_side_effects` | import hygiene | generalize to no-side-effect / no-network import |
| `test_cloud_keys_and_consent::test_script_only_output_is_byte_identical_with_the_cloud_layer_present` | script-only parity | frozen-baseline comparison |
| `test_cloud_keys_and_consent::test_secrets_path_uses_the_2a_per_user_runtime_directory` | per-user runtime directory | settings path test (secrets store neither read nor migrated) |
| `test_cloud_keys_and_consent::test_secrets_file_is_written_atomically_and_permission_restricted` | atomic write | shared atomic-I/O test |
| `test_ai_editor::test_script_only_never_constructs_provider` and `…prepare_run…` | no provider on script-only path | superseded by the autouse network-denial fixture |
| `test_ai_editor::test_the_provenance_lexicon_hash_still_identifies_the_whole_index` | lexicon hash identity | `hashlib` helper test |
| `test_ollama_provider::test_release_shaped_script_only_startup_needs_no_ollama_or_dev_tree` | startup without dev tree | `--check` / launcher test |
| `test_ai_gui_controls::test_constructing_the_window_never_imports_the_ollama_sdk` | window imports no AI package | generalize |
| `test_cloud_gui::test_a_cloud_run_hands_run_batch_a_checkpoint`, `…resumed_checkpoint_completes_the_original_queue` | persistent checkpoint / resume | 02A manifest tests |
| `test_spend_guard::test_a_verdict_carries_no_key_and_no_chapter_text`, `test_rate_limiting::test_the_quota_stop_record_carries_no_key_and_no_chapter_text` | no chapter text in records | manifest/diagnostics privacy test |

`test_dual_mode_provenance` (14) is classed REMOVE-CANDIDATE but should be re-read in 01A for any script-only parity case before deletion.

## 9. Python support and dependency assessment

- Declared floor: Python 3.10 (`config.toml` `python_minimum`).
- Official metadata read from the installed distributions (`Requires-Python`): `pytest 9.1.1` ≥3.10; `pdfminer.six 20260107` ≥3.10 (pinned exactly by `pdfplumber 0.11.10`); `Pillow 12.3.0` ≥3.10; `reportlab 5.0.0` ≥3.9,<4; `pdfplumber 0.11.10` ≥3.8; `natsort 8.4.0` ≥3.7; `tomli 2.4.1` ≥3.8. **Every pin is consistent with a 3.10 floor; the binding constraints are pytest, pdfminer.six and Pillow.** PDF-Splitter's narrower range is not inherited.
- The mismatch is real and small: `files/tests/test_scaffold.py:93` imports `tomllib` unconditionally (stdlib only from 3.11). `scripts/verify.py:90` already has a `ModuleNotFoundError` fallback, and `ai/config.py` (to be deleted) already uses the `tomli` fallback. So on 3.10 the suite would currently fail in one test.
- **Recommendation:** keep the 3.10 floor and the pinned `tomli` fallback; fix `test_scaffold` (and any runtime TOML read) with the same `sys.version_info` pattern in 01A. Raising to 3.11 would drop `tomli` but excludes 3.10 users and needs your approval.
- **Evidence limit:** only 3.13.12 (the `.venv`) was exercised. Base interpreters 3.12 and 3.13 are installed; there is **no 3.10 or 3.11** here and none was installed. "3.10-supported" therefore means metadata-compatible, not tested. The `py` launcher is not on PATH; `WindowsApps\python.exe` / `python3.exe` are 0-byte Microsoft Store aliases (relevant to the Phase 02B discovery tests).
- No dependency was added, installed, upgraded or repaired. `requirements.txt` still lists the three AI pins.

## 10. Bounded-candidate evidence (raw extracted text of the five current local corpora = 12,818 chapters; counts only, no corpus prose in this file)

Scan: `files/test-logs/p00/evidence_scan.py`, over the earlier raw extractions in `files/qa-tools/scratch/index-build/extracted/` (ignored; counts match the current corpora ±1 non-PDF entry) plus a per-page probe of the 60 frozen private sample PDFs (210 pages) with the extractor's tolerances.

| Candidate | Evidence found | Proposal |
|---|---|---|
| **`Asa result` → `As a result`** | **0** occurrences of `Asa result` in 12,818 chapters. Correct `As a result`: 671. Standalone `Asa` tokens exist as a real name: Supreme Magus 11 (5 chapters), Noble Queen 10 (2 chapters). | **Exclude** (no evidence; a real negative-control name exists). |
| **OCR `l` / `1` as `I`** | Confined to Supreme Magus: `l`+verb 51 hits (23 ch.), `1`+verb 15 (14 ch.), `l'm`/`l'll`/`l've` 24 (18 ch.). Renegade Immortal 1, Reverend Insanity 1, Shadow Slave 0, Noble Queen 0. The existing `ocr_repair` fixes **none** of them (probed). | Candidate for a **narrow** rule (closed verb/contraction set at clause start), Supreme Magus-driven; needs the §8.3 negative controls (numbered lists, `l23`, Roman numerals). |
| **Curly double quotes** | Straight doubles dominate three novels: Supreme Magus 227,069 (4,292 ch.), Shadow Slave 63,435 (2,647 ch.), Noble Queen 55,509 (881 ch.); Reverend Insanity is mixed (44k straight / 75k curly); Renegade Immortal is already curly (61k curly / 14 straight). **Today's rule flattens curly doubles to straight**, so it degrades Renegade Immortal's and Reverend Insanity's existing typography. | Approve for Phase 03 as paired-only conversion with uncertainty preserved. **The delta touches most chapters in three of five novels** — expect a very large reviewed diff. |
| **Apostrophes (single quotes)** | Curly already prevalent in Shadow Slave (54,836 curly vs 1,356 straight), Renegade Immortal, Reverend Insanity; straight prevalent in Noble Queen (32,912, no curly) and mixed in Supreme Magus (102,552 curly / 80,881 straight). | Approve only the mechanically unambiguous contraction/possessive class. |
| **Spaced em/en dashes** | Shadow Slave 12,476 (2,649 ch.), Reverend Insanity 1,989, Renegade Immortal 1,083, Supreme Magus 53. Unspaced: Noble Queen 380 em + 195 en. | Keep the legacy two-pass algorithm unchanged (§8.3). |
| **Page numbers (§8.4)** | **0** standalone digit-only lines in 12,818 chapters; **0** page-edge numbers and **0** repeated header/footer lines in the 210 sampled pages. These are scraped web-novel PDFs, not scanned books. | **Defer** the positional adapter (explicitly report the limitation at Gate 03) unless you supply a PDF that actually has page numbers. |

### §8.5 manual-edit evidence

The raw JSONL manual-edit records and the 3194–3226 sample tallies were **not found** anywhere in the repo or its ignored folders (the only `3194` hits are coincidental hashes and an unrelated 429-audit file). Per §8.5 this blocks unsupported evidence claims, not the migration.

| Category | Observed evidence | Existing rule coverage | Conclusion | Fixture |
|---|---|---|---|---|
| typo | unavailable | `ocr_repair` (digit-for-o, dotted words, pipe/backslash) + profile special fixes | existing only | existing |
| punctuation | unavailable | `punctuation.repair_punctuation` (double comma/dot, missing space, space-before-mark) | existing only | existing |
| comma_splice_run_on | unavailable | none | manual-only | — |
| capitalization | unavailable | none | manual-only | — |
| dialogue_tag_punct | unavailable | none | manual-only | — |
| its_its / your_youre / there_their_theyre / then_than | unavailable | none | manual-only | — |
| article | unavailable | `grammar.repair_grammar` (a/an, conservative) | existing only | existing |
| tense_slip / subject_verb_agreement | unavailable | none (explicitly refused by `grammar.py`) | manual-only | — |
| spacing | unavailable | `spacing_cleanup`, `unicode_cleanup.collapse_spaces` | existing only | existing |
| hyphen_em_dash | unavailable | `em_dash.remove_spaced_em_dashes` + `slash_replace` | existing only | existing |
| repeated_word | unavailable | none | manual-only | — |

## 11. Supersession and numbering

Recorded in DECISIONS **074**: `0.4.0` is fixed; `plan-2c-installer-bootstrap.md` is superseded (notice added, history preserved); the historical `v0.4.0 — 2026-06-21 — Phase 4` CHANGELOG heading is untouched and Phase 04 will add a distinct heading; GitHub "Latest" must be set explicitly at release. Current version fields are unchanged.

## 12. Remaining blockers and risks

| Issue | Impact | Resolution needed |
|---|---|---|
| 8 corpus-backed tests skip (name mismatch); `-1` corpora are not byte-identical to `-v2` | Three novels lack corpus regression coverage | D3 |
| Generic Shadow Slave fixes unclassified for promotion | Gate 01 blocked on this item per §4.3 | D4 |
| Consolidation changes audit/edit counts for 5 of 9 profiles | User-visible log/audit delta even with identical text | D9 |
| No Python 3.10/3.11 interpreter; no macOS; single-interpreter test evidence | "3.10 supported" is metadata-based only | accept limit or supply interpreter later |
| Tk tests skip intermittently (3 of 6 runs; real cause hidden by blanket `except TclError → skip`) | Verifier exit 0 can hide skipped GUI coverage | D13 |
| No manual-edit tallies | Blocks category-based rule claims only | none for migration |
| `.test-tmp/` is an unreadable ignored directory (git warns "Permission denied") | Cosmetic noise; could confuse a recursive scan | note for Phase 04 |
| Resume/interrupt exercise cannot be baselined yet | Script-only persistent resume does not exist (§2.2 item 2) | Phase 02A/04 |

## 13. Gate 00 — decisions required before Phase 01

1. **D1 Base and branch.** Recommended: cut `feature/0.4.0-script-only-editor` from the pushed Phase 00 checkpoint SHA, leaving `feature/plan-2b-cloud-providers` frozen as the rollback point for the unmerged v0.13.0 cloud work (the merge commit title embeds the branch name, and "cloud-providers" would mislead). Default alternative: keep working on the current branch to minimize churn. Either way the 33 cloud commits end up in `main` at merge. Cut nothing until you choose.
2. **D2 Baseline acceptance.** Accept the frozen set (92 inputs × 9 profiles; 828 results; hashes above) and the 3,105-chapter workload as the editorial and throughput reference?
3. **D3 Corpus naming.** Should 01A re-point the 8 skipped tests at the existing `*-1` corpora (and re-pin if they are not equivalent), or do the `-v2` corpora exist elsewhere, or accept the skips? I will not rename your corpora.
4. **D4 Generic Shadow Slave fixes** (`Almanach`, `carcassess`, `threestoried`, `tompost shelf`): keep unchanged in Shadow Slave profile data (recommended: zero hits elsewhere, no evidence for promotion), promote selected ones with delta fixtures, or remove?
5. **D5 Quotes/apostrophes.** Approve Phase 03 paired-only curly-quote and mechanical-apostrophe work, accepting a very large reviewed diff in three novels?
6. **D6 OCR / `Asa`.** Approve the narrow Supreme Magus-driven `l`/`1`→`I` candidate and **exclude** `Asa result`?
7. **D7 Page numbers.** Defer the §8.4 positional adapter for lack of any example?
8. **D8 Defaults and Python.** Accept: Light, Universal, PDF on / TXT off, recursion on, audit/debug off; keep the 3.10 floor with the `tomli` fallback and fix `test_scaffold` in 01A (or raise to 3.11)?
9. **D9 Audit-row policy.** When consolidating the pipelines, keep summary-row emission per-profile (preserves today's audit/edit counts) or unify (changes counts for Universal, Renegade Immortal and the four index-only novels)?
10. **D10 Writer and reviewer.** Who writes Phase 01 (Codex Sol 6.1 per the plan, or Claude Code), and which fresh CLI session reviews at Gate 01?
11. **D11 `md-instructions/plan-2-ai-editor-integration.md`** (untracked, older AI drop, not covered by the plan's supersession list): mark superseded, delete, or leave?
12. **D12 Retention number** for session logs stays at the planned 20 unless you want it changed.
13. **D13 Tk reliability.** Approve a 01A test change that fails (rather than skips) Tk-construction errors on HOME-PC and surfaces the real `TclError`, and decide whether you want to investigate the intermittent Tcl library read failures (e.g. antivirus/indexer exclusion for the Python `tcl` folder — a machine change I did not make)?

## Validation of this checkpoint's own contents

Before commit: `git diff --check`; explicit-path staging; staged-diff inspection for chapter text, secrets and absolute home paths; verifier rerun after the final documentation edits (results in the final CLI report). Baselines, harness, JUnit, ledger and workload outputs remain ignored.

## Next allowed step

**STOP at Gate 00.** Phase 01 does not start without your explicit approval of D1–D10 and D13 (D11–D12 are housekeeping). Feature-branch checkpoint commit/push is already authorized; merge, tags and releases are not.
