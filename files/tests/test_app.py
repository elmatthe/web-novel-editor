"""GUI smoke tests.

The real batch logic is tested headlessly in test_batch.py. Here we only confirm the
Tk window constructs with its core widgets and that the log/progress helpers work — run
when a display is available, skipped cleanly otherwise so the suite stays green headless.
"""

from __future__ import annotations

import os
import sys

import pytest
from pathlib import Path


@pytest.fixture
def mixed_app():
    if sys.platform == "win32" and os.environ.get("WNE_GUI_TEST_CHILD") != "1":
        yield None  # pytest_pyfunc_call executes this case with real Tk in its child.
        return
    tk = pytest.importorskip("tkinter")
    from gui.app import WebnovelEditorApp
    try:
        app = WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("Tk could not initialize; strict Windows fixture reports the error")
    app.withdraw()
    app.update_idletasks()
    yield app
    if app.winfo_exists():
        app.destroy()


def test_mixed_queue_appends_new_natural_groups_without_resorting(mixed_app, tmp_path, monkeypatch):
    from gui import app as appmod
    app = mixed_app
    folder = tmp_path / "Book"
    folder.mkdir()
    for name in ("10.txt", "2.pdf", "1.txt"):
        (folder / name).write_text("text")
    first = tmp_path / "manual.txt"
    first.write_text("text")
    app.file_paths = [str(first)]
    app._refresh_file_list()
    app.file_listbox.selection_set(0)
    app.file_listbox.activate(0)
    app._apply_input_folder(str(folder))
    assert [Path(p).name for p in app.file_paths] == ["manual.txt", "1.txt", "2.pdf", "10.txt"]
    monkeypatch.setattr(appmod.filedialog, "askopenfilenames", lambda **k: (str(folder / "2.pdf"), str(first)))
    app._add_pdfs()
    assert len(app.file_paths) == 4
    assert app.import_roots[str(folder / "1.txt")] == str(folder)
    assert app.file_listbox.curselection() == (0,)
    assert app.file_listbox.index("active") == 0


def test_manual_multiselect_moves_preserve_order_selection_and_focus(mixed_app):
    app = mixed_app
    app.file_paths = [f"{i}.txt" for i in range(4)]
    app._refresh_file_list()
    app.file_listbox.selection_set(1, 2)
    app.file_listbox.activate(2)
    app._move_selected(-1)
    assert app.file_paths == ["1.txt", "2.txt", "0.txt", "3.txt"]
    assert app.file_listbox.curselection() == (0, 1)
    assert app.file_listbox.index("active") == 1
    app._move_selected(1)
    assert app.file_paths == [f"{i}.txt" for i in range(4)]
    assert app.file_listbox.curselection() == (1, 2)


def test_no_formats_is_rejected_before_reserving_a_run(mixed_app, tmp_path, monkeypatch):
    from gui import app as appmod
    app = mixed_app
    app.file_paths = [str(tmp_path / "a.txt")]
    app.opt_pdf.set(False)
    app.opt_txt.set(False)
    warnings = []
    monkeypatch.setattr(appmod.messagebox, "showwarning", lambda *a: warnings.append(a))
    monkeypatch.setattr(appmod, "reserve_run_dir", lambda *a: pytest.fail("allocated without a format"))
    app._start_batch()
    assert warnings and not app._running


def test_close_during_pause_requests_stop_without_destroying_tk(mixed_app, monkeypatch):
    from gui import app as appmod
    app = mixed_app
    monkeypatch.setattr(appmod.messagebox, "askyesno", lambda *a, **k: True)
    app._running = True
    app.pause_gate.clear()
    app._on_close()
    assert app.winfo_exists() and app.stop_event.is_set() and app.pause_gate.is_set()
    assert app._exit_when_done


def test_explicit_resume_uses_frozen_settings_and_original_custom_destination(mixed_app, tmp_path, monkeypatch):
    from gui import app as appmod
    from core.batch_runner import run_batch
    src = tmp_path / "a.txt"
    src.write_text("Short prose.", encoding="utf-8")
    old = tmp_path / "old-run"
    run_batch([str(src)], str(old), output_formats=("txt",), novel_name="Shadow Slave", write_debug_text=True)
    calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
    mixed_app.output_root_var.set(str(tmp_path / "new-root"))
    mixed_app.opt_dry_run.set(True)
    mixed_app._resume_run(directory=str(old), retry_failed=True)
    mixed_app.update()
    assert len(calls) == 1
    assert calls[0]["output_dir"] == str(old)
    assert calls[0]["output_formats"] == ("txt",)
    assert calls[0]["dry_run"] is False and calls[0]["write_debug_text"] is True
    assert calls[0]["novel_name"] == "Shadow Slave"
    assert calls[0]["resume"] and calls[0]["retry_failed"]
    assert not (tmp_path / "new-root").exists()


def test_custom_output_root_is_used_directly(mixed_app, tmp_path, monkeypatch):
    from gui import app as appmod
    src = tmp_path / "a.txt"
    src.write_text("Short.", encoding="utf-8")
    calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
    mixed_app.file_paths = [str(src)]
    mixed_app.output_root_var.set(str(tmp_path / "custom"))
    mixed_app.opt_txt.set(True)
    mixed_app._start_batch()
    mixed_app.update()
    assert calls[0]["output_dir"] == str(tmp_path / "custom" / "universal-1")
    assert calls[0]["output_formats"] == ("pdf", "txt")


def test_legacy_resume_refusal_never_allocates_or_modifies(mixed_app, tmp_path, monkeypatch):
    from gui import app as appmod
    path = tmp_path / "run-manifest.json"
    path.write_text('{"schema_version":1,"provider":"legacy"}', encoding="utf-8")
    before = path.read_bytes()
    errors = []
    monkeypatch.setattr(appmod.messagebox, "showerror", lambda *a: errors.append(a))
    monkeypatch.setattr(appmod, "reserve_run_dir", lambda *a: pytest.fail("allocated during refusal"))
    mixed_app._resume_run(directory=str(tmp_path))
    assert errors and path.read_bytes() == before and not mixed_app._running


def test_partial_retry_summary_shows_run_incomplete(mixed_app, monkeypatch):
    from gui import app as appmod
    dialogs = []
    monkeypatch.setattr(appmod.messagebox, "showinfo", lambda *args: dialogs.append(args))
    mixed_app._on_done({"total": 3, "succeeded": 1, "failed": 0, "skipped": 0,
                        "completed_total": 2, "failed_total": 0, "pending_total": 1,
                        "run_complete": False, "output_dir": "original-run", "outputs": []})
    assert dialogs[0][0] == "Run incomplete"


def _all_descendants(widget):
    """Yield every widget in the tree rooted at ``widget`` (children first parent)."""
    for child in widget.winfo_children():
        yield child
        yield from _all_descendants(child)


def test_app_constructs_and_has_widgets():
    tk = pytest.importorskip("tkinter")
    # Import the GUI module lazily so the suite collects cleanly on a machine without
    # tkinter at all (gui.app imports tkinter at module load); skips here, runs on a
    # real machine with a display.
    from gui import app as appmod

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()           # avoid flashing a window during the test
        app.update_idletasks()   # force widget realization
        # Core widgets and state exist.
        assert app.file_paths == []
        assert app.run_button is not None
        assert app.progress is not None
        assert app.opt_dry_run.get() is False
        assert app.opt_replacement_log.get() is False
        assert app.opt_debug_text.get() is False
        # Novel dropdown exists, defaults to Universal (Plan 1 Phase 3), and offers
        # the full roster — Shadow Slave stays selectable, profile-less novels carry
        # the display-only roster marker.
        from core.novel_registry import UNIVERSAL_ONLY_MARKER as NO_PROFILE_MARKER
        assert app.novel_var.get() == "Universal"
        values = list(app.novel_combo["values"])
        assert values[0] == "Universal"
        assert "Shadow Slave" in values
        assert "Re Monster" + NO_PROFILE_MARKER in values
        assert str(app.novel_combo["state"]) == "readonly"
        # The log and progress helpers drive the real widgets without a mainloop.
        app._log("hello", "info")
        app._set_progress(2)
        app.update_idletasks()
        assert int(app.progress["value"]) == 2
    finally:
        app.destroy()


def test_app_paired_product_naming_and_min_size():
    """Phase 7: the window is titled to pair with 'Web Novel Scraper', and a minimum
    size is set so controls are never clipped on small windows (GUI hardening)."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()
        assert app.title() == "Web Novel Editor"
        # A real minimum size is enforced (protects against clipped/truncated controls).
        min_w, min_h = app.minsize()
        assert min_w >= appmod.MIN_WIDTH and min_h >= appmod.MIN_HEIGHT
    finally:
        app.destroy()


def test_app_layout_order_matches_scraper():
    """Structural alignment with web-novel-scraper: novel selection first, the run
    controls last in the control column, and the log alongside them.

    v0.13.0 moved the log from a bottom row to the right-hand column — as a bottom row
    the window had to be tall enough for the controls *plus* the log, which clipped
    both the log and the status strip off a 1080p screen."""
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk
    from gui import app as appmod

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()

        # Grid rows of the section frames (widgets are gridded into a common root frame).
        novel_row = int(app.novel_combo.master.grid_info()["row"])
        files_row = int(app.file_listbox.master.master.grid_info()["row"])
        run_row = int(app.run_button.master.grid_info()["row"])
        log_row = int(app.log_text.master.grid_info()["row"])

        # Novel/source selection comes first (before the file list).
        assert novel_row < files_row
        # The log is its own column beside the controls, never below them (v0.13.0).
        # As a bottom row the window had to be tall enough for the controls *plus* the
        # log, which clipped both the log and the status strip off a 1080p screen.
        assert int(app.log_text.master.grid_info()["column"]) == 1
        assert int(app.run_button.master.grid_info()["column"]) == 0
        # It spans the control rows rather than occupying one of its own.
        assert log_row <= run_row

        # Advanced/debug/dry-run controls are grouped under their own labelled card so
        # they don't dominate the primary workflow.
        labelframe_texts = {
            str(w.cget("text"))
            for w in _all_descendants(app)
            if isinstance(w, ttk.Labelframe)
        }
        assert "Advanced Options" in labelframe_texts
        assert "Novel" in labelframe_texts
    finally:
        app.destroy()


def test_novel_combo_width_fits_longest_real_roster_entry():
    """The novel dropdown must be wide enough to show the longest real roster label
    (e.g. 'Circle of Inevitability — universal rules only') without truncation. The width is
    computed from the live registry, not a guessed constant, so onboarding a longer
    novel name keeps the widget correct. Pure-helper level: needs tkinter importable
    but no display."""
    pytest.importorskip("tkinter")
    from gui import app as appmod
    from core.novel_registry import available_novels

    roster = available_novels()
    longest = max(len(label) for label in roster)
    # The helper returns a character width in font-average units; it must be at least
    # as wide as the longest label so the closed display and the open list both fit it.
    assert appmod._novel_combo_width(roster) >= longest


def test_app_novel_combo_wide_enough_for_longest_entry():
    """Display-gated: the realized combobox widget is sized to the longest roster label,
    so the closed display and the dropdown list never truncate 'Circle of Inevitability
    — universal rules only'."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod
    from core.novel_registry import available_novels

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()
        longest = max(len(label) for label in available_novels())
        assert int(app.novel_combo["width"]) >= longest
    finally:
        app.destroy()


def test_app_input_mode_defaults_to_upload_with_both_toggles():
    """Plan 1 Phase 1: two mutually exclusive input modes exist; Upload is default."""
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk
    from gui import app as appmod

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()

        assert app.input_mode_var.get() == "upload"
        radio_texts = {
            str(w.cget("text"))
            for w in _all_descendants(app)
            if isinstance(w, ttk.Radiobutton)
        }
        assert "PDF / TXT files" in radio_texts
        assert "Select Folder" in radio_texts

        # Upload mode active: upload buttons enabled, folder picker disabled.
        assert "disabled" not in app.add_button.state()
        assert "disabled" in app.choose_folder_button.state()
    finally:
        app.destroy()


def test_app_input_mode_switch_flips_panel_enablement():
    """Selecting the other mode disables the inactive mode's controls (and back)."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()

        app.input_mode_var.set("folder")
        app._on_input_mode_changed()
        app.update_idletasks()
        assert "disabled" in app.add_button.state()
        assert "disabled" not in app.remove_button.state()
        assert "disabled" not in app.clear_button.state()
        assert "disabled" not in app.choose_folder_button.state()

        app.input_mode_var.set("upload")
        app._on_input_mode_changed()
        app.update_idletasks()
        assert "disabled" not in app.add_button.state()
        assert "disabled" in app.choose_folder_button.state()
    finally:
        app.destroy()


def test_app_folder_scan_displays_resolved_natural_order(tmp_path):
    """Choosing a folder resolves the ordered list (input_scanner contract) and shows
    it in the file list, as relative paths in that exact order."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod

    for name in ("10.pdf", "1.pdf", "2.pdf"):
        (tmp_path / name).write_bytes(b"%PDF-stub")
    sub = tmp_path / "extras"
    sub.mkdir()
    (sub / "5.pdf").write_bytes(b"%PDF-stub")

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()

        app.input_mode_var.set("folder")
        app._on_input_mode_changed()
        app._apply_input_folder(str(tmp_path))
        app.update_idletasks()

        shown = list(app.file_listbox.get(0, "end"))
        assert shown == [f"{tmp_path.name}/{rel}" for rel in ["1.pdf", "2.pdf", "10.pdf", "extras/5.pdf"]]
        assert [p.name for p in app.folder_files] == ["1.pdf", "2.pdf", "10.pdf", "5.pdf"]
    finally:
        app.destroy()


class _ImmediateThread:
    """Test double for threading.Thread: runs the target synchronously on start()."""

    def __init__(self, target=None, daemon=None):
        self._target = target

    def start(self):
        self._target()


def _wire_batch_spy(appmod, monkeypatch, tmp_path):
    """Patch the batch seam for GUI tests: synchronous worker, run_batch spy,
    downloads under tmp_path, and silenced dialogs. Returns the spy call list."""
    calls = []

    def spy_run_batch(pdf_paths, output_dir, **kwargs):
        calls.append({"pdf_paths": list(pdf_paths), "output_dir": output_dir,
                      **kwargs})
        return {"total": len(pdf_paths), "succeeded": len(pdf_paths), "failed": 0,
                "skipped": 0, "output_dir": output_dir, "outputs": [],
                "novel": "x", "profile_applied": False}

    monkeypatch.setattr(appmod.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(appmod, "run_batch", spy_run_batch)
    monkeypatch.setattr(appmod, "downloads_dir", lambda: tmp_path / "DL")
    monkeypatch.setattr(appmod.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(appmod.messagebox, "showwarning", lambda *a, **k: None)
    return calls


def test_app_folder_mode_start_runs_mirrored_batch_into_auto_downloads(
        tmp_path, monkeypatch):
    """Phase 2 replaces the Phase-1 folder-mode stub: Start in folder mode now runs a
    real batch — the scanned natural-order list, an auto-numbered Downloads\\<name>-x
    output folder (never user-chosen), and the selected folder mirrored inside it."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod

    src = tmp_path / "MyNovel"
    src.mkdir()
    for name in ("10.pdf", "1.pdf"):
        (src / name).write_bytes(b"%PDF-stub")

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)

        app.input_mode_var.set("folder")
        app._on_input_mode_changed()
        app._apply_input_folder(str(src))
        app._start_batch()
        app.update()

        assert len(calls) == 1, "folder-mode Start must launch exactly one batch"
        call = calls[0]
        # Scanned order preserved, passed as concrete paths.
        assert [os.path.basename(p) for p in call["pdf_paths"]] == ["1.pdf", "10.pdf"]
        # Output is forced to Downloads\<kebab-novel>-1 (first run) and mirrors the
        # selected folder itself inside it.
        expected_name = appmod.kebab_case(app.novel_var.get()) + "-1"
        assert call["output_dir"] == str(tmp_path / "DL" / "PDF-Editor-Outputs" / expected_name)
        assert call["mirror_root"] is None
        assert call["import_roots"] == {p: str(src) for p in call["pdf_paths"]}
        assert app._running is False  # synchronous fake thread completed the run
    finally:
        app.destroy()


def test_app_upload_mode_uses_flat_auto_downloads_output(tmp_path, monkeypatch):
    """Upload mode also outputs to the auto-numbered Downloads folder, flat
    (no mirror root)."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-stub")

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)

        app.file_paths.append(str(pdf))
        app._refresh_file_list()
        app._start_batch()
        app.update()

        assert len(calls) == 1
        call = calls[0]
        assert call["pdf_paths"] == [str(pdf)]
        expected_name = appmod.kebab_case(app.novel_var.get()) + "-1"
        assert call["output_dir"] == str(tmp_path / "DL" / "PDF-Editor-Outputs" / expected_name)
        assert call["mirror_root"] is None
    finally:
        app.destroy()


def test_app_folder_mode_start_with_no_folder_warns(tmp_path, monkeypatch):
    """Folder mode with nothing scanned warns instead of starting (parallel to the
    upload-mode empty-list guard)."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
        warnings = []
        monkeypatch.setattr(appmod.messagebox, "showwarning",
                            lambda *a, **k: warnings.append(a))

        app.input_mode_var.set("folder")
        app._on_input_mode_changed()
        app._start_batch()
        app.update_idletasks()

        assert calls == []
        assert warnings
        assert app._running is False
    finally:
        app.destroy()


def test_app_default_universal_start_passes_clean_name_and_universal_folder(
        tmp_path, monkeypatch):
    """Plan 1 Phase 3: with the default "Universal" selection, Start passes the clean
    name "Universal" to run_batch and the output folder comes out as universal-1."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-stub")

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)

        assert app.novel_var.get() == "Universal"
        app.file_paths.append(str(pdf))
        app._refresh_file_list()
        app._start_batch()
        app.update()

        assert len(calls) == 1
        call = calls[0]
        assert call["novel_name"] == "Universal"
        assert call["output_dir"] == str(tmp_path / "DL" / "PDF-Editor-Outputs" / "universal-1")
    finally:
        app.destroy()


def test_app_marked_selection_strips_marker_before_batch_and_naming(
        tmp_path, monkeypatch):
    """Selecting a marked profile-less novel must reach run_batch (and the output-folder
    kebab-casing) as the CLEAN name — the display marker never leaks downstream."""
    tk = pytest.importorskip("tkinter")
    from core.novel_registry import UNIVERSAL_ONLY_MARKER as NO_PROFILE_MARKER
    from gui import app as appmod

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-stub")

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)

        marked = "Re Monster" + NO_PROFILE_MARKER
        assert marked in app.novel_combo["values"]  # still selectable
        app.novel_var.set(marked)
        app.file_paths.append(str(pdf))
        app._refresh_file_list()
        app._start_batch()
        app.update()

        assert len(calls) == 1
        call = calls[0]
        assert call["novel_name"] == "Re Monster"
        assert call["output_dir"] == str(tmp_path / "DL" / "PDF-Editor-Outputs" / "re-monster-1")
    finally:
        app.destroy()


def test_app_real_profile_selection_passes_through_unchanged(tmp_path, monkeypatch):
    """Selecting a real-profile novel (Shadow Slave) is unaffected by the Phase-3
    mapping: its unmarked name reaches run_batch and its folder naming as before."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-stub")

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)

        assert "Shadow Slave" in app.novel_combo["values"]
        app.novel_var.set("Shadow Slave")
        app.file_paths.append(str(pdf))
        app._refresh_file_list()
        app._start_batch()
        app.update()

        assert len(calls) == 1
        call = calls[0]
        assert call["novel_name"] == "Shadow Slave"
        assert call["output_dir"] == str(tmp_path / "DL" / "PDF-Editor-Outputs" / "shadow-slave-1")
    finally:
        app.destroy()


def test_app_output_folder_picker_is_gone():
    """Phase 2 removes the user-chosen output location entirely: no 'Output Folder'
    card, no 'Choose Output Folder' button, no output-path state on the app."""
    tk = pytest.importorskip("tkinter")
    from tkinter import ttk
    from gui import app as appmod

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()

        labelframe_texts = {
            str(w.cget("text"))
            for w in _all_descendants(app)
            if isinstance(w, ttk.Labelframe)
        }
        assert "Output Folder" not in labelframe_texts
        button_texts = {
            str(w.cget("text"))
            for w in _all_descendants(app)
            if isinstance(w, ttk.Button)
        }
        assert "Choose Output Folder" not in button_texts
        assert not hasattr(app, "output_var")
        assert not hasattr(app, "output_dir")
    finally:
        app.destroy()


def test_app_progress_resets_between_runs():
    """Phase 7 GUI hardening: progress can be driven up and reset back to zero, so a
    second run never starts with a stale progress value."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()
        # Run button starts enabled and not-running.
        assert app._running is False
        assert str(app.run_button["state"]) in ("normal", "!disabled")

        app._set_progress(5)
        app.update_idletasks()
        assert int(app.progress["value"]) == 5

        # Reset (as _start_batch does before a new run) returns the bar to zero.
        app.progress.configure(maximum=3, value=0)
        app.update_idletasks()
        assert int(app.progress["value"]) == 0
    finally:
        app.destroy()


def test_app_pause_button_state_machine():
    """Plan 1 Phase 4: a Pause button exists next to Start — disabled while idle, and
    while a batch runs it toggles Pause ⇄ Continue by clearing/setting the pause gate
    (the worker holds between files while the gate is cleared)."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()

        # Idle: button present, disabled, labelled Pause; toggling is a no-op.
        assert str(app.pause_button["state"]) == "disabled"
        assert str(app.pause_button["text"]) == "Pause"
        app._toggle_pause()
        assert str(app.pause_button["text"]) == "Pause"

        # Running: Pause clears the gate and relabels; Continue sets it back.
        app._running = True
        app.pause_gate.set()
        app._toggle_pause()
        assert not app.pause_gate.is_set()
        assert str(app.pause_button["text"]) == "Continue"
        app._toggle_pause()
        assert app.pause_gate.is_set()
        assert str(app.pause_button["text"]) == "Pause"
    finally:
        app.destroy()


def test_app_start_batch_passes_pause_gate_and_resets_button(tmp_path, monkeypatch):
    """Start wires the app's pause gate into run_batch (set = running), and batch
    completion disables the button and restores the Pause label + open gate."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-stub")

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)

        app.file_paths.append(str(pdf))
        app._refresh_file_list()
        app._start_batch()
        app.update()

        assert len(calls) == 1
        assert calls[0]["pause_gate"] is app.pause_gate
        assert app.pause_gate.is_set()  # a fresh batch always starts un-paused
        # The synchronous fake thread already finished: back to idle state.
        assert app._running is False
        assert str(app.pause_button["state"]) == "disabled"
        assert str(app.pause_button["text"]) == "Pause"
    finally:
        app.destroy()


def test_app_stop_button_state_placement_and_reset(tmp_path, monkeypatch):
    """Stop sits beside Pause, is run-only, and a later run starts cleared."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-stub")
    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    try:
        app.withdraw()
        app.update_idletasks()
        assert str(app.stop_button["state"]) == "disabled"
        assert int(app.stop_button.grid_info()["column"]) == (
            int(app.pause_button.grid_info()["column"]) + 1
        )

        app._running = True
        app.stop_button.configure(state=tk.NORMAL)
        app.stop_event.clear()
        app._request_stop()
        assert app.stop_event.is_set()
        assert str(app.stop_button["state"]) == "disabled"

        app._reset_stop_control()
        assert not app.stop_event.is_set()
        assert str(app.stop_button["state"]) == "disabled"

        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
        app._running = False
        app.file_paths.append(str(pdf))
        app._refresh_file_list()
        app._start_batch()
        app.update()
        assert calls[0]["stop_event"] is app.stop_event
        assert not app.stop_event.is_set()
    finally:
        app.destroy()


# ---------------------------------------------------------------------------
# Layout, pace readout and script-only start (re-homed from test_ai_gui_controls in
# Phase 01A, when the AI card and its test module were removed)
# ---------------------------------------------------------------------------
def _new_app():
    """Construct the window, withdrawn. A Tk failure is reported by conftest, not hidden."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod

    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    app.withdraw()
    app.update_idletasks()
    return appmod, app


def test_the_window_has_no_ai_or_cloud_controls():
    """Phase 01A removed the optional AI pass: no widget may mention it."""
    _appmod, app = _new_app()
    try:
        banned = ("ai ", " ai", "provider", "ollama", "gemini", "groq", "api key",
                  "model", "cloud", "consent", "quota")
        texts = []
        for widget in [app, *_all_descendants(app)]:
            try:
                texts.append(str(widget.cget("text")).lower())
            except Exception:
                continue
        offenders = [t for t in texts if t and any(b in f" {t} " for b in banned)]
        assert offenders == []
        for attr in ("ai_model_combo", "ai_provider_combo", "ai_key_button",
                     "opt_ai_enabled", "ai_status_var", "ai_prefs"):
            assert not hasattr(app, attr), f"leftover AI member {attr}"
    finally:
        app.destroy()


def test_start_passes_only_the_script_only_arguments(tmp_path, monkeypatch):
    """Nothing AI- or checkpoint-shaped is handed to run_batch any more."""
    appmod, app = _new_app()
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-stub")
    try:
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
        app.file_paths.append(str(pdf))
        app._refresh_file_list()
        app._start_batch()
        app.update()
        assert len(calls) == 1
        assert set(calls[0]) == {
            "pdf_paths", "output_dir", "write_replacement_log", "write_debug_text",
            "dry_run", "novel_name", "mirror_root", "pause_gate", "stop_event",
            "gui_log", "progress",
            "output_formats", "import_roots", "resume", "retry_failed", "recover_stale",
        }
    finally:
        app.destroy()


def test_the_log_sits_beside_the_controls_not_below_them():
    """The log was clipped off the bottom of a 1080p screen when it was a bottom row.

    It is the right-hand column, so the control stack's height no longer has to
    accommodate it at all, and every control keeps its natural size at any window size.
    """
    _appmod, app = _new_app()
    try:
        assert int(app.log_text.master.grid_info()["column"]) == 1
        for card in (app.file_listbox.master.master, app.novel_combo.master,
                     app.run_button.master):
            assert int(card.grid_info()["column"]) == 0
    finally:
        app.destroy()


def test_the_window_can_be_made_short_enough_for_a_1080p_screen():
    """The opening geometry is capped at `screenheight - 90`, but `minsize` overrides it,
    so a MIN_HEIGHT above that cap means the bottom of the window is off the desktop.
    1080p is the smallest display this is expected to run on."""
    appmod, app = _new_app()
    try:
        usable = 1080 - 90
        assert appmod.MIN_HEIGHT <= usable, (
            f"MIN_HEIGHT is {appmod.MIN_HEIGHT}px but only {usable}px is usable on a "
            f"1080p desktop - the bottom of the window cannot be reached"
        )
    finally:
        app.destroy()


def _grid_extent(app, appmod):
    """Measured height and width the root grid actually needs.

    A two-column grid (controls left, log right) cannot be measured by summing every
    child: the log shares rows with the cards, so a flat sum double-counts. The real
    requirement is per **row** for height and per **column** for width - the largest
    requested size in each, plus that row's/column's padding. The log is excluded from
    the height side only: it is the one widget allowed to shrink.
    """
    root = app.winfo_children()[0]
    log_frame = app.log_text.master

    rows: dict[int, int] = {}
    cols: dict[int, int] = {}
    for child in root.winfo_children():
        info = child.grid_info()
        row, col = int(info["row"]), int(info["column"])

        def _pad(value):
            return sum(value) if isinstance(value, tuple) else int(value)

        pady, padx = _pad(info.get("pady", 0)), _pad(info.get("padx", 0))
        height = pady if child is log_frame else child.winfo_reqheight() + pady
        rows[row] = max(rows.get(row, 0), height)
        cols[col] = max(cols.get(col, 0), child.winfo_reqwidth() + padx)

    return (sum(rows.values()) + 2 * appmod.PAD_M,
            sum(cols.values()) + 2 * appmod.PAD_M)


def test_both_columns_fit_inside_the_minimum_window_width():
    appmod, app = _new_app()
    try:
        _height, width = _grid_extent(app, appmod)
        assert width <= appmod.MIN_WIDTH, (
            f"the two columns need {width}px but the window can be as narrow as "
            f"{appmod.MIN_WIDTH}px - the log or the controls would be clipped"
        )
    finally:
        app.destroy()


def _offset_below_toplevel(widget) -> int:
    """A widget's y offset inside its window, valid without the window being shown."""
    offset = 0
    node = widget
    while node.master is not None:
        offset += node.winfo_y()
        node = node.master
    return offset


def test_the_run_controls_sit_inside_the_minimum_window_height():
    """Start/Pause/Stop are the controls the user must be able to reach."""
    appmod, app = _new_app()
    try:
        app.update_idletasks()
        for button in (app.run_button, app.pause_button, app.stop_button):
            bottom = _offset_below_toplevel(button) + button.winfo_reqheight()
            assert bottom <= appmod.MIN_HEIGHT, (
                f"{button['text']!r} ends at {bottom}px, past the "
                f"{appmod.MIN_HEIGHT}px minimum window height"
            )
    finally:
        app.destroy()


def test_every_fixed_row_fits_inside_the_minimum_window_height():
    """Only the log flexes; every other row keeps its requested height at any window
    size, so their total (plus padding) has to clear MIN_HEIGHT."""
    appmod, app = _new_app()
    try:
        fixed, _width = _grid_extent(app, appmod)
        assert fixed <= appmod.MIN_HEIGHT, (
            f"fixed rows need {fixed}px but the window can be as short as "
            f"{appmod.MIN_HEIGHT}px - the bottom controls would be clipped"
        )
    finally:
        app.destroy()


def test_progress_updates_publish_a_running_average_and_eta(monkeypatch):
    appmod, app = _new_app()
    try:
        clock = {"now": 100.0}
        monkeypatch.setattr(appmod.time, "monotonic", lambda: clock["now"])

        app._begin_rate_tracking(4)
        clock["now"] = 124.0
        app._set_progress(2)
        app.update_idletasks()

        text = app.rate_var.get()
        assert "12.0 s/chapter" in text
        assert "24s" in text          # 2 chapters left at 12 s each
    finally:
        app.destroy()


def test_rate_readout_clears_between_runs(monkeypatch):
    appmod, app = _new_app()
    try:
        clock = {"now": 0.0}
        monkeypatch.setattr(appmod.time, "monotonic", lambda: clock["now"])
        app._begin_rate_tracking(2)
        clock["now"] = 10.0
        app._set_progress(1)
        assert app.rate_var.get() != ""

        app._begin_rate_tracking(2)
        assert app.rate_var.get() == ""
    finally:
        app.destroy()
