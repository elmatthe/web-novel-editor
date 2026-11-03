"""Phase 02B desktop contracts with real Tk: threads, theme, Preferences & Data, logs, close.

Executed per case in a fresh guarded child on Windows (conftest ``GUI_TEST_MODULES``).
Native dialogs are injected or patched; no case drives a real native dialog.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest


def _make_app(**kwargs):
    tk = pytest.importorskip("tkinter")
    from gui.app import WebnovelEditorApp
    try:
        app = WebnovelEditorApp(**kwargs)
    except tk.TclError:
        pytest.skip("Tk could not initialize; strict Windows fixture reports the error")
    app.withdraw()
    app.update_idletasks()
    return app


@pytest.fixture
def app():
    if sys.platform == "win32" and os.environ.get("WNE_GUI_TEST_CHILD") != "1":
        yield None
        return
    window = _make_app()
    yield window
    try:
        if window.winfo_exists():
            window._shutdown()
    except Exception:
        pass


def _settings():
    path = Path(os.environ["WNE_SETTINGS_FILE"])
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _pump_until(window, predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for the GUI")
        window.update()
        time.sleep(0.01)


def _silence(appmod, monkeypatch):
    for name in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(appmod.messagebox, name, lambda *a, **k: None)
    monkeypatch.setattr(appmod, "open_in_file_manager", lambda path: True)


# --------------------------------------------------------------------- worker / Tk threads

def test_worker_thread_never_calls_tk_and_events_arrive_on_the_tk_thread(app, tmp_path, monkeypatch):
    import tkinter
    from gui import app as appmod
    main_thread = threading.get_ident()
    tk_calls_off_main = []

    def guard(name, original):
        def wrapped(self, *args, **kwargs):
            if threading.get_ident() != main_thread:
                tk_calls_off_main.append(name)
            return original(self, *args, **kwargs)
        return wrapped
    for cls, names in ((tkinter.Misc, ("after", "after_idle", "after_cancel", "_configure", "update",
                                        "update_idletasks", "event_generate", "destroy", "winfo_exists")),
                       (tkinter.Variable, ("set", "get")), (tkinter.Text, ("insert", "delete")),
                       (tkinter.Listbox, ("insert", "delete"))):
        for name in names:
            monkeypatch.setattr(cls, name, guard(f"{cls.__name__}.{name}", getattr(cls, name)))
    job_threads, render_threads = [], []
    original_job, original_render = app._on_job, app._render
    app.activity.job_sink = lambda e: (job_threads.append(threading.get_ident()), original_job(e))
    app.activity.on_render = lambda u: (render_threads.append(threading.get_ident()), original_render(u))
    worker_ids = []

    def fake_run_batch(paths, output_dir, **kwargs):
        worker_ids.append(threading.get_ident())
        for i, path in enumerate(paths, 1):
            kwargs["gui_log"](f"[{i}/{len(paths)}] {Path(path).name} — done (1 edit)", "success")
            kwargs["gui_log"](f"        {Path(path).name}: extract 0.01s", "muted")
            kwargs["item_result"](path, "completed")
            kwargs["progress"](i)
        return {"total": len(paths), "succeeded": len(paths), "failed": 0, "skipped": 0,
                "output_dir": output_dir, "outputs": []}
    monkeypatch.setattr(appmod, "run_batch", fake_run_batch)
    monkeypatch.setattr(appmod, "downloads_dir", lambda: tmp_path / "DL")
    _silence(appmod, monkeypatch)
    files = []
    for i in range(30):
        files.append(tmp_path / f"{i}.txt")
        files[-1].write_text("x")
    app.file_paths = [str(p) for p in files]
    app._start_batch()
    _pump_until(app, lambda: not app._running)
    assert worker_ids and worker_ids[0] != main_thread
    assert tk_calls_off_main == []
    assert set(job_threads) == {main_thread} and set(render_threads) == {main_thread}
    assert app.counts_var.get() == "Completed 30 · Failed 0 · Skipped 0"
    assert float(app.progress["value"]) == 30


def test_close_during_run_stops_at_a_boundary_and_destroys_only_after_the_worker(app, tmp_path, monkeypatch):
    from gui import app as appmod
    release, started = threading.Event(), threading.Event()
    observed = {}

    def slow_run_batch(paths, output_dir, **kwargs):
        started.set()
        release.wait(10)
        observed["stop_seen"] = kwargs["stop_event"].is_set()
        kwargs["gui_log"]("Stop requested — batch ended before chapter 2 of 2.", "warn")
        return {"total": 2, "succeeded": 1, "failed": 0, "skipped": 0, "stopped": True,
                "output_dir": output_dir, "outputs": []}
    monkeypatch.setattr(appmod, "run_batch", slow_run_batch)
    monkeypatch.setattr(appmod, "downloads_dir", lambda: tmp_path / "DL")
    monkeypatch.setattr(appmod.messagebox, "askyesno", lambda *a, **k: True)
    _silence(appmod, monkeypatch)
    destroyed = []
    monkeypatch.setattr(app, "_shutdown", lambda: destroyed.append(True))
    src = tmp_path / "a.txt"
    src.write_text("x")
    app.file_paths = [str(src)]
    app._start_batch()
    assert started.wait(10)
    app._on_close()
    for _ in range(20):
        app.update()
        time.sleep(0.01)
    assert destroyed == [] and app._running and app.stop_event.is_set()
    release.set()
    _pump_until(app, lambda: destroyed)
    assert observed["stop_seen"] and destroyed == [True]


# ------------------------------------------------------------------------------- appearance

def test_theme_toggle_repaints_in_place_persists_and_preserves_state(app, tmp_path):
    from gui import appearance as look
    app.file_paths = [str(tmp_path / f"{i}.txt") for i in range(40)]
    app._refresh_file_list()
    app.file_listbox.selection_set(3, 5)
    app.file_listbox.yview_moveto(0.5)
    app.progress.configure(maximum=10, value=4)
    app._report("Before toggle", summary=True)
    app.activity_tabs.select(1)
    before = (app.file_listbox.curselection(), app.summary_text.get("1.0", "end"), float(app.progress["value"]),
              app.activity_tabs.index("current"), app.file_listbox.yview()[0])
    app.dark_var.set(True)
    app.toggle_appearance()
    app.update_idletasks()
    after = (app.file_listbox.curselection(), app.summary_text.get("1.0", "end"), float(app.progress["value"]),
             app.activity_tabs.index("current"), app.file_listbox.yview()[0])
    assert after == before
    dark = look.DARK_COLORS
    assert str(app.file_listbox.cget("background")) == dark["field"]
    assert str(app.summary_text.cget("background")) == dark["field"]
    assert str(app.cget("background")) == dark["window"]
    assert _settings()["appearance"] == "dark"
    app.dark_var.set(False)
    app.toggle_appearance()
    assert str(app.file_listbox.cget("background")) == look.LIGHT_COLORS["field"]
    assert _settings()["appearance"] == "light"


def test_saved_preferences_are_restored_and_invalid_values_fall_back_visibly(tmp_path, monkeypatch):
    if sys.platform == "win32" and os.environ.get("WNE_GUI_TEST_CHILD") != "1":
        return  # executed in the guarded child
    from gui import appearance as look
    custom = tmp_path / "custom-root"
    Path(os.environ["WNE_SETTINGS_FILE"]).write_text(json.dumps({
        "appearance": "dark", "novel": "Shadow Slave", "output_formats": ["txt"], "include_subfolders": False,
        "output_root": str(custom), "legacy_ai_provider": "groq"}), encoding="utf-8")
    window = _make_app()
    try:
        assert window.bundle["appearance"] == "dark" and window.dark_var.get()
        assert str(window.file_listbox.cget("background")) == look.DARK_COLORS["field"]
        assert window.novel_var.get() == "Shadow Slave"
        assert (window.opt_pdf.get(), window.opt_txt.get(), window.recursive_var.get()) == (False, True, False)
        assert window.output_root() == custom and "custom folder" in window.output_root_var.get()
        assert "protected term" in window.terms_var.get()
    finally:
        window._shutdown()
    Path(os.environ["WNE_SETTINGS_FILE"]).write_text(json.dumps({
        "appearance": "purple", "output_formats": [], "output_root": "relative/path"}), encoding="utf-8")
    window = _make_app()
    try:
        assert window.bundle["appearance"] == "light" and window.opt_pdf.get() and not window.opt_txt.get()
        assert window.output_root().name == "PDF-Editor-Outputs"
        summary = window.summary_text.get("1.0", "end")
        assert summary.count("was invalid; the default is in use") == 3
    finally:
        window._shutdown()


def test_option_changes_persist_but_audit_debug_and_dry_run_stay_session_only(app):
    app.opt_txt.set(True)
    app._on_formats_changed()
    app.recursive_var.set(False)
    app._on_recursive_changed()
    app.novel_var.set("Supreme Magus")
    app._on_novel_changed()
    app.opt_pdf.set(False)
    app.opt_txt.set(False)
    app._on_formats_changed()  # no format selected: not a valid saved state, keep the last one
    for var in (app.opt_replacement_log, app.opt_debug_text, app.opt_dry_run):
        var.set(True)
    saved = _settings()
    assert saved == {"output_formats": ["pdf", "txt"], "include_subfolders": False, "novel": "Supreme Magus"}


# ------------------------------------------------------------------------ Preferences & Data

def test_preferences_custom_default_and_validation_feedback(app, tmp_path):
    from gui.preferences import PreferencesDialog
    chosen = tmp_path / "My Outputs"
    chosen.mkdir()
    dialog = PreferencesDialog(app, ask_directory=lambda **k: str(chosen), confirm=lambda *a: True)
    try:
        dialog.browse()
        assert dialog.status_kind == "ok" and app.output_root() == chosen
        assert _settings()["output_root"] == str(chosen)
        dialog.var_custom.set("relative/folder")
        assert dialog.save_output_root() is False and dialog.status_kind == "error"
        a_file = tmp_path / "file.txt"
        a_file.write_text("x")
        dialog.var_custom.set(str(a_file))
        assert dialog.save_output_root() is False and app.output_root() == chosen
        dialog.var_mode.set("default")
        dialog._on_mode_change()
        assert str(dialog.entry_custom["state"]) == "disabled"
        assert dialog.save_output_root() and app.output_root() == app.default_output_root()
        assert _settings()["output_root"] is None
    finally:
        dialog.close()
    assert app._preferences_dialog is None


def test_reset_preferences_touches_only_settings_json(app, tmp_path):
    from gui.preferences import PreferencesDialog
    settings_file = Path(os.environ["WNE_SETTINGS_FILE"])
    folder = settings_file.parent
    sentinels = {"secrets.json": b'{"GROQ_API_KEY": "sentinel-not-a-real-key"}',
                 "unrelated.txt": b"user file", "logs/old.log": b"log"}
    for name, data in sentinels.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
    app.set_appearance("dark")
    app.set_output_root(str(tmp_path / "custom"))
    app.opt_txt.set(True)
    app._on_formats_changed()
    dialog = PreferencesDialog(app, ask_directory=lambda **k: None, confirm=lambda *a: True)
    try:
        assert dialog.reset_preferences() and dialog.status_kind == "ok"
    finally:
        dialog.close()
    assert not settings_file.exists()
    for name, data in sentinels.items():
        assert (folder / name).read_bytes() == data
    assert app.bundle["appearance"] == "light" and not app.dark_var.get()
    assert app.output_root() == app.default_output_root() and not app.opt_txt.get() and app.opt_pdf.get()
    declined = PreferencesDialog(app, ask_directory=lambda **k: None, confirm=lambda *a: False)
    try:
        app.set_appearance("dark")
        assert declined.reset_preferences() is False and settings_file.exists()
    finally:
        declined.close()


def test_preferences_dialog_follows_live_theme_changes(app):
    from gui import appearance as look
    app.open_preferences()
    dialog = app._preferences_dialog
    app.open_preferences()  # a second request focuses the same dialog
    assert app._preferences_dialog is dialog
    app.set_appearance("dark")
    assert str(dialog.cget("background")) == look.DARK_COLORS["window"]
    dialog.close()


# ---------------------------------------------------------------------- logs and privacy

def test_clear_log_empties_views_but_not_the_session_log_file(app):
    app._report("Keep me on disk", summary=True)
    app.clear_log()
    assert app.summary_text.get("1.0", "end").strip() == "" and app.detailed_text.get("1.0", "end").strip() == ""
    path = app.activity.session_log.path
    assert path.parent == Path(os.environ["WNE_LOG_DIR"])
    assert "Keep me on disk" in path.read_text(encoding="utf-8")


def test_real_run_session_log_carries_names_and_counts_but_no_chapter_text(app, tmp_path, monkeypatch):
    from gui import app as appmod
    _silence(appmod, monkeypatch)
    monkeypatch.setattr(appmod, "downloads_dir", lambda: tmp_path / "DL")
    body = "Unmistakable sentinel prose about Clan Valor walking slowly through the rain"
    src = tmp_path / "Chapter 7.txt"
    src.write_text(f"Chapter 7: Rain\n\n{body}.\n", encoding="utf-8")
    app.file_paths = [str(src)]
    app.opt_txt.set(True)
    app._start_batch()
    _pump_until(app, lambda: not app._running, timeout=60)
    log_text = app.activity.session_log.path.read_text(encoding="utf-8")
    assert "Chapter 7.txt — done" in log_text and "Run totals: completed 1" in log_text
    assert "edits by category" in app.detailed_text.get("1.0", "end")
    assert body not in log_text and "sentinel prose" not in log_text
    out = tmp_path / "DL" / "PDF-Editor-Outputs" / "universal-1"
    assert (out / "Chapter 7.pdf").is_file() and (out / "Chapter 7.txt").is_file()
    assert "Clan Valor" in (out / "Chapter 7.txt").read_text(encoding="utf-8")
