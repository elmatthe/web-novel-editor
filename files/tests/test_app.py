"""GUI smoke tests.

The real batch logic is tested headlessly in test_batch.py. Here we only confirm the
Tk window constructs with its core widgets and that the log/progress helpers work — run
when a display is available, skipped cleanly otherwise so the suite stays green headless.
"""

from __future__ import annotations

import os

import pytest


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
        # the "no profile yet" marker.
        from core.novel_registry import NO_PROFILE_MARKER
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
    """Phase 7 structural alignment with web-novel-scraper: novel selection first, and
    the log widget at the bottom with the run controls (progress + Start) above it."""
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
        # The log sits below the run controls (log at the bottom of the workflow).
        assert run_row < log_row

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
        assert "Upload PDFs" in radio_texts
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
        assert "disabled" in app.remove_button.state()
        assert "disabled" in app.clear_button.state()
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
        assert shown == ["1.pdf", "2.pdf", "10.pdf", "extras/5.pdf"]
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
        assert call["output_dir"] == str(tmp_path / "DL" / expected_name)
        assert call["mirror_root"] == str(src)
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
        assert call["output_dir"] == str(tmp_path / "DL" / expected_name)
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
        assert call["output_dir"] == str(tmp_path / "DL" / "universal-1")
    finally:
        app.destroy()


def test_app_marked_selection_strips_marker_before_batch_and_naming(
        tmp_path, monkeypatch):
    """Selecting a marked profile-less novel must reach run_batch (and the output-folder
    kebab-casing) as the CLEAN name — the display marker never leaks downstream."""
    tk = pytest.importorskip("tkinter")
    from core.novel_registry import NO_PROFILE_MARKER
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
        assert call["output_dir"] == str(tmp_path / "DL" / "re-monster-1")
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
        assert call["output_dir"] == str(tmp_path / "DL" / "shadow-slave-1")
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
