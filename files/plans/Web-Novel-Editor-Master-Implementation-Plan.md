# Web Novel Editor — Master Implementation Plan

**Status:** Revision 2 — engineering-audit amendments integrated; execution remains gated.  
**Prepared:** October 26, 2026.  
**Repository:** [elmatthe/web-novel-editor](https://github.com/elmatthe/web-novel-editor).  
**Planning branch:** `feature/plan-2b-cloud-providers`.  
**Release target:** `0.4.0` — fixed; this deliberately replaces the former `0.14.0` proposal.  
**Execution:** Codex CLI, using the user-selected Sol 6.1 model at High effort, starts Phase 00 locally on HOME-PC. Codex is the default implementation owner thereafter unless the user assigns a slice to Claude Code. A fresh, separate CLI review session verifies each designated gate.  
**Suggested destination:** `files/plans/Web-Novel-Editor-Master-Implementation-Plan.md` in the local repository.

## 1. Purpose and authority

Modernize the working editor into an offline, deterministic, script-only desktop application. Preserve its validated editing functions and sequential batch loop. Remove every local and cloud AI editing path, then add the bounded interface, input/output, recovery, and correction improvements specified here.

The existing script-only result is the editorial baseline. This is a migration and selective enhancement, not a new editor. Refactoring must not silently change prose. Every intentional difference needs an identified rule, evidence, positive and negative fixtures, and an approved expected result.

This document supersedes earlier product directions to retain or extend Ollama, Qwen, Gemini, Groq, model selection, AI prompts, provider quotas, or cloud billing safeguards. It also supersedes `md-instructions/plan-2c-installer-bootstrap.md`, including its `0.14.0` target, AI onboarding, uninstaller, and conflicting runtime-storage directions. Phase 00 adds a short superseded notice to that drop and records the ruling without rewriting its history. Preserve their historical development records; update current-facing documentation to make the new direction unmistakable. Removing product AI does not remove development instructions for Claude Code or Codex.

Follow applicable local `AGENTS.md`/`CLAUDE.md`, `AI-WORKSPACE.md`, `Vibe-Coding_Chat_Workflow.md` or its actual local spelling, and the repository’s `md-instructions/HANDOFF.md`, `BRIEFING.md`, `CHANGELOG.md`, and `DECISIONS.md`. Read current sections once and consult older sections only for a concrete dependency or unresolved decision. Explicit user requirements in this plan take precedence over obsolete product decisions.

**Planning-session limits:** GitHub inspection was read-only. No application code, repository files, branches, commits, or releases were changed. Revision 2 incorporates the supplied Claude engineering audit and the supplied `AGENTS.md`, `AI-WORKSPACE.md`, and `Vibe-coding-chat-workflow.md`. The audit’s Linux results are reviewer-reported evidence, not a new test run by this planning session. Raw manual-edit JSONL records remain unavailable here. Local HOME-PC state, ignored corpora, installed dependencies, and desktop behavior remain Phase 00 responsibilities.

The current user request explicitly selects Codex for kickoff. The audit’s assumption that Codex is unavailable is therefore not adopted. Its valid independence concern is addressed with a separate reviewer session; the implementation session cannot approve its own work. The planning chat reviews pushed source/diffs and reports, and obtains the user’s gate decisions; it does not claim to have executed tests on HOME-PC.

## 2. Verified remote baseline and evidence limits

### 2.1 Remote state observed on October 26, 2026

| Item | Verified value | Consequence |
|---|---|---|
| Planning branch HEAD | `c8a52595dd1f46f5b07f15d63798cc09e76c1145` | The historical SHA supplied in the handoff was independently confirmed as the current remote branch tip. Recheck locally before implementation. |
| Commit tree | `0f3e9ce8cec10ebf3b01f2c0adce8ee792bea0a7` | Source inventory is tied to this commit, not an assumed future branch state. |
| Remote `main` | `72d68caa3588856c063c62b9b39588fd965db603` | Do not assume the planning branch has merged. |
| GitHub comparison | Planning branch ahead 33 commits, behind 0; merge base is the above `main` SHA | No merge, reset, rebase, or branch creation is authorized by discovery. |
| Project version | `0.13.0` in `config.toml`; current Briefing and Changelog agree | The new release target is fixed at `0.4.0`, not a Gate 00 version choice. Record the intentional numbering reset in DECISIONS; bump all current version surfaces together in Phase 04. |
| Entry point | `scripts/Universal/main.py` | Both root launchers target this path today. |
| PDF stack | `pdfplumber` extraction; ReportLab reconstruction | Preserve both initially. PDF-Splitter’s stack is a reference, not permission to replace these dependencies. |
| Tests | 33 tracked `test_*.py` modules under `files/tests/` | Preserve useful coverage; classify mixed modules before deleting anything. |
| Historical verification | Handoff reports 1,265 passed / 8 skipped; supplied audit reports Linux 1,203 passed / 67 skipped / 5 failed | Neither is a HOME-PC baseline. The reviewer attributes its failures to Windows-path expectations and missing Tk; Phase 00 must reproduce/classify them before accepting that attribution. |
| Workflow files | Four main orientation documents exist under `md-instructions/`; no tracked `AI-WORKSPACE.md`, `Vibe-Coding_Chat_Workflow.md`, `AGENTS.md`, or `CLAUDE.md` appeared in the inspected tree | Those may exist in a parent workspace or as local files. Locate them without inventing their contents. |

Sources: [branch metadata](https://api.github.com/repos/elmatthe/web-novel-editor/branches/feature/plan-2b-cloud-providers), [main metadata](https://api.github.com/repos/elmatthe/web-novel-editor/branches/main), [comparison](https://github.com/elmatthe/web-novel-editor/compare/72d68caa3588856c063c62b9b39588fd965db603...c8a52595dd1f46f5b07f15d63798cc09e76c1145), [pinned source tree](https://github.com/elmatthe/web-novel-editor/tree/c8a52595dd1f46f5b07f15d63798cc09e76c1145), and [current Handoff section](https://github.com/elmatthe/web-novel-editor/blob/c8a52595dd1f46f5b07f15d63798cc09e76c1145/md-instructions/HANDOFF.md).

### 2.2 Architectural findings that change implementation order

1. **Useful infrastructure imports `ai/` even with AI off.** `core/batch_runner.py` imports `AIEditor`, provider state/policy, and `ai.provenance.text_hash`; `core/run_manifest.py` imports redaction and atomic settings writing from `ai/`; `gui/app.py` imports redaction and AI GUI modules. Extract the genuinely shared utilities before deleting the AI package.
2. **Persistent checkpoints are currently wired for cloud runs only.** The batch seam accepts a checkpoint, but `gui/app.py::_begin` creates it only for non-dry-run cloud processing. Script-only persistent resume is an enhancement, not an already verified feature.
3. **The present manifest is insufficient for the new resume guarantee.** It records source size/mtime and a single output path, and resume primarily uses `next_index`. It does not verify completed output content or prove unchanged source bytes before skipping. Extend it in place.
4. **The current batch writer writes the final PDF directly.** Manifest writes are atomic; the visible PDF and debug/audit publication sequence is not a multi-output transaction. Add staged publication rather than claiming the current writer already meets the target.
5. **Five novel pipeline modules duplicate the universal stages.** `lord_of_mysteries`, `shadow_slave`, `supreme_magus`, `the_noble_queen`, and `renegade_immortal` run substantially the same cleanup/masking/editorial sequence with different profile data. Consolidate orchestration only after recording their differences and freezing outputs.
6. **Runtime indexes and edit-reference Markdown are already bundled in `scripts/Universal/resources/`.** This is a path migration and authority cleanup, not a reason to rebuild the term indexes. The Markdown loader provides reference/specification text; it does not execute arbitrary Markdown as editing rules.
7. **PDF page furniture is not safely removed today.** `spacing_cleanup.remove_headers_footers` intentionally returns unchanged text because page-position metadata is unavailable. `pdf/extractor.py` flattens pages into newline-joined text. Existing fused-number repair is a different heuristic and must also be preserved in the migration baseline.
8. **Quotation normalization is explicitly the old direction.** `unicode_cleanup.normalize_quotes` converts double-quote variants to ASCII, leaving single quotes alone; `test_rules.py` asserts this. Reversing that behavior belongs in Phase 03 with reviewed expected changes.

Pinned implementation evidence: [batch runner](https://github.com/elmatthe/web-novel-editor/blob/c8a52595dd1f46f5b07f15d63798cc09e76c1145/scripts/Universal/core/batch_runner.py), [manifest](https://github.com/elmatthe/web-novel-editor/blob/c8a52595dd1f46f5b07f15d63798cc09e76c1145/scripts/Universal/core/run_manifest.py), [GUI](https://github.com/elmatthe/web-novel-editor/blob/c8a52595dd1f46f5b07f15d63798cc09e76c1145/scripts/Universal/gui/app.py), [registry](https://github.com/elmatthe/web-novel-editor/blob/c8a52595dd1f46f5b07f15d63798cc09e76c1145/scripts/Universal/core/novel_registry.py), [pipeline](https://github.com/elmatthe/web-novel-editor/blob/c8a52595dd1f46f5b07f15d63798cc09e76c1145/scripts/Universal/pipelines/shadow_slave.py), [spacing rules](https://github.com/elmatthe/web-novel-editor/blob/c8a52595dd1f46f5b07f15d63798cc09e76c1145/scripts/Universal/rules/spacing_cleanup.py), [quote rules](https://github.com/elmatthe/web-novel-editor/blob/c8a52595dd1f46f5b07f15d63798cc09e76c1145/scripts/Universal/rules/unicode_cleanup.py), and [test bootstrap](https://github.com/elmatthe/web-novel-editor/blob/c8a52595dd1f46f5b07f15d63798cc09e76c1145/files/tests/conftest.py).

### 2.3 Audit reconciliation and fixed decisions

The branch and main SHAs above were rechecked through GitHub for this revision and remain unchanged. The current `.gitignore`, `scripts/verify.py`, `config.toml`, legacy bootstrap drop, and selected settings/secrets/scaffold tests were also inspected. The legacy drop really conflicts with this plan, baseline directories really lack ignore rules, and `test_scaffold` really imports `tomllib` despite the declared Python 3.10 floor. Tag availability and local state must still be checked at execution time.

| Audit issue | Binding resolution |
|---|---|
| Actual agent workflow and independence | Codex starts Phase 00 and is the default writer. A fresh Codex or Claude Code CLI session independently reviews the named base-to-head diff and targeted behavior; the user approves gates (§11). |
| Missing Git restore points | Verified working-branch checkpoints are committed/pushed per standing workspace policy at every completed slice. Gate approval controls continuation; it is not a delayed permission to save work (§9, §11). |
| Copyrighted baselines not ignored | Phase 00 may make the narrow `.gitignore` safety edit before writing any baseline text; prove ignore behavior and preserve credential exclusions (§9). |
| Release/version ambiguity | Target fixed at `0.4.0`; duplicate historical heading distinguished, version surfaces synchronized, final candidate and merge SHAs verified before tagging (§9 Phase 04). |
| Rename review, skipped/deleted tests, largest phase | Separate content-identical move commit, named test-disposition ledger and skip-reason comparison, mandatory STOP/review at Gate 02A before GUI/bootstrap (§9–11). |
| Residual secrets and offline proof | Preserve old credential files and ignore rules; settings reset touches only settings; scoped network-denial tests and clean offline startup (§6.5). |
| Windows publication/path/locking edge cases | Bounded sharing-violation retries, normalized collision keys, length preflight, explicit single-writer and stale-lock protocol (§6.2–6.3). |
| CLI limits and desktop/setup tests | Durable background workload with progress/logs; patched native dialogs; real Tk gates; simulated no-Python distinguished from VM evidence (§7.2, §9 Phase 04). |
| Suggested third-party skills | Optional, inspect availability first; no installation, assumed plugin commands, or automatic gate traversal (§11). |

Source additions: [ignore rules](https://github.com/elmatthe/web-novel-editor/blob/c8a52595dd1f46f5b07f15d63798cc09e76c1145/.gitignore), [version verifier](https://github.com/elmatthe/web-novel-editor/blob/c8a52595dd1f46f5b07f15d63798cc09e76c1145/scripts/verify.py), [legacy bootstrap plan](https://github.com/elmatthe/web-novel-editor/blob/c8a52595dd1f46f5b07f15d63798cc09e76c1145/md-instructions/plan-2c-installer-bootstrap.md), [scaffold tests](https://github.com/elmatthe/web-novel-editor/blob/c8a52595dd1f46f5b07f15d63798cc09e76c1145/files/tests/test_scaffold.py), and [legacy secrets storage](https://github.com/elmatthe/web-novel-editor/blob/c8a52595dd1f46f5b07f15d63798cc09e76c1145/scripts/Universal/ai/secrets.py).

## 3. Locked product requirements

| Area | Required result |
|---|---|
| Editing | One conservative universal engine for every novel; existing working corrections retained. Ambiguous prose stays unchanged. |
| AI removal | No cloud/local model editing, providers, model pickers, API-key controls, prompts, AI quotas, or AI-specific runtime dependencies. No model service needs to be installed or running. |
| Profiles | Only protected terms, canonical spellings, and approved narrow name/term corrections. Add a novel through data without changing GUI code. |
| Inputs | PDF and TXT; files and folders in one ordered queue; optional recursive import; natural chapter ordering on import; remove/reorder selections. |
| Outputs | PDF only, TXT only, or both; original chapter stem retained where filesystem-safe; applicable relative folder structure retained; source files never modified. |
| Default destination | Actual user Downloads known folder, then `PDF-Editor-Outputs/`, then a distinct numbered batch folder. |
| Custom destination | Preferences & Data chooses the replacement output root. Numbered batch folders live directly beneath that selected root. Label this clearly; do not append a second unexpected `PDF-Editor-Outputs` directory. |
| Batch operation | Sequential; Start, safe-boundary Pause, Continue, Stop/cancel, Resume incomplete run, Retry Failed where useful. |
| Resume | Original run directory and frozen options; validate source identity and completed selected outputs before skipping. Never silently create a different run folder. |
| GUI | Compact Tkinter/ttk; persistent manual Light/Dark; four numbered control groups left; large horizontally resizable Activity pane right; Summary/Detailed tabs; bottom status bar; native dialogs and shortcuts. No navigation sidebar. |
| Logging | Structured events and bounded display; session files; retention; optional edit audit; Clear Log clears display only; Open Log Folder. No full chapter text in ordinary diagnostics. |
| Setup | Healthy `.venv` fast path; compatible Python discovery; guided missing-Python setup; repair/recreate broken project `.venv`; exact dependency pins; Tk/import checks; visible recovery errors. |
| Offline contract | Normal launch and editing need no internet. First setup or dependency repair may need downloads unless suitable local installers/wheels/cache exist. Never describe dependency provisioning as guaranteed offline installation. |

Defaults proposed for Gate 00: Light appearance, Universal novel selection, PDF output enabled and TXT disabled to preserve the present default workflow, recursion enabled to match current folder scanning, audit/debug text disabled. Persist user choices after validation. These defaults do not narrow any required output combination.

## 4. Current and target organization

### 4.1 Target tree

```text
repository/
    Setup_and_Run-Web-Novel-Editor.bat
    Setup_and_Run-Web-Novel-Editor.command
    config.toml
    scripts/
        core/
        gui/
        pdf/
        pipelines/
        profiles/
        resources/
        rules/
        utils/
        main.py
        bootstrap.py
        launcher.py
        requirements.txt
        verify.py
    files/
        tests/
        test-files/
        plans/
        checkpoints/
        runtime-data/
        temp/
    md-instructions/
        HANDOFF.md
        BRIEFING.md
        CHANGELOG.md
        DECISIONS.md
        ...existing development references...
    .venv/
```

`files/runtime-data/`, `files/temp/`, and baseline/QA logs are ignored writable state created on demand in the repository workflow, never editing-reference assets. They need not exist in a fresh distribution: bootstrap creates required writable directories and reports an unwritable checkout clearly. No production import or editing resource lookup may depend on pre-existing `files/` content. Preserve the existing per-user application-data location for settings. Run manifests belong to output run folders; completed output stays outside `files/` by default. This supersedes the older bootstrap drop’s conflicting blanket storage direction; it does not move existing settings or secrets.

All production editing data must live under `scripts/`: term indexes under `resources/novel-index/`, profile declarations/corrections under `profiles/`, and universal data-only definitions under `rules/` or `resources/` with one explicit owner. Keep root `config.toml` for project/version/bootstrap/default preferences metadata; do not put editing-reference data there or write user preferences into it.

### 4.2 Migration and removal inventory

Paths below are verified source paths; targets are design instructions. Phase 00 must reconcile local additions before applying them.

| Current source | Target/action | Required safeguard |
|---|---|---|
| `scripts/Universal/main.py` | `scripts/main.py` | Preserve `--check` as a headless startup/import check; update launchers/tests. |
| `core/batch_runner.py` beneath Universal | `scripts/core/batch_runner.py` | Keep sequential loop and per-file isolation; remove AI seam and metadata; add outputs/checkpoints in Phase 02. |
| `core/run_manifest.py` | `scripts/core/run_manifest.py` | Retain atomic writer/resume seam; remove quota/provider fields; version new schema and strengthen validation. |
| `core/input_scanner.py` | `scripts/core/input_scanner.py` | Extend existing natural-order scanner for mixed inputs and recursion control. |
| `core/novel_registry.py` | `scripts/core/novel_registry.py` | Discover profile/index data and route every novel to one pipeline. Preserve display aliases and Universal behavior. |
| `core/protected_lexicon.py` | `scripts/core/protected_lexicon.py` | Preserve mask/unmask, longest phrase handling, and existing term contents; test new path root. |
| `core/replacement_log.py`, `core/edit_details.py` | Same filenames under `scripts/core/` | Keep useful JSONL audit and bundled reference loading; remove AI-only payload branches after caller analysis. |
| `gui/app.py` | `scripts/gui/app.py` | First remove AI controls without editorial changes; then adapt compact layout. |
| `gui/ai_settings.py`, `gui/cloud_ui.py` | Remove | Extract any general settings/resume presentation first; no provider-shaped replacement API. |
| `pdf/extractor.py`, `pdf/builder.py` and package initializers | `scripts/pdf/` | Keep extraction tolerances and renderer behavior; add publication wrapper around existing builder. |
| Five `pipelines/*.py` implementations | One `scripts/pipelines/universal.py` | Reuse existing stages and signatures. Temporary thin compatibility wrappers may ease Phase 01, but final runtime uses one orchestrator. |
| Five profile packages with `canonical_names.py` / `special_fixes.py` | `scripts/profiles/` data and small shared loader | Consolidate canonical protection into indexes and literal approved corrections into TOML. Keep one authoritative definition per rule. |
| `resources/novel-index/*.txt` | `scripts/resources/novel-index/*.txt` | Preserve all eight indexes, comments, and unresolved candidates; do not activate commented terms silently. |
| `resources/Novel-Edits-Details/{UNIVERSAL,Shadow-Slave,Supreme-Magus,The-Noble-Queen}.md` | Same relative location beneath `scripts/resources/` | Bundle if still displayed; explain that these describe executable definitions rather than independently overriding them. |
| `resources/Novel-Edits-Details/UNIVERSAL-AI.md` | Remove from runtime | Preserve any needed history through Git; do not convert its prose into automated rules. |
| Ten `rules/*.py` modules | `scripts/rules/` | Move intact first: `chapter_titles`, `em_dash`, `grammar`, `junk_strip`, `ligature_cleanup`, `ocr_repair`, `punctuation`, `slash_replace`, `spacing_cleanup`, `unicode_cleanup`. |
| `utils/file_utils.py` | `scripts/utils/file_utils.py` | Retain Downloads known-folder handling and filename sanitation; generalize output extensions/allocation safely. |
| `ai/settings.py` shared functions | Small `scripts/utils/settings.py` / atomic-I/O helper | Reuse per-user paths and tempfile/fsync/replace writing; no AI dependency remains. |
| `ai/redaction.py`, `ai/provenance.py` | Retain only caller-required generic functionality under `utils/` | Do not transplant model-attempt machinery. A hash can use `hashlib` directly. Keep bounded diagnostic sanitization where still needed. |
| `scripts/Universal/ai/` | Remove all 23 tracked Python files after shared-utility extraction | Inventory below; verify imports, installed dependencies, tests, launchers, and configs independently. |
| `scripts/{Windows,MacOS}/.gitkeep` | Remove directories | These are placeholders at the inspected commit. Preserve root platform launchers. |
| `scripts/requirements.txt` | Keep at current path; remove AI pins | Preserve PDF/order/TOML/test requirements initially; avoid unrelated upgrades. |
| `scripts/verify.py`, `files/tests/conftest.py` | Update root resolution and required checks | Test imports resolve from `scripts/`; retain version/dependency gates. |
| Both root launchers | Keep exact names; adapt to bootstrap/launcher | Preserve `.bat` CRLF, `.command` LF and executable bit; handle spaces/Unicode in paths. |
| `config.toml`, current README/orientation sections | Remove active AI configuration/instructions; update paths and scope | Keep append-only historical entries and explain supersession in a new decision. |

AI package inventory: `__init__`, `approved_models`, `chunking`, `cloud`, `config`, `disclosure`, `editor`, `errors`, `factory`, `models`, `prompt`, `provenance`, `provider`, `rate_limits`, `redaction`, `secrets`, `settings`, `spend_guard`, `validation`, and `providers/{__init__,gemini,groq,ollama}`. Generic pieces are extracted, not the provider architecture.

Remove direct pins `ollama==0.6.2`, `google-genai==2.14.0`, and `groq==1.6.0`. Retain current non-AI pins initially: `pdfplumber==0.11.10`, `reportlab==5.0.0`, `natsort==8.4.0`, `tomli==2.4.1`, and `pytest==9.1.1`. These are observed pins, not a claim about current latest versions or verified installability on HOME-PC. Python 3.10 is the current declared minimum; do not inherit PDF-Splitter’s narrower Python range accidentally. Phase 00 confirms the supported range against actual installs and official dependency metadata. Explicitly decide whether to retain 3.10 with the existing pinned `tomli` fallback in runtime and scaffold tests, or raise the minimum with user approval. `test_scaffold` currently imports `tomllib` unconditionally; do not claim 3.10 support while leaving that test broken. Bootstrap detection, config, README, tests and version loading must agree with the chosen range.

AI-only deletion candidates: `test_ai_editor.py`, `test_ai_foundation.py`, `test_ai_gui_controls.py`, `test_ai_validation.py`, `test_cloud_gui.py`, `test_cloud_keys_and_consent.py`, `test_gemini_provider.py`, `test_groq_provider.py`, `test_ollama_provider.py`, `test_rate_limiting.py`, `test_spend_guard.py`, and `test_dual_mode_provenance.py`. **Candidate classification is not blanket deletion permission:** extract any general atomic-I/O, privacy, script-only, checkpoint, or shutdown tests from them. Mixed tests including `test_app`, `test_batch`, `test_plan2a_phase5`, `test_run_manifest`, `test_pause_and_condensed_log`, and launcher/scaffold tests need case-level review. The expected test count will shrink; count reduction alone is neither failure nor proof of safety. Maintain a compact ledger of every removed or extracted test node ID (module/class/function plus parameter IDs where applicable), old responsibility, disposition/reason, and replacement node IDs. Never delete an entire mixed module on its filename alone. When extracting per-user path tests, parameterize platform contracts with `PureWindowsPath` and `PurePosixPath` or equivalent path-component assertions; host-native string separators must not decide whether a Windows path contract passes on POSIX.

### 4.3 One engine without losing profile behavior

Preserve the existing three-block sequence: pre-mask extraction/Unicode/paragraph cleanup; masked letter-changing corrections and first spaced-dash pass; unmask followed by chapter titles, conservative punctuation/grammar, final dash sweep, duplicate-heading handling and page breaks. Preserve the two pipeline calls to the existing dash function and its internal repeated/fallback substitutions.

Use a small profile record: display name/aliases, index path, canonical replacement data. No plugin discovery framework, executable user expressions, or separate novel grammars. Deterministic data loading needs a stable tie-breaker for equal-length terms/replacements; ensure it does not change outputs relative to the baseline.

**Resolve one real legacy conflict at Gate 00.** Shadow Slave’s existing special-fixes map contains generic corrections such as `carcassess`, `threestoried`, and `tompost shelf` alongside name-like corrections. New profiles may not retain novel-specific grammar/typo engines. Classify each existing entry as a name/term correction, universally safe literal correction, or unsafe/ambiguous legacy behavior. Keep the existing behavior during initial moves. Before final consolidation, obtain approval for any generic correction’s promotion to the universal engine or removal; promotion changes other novels’ output and requires explicit delta fixtures. Do not silently broaden its scope to satisfy the target tree. If an entry cannot be classified safely, Gate 01 remains blocked for that item rather than inventing a new profile exception mechanism.

## 5. Reference sources and exact reuse boundaries

Reference commits were resolved during inspection. Pin adaptation notes to these versions so later reference changes do not become accidental scope changes.

| Repository | Inspected ref | Role |
|---|---|---|
| Audiobook Creation Tool | `master` at `62b0c09543fc5e2a8e6eca18262816e244ca1006` | Visual authority and proven compact appearance/preferences/import-list patterns. |
| PDF-Splitter | `main` at `edcbd4fe6db96bb7515e719172fbd4172fe3ef19` | Smaller Activity/launcher/bootstrap patterns; position-aware page-number safety evidence. |
| Web Novel Scraper | `main` at `f6a5dd0fb5048dd142990312d9ae1b693144c004` | Activity projection/pump and run-summary patterns. |

### 5.1 GUI, logging, and preferences mapping

| Source at pinned commit | Adapt here | Do not import |
|---|---|---|
| ACT [`shared/appearance.py`](https://github.com/elmatthe/audiobook-creation-tool/blob/62b0c09543fc5e2a8e6eca18262816e244ca1006/scripts/Universal/shared/appearance.py) | Compact Light/Dark palettes, named ttk styles, live repaint of raw Tk widgets and app dialogs, remembered manual choice | ACT’s entire style catalogue or outer launcher shell. `shared/ui_theme.py` is largely the legacy shell; it is not the primary compact appearance authority. |
| ACT [`tts/epub2tts_gui.py`](https://github.com/elmatthe/audiobook-creation-tool/blob/62b0c09543fc5e2a8e6eca18262816e244ca1006/scripts/Universal/tts/epub2tts_gui.py) and [`shared/job_ui.py`](https://github.com/elmatthe/audiobook-creation-tool/blob/62b0c09543fc5e2a8e6eca18262816e244ca1006/scripts/Universal/shared/job_ui.py) | Queue controls, list shortcuts, compact sections, Summary/Detailed presentation, main-thread pump behavior | Voice engines, audio options, worker pools, controller hierarchy, duplicate-occurrence features not needed by this editor. |
| ACT [`shared/preferences_ui.py`](https://github.com/elmatthe/audiobook-creation-tool/blob/62b0c09543fc5e2a8e6eca18262816e244ca1006/scripts/Universal/shared/preferences_ui.py) / [`shared/settings.py`](https://github.com/elmatthe/audiobook-creation-tool/blob/62b0c09543fc5e2a8e6eca18262816e244ca1006/scripts/Universal/shared/settings.py) | Default/custom output selection, user settings persistence, reset semantics, themed modal dialog | Downloaded models/assets cleanup and separate cleanup-helper processes. This product has no such data to manage. |
| PDF-Splitter [`activity.py`](https://github.com/elmatthe/PDF-Splitter/blob/edcbd4fe6db96bb7515e719172fbd4172fe3ef19/scripts/pdf_splitter/activity.py) | Preferred small basis for structured events, bounded channel/model, `ActivityPump`, session log, display-only clear | PDF analysis job types, OCR controllers, or payload graphs. |
| Scraper [`ui/activity.py`](https://github.com/elmatthe/web-novel-scraper/blob/f6a5dd0fb5048dd142990312d9ae1b693144c004/scripts/webnovel_scraper/ui/activity.py) / [`ui/run_activity.py`](https://github.com/elmatthe/web-novel-scraper/blob/f6a5dd0fb5048dd142990312d9ae1b693144c004/scripts/webnovel_scraper/ui/run_activity.py) | Cross-check warning retention, bounded pumping, concise file/run events | Scraper rescue/network/retry orchestration. |
| ACT [`shared/logging_setup.py`](https://github.com/elmatthe/audiobook-creation-tool/blob/62b0c09543fc5e2a8e6eca18262816e244ca1006/scripts/Universal/shared/logging_setup.py) | Session naming and retention policy | Audio/native-crash machinery unless a demonstrated need exists. |

All four requested ACT screenshots were visually inspected: [TTS Dark](https://github.com/elmatthe/audiobook-creation-tool/blob/62b0c09543fc5e2a8e6eca18262816e244ca1006/files/UI-Tool-Screenshots/TTS-Audiobook-UI-%28DARK%29.png), [TTS Light](https://github.com/elmatthe/audiobook-creation-tool/blob/62b0c09543fc5e2a8e6eca18262816e244ca1006/files/UI-Tool-Screenshots/TTS-Audiobook-UI-%28LIGHT%29.png), [Preferences Dark](https://github.com/elmatthe/audiobook-creation-tool/blob/62b0c09543fc5e2a8e6eca18262816e244ca1006/files/UI-Tool-Screenshots/Preferences-and-Data-UI-%28DARK%29.png), [Preferences Light](https://github.com/elmatthe/audiobook-creation-tool/blob/62b0c09543fc5e2a8e6eca18262816e244ca1006/files/UI-Tool-Screenshots/Preferences-and-Data-UI-%28LIGHT%29.png). Copy their compact content-area vocabulary, spacing, controls, and log arrangement. The ACT screenshot has three TTS-specific groups and a tool sidebar; this editor deliberately uses four groups and no sidebar, per the user’s explicit contract. Do not copy ACT’s overwrite-existing checkbox.

### 5.2 Bootstrap mapping

Use PDF-Splitter’s [`scripts/Setup-and-Run/bootstrap.py`](https://github.com/elmatthe/PDF-Splitter/blob/edcbd4fe6db96bb7515e719172fbd4172fe3ef19/scripts/Setup-and-Run/bootstrap.py) as the smaller initial reference: `fast_health_check`, external base-Python discovery, health probes, `running_from_project_venv`, repair guard, requirements fingerprint, bounded subprocesses, and setup/launch log separation. Adapt its [`scripts/launcher.py`](https://github.com/elmatthe/PDF-Splitter/blob/edcbd4fe6db96bb7515e719172fbd4172fe3ef19/scripts/launcher.py) for lazy GUI imports, headless help/version, and startup error reporting.

ACT’s [`shared/bootstrap.py`](https://github.com/elmatthe/audiobook-creation-tool/blob/62b0c09543fc5e2a8e6eca18262816e244ca1006/scripts/Universal/shared/bootstrap.py) and [`launcher.py`](https://github.com/elmatthe/audiobook-creation-tool/blob/62b0c09543fc5e2a8e6eca18262816e244ca1006/scripts/Universal/launcher.py) provide additional health/launch patterns, not a requirement to copy their large audio dependency system.

Python cannot acquire itself when no Python exists. Keep the small host-native acquisition boundary in the existing root `.bat`/`.command`; study PDF-Splitter’s [`bootstrap_host.ps1`](https://github.com/elmatthe/PDF-Splitter/blob/edcbd4fe6db96bb7515e719172fbd4172fe3ef19/scripts/Setup-and-Run/bootstrap_host.ps1) and [`bootstrap_host_macos.sh`](https://github.com/elmatthe/PDF-Splitter/blob/edcbd4fe6db96bb7515e719172fbd4172fe3ef19/scripts/Setup-and-Run/bootstrap_host_macos.sh). Its specific Python 3.12 range, installer version/hash, Tk package names, and PDF imports are reference-product settings, not this product’s defaults. Reverify any installer details against official sources at implementation time. Prefer existing installed Python and guided official installation over adding a new platform-script directory.

### 5.3 PDF editing and page-number reference mapping

PDF-Splitter’s [`classification.py::detect_running_artifacts`](https://github.com/elmatthe/PDF-Splitter/blob/edcbd4fe6db96bb7515e719172fbd4172fe3ef19/scripts/pdf_splitter/classification.py) uses selectable lines, page geometry, repeated positions, page-tracking numbers, and unresolved candidates. [`cleaning.py`](https://github.com/elmatthe/PDF-Splitter/blob/edcbd4fe6db96bb7515e719172fbd4172fe3ef19/scripts/pdf_splitter/cleaning.py) consumes accepted artifact decisions. [`test_page_number_correction.py`](https://github.com/elmatthe/PDF-Splitter/blob/edcbd4fe6db96bb7515e719172fbd4172fe3ef19/files/tests/test_page_number_correction.py) explicitly protects chapter labels, narrative references, list items, headings, and body numbers.

Adapt that evidence standard and negative-test corpus shape. Do not import its analysis model, OCR worker/IPC system, cleaned-document graph, or whole classification engine. Keep pdfplumber initially. Any enabled page-number enhancement requires the small positional extraction seam and approval described in §8.4.

## 6. Input/output, run-state, and logging contracts

### 6.1 Queue and text ingestion

Extend the existing list/scanner instead of introducing a new queue framework. Each item needs only stable identity, absolute source path, input kind, import root/relative path, and reserved output paths. Deduplicate repeated additions of the same resolved source path by default; do not deduplicate distinct files merely because their content hashes match.

Add Files accepts `.pdf` and `.txt` case-insensitively. Add Folder appends an expanded snapshot to the same visible queue. Preserve the existing depth-first rule: a directory’s own eligible files in natural order, followed by naturally ordered subdirectories when recursion is enabled. Sort a newly imported group naturally; never resort previously queued items or undo manual reordering. Provide Move Up/Down, Remove, and Clear All. Retain multi-selection order and focus.

Skip directory symlinks/junction traversal by default to prevent cycles; expose unreadable-directory warnings. Reject output destinations overlapping source files and avoid importing the active output tree. Freeze the queue, profile, rules, and options when Start is accepted; worker code receives ordinary immutable values, never Tk variables.

TXT starts with strict UTF-8/UTF-8 BOM handling and newline normalization. Do not use lossy `errors="ignore"` or silently guess an encoding. Unsupported encodings get a useful per-file failure. Do not apply PDF’s `<100 characters` confidence heuristic blindly to a legitimate short TXT chapter. Empty text is flagged/skipped; PDF image-only/low-confidence handling stays intact. TXT retains explicit blank paragraphs; any input-kind adapter around PDF-only reconstruction must be fixture-backed and must not create a novel-specific engine.

### 6.2 Destination allocation and selected formats

Resolve Downloads with the existing Windows known-folder implementation. Fresh runs reserve `<output-root>/<novel-slug>-N/` using exclusive directory creation and retry on collision; merely computing the next number is insufficient when two launches race. Custom roots replace the default output root. Never overwrite an existing completed run.

Preserve a directly added file’s stem at the run root; folder imports preserve the selected folder name and descendant paths. Disambiguate duplicate folder roots and stem collisions deterministically during preflight and display the mapping. Compare every reserved relative path component after Unicode NFC normalization and casefolding, even on a case-sensitive development volume; preserve the displayed spelling when unique. Cover `Chapter 1.pdf` versus `chapter 1.PDF`, composed/decomposed Unicode, sanitized stems, duplicate roots and companion files. Validate actual absolute final and temporary paths, including suffixes, before work: Windows defaults to a conservative 240 UTF-16-code-unit full-path budget unless long-path support is explicitly proven, and platform component limits still apply. Report an overlong path with the proposed destination and ask for a shorter root/name choice; never silently truncate chapter names or rely on enabling system policy. A `Chapter 1.pdf` and `Chapter 1.txt` input cannot both reserve the same output pair. Use a numeric suffix for the second logical item and store it once. Reject paths escaping the run root, including through symlink resolution. Reuse filename sanitation and report necessary changes.

Validate at least one selected format before allocating a run. Render PDF and write TXT from the **same** corrected text. TXT uses UTF-8, normalized newlines and blank chapter/paragraph separators; replace internal PDF form-feed separators with readable chapter spacing. Do not reuse the old `DEBUG_*.txt` naming as the real TXT product. No PDF file is created or scanned when PDF output is disabled. Phase 01 retains exact internal text; Phase 02’s TXT serialization is a documented output-format change.

### 6.3 Atomic publication and persistent resume

Keep `RunCheckpoint` and file-boundary coordination. Introduce a new manifest schema with a small explicit migration policy rather than extending AI-shaped fields indefinitely. Acquire a run-writer lock before starting/resuming or mutating the manifest; a second instance cannot write that destination. This is a single-writer safeguard, not parallel processing or a new queue system.

Use a small stdlib helper: exclusively create the lock metadata (`O_CREAT | O_EXCL`) containing schema, run ID, random owner token, PID, host identity, process creation identity and acquisition UTC time. PID alone is not identity. On Windows query PID liveness and process creation time through the OS (stdlib `ctypes` is sufficient); PID reuse cannot prove ownership. Use the analogous available process identity on macOS, or return unknown. Access denied, malformed metadata, foreign-host ownership and unverifiable identity fail closed; elapsed age alone never proves staleness.

Serialize acquire/recovery/release with one small OS-backed guard held for the writer lifetime (`msvcrt` on Windows / `fcntl` on macOS, or an equally small proven existing helper). It prevents two contenders recovering the same stale metadata; kernel ownership is released on process exit. A stale-metadata recovery requires explicit operator confirmation after proving the old owner has exited or its creation identity differs. Recheck under the guard, preserve the old metadata for diagnosis, then create the new owner record. Release only metadata matching this process’s owner token. Test live owner, reused PID, crash, unknown/foreign host, denied probe and simultaneous recovery. Do not claim distributed locking across machines or cloud-sync replicas.

Record: schema/run ID, original destination, entire ordered queue and import mapping, profile ID and effective data/rule digest, selected formats and rendering options, source SHA-256/size/mtime, reserved outputs and their hashes/sizes, per-item state/attempt outcome, run timestamps and stop reason. Compute streaming source hashes before processing and check identity again before completion; a changed source cannot be recorded as successfully processed under the old fingerprint. No chapter text or credentials belong in the manifest.

Publication order for one item:

1. Build each selected output into a same-filesystem temporary file using the existing renderer/writer. Close handles; validate PDF readability or TXT decoding/nonempty structure; compute output hashes.
2. Atomically persist a minimal prepared record containing reserved paths and expected hashes. This makes a crash between publication and completion recoverable without guessing ownership.
3. Publish individual files with atomic replacement/rename only to the run-owned reserved paths; an unrelated existing file is a collision, never overwrite permission. Close all handles first. For Windows sharing/access errors consistent with transient antivirus/OneDrive holds (WinError 5/32), retry at most four times after the first attempt, with bounded backoff totaling at most two seconds. Revalidate ownership/containment before each attempt. Do not retry arbitrary permission, disk-full or path failures as if they were transient; exhaustion produces an accurate retryable item failure and keeps prepared state. Apply the same bounded discipline to atomic manifest publication. Tests inject transient success, exhaustion and permanent errors without real sleeps. Requested audit/debug companions are required when enabled: their failure leaves the item incomplete and retryable. Ordinary session-log failure is nonfatal and produces a visible warning.
4. Mark the item completed atomically only after all required selected outputs are present and match their hashes. Only then increment success and show its completion event.

Two file renames are not a filesystem-wide atomic transaction. The prepared/completed distinction supplies the logical boundary: a partial PDF+TXT pair is never declared completed. Recovery validates the prepared outputs and either finishes publication/reprocessing into its own reserved paths or reports a conflict. Do not manufacture suffixed duplicates on resume. Modified external files or uncertain ownership are preserved and reported. A checkpoint-write failure pauses/stops safely with a visible error; do not continue thousands of files while falsely promising resumability.

At Resume, validate schema, queue, destination containment, effective rules/profile/options, source hashes, and completed selected output hashes before skipping. Size/mtime are useful hints, not sufficient identity. Carry previous entries forward across repeated resumes; never replace the original full queue/history with only the remaining slice. A queue index may remain a progress hint, not the sole authority for skipped work.

Preference changes affect new runs only. Resume always uses the original destination; provide explicit run-folder selection in addition to discovering recent incomplete runs, so changing the output preference does not strand older runs. Never silently resume into a different existing directory or allocate a new one when a manifest is corrupt. Report why resume was refused and offer a separate explicit fresh run.

Legacy schema-1 cloud manifests have no equivalent deterministic fingerprint/output guarantees and may contain AI-edited completed outputs. Preserve them read-only and refuse automatic conversion/resume as a homogeneous new script-only run. Explain that a new run is required; leave historical outputs untouched.

Pause is requested immediately but acknowledged after the current file publishes/checkpoints. Continue resumes that same run. Stop while paused must release the wait and start no new file. Window close during a run offers safe-boundary stop/exit; it must not destroy Tk while the worker still needs GUI callbacks. Unexpected process termination is recovered through the manifest.

Retry Failed selects failed eligible items from the original run, retains its options/destination/mapping, and preserves completed items. Missing sources or unsupported/encrypted PDFs receive actionable outcomes rather than an infinite retry. A drained queue with failures is reported as finished with errors; an explicit Retry Failed remains available. Track terminal results per item so attempts do not inflate completed totals.

### 6.4 Activity and audit boundaries

Use a small event record with severity, run/item identity, stage, message, and Summary inclusion. The existing string callback can be bridged during migration. Worker threads emit to a channel; only the Tk thread schedules/drains and updates widgets. Bound display history and per-tick work; coalesce progress, preserve warnings/errors and terminal outcomes, and expose any dropped routine-detail count.

Summary shows run start/destination, one result per file, pauses/stops, warnings/failures, and final counts. Detailed adds stage timings, rule/category counts, recovery diagnostics, and setup errors where appropriate. Session files receive useful diagnostic events independently of Clear Log. Adapt ACT-style retention, initially the latest 20 closed session logs; prune only application-owned matching logs, never active logs, run folders, audits, sources, or user files. Gate 00 may adjust the retention number without changing editing behavior.

Keep optional JSONL replacements separate from ordinary session diagnostics. Default diagnostics contain IDs, counts, hashes, durations, and bounded errors without chapter bodies. Audit may contain short before/after snippets by explicit opt-in; debug full text is separately opt-in and clearly named. Neither should be enabled implicitly by Detailed view. Reset Preferences removes saved preferences only; it does not delete `.venv`, outputs, profiles, manifests, credentials, or chapter files. Ignore obsolete AI preferences; do not read or delete legacy secret stores or edit system environment variables.

### 6.5 Credentials and executable offline evidence

Old keys may remain in `%LOCALAPPDATA%/WebNovelEditor/secrets.json`, alongside `settings.json`; on macOS the existing application-support equivalent applies. They may also exist in a repo-root `.env` or process/user/system `GEMINI_API_KEY` / `GROQ_API_KEY` variables. After AI removal the application must not load, migrate, display, remove or use them. Reset Preferences deletes/recreates only its exact `settings.json`, never the parent directory. A sandbox test with sentinel settings, secrets, logs and unrelated siblings must prove that only settings change.

Keep the existing **Credentials (Plan 2b)** `.gitignore` block (including `.env`, `.env.*`, `secrets.json`, `*.key`, `*.pem`); its historical label is not a reason to delete protections. Release migration notes identify the old locations and tell users how to manually remove old keys and revoke them with each provider. Revocation/removal is a user action, not a migration side effect. Never inspect or print real key values as part of discovery.

Phase 00 runs applicable baseline tests through a development-only, stdlib offline harness, without editing the engine/conftest. Clear key variables in the child-process environment only, not the user’s saved environment. Phase 01 adds an autouse network-denial fixture in `files/tests/conftest.py` for normal app, batch, and healthy-launch tests: block `socket.socket.connect`, `connect_ex` and `socket.create_connection`, and outbound datagram paths if reachable. Record attempted calls and fail teardown even if production code catches the exception. Retain fake providers only until their tests are classified; no live provider test is needed.

The guard must reach Python subprocess smoke tests, e.g. through a dedicated subprocess harness/temporary `sitecustomize` and inherited environment. Test the guard itself with a harmless attempted connection; do not assume an in-process monkeypatch protects a new interpreter. Provisioning/download tests have an explicit separate scope and mocked installers; runtime tests cannot opt out just to pass. A socket monkeypatch is Python-level evidence, not an OS firewall: also inspect remaining network callers/subprocesses, test a fresh non-AI dependency environment, and perform a real healthy launch/edit while network access is disabled. No OAuth or provider account is required.

## 7. GUI and bootstrap implementation contract

### 7.1 Four groups and one Activity pane

| Left group | Controls |
|---|---|
| **1. Sources** | Unified PDF/TXT list and count; Add Files, Add Folder, Move Up, Move Down, Remove, Clear All; Include subfolders. |
| **2. Novel & Editing** | Data-discovered novel selector with Universal default; protected-term count/status; concise description of universal conservative editing. No provider/model/grammar-mode panel. |
| **3. Output** | Independently selectable PDF/TXT; effective output root; Open Output Folder; optional audit/debug and existing useful dry-run control. Destination changes go through Preferences & Data. |
| **4. Run** | Start, Pause/Continue, Stop, Resume incomplete run, Retry Failed; progress, completed/failed/skipped counts and measured elapsed time. Show ETA only when supported by measurements. |

Use a horizontal `ttk.Panedwindow` or the smallest equivalent existing layout; the Activity pane receives most extra width/height. Source list and Activity scroll locally; compact controls must not force a huge minimum window. Native file dialogs retain OS appearance. Bottom status includes persistent Light/Dark toggle, Preferences & Data, and Open Log Folder. Theme changes preserve queue selection, scroll positions, text, progress, and open dialog state.

Preferences & Data needs default/custom output selection, browse/save feedback, log location/retention information, and reset preferences. Do not add downloaded-data cleanup, model management, or unrelated maintenance pages. Keep familiar Ctrl/Cmd+A selection, Delete/Backspace removal, Alt+Up/Down movement, and native open/copy behavior without intercepting text-entry shortcuts globally.

### 7.2 Bootstrap ownership and recovery

Root launcher: locate its own repository directory; use a healthy existing `.venv` without requiring a new base-Python search or internet; otherwise locate/acquire a compatible external Python and invoke `scripts/bootstrap.py`. Do not rely on Microsoft Store Python aliases. The host-native launcher is responsible for a clear guided path when Python does not exist. Avoid hidden system-wide installs or automatic Homebrew installation.

`bootstrap.py`: stdlib-only startup as far as practical, bounded probes, requirements fingerprint, exact pins, Tk/Tcl and critical imports (`pdfplumber`, `reportlab`, `natsort`, TOML reader as needed), setup logs, and safe repair. Never delete/recreate `.venv` while executing inside it. Relaunch repair through a validated external base interpreter first; if unavailable, stop with a clear instruction. Prove the deletion target is the project `.venv`, not a symlink/junction to unrelated data. Handle locked files and failed installs honestly. Mark health state only after install, `pip check`, critical imports, and headless entry smoke succeed.

`launcher.py`: headless `--help`/`--version`, delegated `--check`, lazy GUI start, visible nonzero startup errors and setup-log link. `--version` reads `config.toml` through the agreed TOML path rather than a duplicate version constant; extend verify/scaffold coverage to require agreement. Preserve pre-environment bootstrap’s stdlib-only boundary when choosing how metadata is read. `main.py` remains the application entry compatibility boundary. Define one launch chain without recursive bootstrap/launcher calls. Normal healthy launch must never run `pip install --upgrade pip`, query package indexes, probe AI services, or request network access.

Automated GUI tests patch `tkinter.filedialog` responses rather than requiring an agent to drive native dialogs. Windows Gate 02 must actually execute the meaningful Tk tests with a usable display, not skip them; opening temporary test windows is expected. Keep the human check for the real native dialog and theme/keyboard behavior.

The missing-Python path needs explicit evidence: unit/subprocess tests control interpreter discovery, `where`/`py` results and a stripped PATH, and simulate a Microsoft Store alias without executing it. Those are simulations even on a machine with Python installed; they cannot prove a truly empty machine. Use Windows Sandbox/VM without Python for genuine end-to-end acquisition evidence if claiming that path was tested; record a pending limitation otherwise. A healthy `.venv` must still work with base-Python discovery unavailable. Never uninstall the user’s Python, change global PATH, or disable Store aliases as a test.

Do not rebuild a healthy environment solely to purge dormant AI packages. Remove them from declared requirements and prove clean fresh setup excludes them. If the existing environment remains healthy, unused installed distributions need not be destructively uninstalled. Missing packages may be repaired in place; broken interpreter/environment may be recreated, strictly within `.venv`.

## 8. Editing-rule controls and approved changes

### 8.1 Baseline and rule authority

Existing Python implementations remain authoritative for complex universal logic. Move simple literal data into TOML/plain text only where it reduces duplication. No generic regex DSL, arbitrary hooks, profile-specific punctuation switches, NLP/model service, or comprehensive parser. Give each added/reclassified rule a stable ID and one short comment/record documenting scope, evidence, exclusions, and expected fixtures. Reuse the existing audit rather than creating a parallel editorial reporting system.

Migration fixtures retain exact pre-change Unicode text, blank lines, heading text, and form feeds. Do not normalize quotes or whitespace when comparing editorial baselines. PDF bytes may vary because of metadata; validate extracted content, layout/page structure, and render samples in addition to exact internal text. Baseline output hashes still prove historical artifacts stayed untouched.

Existing heuristics are not newly certified as universally infallible. If a negative control exposes a legacy bug, record it; changing it requires a named approved delta. Do not silently weaken or strengthen every old OCR/grammar rule while moving files.

### 8.2 Protected names: mandatory safety floor

**`Clan Valor` → `Valor` is prohibited.** Protection/canonicalization must preserve `Clan Valor`, `Valor Clan`, and `Valor` exactly. Do not delete, reorder, shorten, or rewrite neighboring prose to match a canonical label. No fuzzy matching, aliases that consume surrounding words, unrestricted substring replacement, or capitalization-by-context guessing.

Use escaped literals with explicit token/phrase boundaries and deterministic longest-match ordering for approved corrections. Preserve possessives and punctuation. Validate replacement maps for conflicting keys, cascades/cycles, malformed data, and keys masked by protection before they can be corrected. Phase 00 records the existing stage behavior; Phase 03 introduces only the smallest safe canonical-correction seam, tested against masked and unmasked cases. Do not solve a typo/protection conflict by unmasking all names during OCR.

Mandatory unchanged examples include sentences containing:

- `Clan Valor`, `Valor Clan`, `Valor`, and their adjacent adjectives, ranks, articles, punctuation, and possessives.
- `Grey Wolf Tribe`.
- Both distinct words `ember` and `amber`; valid name `Ember Queen`.
- `the God of Peace` and `Demon of Desire`.
- `War God` with female pronouns, and `War God, the Goddess of Life`.

These are protection/reference rulings, not a pronoun-rewriting feature or permission to replace all alternate wording. Misspellings of Valor or any other term require exact evidence and approved mappings; none are invented by this plan. An isolated name-normalization test must prove all characters outside the approved replacement span are unchanged. Add positive, negative, possessive, neighboring-word, overlapping-term, Unicode-boundary, and placeholder-restoration fixtures. No `Clan` deletion is permitted anywhere in a fixture’s expected output.

### 8.3 Curly quotes, dashes, and OCR

| Change | Allowed behavior | Required negative controls |
|---|---|---|
| Curly double quotes | Preserve already correct pairs; convert clearly paired straight quotes to `“…”`; retain/flag uncertain boundaries. Update straight-quote-dependent heading/paragraph tests where necessary. | Odd quotes; multi-paragraph speech; mismatched/nested quotes; quoted names; inch marks; unmatched extracted fragments. No global alternating-open/close counter. |
| Apostrophes | Normalize mechanically identifiable contractions/possessives to `’` only where unambiguous; preserve uncertain single quotation marks. | Leading elisions, plural possessives, feet marks, transliterated names, nested single quotes. Protected spelling wins unless a specific typographic variant is explicitly approved. |
| Spaced em/en dashes | Preserve the current mandatory two-pass pipeline behavior and internal fallback sweeps. | `word—word`, `word–word`, partial spacing, NBSP/Unicode spaces, adjacent protected names, repeated spaced dashes. Do not introduce a contextual grammar parser. |
| `Asa result` | Candidate for a narrowly bounded, validated universal correction to `As a result`. | A character/person named Asa; substring inside another term; unusual capitalization; quoted literal text. No global `Asa` substitution. |
| OCR `l` / `1` for `I` | Investigate exact recurring contexts; add only proven bounded cases. | Numbered lists, chapter numbers, Roman numerals, letter names, measurements, identifier/name tokens. Never replace every standalone `l` or `1`. |
| Repeated words / grammar | Keep current validated behavior. Any new literal fix needs separate evidence. | Deliberate repetition, dialogue, tense shifts, agreement depending on meaning, common-word names. Frequency does not establish safety. |

Keep quote handling small and conservative: classify only reliably bounded local spans; do not infer missing dialogue, pair across chapters, or flatten punctuation before deciding whether it was ambiguous. For uncertain input, preserve its original quotation glyphs or preserve and flag; do not first convert everything to ASCII and then claim preservation. If safe conversion is unavailable for a case, leaving it unchanged satisfies the conservative contract. Run new quote behavior through full pipeline and PDF extraction/render fixtures because existing reconstruction/title recognition may depend on quote shapes.

### 8.4 Bounded page-number improvement

This is a separately reviewed universal extraction enhancement motivated by the PDF-Splitter reference. Keep it outside Phase 01’s output-preserving moves.

Phase 00 identifies actual recurring page-furniture examples. Phase 03 may add a small pdfplumber-based positional adapter for standalone numeric page fields only, with repeated page-edge placement, at least three corroborating pages, and a consistent relationship to page sequence. Preserve headings, body numbers, lists, dates, counters, and quoted page references. Ambiguous and short documents retain their content and receive a bounded warning where useful. TXT never uses this positional filter.

The adapter runs before page flattening and returns the existing text interface; when disabled or no candidate is accepted, extraction must match the previous path. Use existing pdfplumber line/word coordinates rather than switching PDF libraries. Repeat-pattern thresholds are conservative engineering starting points and must be ratified against fixtures at Gate 00. Broader recurring header/footer removal, Roman numerals, split footer rows, and nonstandard layouts are not implicitly authorized by PDF-Splitter’s support for them. Expand only through reviewed examples; otherwise retain/flag.

If achieving even this narrow feature requires importing a large layout-analysis subsystem, stop that feature and report it at Gate 03. The rest of the modernization can be accepted with page-number removal explicitly deferred; do not hide that limitation or replace it with digit-line deletion. Existing unsafe-looking legacy fused-number behavior is reviewed separately, never silently removed under this feature’s name.

### 8.5 Historical manual-edit evidence

The handoff describes sampled Shadow Slave chapters 3194–3226 with gaps, per-chapter category counts, and up to three short examples. Raw records and the full protected editorial reference were not supplied in this planning session. Phase 00 locates them locally or records them as unavailable; do not invent chapter coverage, numerical totals, or examples.

Keep these category keys unchanged when assessing the evidence:

```text
typo, punctuation, comma_splice_run_on, capitalization, dialogue_tag_punct,
its_its, your_youre, there_their_theyre, then_than, article, tense_slip,
subject_verb_agreement, spacing, hyphen_em_dash, repeated_word
```

Use one compact table in the Phase 00 report: category, observed evidence if available, existing rule coverage, safe candidate or manual-only conclusion, fixture. Do not build a new production category counter, chapter edit-log workflow, or running open-flags database merely to reproduce the historical human process. Missing tallies do not block the migration; they block unsupported evidence claims and candidate rules depending on them.

## 9. Five execution phases and approval gates

The five phases remain 00–04. Gate 02A is an additional mandatory stop inside Phase 02. Other approved phase slices may continue within their scope after verified checkpoint commits; no agent may infer approval for the next phase. Check each slice’s starting branch/HEAD against the last approved gate SHA or the preceding recorded verified slice SHA. Implementation requires a clean tracked/index state and no unexplained untracked work; ignored private corpora are expected. Preserve dirty user work and report it—never clean, stash, restore or commit it automatically to meet this rule.

### Phase 00 — Codex discovery, safety preparation, and baseline capture

**Allowed writes:** local ignored QA/baseline artifacts; the narrow additive `.gitignore` safety edit below; this approved master plan if not yet saved locally; one Phase 00 checkpoint; and short HANDOFF/DECISIONS/supersession notices. No application, test, dependency, product-config or launcher changes; no installs/repair or setup launchers. No branch switching/creation during discovery. Read-only fetch/ref inspection is allowed by workspace policy. Verified preparation/docs can be committed/pushed on the existing working branch under that same policy; never on `main`. This is a precise exception to the earlier all-read-only Phase 00, needed before copyrighted baselines exist.

Tasks:

1. Confirm the actual HOME-PC repository and applicable parent/repository instructions; read current orientation sections once. Record the instruction paths and local environment identity privately where required by workspace rules. Do not assume the template attachment is the live installed instruction file.
2. Record branch, HEAD, upstream, remotes, staged/unstaged/untracked work and live origin refs; fetch/prune through the normal authorized path when available. Recheck the historical SHAs; never reset to them. Resolve ancestry or state unknowns honestly. Identify the trusted script-only code/config/profile state, including local differences, before naming the baseline authority. Dirty state can be inspected but blocks implementation until the user’s work has a safe disposition.
3. **Before any baseline chapter text is written**, preserve all current ignore rules and append anchored rules for `/files/checkpoints/baselines/`, `/files/runtime-data/`, `/files/temp/`, `/files/run-temp/`, and `/files/test-logs/` where absent. Do not ignore all checkpoints. Verify representative prospective paths with `git check-ignore -v --no-index`; use `git ls-files` separately to detect already-tracked private files (ignore rules do not untrack them). Ensure reports remain trackable. If a private artifact is already tracked/staged, stop publication and report metadata only; do not silently remove it from history or stage it. Preserve the credential block verbatim.
4. Inspect the §4 import/dependency/migration inventory and mixed tests; compare the five pipelines’ stage order, special-fix timing, logging and protection. Build the named test-disposition ledger. Inspect the legacy `plan-2c-installer-bootstrap.md`; add a brief superseded notice pointing here. Append a concise DECISIONS entry locking `0.4.0`, the supersession and storage contract; do not bump current product version fields yet.
5. Probe the existing interpreter/venv/Tk/pins without modifying the environment. Run the existing complete verifier once through an offline development harness with key variables unset in child processes. Capture detailed pytest skip reasons/node IDs (reuse the same pytest run via an ignored reporting plugin/arguments where possible; do not duplicate the full suite just for counts). Record exact failures, not merely an exit code. Separate the reviewer’s 1,203/67/5 Linux report from this new HOME-PC evidence; do not dismiss a failure as platform-only without checking it. Settle Python 3.10 fallback versus a supported-range change using actual official dependency metadata. Any test/code fix waits for Phase 01.
6. Freeze exact extracted/pre-render text, inputs or stable identities, code/config/profile/rule hashes, options and representative PDFs/audits in ignored `files/checkpoints/baselines/script-only/`. Cover every supported profile and Universal, clean prose, OCR/junk, headings, quotes/dashes, protected terms and error pages. Use synthetic/minimal tracked fixtures and private ignored corpora. Confirm no chapter text entered the staged diff. Missing essential baseline evidence blocks Phase 01.
7. Select a fixed corpus for comparisons and a real workload of at least 1,000 chapters, preferably approximately 3,000. Record baseline timing, outcome counts, peak memory and source/output identities where possible. Use the durable background-run procedure under Phase 04 for long work. Missing corpus/capacity stays an explicit release blocker; a small sample cannot satisfy the large-batch gate.
8. Propose the bounded output-delta list: legacy generic-fix classification, validated quote/OCR/page-number candidates, defaults and support range. Missing manual-edit tallies block unsupported rules, not basic migration. Recheck tags locally/remotely; the audit reports only `v0.12.0` and no `v0.4.0`, but do not rely on that historical absence. Recommend retaining the current feature branch by default to minimize churn, or a new `feature/0.4.0-script-only-editor` from the **approved reconciled SHA**. Gate 00 selects; never cut blindly from `c8a5259` if trusted local work differs.
9. Write `files/checkpoints/WNE-P00-discovery.md` and concise HANDOFF state. Review explicit staged paths for private text/secrets/unrelated changes. If safe on the existing feature branch, commit/push the preparation checkpoint and report the exact resulting SHA; otherwise state why it remains local. Do not fabricate a clean/verified checkpoint if pre-existing tests fail.

**Acceptance:** ignore safety demonstrated before captures; exact Git/test/skip baseline and evidence limits recorded; editorial baseline frozen; migration/test ledger complete; `0.4.0` and legacy-plan precedence explicit; no product behavior changed. Unavailable essential evidence is a blocker, not an assumed pass.

**Gate 00 — STOP:** user approves implementation base/branch, baseline, bounded deltas (including generic fixes), defaults/Python scope, and Phase 01. Feature checkpoint commit/push is already authorized by standing policy; approval does not grant merge/tag/release. After approval only, create/switch the chosen working branch if needed and record its start SHA.

### Phase 01 — Remove AI and migrate the existing engine

Default writer: Codex Sol 6.1 / High; Claude Code may own a specifically assigned slice. One writer at a time.

**01A — Disconnect AI and retain shared behavior.** Extract generic settings/atomic I/O/sanitization/hash helpers and their non-AI tests before deleting callers. Remove provider construction, UI/key/consent/model/quota controls, AI fields/runtime prompt reference, SDK pins and genuinely AI-only code/tests. Add the network-denial fixture; keep the credential ignore rules and legacy secret files untouched. Extract cross-platform settings-path assertions and fix the agreed `tomllib`/minimum-version mismatch. Keep sequential processing and existing pause/stop seams. Verify focused batch/settings/protection/import coverage and exact frozen text; commit/push the verified slice, updating the test ledger and HANDOFF.

**01B — Move paths, then repair paths in a separate commit.** Use `git mv` to move existing `scripts/Universal/` children to their approved direct `scripts/` destinations. The move commit contains content-identical renames only: no utility edits, import fixes, formatting, deletion or checkpoint narrative inside it. Prove old/new blob identity and inspect rename status (`R100`); record the preceding passing SHA. This intermediate commit may temporarily break path-based startup; do not call it verified/runnable, do not push it alone, and do not stop there unless reporting a blocker. Immediately make a separate path/import/resource/launcher/test/doc repair commit, remove obsolete platform placeholders there, and run focused startup, different-CWD/resource and exact-baseline tests. Push the pair after the repaired tip passes; review the move and repairs separately. Git detects renames by content, so verify the diff rather than assume `git mv` alone guarantees history display.

**01C — Consolidate common orchestration and profile data.** Reuse the existing three-block stage sequence in one universal pipeline. Keep all eight term indexes and builtin-only protection; commented candidates remain inactive. Move literal approved correction data to TOML with a small shared loader and no GUI registry changes for new novels. Preserve useful JSONL and bundled descriptive references. Apply only Gate 00-approved generic-fix dispositions, with their explicit delta fixtures. Keep current docs/decision notice accurate; commit/push the verified slice.

**Focused validation:** existing rule/pipeline/profile/registry/protection/junk/batch/pause suites; migrated `--check`, launcher/resource/different-CWD coverage; import/launch in a fresh non-AI dependency environment when provisioning is authorized; frozen text comparisons; offline guard; reset/secrets invariance. Report every removed/extracted test by node ID and same-machine skips by reason.

**Acceptance:** target root works; no provider/model/runtime-AI dependency remains; one universal engine and all retained protection/data work; no unapproved editorial difference; both root launchers reach the migrated app. Fresh independent CLI reviewer checks actual deletion/rename diffs, test ledger, resource roots and a sampled baseline rerun. Product-facing AI removal does not delete development-agent instructions.

**Gate 01 — STOP:** checkpoint SHAs pushed and independently reviewed; user accepts migration and authorizes Phase 02A only.

### Phase 02 — Mixed I/O and recovery, then desktop and bootstrap

**02A — Data-path slice:** extend the existing scanner/queue for PDF/TXT/files/folders/optional recursion/manual order; strict TXT decoding; selected PDF/TXT writers from the same corrected text. Add exclusive numbered destinations, stable mapping, normalized case/Unicode collision keys, long-path preflight and source/symlink containment checks. Strengthen the in-place manifest seam with hashes, frozen options, prepared/completed publication, bounded Windows sharing-error retries, explicit writer ownership/stale-lock recovery, resume and Retry Failed. Preserve old cloud manifests read-only and refuse automatic new-engine resume.

Use a minimal adapter to the existing GUI only where needed to exercise this slice; the layout/theme/bootstrap rewrite waits. Fault-injection covers every crash window, half-published pairs, changed sources/outputs, simultaneous writers/recovery, corrupt/future schema, read-only/locked destinations, repeated resumes and failed retries. Prove exact existing PDF-only editorial results.

**Gate 02A — mandatory operator STOP:** commit/push the verified data-path slice and complete a fresh independent review of publication, locks, collision/preflight and resume. User must accept the report/SHA and explicitly authorize 02B. A single Phase 02 approval cannot silently carry through this stop. Do not start GUI/bootstrap changes while crash-safety findings remain unresolved.

**02B — Desktop/bootstrap slice:** adapt the pinned compact reference patterns: four groups, resizable Activity, persistent Light/Dark, Summary/Detailed, status bar, native shortcuts, Preferences & Data and log access/retention. Workers emit events, never call Tk. Reset only settings; diagnostics exclude chapter bodies by default. Add/adapt `scripts/bootstrap.py` / `scripts/launcher.py`; root launcher names stay fixed. Implement external-interpreter repair, bounded health checks and healthy offline fast path without unnecessary AI-package purging. No test destroys the developer’s working environment.

**Focused validation:** GUI/event/thread/history bounds; both themes/preferences; dialog functions patched in automated tests; real usable Windows Tk tests actually execute (not import/display skips); healthy/missing/broken/locked/symlinked venv; no-Python discovery simulations and Store-alias exclusion; healthy offline startup; reset sentinel secrets unchanged. Test the external-interpreter deletion guard and exact venv boundary in disposable contained sandboxes.

**Acceptance:** §3/§6/§7 paths work; no source/historical-output loss; completed records follow all selected publications; resume stays at the original destination; meaningful Tk coverage runs on HOME-PC. User checks both themes, real dialogs, Preferences and normal Windows launch. macOS static/mocked checks remain distinct from actual macOS testing. Commit/push 02B and have a fresh reviewer inspect its GUI/setup changes and a targeted 02A regression smoke.

**Gate 02 — STOP:** user accepts 02B desktop/setup evidence and authorizes Phase 03. No punctuation changes belong in Phase 02.

### Phase 03 — Approved small corrections and protection hardening

1. Add mandatory name/ruling negative controls first: `Clan Valor`, `Valor Clan`, `Valor` and all surrounding words preserved; no pronoun/gender automation. Reject shortening/cascading/conflicting replacement data.
2. Add only unambiguous paired curly quotes/apostrophes through small existing-function changes. Preserve/flag uncertainty without first flattening original glyphs. Verify title/paragraph/audit/PDF glyph behavior.
3. Keep the existing two-pass spaced-dash algorithm unchanged; preserve unspaced dashes. Do not substitute a contextual parser.
4. Validate exact OCR candidates against real evidence and clean counterexamples; unsupported `l`/`1`/`Asa` contexts remain untouched. Narrow approved canonical corrections cannot consume neighboring text. Apply generic-fix relocation only as explicitly approved.
5. Add the §8.4 positional page-number adapter only if evidence and approved scope support it. No broad numeric-line stripping; report a justified explicit deferral rather than importing a new layout subsystem.
6. Compare the full frozen corpus to the original baseline plus approved expectations. Attribute every changed chapter to rule IDs/counts and local reviewable diffs. Preserve original baselines. New supported rule cases should be stable on second application; record legacy non-idempotence separately.

Commit/push after each verified meaningful correction group. Update the same phase report and test ledger; use focused tests while working. A fresh reviewer challenges negative controls and actual corpus deltas, especially quotation uncertainty, protected neighbors and numeric deletion. User reviews representative before/after examples.

**Acceptance:** zero prohibited word deletions or unapproved prose changes; all corpus deltas attributed; legacy dash coverage intact; no generic tense/agreement/pronoun system. Unproven candidates stay excluded.

**Gate 03 — STOP:** user accepts the pushed correction SHA, reviewed deltas and declared page-number limits, and authorizes Phase 04 for the fixed `0.4.0` release.

### Phase 04 — Verify the final candidate and prepare release

**Order is binding; a pass before later edits does not certify the final commit.**

1. Reconcile the approved Phase 03 SHA and clean working tree; freeze scope. In one version-preparation commit synchronize `config.toml [project].version`, current BRIEFING version/status, the top new CHANGELOG heading and README status to `0.4.0`. Launcher `--version` must read the config value; extend verify to compare its output. Retain historical `since v0.13.0` comments unless naturally removed with obsolete code.
2. Use a distinct new heading such as `v0.4.0 — <release date> — Offline Script-Only Modernization`. Add one sentence explaining the intentional numbering reset and the historical same-number entry. Keep `v0.4.0 — 2026-06-21 — Phase 4: Editorial Rule Pipeline` untouched; the verifier still uses the top current heading. Record the numbering decision append-only in DECISIONS. Never change historical tags/releases to make the sequence look monotonic.
3. On that committed candidate, run full `scripts/verify.py`, required local-corpus coverage, `git diff --check`, frozen-corpus deltas, fresh declared-dependency/healthy-offline startup, setup recovery and the large-batch/manual gates below. `--require-local-corpora` belongs to pytest/conftest at the inspected baseline. Supply `-rs --require-local-corpora` through child-process-only `PYTEST_ADDOPTS` when invoking the verifier, so its pytest subprocess enforces corpora and reports reasons in the same full run. Alternatively deliberately add and test verifier forwarding; do not pass an unsupported verifier flag or rerun the whole suite solely to collect skips. Capture all skip reasons. Keep same-machine comparisons and mandatory Tk/corpus evidence separate from the overall exit code.
4. Complete fresh independent review against the actual candidate SHA/diff, including data loss, false resume-skips, locks, output collisions, malformed data, Tk shutdown, privacy and venv deletion. Fix findings in bounded commits; rerun focused checks plus the full verifier after **any subsequent tracked change**, including docs/version changes. Rerun the relevant corpus/workload/manual checks when their affected behavior changes; do not rerun long workloads for unrelated prose edits.
5. Finalize release notes, CHANGELOG/README/BRIEFING, migration limitations and HANDOFF before the final candidate commit. Use publication-neutral current product wording such as `Version: v0.4.0 — Offline Script-Only Modernization; see GitHub Releases for publication status`; no misleading pre-tag released claim or permanently stale awaiting-publication product status. The checkpoint/external report states that publication is pending, and the GitHub release/tag becomes the publication record; no tracked post-tag status edit is required. Release notes must cover AI removal, nonresumable old cloud manifests, old key locations/manual removal and provider revocation, TXT output, output destinations and platform limits. Commit/push the complete candidate, run full verify again on that **exact clean SHA**, and report its SHA and results without modifying tracked files afterward. Resolve a commit’s own SHA in the external CLI report; never create endless evidence-only commits trying to embed a commit’s own hash.

**Large-batch procedure:** at least 1,000 real representative chapters, preferably about 3,000 or the largest agreed corpus; at least one real interruption/resume/retry exercise. Use a durable background process (e.g. PowerShell `Start-Process` with explicit executable, working directory, PID and stdout/stderr log files under ignored `files/test-logs/`), not a foreground command held beyond CLI time limits or a transient job that dies with the session. Record corpus/options/code hashes, original run destination and process ownership; poll progress from a new short command and keep the user informed. Stop only this recorded process through the application’s safe-boundary controls; never kill every Python process. If background execution is unavailable, provide the exact operator command and retain a pending gate until results return.

Account for every item; source hashes unchanged; no unexplained editorial differences, missing selected outputs, duplicated resume outputs or false-success records. Check responsiveness, bounded display memory/no chapter accumulation, Pause/Stop, wall time, median/p95 file time, peak memory, checkpoint/hash overhead and resume-validation time. Investigate greater than 20% like-for-like throughput regression on unchanged PDF work on the same machine; attribute added work and obtain acceptance of material overhead. Optimize measured bottlenecks before considering a different journal or parallelism.

**Platform/operator gate:** actual Windows Light/Dark/native-dialog/Preferences/keyboard tests, PDF glyph/layout/page inspection and TXT/TTS inspection; fresh setup/healthy relaunch/recovery/quoted-Unicode paths and standard-user behavior. No-Python PATH/mocked tests are simulations; use Sandbox/VM for a genuine empty-machine claim. Test macOS on actual hardware or withhold macOS release-readiness claims and record the outstanding gate. Linux-container results alone do not certify either desktop.

**Gate 04 — STOP before publication:** user reviews the exact pushed release-candidate SHA, independent report, complete checks/skips, platform limitations and release notes. Ask for concrete authorization for merge/push to `main`, annotated `v0.4.0` tag and GitHub release; these are outside standing working-branch permission. Do not use automatic ship/build commands to cross this gate.

**Only after that authorization, close out as follows:**

1. Fetch current `main` and the working branch; verify origin identity and that the feature SHA still equals the approved candidate. Compare `main` with the **recorded release-candidate base** (initial historical main is `72d68caa3588856c063c62b9b39588fd965db603`). If it advanced, incorporate current main into the working branch without rewriting history, resolve conflicts, then return to candidate verification/review/Gate 04. Do not use stale approval for changed content.
2. Confirm `v0.4.0` is absent both locally and remotely; any collision blocks tagging, never overwrite it. The audit reports only an annotated `v0.12.0`, but Phase 00 and closeout must recheck. An optional non-release archive tag on the old cloud tip is a separately approved action, unnecessary for normal implementation.
3. With a clean tree, merge `--no-ff` into `main`, using the repository convention `Merge feature/<actual-branch> into main — v0.4.0`. Run full verify and `git diff --check` on the resulting exact merge SHA before tagging/pushing. If it fails, stop publication, preserve the merge for inspection and obtain a repaired/reverified candidate; never tag a known failure.
4. Create the annotated `v0.4.0` tag on the verified merge SHA; push `main`, confirm it reached the expected SHA, then push the tag and confirm its peeled target. A race/non-fast-forward refusal is a stop, not permission to force. Publish the approved GitHub release from the final notes and explicitly mark it **Latest**, because semantic version ordering may otherwise prefer `v0.12.0` over `v0.4.0`. Record merge/tag/release URL in the external completion report. No source/docs edits after tagging.
5. Keep the prior approved tag/commit and old run outputs reachable for rollback. If a release must be withdrawn, stop using it and consult the user before moving main, changing tags or publishing a revert. Do not resume a new-schema run with old code or silently downgrade manifests/settings. Rollback authorization is separate from this release approval.

**Release acceptance:** exact final candidate and merge verified; mandatory baseline/workload/Windows evidence complete; independent findings resolved or explicitly accepted; remaining macOS/no-Python evidence limitations stated honestly; no hidden AI/network requirement and no post-verification source drift.

## 10. Verification matrix and fixture strategy

Use existing test modules wherever possible. Add a small test file only when it owns a distinct behavior; do not generate one test file per checkpoint or mirror private helper implementations.

| Risk/behavior | Existing foundation | New evidence needed |
|---|---|---|
| Editorial parity | `test_rules`, `test_pipeline`, `test_multi_novel`, `test_novel_profiles`, `test_novel_registry` | Exact frozen outputs per profile and Universal; approved delta list; title/paragraph/form-feed fidelity. |
| Protection | `test_protection`, profile tests | Clan/Valor surrounding-word invariance; all Shadow Slave rulings; punctuation/possessive/overlap and replacement-boundary cases. |
| Junk/extraction safety | `test_junk_strip_corpus`, `test_junk_strip_hardening`, `test_robustness`, `test_pdf` | Error pages preserved/flagged, legitimate ads/URLs in dialogue, optional positional page-number positives/negatives. |
| Mixed imports | `test_input_scanner`, `test_app` | PDF/TXT/files/folders; optional recursion; natural order + manual overrides; duplicate path/root and same-stem cases; unreadable paths and traversal cycles. |
| Output/serialization | `test_output_layout`, `test_batch`, `test_pdf` | Six PDF/TXT input-to-output selections; paired publication; bounded Windows sharing retries/exhaustion; NFC/casefold collisions; full temporary/final path lengths; TXT decoding/blank lines/form feeds; glyphs; source immutability. |
| Resume/cancel | `test_run_manifest`, `test_pause_and_condensed_log`, `test_batch` | Hash identity despite same size/mtime; deleted/changed output; corrupt/future/legacy schema; repeated resume history; Stop during pause; retry failures; preference/rule changes. |
| Crash recovery | Manifest/batch tests | Fault before/after prepared write, between PDF/TXT renames, before completed write, and on manifest fsync/replace. Recovery uses reserved names and never skips incomplete pairs. Two simultaneous resumes/recoveries cannot own the same run; PID reuse/unknown ownership cannot remove a live lock. |
| GUI/events | `test_app` plus adapted Activity tests | No worker Tk calls; bounded pumping/history; theme state; mocked native dialog responses; actual HOME-PC Tk tests; reset changes only settings and preserves sentinel secrets/siblings; Clear Log leaves disk logs. |
| Bootstrap/entry | `test_launchers`, `test_main_check_flag`, `test_scaffold` | Healthy offline fast path; no base interpreter with healthy venv; broken/locked/symlinked venv; missing pip/Tk/dependency; absent Python guidance; external repair; error visibility. |
| Product independence | Existing AI-off coverage, extracted before deletion | Fresh non-AI environment; fail any attempted network/service use during normal launch/editing; runtime does not require `files/` reference docs. |
| Workload/platform | Local corpus and user runs | Real thousands-scale evidence, Windows UI/setup, actual macOS or explicit pending status. |

Compare text byte-exactly in Phase 01. In later phases, compare exact text against the original baseline plus explicitly approved changes; never scrub all punctuation/spacing to make a broad comparison pass. Track output-format/layout changes independently from editorial differences. Audit/timing/session timestamps need semantic comparison rather than byte equality.

A proposed rule needs at least a positive example, a plausible clean counterexample, a protected-term example, and a full-pipeline example. Evidence-based parametrized tests are sufficient; avoid introducing a property-testing dependency or exhaustive grammar corpus solely for this plan. Test source/output immutability using hashes, not visual confidence alone.

Baseline fixture layout should be compact: one manifest/index identifying source, code/config/data hashes and expected text; corresponding ignored input/extracted/expected/render artifacts. Reuse checked-in fixtures where suitable. Never commit full copyrighted chapters or local secrets merely to obtain reproducibility; use synthetic/minimal fixtures for repository regression coverage and private corpus identities for local validation.

## 11. Checkpoint workflow and agent responsibilities

Keep one authoritative master plan and one concise report per phase: `files/checkpoints/WNE-P00-discovery.md` through `WNE-P04-release-readiness.md`. Phase 02 may use a clearly separated 02A/02B section or one necessary extra 02A report; do not duplicate narratives. Original baselines stay frozen/ignored. A small node-ID test-disposition table and skip inventory may live in those reports or an ignored machine-readable companion when too large; no chapter text or private paths in tracked reports.

| Owner | Responsibility |
|---|---|
| User | Approves Gate 00, 01, 02A, 02, 03, 04; resolves canonical/support ambiguities; performs visual/TTS/platform checks; explicitly authorizes main/tag/release publication. |
| Codex CLI, Sol 6.1 / High (default writer) | Starts Phase 00, then executes only approved implementation slices; tests, baseline attribution, docs and verified feature-branch checkpoint commits/pushes. User may transfer a named slice to Claude Code. |
| Fresh independent Codex or Claude Code CLI session | Read-only review at Gates 01/02A/02/03/04 against named base/head SHAs and actual source/tests; runs targeted checks and records findings separately. It did not author the reviewed slice; it does not silently modify code or approve the user’s gate. |
| Planning/review chat | Verifies reported pushed refs/diffs through available GitHub access, assesses reports/limitations, guides manual tests and supplies the next bounded prompt. Cannot claim local HOME-PC execution. |

A new independent session starts with the approved requirements relevant to the slice, exact base/head SHAs/diff and checkpoint report, not the writer’s narrative conversation. It then inspects necessary unchanged callers/tests and runs targeted checks; restricting it to a diff alone would hide integration bugs. A fresh Codex session is acceptable when Codex wrote the change; Claude provides a second tool/model perspective when available. Reviewer availability must be named in each report. If no real independent session has reviewed, mark that gate pending; a planning chat’s report review is not a claimed local test rerun. Do not assume plugins or subagents exist, install them, or launch a whole agent team.

One active writer at a time. Read the current checkpoint plus relevant source/diffs; do not repeatedly read the entire 340 KB HANDOFF or 133 KB DECISIONS. Standalone review may write ignored test logs and its requested report, with no product edits. The writer resolves findings, checkpoints fixes and returns the changed diff to review.

### Git checkpoint policy

The supplied `AI-WORKSPACE.md` and chat workflow already authorize working-branch creation, scoped verified commits and pushes to the existing origin. Apply the live repository’s actual rules; resolve a material conflict once, not through repeated per-command questions. Main merges/pushes, force/history operations, tags/releases, remote changes and discarded user work retain their explicit approval requirements.

At every verified slice (Phase 00 preparation when safe, 01A, 01B repaired pair, 01C, 02A, 02B, meaningful Phase 03 groups and Phase 04 fixes/candidate), update concise HANDOFF/report state, stage explicit task paths, inspect staged content for secrets/private corpus/unrelated changes, commit, push and confirm remote SHA. Never blind `git add -A`. Full verify runs at phase gates and before pushes as required by the live workspace; use focused tests during edits. The content-identical 01B move is the sole documented non-runnable intermediate commit, pushed only with its passing repair commit. Do not end ordinary sessions with completed verified work uncommitted.

Each implementation slice begins from the recorded clean SHA; compare both local and live origin. Do not continue on an unexpected HEAD or unresolved tracked/untracked user changes. Review approval is attached to a specific SHA/delta. Preserve uncommitted work and report its disposition need without stashing/discarding it. If a checkpoint cannot be verified, keep it clearly blocked; never push private text or relabel failures as a pass to create a restore point.

A commit cannot include its own SHA. A tracked report records the input/base SHA and prior verified slice SHAs, commands/results and intended scope before commit. Resolve the resulting commit SHA afterward in the CLI response/ignored evidence log; the next checkpoint may record it. Final release verification runs against the exact clean committed candidate; external reporting binds that SHA to its results without another tracked edit.

### Checkpoint template

```markdown
# WNE Phase XX / slice — checkpoint
Status: PASS / BLOCKED / READY FOR USER ACCEPTANCE
Scope: approved phase/slice and performed behavior
Writer: CLI/model/effort actually used
Independent reviewer: separate session, reviewed base/head SHA, outcome or pending

Git state:
- Working branch / input or last approved SHA / upstream:
- Live origin/main refs and check time; ahead/behind:
- Staged / unstaged / untracked; unrelated changes preserved:
- Prior slice commit SHAs; current commit SHA resolved in external CLI report:
- Push result and remote-confirmed SHA (external report if not yet committed):

Actual changed files:
- path — reason; identify rename blob identity, repairs and deletions separately

Validation:
- exact command/interpreter/platform — pass/fail/skip counts, artifact location
- skips: node IDs/reasons; same-machine P00 comparison and new skip explanation
- deleted/extracted tests: old node IDs — reason/disposition — replacement IDs
- offline guard and child-process coverage; no real key values
- baseline identity/hashes — exact comparison and private artifact location
- intentional output deltas: rule IDs/examples; unexplained deltas zero or blocker
- manual/Tk/corpus/platform checks: actually run vs pending

Remaining blockers/risks:
- issue, impact, exact resolution needed

Next allowed step:
- STOP at Gate XX (including 02A); state concrete user decision and reviewed SHA
- or bounded remaining slice inside the already approved phase
```

Collect skip reasons and node identities in the same test execution where practical (`-ra`/`-rs`/report hook); preserve a same-machine Phase 00 reference. A green verify exit is insufficient if meaningful GUI/corpus coverage did not run. Deleted test counts must reconcile with the ledger; new unexplained skips or disappeared checks block acceptance. Platform-only skips need explicit support-scope justification, not blanket acceptance of the historical count.

### Optional skill use

The supplied audit recommends `addyosmani/agent-skills`. This plan does not assume it is installed or authorize installation/authentication. Where already available and permitted, select one relevant capability rather than loading the collection: source-driven/deprecation discovery for 00; migration/TDD for 01; interface/security/error-recovery for 02; negative-control/doubt-driven review for 03; independent code/test/security review and shipping checklist for 04. Context engineering and constraint-driven checks mean loading current scope and preserving tests, not extra documentation.

Do not use `/build auto` to traverse phases or `/ship` before Gate 04 publication authorization. The audit notes a `/review` command-name collision; inspect installed help before invoking any plugin-qualified command such as `/agent-skills:review`. Normal CLI source inspection and pytest must remain sufficient when these capabilities are absent. Skill defaults never override this plan’s gates or working-branch Git policy.

## 12. Explicit scope exclusions

- All AI editing and model-service integrations, including local inference, NLP/grammar models and cloud APIs.
- A new editing engine, comprehensive grammar parser, generic pronoun/gender correction, stylistic rewriting, or semantic tense/agreement changes.
- Destructive canonical substitutions, surrounding-word normalization, or fuzzy global name repair.
- A general plugin/rules platform, arbitrary expression engine, or duplicate authoritative reference system.
- Parallel chapter processing, distributed queues, databases, web/Electron migration, or a queue-controller rewrite.
- OCR recognition for scanned PDFs, automatic rescraping, or importing PDF-Splitter’s analysis/OCR subsystem. Existing OCR-artifact text repairs remain in scope.
- Automatic deletion of heading-only pages, aggressive headers/footers stripping, broad digit-line deletion, or unsupported layout reconstruction.
- Audio generation, TTS engine integration, EPUB support, novel scraping, or a manual copy-edit workspace with running open flags.
- Downloaded-model cleanup, a general installer framework, bundled Python/wheel distributions, or guaranteed internet-free provisioning from an empty machine.
- Repository-history cleanup, unrelated formatting/dependency upgrades, automatic branch surgery, unapproved main merges/pushes/tags/releases, a new uninstaller, or deleting old credentials/user outputs. Verified working-branch checkpoint commits/pushes remain in scope under the standing policy and bounded gates.

## 13. Phase 00 kickoff prompt — fresh local Codex CLI session

Save this Revision 2 plan at `files/plans/Web-Novel-Editor-Master-Implementation-Plan.md` in the actual HOME-PC repository. Select Sol 6.1 at High effort in the installed Codex CLI and confirm the selected model/effort using its available status/model UI. Do not invent a model ID or unsupported CLI flags; the chat cannot change another session’s model setting. Start Phase 00 only; implementation follows Gate 00 approval.

```text
Perform Phase 00 ONLY from files/plans/Web-Novel-Editor-Master-Implementation-Plan.md
(Revision 2). Use the selected Codex Sol 6.1 model at High effort; report the actual
selection if it differs. Release target is fixed at 0.4.0.

Orient from live parent/repository AGENTS.md, AI-WORKSPACE.md, current HANDOFF and
the plan; read other current sections only as needed. Reconcile branch/HEAD,
dirty/untracked work, upstream and live origin. Historical planning branch:
feature/plan-2b-cloud-providers at c8a52595dd1f46f5b07f15d63798cc09e76c1145;
main at 72d68caa3588856c063c62b9b39588fd965db603. Recheck; never reset to these.

Follow the plan's narrow Phase 00 writes: additive .gitignore protection BEFORE
private baselines; ignored QA artifacts; plan/checkpoint and short orientation,
decision/supersession notices. Prove baselines ignored, reports trackable, and no
already-tracked private artifacts. Keep credential exclusions and all real secrets.
No product/test/config/launcher edits, setup runs, installs/repairs, source/output
changes, branch switching, main/tag/release actions or model/cloud calls.

Identify trusted script-only state and freeze exact per-profile extracted and
pre-render text with code/data/input identities. Inventory AI/shared utilities,
migrations and every removed/extracted test candidate. Establish current tests
through the no-network harness with key variables unset only in child processes;
record failures and skip node IDs/reasons. Settle Python-support/tomllib mismatch,
generic-fix scope, bounded approved deltas, defaults and branch recommendation.
Mark old plan-2c superseded and record the fixed 0.4.0 numbering decision without
bumping current version fields. Preserve Clan Valor, Valor Clan, Valor and all
surrounding prose. No Clan Valor -> Valor replacement is allowed.

Write files/checkpoints/WNE-P00-discovery.md with exact state, baseline identities,
commands/results, skip inventory, blockers and the smallest Phase 01 scope.
Commit/push only the safe verified preparation/docs checkpoint on the existing
feature branch under standing Git policy; stage explicit paths and report the
resulting/remote-confirmed SHA, or explain the blocker. Preserve unrelated work.
STOP at Gate 00 for approval of base/branch, baselines/deltas/support and Phase 01.
Do not start Phase 01 or infer approval from completing discovery.
```

The next approved implementation prompt starts from this checkpoint and SHA; it does not repeat Phase 00, drop independent review, or revive the historical cloud-provider plan.
