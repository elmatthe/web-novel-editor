# WNE Phase 01 — checkpoint (remove AI, migrate the engine, consolidate)
Status: **READY FOR GATE 01 — STOP.** Slices 01A, 01B and 01C are complete and verified; nothing from Phase 02 has been started.
Scope: Master Plan Revision 2, Phase 01 only (01A, 01B, 01C in order). No Phase 02 work.
Writer: Claude Code, model Sonnet 5.5, effort high. The prompt asked for Codex Sol 6.1 / High; that selection was not available to this session, so the actual selection is reported here as it differs.
Independent reviewer: pending — a fresh Claude Code session reviews after Phase 01 (Gate 01).
Machine: HOME-PC (Windows 11, Python 3.13.12 in the project `.venv`).

## Git state
- Branch: `feature/0.4.0-script-only-editor`, created from the exact approved checkpoint `0c1ac0b1e883ce2061f5ee67bccc2fbf00da2183` (identity confirmed: local HEAD, `origin/feature/plan-2b-cloud-providers` and the approved SHA were equal before branching).
- `feature/plan-2b-cloud-providers` is preserved unchanged at `0c1ac0b`. `origin/main` is `72d68caa3588856c063c62b9b39588fd965db603` and is not touched.
- Untouched user work: `md-instructions/plan-2-ai-editor-integration.md` (untracked historical AI instruction file) was never staged, edited or deleted.
- Verified slice commits, in order (all on `feature/0.4.0-script-only-editor`, each pushed after its tip passed):
  `8e4094c` 01A corpus-test restoration -> `08976f1` 01A AI removal -> `a7c1aec` 01B pure move (**not pushed alone**) -> `275fe8f` 01B repair (pushed together with the move) -> the 01C commit (its own SHA cannot be embedded here; resolve it with `git log -1 --format=%H -- scripts/pipelines/universal.py` or from the final CLI report).
- The approved checkpoint `0c1ac0b` is the base; Phase 01's review range is `0c1ac0b..HEAD`.

## 01A — Remove AI functionality safely

### What changed
- **Restored the 8 skipped corpus tests** (own commit, before any removal): hash-pinned fixtures in `files/tests/corpus_pins.py` + `corpus_pins.json` (120 files, SHA-256 verified before use). The old `-v2` corpora no longer exist and the Phase 00 hash check found 0 byte-identical PDFs against the current re-scrapes, so a directory alias would have silently changed coverage. All 46 tests of the two modules pass with `--require-local-corpora`.
- **Shared utilities extracted before deletion:** `utils/settings.py` (per-user runtime dir, atomic JSON writer — unchanged behaviour) and `utils/pace.py` (running-average/ETA readout). `text_hash` needed no replacement (its only use was AI provenance). The key redactor was **not** carried over: it only masked provider API keys, and no key exists any more.
- **Removed:** `scripts/Universal/ai/` (23 files), `gui/ai_settings.py`, `gui/cloud_ui.py`, `resources/Novel-Edits-Details/UNIVERSAL-AI.md`; the AI card, key/consent/estimate/resume dialogs and quota relay in `gui/app.py` (1,461 -> 757 lines); the AI seam, AI metadata and AI audit channel in `core/batch_runner.py` and `core/replacement_log.py`; all `[ai*]` tables in `config.toml` (only `[project]` remains); the `ollama`, `google-genai` and `groq` pins in `scripts/requirements.txt`. `tomli==2.4.1` stays, now annotated as the Python 3.10 TOML reader.
- **Checkpoint seam preserved, script-only:** `RunCheckpoint` / `load_manifest` / `find_resumable_run` / `plan_resume` remain. Provider, model, prompt, gate, policy, `ai_status` and quota fields are gone. `SCHEMA_VERSION` is now **2** and only schema 2 is read, so a schema-1 manifest written by a retired cloud run is **refused and left untouched on disk** (never converted into a resume). GUI wiring of the checkpoint for all non-dry runs is Phase 02A.
- **Offline coverage added:** an autouse network-denial fixture in `conftest.py` (refuses and records `socket.connect`, `connect_ex`, `create_connection`, `sendto`; a recorded attempt fails the test at teardown even if the code swallowed the error) and `test_offline_guard.py`, which proves the guard reaches a child interpreter via a throwaway `sitecustomize`, that `main.py --check` and a real `run_batch` make no attempt, and that importing the app loads none of the retired SDKs.
- **Python 3.10 TOML fix:** `test_scaffold` no longer imports `tomllib` unconditionally (`sys.version_info` switch to the pinned `tomli`), plus a test that `tomli` and `tomllib` parse `config.toml` identically.
- **Strict Tk on Windows:** an autouse fixture turns any `TclError` raised by `tkinter.Tk()` into a test **error** carrying the real Tcl message, instead of the old blanket "no display available for Tk" skip. `WNE_ALLOW_TK_SKIP=1` restores skipping (headless CI); `@pytest.mark.allow_tk_failure` exempts a test that provokes it deliberately.

### Test results (full suite, offline harness, keys unset in the child only)
- **637 passed, 0 skipped, 0 failed** (was 1,267 passed / 8 skipped at Phase 00). Without `--require-local-corpora` the 8 formerly skipped corpus tests now run.
- Count reconciliation: 1,275 old node IDs -> 582 kept unchanged, 14 adapted, 26 extracted, 6 superseded, 1 deferred, 646 retired. 55 new node IDs are adapted/extracted replacements or brand-new tests. Fewer tests is the expected consequence of deleting 11 AI-only modules; it is not evidence of safety by itself — the ledger below accounts for every node.
- **Editorial baseline:** all 828 frozen results recomputed with the current code are **byte-identical** to the Phase 00 baseline (0 output mismatches, 0 input mismatches, 0 network attempts).

### Test-disposition ledger (every old node accounted for)
Full per-node CSV (old node ID, fate, reason, replacement IDs; validated so every replacement ID exists in the new collection): ignored companion `files/test-logs/p00/test-disposition-ledger-01A.csv`, SHA-256 `12e2ccda6c07a074613bd81afa6af7a1c9089dc9fa774da8c52f4bda6268bdb3`.

Retired by module (AI/provider/cloud-only responsibility, module removed unless noted; count = nodes):

| Module / source | Nodes |
|---|---|
| `test_ai_editor` | 46 |
| `test_ai_foundation` | 13 |
| `test_ai_gui_controls` | 34 |
| `test_ai_validation` | 33 |
| `test_cloud_gui` | 91 |
| `test_cloud_keys_and_consent` | 51 |
| `test_gemini_provider` | 78 |
| `test_groq_provider` | 92 |
| `test_ollama_provider` | 31 |
| `test_plan2a_phase5` | 17 |
| `test_rate_limiting` | 101 |
| `test_run_manifest` | 13 |
| `test_spend_guard` | 46 |

Extracted (generic behaviour re-homed before its module was deleted):

| Old node | Reason | Replacement node(s) |
|---|---|---|
| `test_ai_foundation::test_per_user_paths` | per-user settings path contract; asserted on path components, host-independent | `test_settings::test_windows_runtime_dir_is_under_localappdata`<br>`test_settings::test_windows_runtime_dir_falls_back_to_the_home_appdata_folder`<br>`test_settings::test_macos_runtime_dir_is_application_support`<br>`test_settings::test_an_unsupported_platform_is_refused_not_guessed` |
| `test_ai_foundation::test_atomic_settings_write_and_no_leftover` | atomic write, no residue; plus failed-replace case | `test_settings::test_atomic_write_round_trips_and_leaves_no_temp_file`<br>`test_settings::test_a_failed_replace_keeps_the_old_file_and_leaves_no_residue` |
| `test_ai_foundation::test_import_has_no_filesystem_or_sdk_side_effects` | import hygiene generalised to utilities + app imports | `test_settings::test_importing_the_utilities_has_no_filesystem_side_effects`<br>`test_offline_guard::test_the_application_imports_load_no_retired_sdk` |
| `test_ai_foundation::test_committed_config_is_disabled_and_secret_free` | credential-free config check without the retired redactor | `test_scaffold::test_committed_config_holds_only_project_metadata_and_no_credentials` |
| `test_ai_gui_controls::test_rate_is_unknown_before_the_first_chapter_completes` | pace readout | `test_pace::test_rate_is_unknown_before_the_first_chapter_completes` |
| `test_ai_gui_controls::test_rate_is_a_running_average_with_an_eta` | pace readout | `test_pace::test_rate_is_a_running_average_with_an_eta` |
| `test_ai_gui_controls::test_rate_drops_the_eta_once_every_chapter_is_done` | pace readout | `test_pace::test_rate_drops_the_eta_once_every_chapter_is_done` |
| `test_ai_gui_controls::test_rate_ignores_impossible_inputs` | pace readout | `test_pace::test_rate_ignores_impossible_inputs` |
| `test_ai_gui_controls::test_duration_formatting (x6)` | pace readout (6 parametrised cases) | `test_pace::test_duration_formatting` |
| `test_ai_gui_controls::test_constructing_the_window_never_imports_the_ollama_sdk` | window construction imports no AI package; no AI widgets | `test_offline_guard::test_the_application_imports_load_no_retired_sdk`<br>`test_app::test_the_window_has_no_ai_or_cloud_controls` |
| `test_ai_gui_controls::test_ai_off_start_passes_no_editor_at_all` | start passes only script-only arguments | `test_app::test_start_passes_only_the_script_only_arguments` |
| `test_ai_gui_controls::test_the_log_sits_beside_the_controls_not_below_them` | GUI layout | `test_app::test_the_log_sits_beside_the_controls_not_below_them` |
| `test_ai_gui_controls::test_the_window_can_be_made_short_enough_for_a_1080p_screen` | GUI layout | `test_app::test_the_window_can_be_made_short_enough_for_a_1080p_screen` |
| `test_ai_gui_controls::test_both_columns_fit_inside_the_minimum_window_width` | GUI layout | `test_app::test_both_columns_fit_inside_the_minimum_window_width` |
| `test_ai_gui_controls::test_the_run_controls_sit_inside_the_minimum_window_height` | GUI layout | `test_app::test_the_run_controls_sit_inside_the_minimum_window_height` |
| `test_ai_gui_controls::test_every_fixed_row_fits_inside_the_minimum_window_height` | GUI layout | `test_app::test_every_fixed_row_fits_inside_the_minimum_window_height` |
| `test_ai_gui_controls::test_progress_updates_publish_a_running_average_and_eta` | pace readout in the app | `test_app::test_progress_updates_publish_a_running_average_and_eta` |
| `test_ai_gui_controls::test_rate_readout_clears_between_runs` | pace readout in the app | `test_app::test_rate_readout_clears_between_runs` |
| `test_cloud_keys_and_consent::test_secrets_file_is_written_atomically_and_permission_restricted` | atomic-write behaviour kept; POSIX permission part retired with the secrets file | `test_settings::test_atomic_write_round_trips_and_leaves_no_temp_file` |
| `test_cloud_keys_and_consent::test_secrets_path_uses_the_2a_per_user_runtime_directory` | per-user runtime directory contract; the secrets store itself is neither read nor migrated | `test_settings::test_windows_runtime_dir_is_under_localappdata` |
| `test_ollama_provider::test_release_shaped_script_only_startup_needs_no_ollama_or_dev_tree` | release-shaped startup, now shadowing every retired SDK | `test_main_check_flag::test_release_shaped_startup_needs_no_dev_tree_and_no_ai_sdk` |

Adapted:

| Old node | Reason | Replacement node(s) |
|---|---|---|
| `test_dual_mode_provenance::test_normalization_reaches_the_ai_stage_already_canonical (x2)` | same normalization guarantee proven through run_batch's built text, no provider | `test_dual_mode_provenance::test_normalization_is_applied_in_the_run_batch_output` |
| `test_plan2a_phase5::test_ai_disabled_preserves_exact_build_text_and_constructs_no_provider` | drops ai_editor/provider; keeps the script-only guarantee | `test_batch_stop_safety::test_the_pipeline_output_reaches_build_pdf_exactly` |
| `test_plan2a_phase5::test_default_dry_run_never_initializes_ai_and_writes_no_pdf` | drops ai_editor/provider; keeps the script-only guarantee | `test_batch_stop_safety::test_a_dry_run_builds_no_pdf_and_creates_no_output_folder` |
| `test_plan2a_phase5::test_stop_during_pdf_write_finishes_current_then_stops` | drops ai_editor/provider; keeps the script-only guarantee | `test_batch_stop_safety::test_stop_during_pdf_write_finishes_current_then_stops` |
| `test_plan2a_phase5::test_stop_already_requested_begins_no_file` | drops ai_editor/provider; keeps the script-only guarantee | `test_batch_stop_safety::test_stop_already_requested_begins_no_file` |
| `test_plan2a_phase5::test_stop_releasing_paused_worker_begins_no_next_file` | drops ai_editor/provider; keeps the script-only guarantee | `test_batch_stop_safety::test_stop_releasing_paused_worker_begins_no_next_file` |
| `test_plan2a_phase5::test_pause_is_still_consulted_only_between_ai_files` | drops ai_editor/provider; keeps the script-only guarantee | `test_batch_stop_safety::test_pause_is_consulted_only_between_files` |
| `test_plan2a_phase5::test_source_pdf_bytes_and_mtime_are_unchanged` | drops ai_editor/provider; keeps the script-only guarantee | `test_batch_stop_safety::test_source_pdf_bytes_and_mtime_are_unchanged` |
| `test_plan2a_phase5::test_ai_enabled_still_isolates_pdf_build_failure` | drops ai_editor/provider; keeps the script-only guarantee | `test_batch_stop_safety::test_one_pdf_build_failure_is_isolated_from_the_rest_of_the_batch` |
| `test_plan2a_phase5::test_the_condensed_line_reports_the_edit_count_AND_the_ai_verdict` | drops ai_editor/provider; keeps the script-only guarantee | `test_batch_stop_safety::test_the_condensed_line_reports_the_real_edit_count` |
| `test_run_manifest::test_the_manifest_carries_every_field_the_plan_requires` | provider/model/ai_status fields removed; schema 2 asserted | `test_run_manifest::test_the_manifest_carries_every_field_the_plan_requires` |
| `test_run_manifest::test_the_manifest_holds_no_api_key_and_no_chapter_text` | key half retired; chapter-text half kept | `test_run_manifest::test_the_manifest_holds_no_chapter_text` |
| `test_run_manifest::test_a_real_chapter_run_puts_no_prose_and_no_key_in_the_manifest` | key half retired; prose half kept | `test_run_manifest::test_a_real_chapter_run_puts_no_prose_in_the_manifest` |

Superseded:

| Old node | Reason | Replacement node(s) |
|---|---|---|
| `test_ai_editor::test_script_only_never_constructs_provider` | no provider exists; offline guard + exact script-only arguments | `test_offline_guard::test_a_batch_run_makes_no_network_attempt`<br>`test_app::test_start_passes_only_the_script_only_arguments` |
| `test_ai_editor::test_script_only_prepare_run_never_constructs_provider` | no provider exists; offline guard | `test_offline_guard::test_a_batch_run_makes_no_network_attempt` |
| `test_cloud_gui::test_a_resumed_checkpoint_completes_the_original_queue` | resume semantics covered by test_run_manifest::test_resuming_processes_exactly_the_files_the_first_run_did_not; GUI wiring is Phase 02A | `test_run_manifest::test_resuming_processes_exactly_the_files_the_first_run_did_not` |
| `test_cloud_keys_and_consent::test_script_only_output_is_byte_identical_with_the_cloud_layer_present` | replaced by the exact comparison against the 828 frozen script-only results (ignored baseline) plus test_pipeline | - |
| `test_rate_limiting::test_the_quota_stop_record_carries_no_key_and_no_chapter_text` | no-chapter-text privacy is covered by the manifest tests | `test_run_manifest::test_the_manifest_holds_no_chapter_text` |
| `test_spend_guard::test_a_verdict_carries_no_key_and_no_chapter_text` | no-chapter-text privacy is covered by the manifest tests | `test_run_manifest::test_the_manifest_holds_no_chapter_text` |

Deferred:

| Old node | Reason | Replacement node(s) |
|---|---|---|
| `test_cloud_gui::test_a_cloud_run_hands_run_batch_a_checkpoint` | script-only checkpoint wiring for ALL non-dry runs is Phase 02A; seam tests remain in test_run_manifest | - |

Brand-new tests (no old ancestor): `test_offline_guard` (5), `test_run_manifest::test_the_manifest_has_no_provider_model_or_quota_fields`, `::test_a_legacy_schema_1_cloud_manifest_is_refused_and_left_untouched`, `::test_a_stopped_run_is_offered_for_resume_from_exactly_where_it_stopped`, `test_scaffold::test_tomli_backport_reads_the_config_exactly_like_the_stdlib`, `::test_requirements_declare_no_ai_sdk`, `test_settings::test_the_module_exposes_no_secret_or_provider_helpers`.

### Findings worth the reviewer's attention
1. **Test adaptation (judgement call):** `test_corpus_asterisks_and_hashes_survive_strip_junk` asserted that every `*` and `#` survives `strip_junk`. The Supreme Magus re-scrape carries `*** ... freewebnovel` watermark lines whose asterisks are part of the junk, so the blanket assertion failed on 2 of 81 sampled files. The invariant is kept strict where it matters: any lost character must be explained by a whole watermark line; in-line loss or removal of a non-watermark line still fails. This is the one place a restored test was changed in meaning, not just in fixtures.
2. `test_nq_corpus_chapter_protected_terms_survive_profile_mode` could pass vacuously (`if n_in:`). It now also asserts the chapter really contains a protected term (`Noble` x26 in the pinned chapter).
3. `utils.settings.runtime_dir` does `environ = environ or os.environ`, so an explicitly **empty** mapping falls back to the real environment. Extracted unchanged (no behaviour change in this slice); a test notes it.
4. The Phase 00 ledger under-counted extractions: `test_dual_mode_provenance` is about Shadow-Slave-mode vs Universal-mode dispatch, not AI, and `test_ai_gui_controls` held the GUI layout and pace tests. All were re-homed (see tables) instead of being deleted with their module.
5. Legacy cloud manifests are refused by schema, and legacy key files are neither read, migrated nor deleted by anything in this application.

## 01B — Migrate scripts

Preceding passing commit: `08976f1`. Two commits, reviewed separately, pushed together only after the repaired tip passed.

**Move commit `a7c1aec`** — `git mv` of `scripts/Universal/{core,gui,pdf,pipelines,profiles,resources,rules,utils}` and `main.py` to `scripts/`. **63 of 63 files are `R100`; every old/new blob SHA was compared (0 mismatches).** The commit contains no edit of any kind. It is intentionally not runnable alone (launchers, tests and comments still named the old path) and was never pushed on its own.

**Repair commit `275fe8f`** — 49 lines out, 49 lines in, all path text: launcher `MAIN_SCRIPT` (`.bat` stays CRLF, `.command` stays LF with mode 100755), `conftest.py` and six tests that built the old path, comments/docstrings and bundled resource docs that named `scripts/Universal` (a diff filter confirmed **no code line in `scripts/` changed**), the README developer paths and placeholder sentence, and removal of the obsolete `scripts/Windows/.gitkeep` and `scripts/MacOS/.gitkeep`. Resource anchors (`Path(__file__).parents[1] / "resources"`) needed no edit because `resources/` moved with `core/`.

Evidence at the repaired tip:
- `main.py --check` exits 0 from an unrelated working directory; the 8 novel indexes, 9 roster entries, 540 Shadow Slave terms and the Shadow Slave edit-details document all resolve from that directory.
- Full suite 637 passed / 0 skipped; full `scripts/verify.py` PASS; **all 828 frozen results identical (0 output changes, 0 audit-rule-count changes, 0 input changes)**, 0 network attempts.
- Remote-confirmed after the push: `275fe8fbce1a41bb60658f0ba1ee3541feb86774`.

## 01C — Consolidate the universal pipeline

### What changed
- **One engine.** `scripts/pipelines/universal.py` is the former `shadow_slave.py`, moved with `git mv` and edited in place, so the two Unicode character-class regexes are byte-identical (their hash was compared against `HEAD:scripts/pipelines/shadow_slave.py`). The three-block stage sequence exists once. A novel is a `PipelineProfile(name, special_fixes, summary_rows)`; `universal.bind(profile)` yields the `run_pipeline(text, lexicon, *, repl_log, gui_log, dry_run)` callable the registry and `run_batch` expect.
- **Deleted:** `pipelines/{supreme_magus,the_noble_queen,renegade_immortal,lord_of_mysteries}.py` and the empty `profiles/lord_of_mysteries/` placeholder package (3 files).
- **Corrections as data:** `profiles/corrections/{shadow-slave,supreme-magus,the-noble-queen,renegade-immortal}.toml` (generated from the live Python maps, with an assertion that the parsed TOML equals the original mapping and preserves order) and `profiles/loader.py`, which rejects non-strings, empty keys, self-maps and any key occurring inside a value (cascade). Each `profiles/<x>/special_fixes.py` keeps its public constant and loads its file. Entries: Shadow Slave 2, Supreme Magus 15, Noble Queen 1, Renegade Immortal 2.
- **Registry** binds profiles to the one engine; the fallback and "Universal" use the empty `UNIVERSAL_PROFILE`.
- **Gate 00 dispositions implemented, and nothing else:**
  - `carcassess` -> `carcasses` promoted to a **bounded universal fix** (whole word, exact lowercase, applied while protected terms are masked, recorded as `special_fixes` / `forced_substitution`).
  - `threestoried` and `tompost shelf` **retired**. `Almanach` -> `Almanac` and `Obers` -> `Obels` remain Shadow Slave profile corrections. Supreme Magus, Noble Queen and Renegade Immortal corrections are untouched.
  - **Legacy audit-row counts unchanged:** Shadow Slave, Supreme Magus and The Noble Queen keep the `quote_normalize` / `slash_replace` / `em_dash` summary rows; Universal, Renegade Immortal and the index-only novels still emit none (a test pins both directions and that the flag never changes the text).
  - Canonical-name floors, the eight indexes and the commented candidates were **not touched** (no commented protected-term candidate was activated).
- Docs: DECISIONS 075, README status (AI removed, legacy-key guidance, version fields unchanged), BRIEFING direction note, HANDOFF, registry docstring.

### Intentional editorial deltas against the frozen baseline (the complete list)
Recomputed all 828 frozen results with the consolidated engine: **810 identical, 18 changed**, every one of the 18 on the synthetic `special_fix_triggers` input (direct text and PDF round-trip) across the 9 profiles. Verified at word level (not just by hash):

| Profiles (x2 inputs: direct + PDF) | Results | Only token change | Reason |
|---|---:|---|---|
| Shadow Slave | 2 | `three-storied` -> `threestoried`, `topmost` -> `tompost` | retired entries (the baseline captured the old, now-removed corrections) |
| Universal, Circle of Inevitability, Lord of the Mysteries, Re:Monster, Reverend Insanity, Renegade Immortal, Supreme Magus, The Noble Queen | 16 | `carcassess` -> `carcasses` | promoted bounded universal fix |

- **Zero unexplained prose changes.** No private-corpus result (60 inputs x 9 profiles), no pinned fixture and none of the other nine synthetic cases changed; `Clan Valor`, `Valor Clan`, `Valor`, possessives and surrounding prose are identical (the invariant check passes on all 9 profiles, and `test_clan_valor_valor_clan_and_valor_are_never_rewritten` runs it on every roster profile).
- The 18 audit-rule-count changes fall on the same 18 results (Shadow Slave loses the two retired rows; the other eight gain the one promoted row). The three summary rows are unchanged everywhere.
- The approved list is stored beside the baseline as `files/checkpoints/baselines/script-only/APPROVED-DELTAS-P01.json` (ignored); the original Phase 00 baseline files were not modified.
- **One non-prose, non-row audit change:** the JSONL `run_metadata.pipeline` header value is now `pipelines.universal` for every run (it named the per-novel module). Tests were updated accordingly.

### Test changes in 01C
Suite went from 637 to **708** node IDs: 6 IDs renamed one-to-one (the `test_junk_strip_hardening` pipeline parametrisations `[shadow_slave|lord_of_mysteries]` -> `[Shadow Slave|Universal]`; `test_dual_mode_provenance::test_ss_special_fix_code_not_called_in_universal_mode` -> `..._special_fix_map_is_never_applied_in_universal_mode`; `test_novel_registry::test_universal_fallback_applies_no_special_fixes` -> `..._no_profile_special_fixes`) and **71 new** (`test_universal_engine` 52, `test_profile_corrections` 19). Dispatch-identity assertions (`d.run_pipeline is X.run_pipeline`) became profile assertions (`d.run_pipeline.profile ...`); ~40 direct pipeline calls now go through `resolve_dispatch(...)`. Two existing tests changed meaning on purpose because `carcassess` is now universal: the "bait untouched in universal mode" test (now asserts `Almanach` untouched and `carcassess` corrected) and the NQ/SM "Shadow Slave bait survives" test (same). No test was deleted without a replacement, skipped, or loosened to pass.

## Verification summary (Gate 01 evidence)

| Check | Result |
|---|---|
| Full suite, offline harness, keys unset in child only | **708 passed, 0 skipped, 0 failed** |
| Same, with `--require-local-corpora` | **708 passed** (the 8 formerly skipped corpus tests run and are mandatory-capable) |
| `scripts/verify.py` (all four checks) on the 01C working tree | **PASS** (pins `==`, CHANGELOG = BRIEFING = `config.toml` = v0.13.0) |
| Frozen baseline, 828 results | 810 identical; 18 changed = the approved list above; 0 unexplained |
| Mandatory name invariants (`Clan Valor` etc.), all 9 profiles, direct + PDF | pass |
| Network attempts logged (verifier, baseline runs, workload) | **0** |
| No runtime dependency on the AI-era packages | `.venv` still holds **22 dormant distributions** (not purged, per plan: `annotated-types anyio certifi distro google-auth google-genai groq h11 httpcore httpx idna ollama pyasn1 pyasn1-modules pydantic pydantic-core requests sniffio tenacity typing-inspection urllib3 websockets`). With imports of all 21 of their top-level modules refused, `main.py --check` and a real `run_batch` over a pinned fixture still succeed and **0** dormant modules load (`files/test-logs/p00/dormant_dep_proof.py`). |
| Declared dependencies | `ollama`, `google-genai`, `groq` removed; `requirements.txt` has no AI SDK (test). A *fresh* non-AI environment was not built: that needs an install, which Phase 01 did not authorise. |
| Python 3.10 | Not exercised (no 3.10 interpreter on this machine). Covered by metadata (Phase 00), by `test_scaffold` using the `sys.version_info` switch, and by a test that `tomli` and `tomllib` parse `config.toml` identically. The new corrections loader uses the same switch. |
| Launch | `main.py --check` passes from an unrelated CWD; both root launchers point at `scripts/main.py`. A real double-click launch and a visual/Tk interaction check were **not** run (manual gate, Phase 02/04). |

### Real skip reasons and the intermittent Tk fault
- **Skips:** none in the final runs. (Phase 00 had 8, all corpus-name mismatches; they now run on hash-pinned fixtures.)
- **Intermittent Tk fault reproduced and now surfaced.** One full run during 01C returned `707 passed, 1 skipped, 1 error` because `tkinter.Tk()` raised `invalid command name "tcl_findLibrary"` (the Phase 00 family of Tcl-library read failures on HOME-PC). Under the old behaviour that would have been a silent "no display" skip and `verify` would still have exited 0; the strict-Tk fixture turned it into an **error carrying the real Tcl message** and a non-zero exit (log kept ignored as `verify-stdout-01C-run1-tkflake.log`). An immediate rerun on the unchanged tree was clean (708 passed). Cause remains unproven; nothing on the machine was changed. Gate evidence therefore means a run with **no** Tk error, and any Tk error is rerun and recorded, never accepted as a pass.

## Corrections to the Phase 00 report
- Supreme Magus has **15** special-fix entries, not 13 (Phase 00 sections 8.3 and 8.4 said 13).
- The Phase 00 ledger classed `test_dual_mode_provenance` as a removal candidate and under-counted extractions from `test_ai_gui_controls` (layout and pace tests); both were corrected here (see the findings above).

## Other findings for the reviewer
- **Canonical-name floors stay as Python modules** next to the indexes. Folding them into the index files would change lexicon load order (placeholder numbering, equal-length ties), which the exact-baseline rule forbids; it gains nothing editorially yet. Flagged rather than done.
- **`tomli` is now a runtime dependency on Python 3.10** (the loader reads TOML); the requirements note says so.
- **`verify.py` reads the first version-like line of `BRIEFING.md`.** A banner I first added above the `## Version` heading made it read 0.4.0 and fail; the gate was *not* changed. The banner is now a blockquote after the heading.
- The legacy cloud manifests and key files are untouched by anything here.

## Review handoff (fresh Claude Code session)
- **Range:** base `0c1ac0b1e883ce2061f5ee67bccc2fbf00da2183` (approved Gate 00 checkpoint) to the branch head of `origin/feature/0.4.0-script-only-editor`. Do not review `main`, and do not edit product files.
- **Review the 01B pair separately:** `git diff -M a7c1aec^ a7c1aec` must show only `R100` renames; `git diff 275fe8f^ 275fe8f` is path text only.
- **Where to look hardest:** (1) the asterisk/hash invariant adaptation in `test_junk_strip_corpus.py` and the vacuity fix in `test_novel_profiles.py` (judgement calls); (2) `core/run_manifest.py` schema 2 and the legacy-manifest refusal; (3) the autouse fixtures in `files/tests/conftest.py` (network denial, strict Tk) for ways a test could slip past them; (4) `git diff -M 275fe8f -- scripts/pipelines/` (`shadow_slave.py` -> `universal.py`: git reports only 57% similarity because the file roughly doubled, but the diff is purely additive structure - the profile dataclass, the two fix appliers, three `if profile.summary_rows` guards around existing lines, and `bind`; every stage call and both Unicode regex lines are unchanged) and `scripts/core/novel_registry.py`; (5) `profiles/loader.py` validation; (6) the deleted-file list for anything shared that was lost.
- **Commands (HOME-PC, project `.venv`):** `.venv\Scripts\python.exe scripts\verify.py` for the gate; `.venv\Scripts\python.exe -m pytest files\tests --require-local-corpora -rs` for the strict run. Clear `GEMINI_API_KEY` / `GROQ_API_KEY` in the child environment only.
- **Exact baseline rerun (ignored harness, present on this machine):** `.venv\Scripts\python.exe files\test-logs\p00\freeze_baselines.py deltas` (about 10 minutes) recomputes all 828 results and prints every difference; the expected answer is exactly the 18 listed above (`files/checkpoints/baselines/script-only/APPROVED-DELTAS-P01.json`). `verify` mode demands zero differences and will therefore report those 18.
- **Per-node test ledger:** `files/test-logs/p00/test-disposition-ledger-01A.csv` (1,275 old IDs -> fate and replacements) plus the 01C changes above.
- **Remaining limits (not defects):** no Python 3.10/3.11 interpreter, no macOS, no real double-click launch or Tk interaction check, the workload resume/retry exercise (needs Phase 02A), the `.venv` still holds the dormant packages, and the Tk Tcl-library fault is intermittent and unexplained.

## Next allowed step
**STOP at Gate 01.** Phase 02A, merge, tags and releases require your explicit approval after the independent review.
