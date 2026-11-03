# WNE Phase 02B — Desktop and bootstrap checkpoint

Status: **PASS (internal Gate 02, 2026-11-01)** — technical acceptance met; human visual checks
are collected for the final release gate (see "Manual checks pending").
Scope: Master Plan §7 / Phase 02B — compact desktop, Activity/logging, Preferences & Data,
bootstrap/launcher, root launchers.
Writer: Claude Code, Opus 5.5 / xHigh, HOME-PC (Windows 11).
Independent reviewer: none scheduled here (user directive, DECISIONS 078); the single final
Codex review covers the complete v0.4.0 candidate.

## Git state

- Branch `feature/0.4.0-script-only-editor`; input = Gate 02A remediation `08f1010`
  (local = tracking = live origin before work). Unrelated untracked
  `md-instructions/plan-2-ai-editor-integration.md` preserved, never staged.
- Commit SHA for this slice is resolved in the CLI report (a commit cannot contain its own SHA).

## Implementation

- `scripts/gui/app.py` — rewritten layout: header; horizontal `ttk.Panedwindow` with four
  numbered groups left (1. Sources, 2. Novel & Editing, 3. Output, 4. Run) and the Activity pane
  right (Summary/Detailed notebook, Clear Log); bottom status bar (state text, persistent Dark
  mode toggle, Preferences & Data…, Open Log Folder). No sidebar. Minimum 900×620; every
  control and the status bar stay visible at minimum size. Unified PDF/TXT queue with Add
  Files/Add Folder/Move Up/Move Down/Remove/Clear All and Include subfolders; protected-term
  count per novel; PDF/TXT toggles; effective output root (default/custom); Open Output Folder;
  session-only audit/debug/dry-run; Start/Pause⇄Continue/Stop/Resume Run…/Resume Recent/
  Retry Failed; progress, completed/failed/skipped counts, measured elapsed time and the existing
  measured rate/ETA. Shortcuts bound to the list only (Ctrl/Cmd+A, Delete/Backspace,
  Alt+Up/Down), Ctrl/Cmd+A in Activity text, Ctrl/Cmd+O Add Files.
- Threading: Start/Resume freezes an immutable `RunRequest`. The worker calls only
  `Activity.emit` (log lines, coalesced progress, per-item outcomes, done/error/stale); the Tk
  thread drains with `ActivityPump`. Window close during a run asks, requests a safe-boundary
  stop and destroys Tk only after the worker's completion event.
- `scripts/gui/activity.py` — adapted from PDF-Splitter `activity.py` (`edcbd4f`): bounded
  coalescing channel, capped Summary/Detailed model, fail-once session log, Tk-free pump; bridge
  from the batch runner's `gui_log(message, level)`; diagnostics bounded to 300 chars; session
  logs `files/runtime-data/logs/session-YYYYMMDD-HHMMSS.log`, retention = latest 20 closed
  application session logs (exact-name match only; active log never pruned).
- `scripts/gui/appearance.py` — ACT (`62b0c09`) Light/Dark palettes and compact metrics on the
  existing `clam` theme; live in-place repaint of ttk and raw Tk widgets; combobox drop-down
  recolor; best-effort native dark title bar (Windows DWM / macOS appearance).
- `scripts/gui/preferences.py` — ACT-style Preferences & Data modal: default/custom output folder
  (Browse/Save with feedback and validation), log location/retention + Open Log Folder, Reset
  Preferences (confirmed; removes only `settings.json`), live theme following.
- `scripts/utils/settings.py` — validated preferences (appearance, novel, formats, include
  subfolders, output root) in the existing per-user `settings.json`; unrelated/legacy keys
  preserved verbatim; legacy key files never opened; reset deletes only the exact file.
- `scripts/core/batch_runner.py` — additive only: `item_result(source, outcome)` callback and one
  Detailed line per file (stage timings + edit-category counts). No editorial change.
- `scripts/bootstrap.py` — adapted from PDF-Splitter bootstrap (`edcbd4f`): stdlib-only;
  ASSESS→RECONCILE/REPAIR→PROVE→LAUNCH→REPORT; Python ≥ 3.10 (tested 3.13/3.12/3.11/3.10
  preferred); 3.10-safe config reader; exact-pin verification; pip check; `launcher.py --check`
  smoke; health record after full proof; in-place repair of missing packages; rebuild only from
  an external interpreter; Store-alias exclusion; deletion guard (project path, no link/junction,
  venv-shaped contents only, never from inside the venv); detached launch with immediate-failure
  detection. Healthy fast path never installs, upgrades pip or uses the network.
- `scripts/launcher.py` — headless `--help`/`--version` (config.toml via tomllib/tomli),
  delegated `--check`, lazy GUI, visible non-zero startup errors with the log location.
- Root launchers (names unchanged; `.bat` CRLF, `.command` LF/100755) — thin wrappers: offline
  `--launch-only` first; then external Python discovery (py launcher, user/system install dirs,
  PATH, never WindowsApps aliases or Apple's `/usr/bin/python3`); consent-gated user-scope
  `winget install Python.Python.3.13` (ID verified as PSF/python.org) or python.org guidance on
  macOS (no automatic Homebrew); in-place repair with the existing venv when no Python exists;
  window stays open with "Press Enter to close".
- `scripts/verify.py` — fifth check: `launcher.py --version` equals the config version.

## Validation

- Strict offline verifier (project `.venv` 3.13.12, `PYTEST_ADDOPTS=--require-local-corpora -rs`,
  provider variables removed, network guard in the child): **889 passed, 0 skipped, 0 failed**,
  all five checks PASS (new: launcher `--version` equals config), **zero network attempts**
  (`files/test-logs/rc/verify-02b-3.*`, final tree). Frozen corpus after 02B: 828 = 810 identical +
  18 approved Phase 01 deltas, zero unexpected, all protection invariants true.
- Real Windows Tk: all `test_app.py` (29) and `test_gui_desktop.py` (10) cases execute in fresh
  guarded children with real widgets; zero skips. Includes a real worker thread with Tk methods
  instrumented (no Tk call off the main thread), close-during-run, theme repaint preserving
  selection/scroll/text/progress/tab, Preferences reset with sentinel `secrets.json`/siblings
  unchanged, and a real TXT→PDF+TXT run whose session log contains names/counts but no chapter text.
- Bootstrap: 25 tests — real offline `--venv-check` on the project `.venv` under the network guard;
  a real interpreter-only sandbox venv fails the fast path unchanged; deletion guard vs junction,
  unexpected files, in-venv execution and locked files; no-Python and alias-only simulations;
  tested-version preference; immediate launch failure detected.
- Root launchers: the `.bat` really executes in a sandbox path with spaces, parentheses and "Ü":
  healthy fast path (stripped PATH, no base Python needed), launch failure, repair via external
  Python with a Store-alias look-alike first on PATH (never executed), in-place repair without
  Python, declined install (nothing installed), missing helper. The `.command` control flow runs
  under Git Bash with stub interpreters (not macOS execution); `bash -n` passes.
- Screenshots (ignored, `files/run-temp/p02b/*.png`) of Light, Dark, minimum size and Preferences
  were inspected: compact ACT vocabulary, four groups, dark native title bar.

## Test disposition (Phase 02B)

| Retired node (old contract) | Disposition | Replacement |
|---|---|---|
| `test_app::test_app_constructs_and_has_widgets`, `test_app_paired_product_naming_and_min_size`, `test_app_layout_order_matches_scraper`, `test_the_log_sits_beside_the_controls_not_below_them`, `test_the_window_can_be_made_short_enough_for_a_1080p_screen`, `test_both_columns_fit_inside_the_minimum_window_width`, `test_the_run_controls_sit_inside_the_minimum_window_height`, `test_every_fixed_row_fits_inside_the_minimum_window_height` | Old two-column layout superseded by §7.1 | `test_four_numbered_groups_activity_pane_and_status_bar`, `test_minimum_window_keeps_every_control_and_the_status_bar_visible` |
| `test_app_input_mode_defaults_to_upload_with_both_toggles`, `test_app_input_mode_switch_flips_panel_enablement`, `test_app_folder_mode_start_with_no_folder_warns` | Two-mode input replaced by one unified queue | `test_folder_import_respects_include_subfolders`, `test_empty_queue_warns_and_starts_nothing` |
| `test_app_folder_scan_displays_resolved_natural_order`, `test_app_folder_mode_start_runs_mirrored_batch_into_auto_downloads`, `test_app_upload_mode_uses_flat_auto_downloads_output` | Adapted | `test_mixed_queue_appends_new_natural_groups_without_resorting`, `test_folder_import_start_runs_into_default_downloads_root`, `test_direct_files_use_flat_default_output_and_numbering_advances` |
| `test_app_default_universal_start_passes_clean_name_and_universal_folder`, `test_app_marked_selection_strips_marker_before_batch_and_naming`, `test_app_real_profile_selection_passes_through_unchanged` | Merged | `test_novel_selection_reaches_dispatch_and_folder_as_clean_name[...]` (3 params) |
| `test_novel_combo_width_fits_longest_real_roster_entry`, `test_app_novel_combo_wide_enough_for_longest_entry` | Merged | `test_novel_combo_shows_the_longest_roster_entry_in_full` |
| `test_app_output_folder_picker_is_gone` | Destination now via Preferences | layout test asserts no Output browse control; `test_preferences_custom_default_and_validation_feedback` |
| `test_app_progress_resets_between_runs`, `test_app_pause_button_state_machine`, `test_app_start_batch_passes_pause_gate_and_resets_button`, `test_app_stop_button_state_placement_and_reset` | Adapted to event-driven worker | `test_start_wires_gates_counts_progress_and_resets_controls`, `test_pause_continue_stop_state_machine` |
| `test_rate_readout_clears_between_runs` | Merged | `test_progress_updates_publish_a_running_average_and_eta` |
| Kept/adapted: mixed queue, multiselect moves, no-formats, close during pause, explicit resume, custom root, legacy refusal, partial summary, no-AI controls, script-only arguments (now with `item_result`, without `mirror_root`) | Adapted in place | same names |
| `test_launchers::*` 15 static checks of the old 4-step self-installing scripts (`pip install` failure handling, step banners, in-script venv rebuild/version gate/preflight) | Superseded: dependency/venv work moved to `bootstrap.py` | executed `.bat`/`.command` flows, `test_bat_jumps_and_calls_only_defined_labels`, `test_both_launchers_enforce_the_python_3_10_floor_by_execution`, `test_bootstrap.py` (install failure, rebuild guard, health proof) |

## Manual checks pending (collected for the final release gate)

- Human visual acceptance of Light/Dark against the ACT references, real native file/folder
  dialogs, Preferences & Data, keyboard behavior and a normal double-click Windows launch.
- macOS: no actual macOS execution here; `.command` evidence is static + Git Bash simulation.
- Genuine Python-free machine (Windows Sandbox/VM) acquisition was not performed; discovery and
  missing-Python behavior are simulations.

## Next step

Phase 03 (conservative editorial rules) continues without an intermediate review.
