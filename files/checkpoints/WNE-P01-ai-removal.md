# WNE Phase 01 — checkpoint (remove AI, migrate the engine, consolidate)
Status: **IN PROGRESS** — slice 01A complete and verified; 01B and 01C follow. Final status is set at Gate 01.
Scope: Master Plan Revision 2, Phase 01 only (01A, 01B, 01C in order). No Phase 02 work.
Writer: Claude Code, model Sonnet 5.5, effort high. The prompt asked for Codex Sol 6.1 / High; that selection was not available to this session, so the actual selection is reported here as it differs.
Independent reviewer: pending — a fresh Claude Code session reviews after Phase 01 (Gate 01).
Machine: HOME-PC (Windows 11, Python 3.13.12 in the project `.venv`).

## Git state
- Branch: `feature/0.4.0-script-only-editor`, created from the exact approved checkpoint `0c1ac0b1e883ce2061f5ee67bccc2fbf00da2183` (identity confirmed: local HEAD, `origin/feature/plan-2b-cloud-providers` and the approved SHA were equal before branching).
- `feature/plan-2b-cloud-providers` is preserved unchanged at `0c1ac0b`. `origin/main` is `72d68caa3588856c063c62b9b39588fd965db603` and is not touched.
- Untouched user work: `md-instructions/plan-2-ai-editor-integration.md` (untracked historical AI instruction file) was never staged, edited or deleted.
- Slice commit SHAs are listed in the final CLI report (a commit cannot contain its own SHA).

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
