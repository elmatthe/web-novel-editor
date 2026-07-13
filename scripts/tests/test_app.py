"""GUI smoke tests.

The real batch logic is tested headlessly in test_batch.py. Here we only confirm the
Tk window constructs with its core widgets and that the log/progress helpers work — run
when a display is available, skipped cleanly otherwise so the suite stays green headless.
"""

from __future__ import annotations

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
        # Novel dropdown exists, defaults to Shadow Slave, and offers the full roster.
        assert app.novel_var.get() == "Shadow Slave"
        assert "Shadow Slave" in app.novel_combo["values"]
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
