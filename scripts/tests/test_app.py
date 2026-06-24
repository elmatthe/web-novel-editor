"""GUI smoke tests.

The real batch logic is tested headlessly in test_batch.py. Here we only confirm the
Tk window constructs with its core widgets and that the log/progress helpers work — run
when a display is available, skipped cleanly otherwise so the suite stays green headless.
"""

from __future__ import annotations

import pytest


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
