"""Main-window behavior: queue, run control, resume/retry, layout contract and run arguments.

On Windows each case executes in a fresh guarded child interpreter (conftest
``pytest_pyfunc_call``); child skips/errors fail the parent. Native dialogs are always
patched; real Tk widgets are created. Preferences and session logs are isolated per test.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest


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
    try:
        if app.winfo_exists():
            app._shutdown()
    except tk.TclError:
        pass


class _ImmediateThread:
    """Test double for threading.Thread: runs the target synchronously on start()."""

    def __init__(self, target=None, args=(), daemon=None):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


def drain(app):
    """Deliver worker events on the Tk thread exactly as the pump would."""
    while app.activity.channel.pending():
        app.activity.pump()
    app.update_idletasks()


def _wire_batch_spy(appmod, monkeypatch, tmp_path, summary=None):
    """Synchronous worker, run_batch spy, Downloads under tmp_path, silenced dialogs."""
    calls = []

    def spy_run_batch(pdf_paths, output_dir, **kwargs):
        calls.append({"pdf_paths": list(pdf_paths), "output_dir": output_dir, **kwargs})
        return summary or {"total": len(pdf_paths), "succeeded": len(pdf_paths), "failed": 0, "skipped": 0,
                           "output_dir": output_dir, "outputs": [], "novel": "x", "profile_applied": False}

    monkeypatch.setattr(appmod.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(appmod, "run_batch", spy_run_batch)
    monkeypatch.setattr(appmod, "downloads_dir", lambda: tmp_path / "DL")
    for name in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(appmod.messagebox, name, lambda *a, **k: None)
    monkeypatch.setattr(appmod, "open_in_file_manager", lambda path: True)
    return calls


def _all_descendants(widget):
    out = []
    for child in widget.winfo_children():
        out.append(child)
        out.extend(_all_descendants(child))
    return out


def _texts(app):
    found = []
    for widget in [app, *_all_descendants(app)]:
        try:
            found.append(str(widget.cget("text")))
        except Exception:
            continue
    return found


# ------------------------------------------------------------------------------- queue

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
    app._add_files()
    assert len(app.file_paths) == 4  # duplicates of queued paths are not re-added
    assert app.import_roots[str(folder / "1.txt")] == str(folder)
    assert app.file_listbox.curselection() == (0,)
    assert app.file_listbox.index("active") == 0
    assert app.count_var.get() == "4 file(s) queued"
    assert app.file_listbox.get(1) == "Book/1.txt"


def test_folder_import_respects_include_subfolders(mixed_app, tmp_path):
    folder = tmp_path / "Novel"
    (folder / "Arc 2").mkdir(parents=True)
    for name in ("10.pdf", "1.pdf", "5.txt"):
        (folder / name).write_bytes(b"x")
    (folder / "Arc 2" / "3.txt").write_text("x")
    mixed_app.recursive_var.set(False)
    mixed_app._apply_input_folder(str(folder))
    assert [Path(p).name for p in mixed_app.file_paths] == ["1.pdf", "5.txt", "10.pdf"]
    mixed_app._clear_all()
    mixed_app.recursive_var.set(True)
    mixed_app._apply_input_folder(str(folder))
    assert [Path(p).name for p in mixed_app.file_paths] == ["1.pdf", "5.txt", "10.pdf", "3.txt"]


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


def test_remove_and_clear_update_queue_and_import_roots(mixed_app, tmp_path):
    folder = tmp_path / "B"
    folder.mkdir()
    for name in ("1.txt", "2.txt", "3.txt"):
        (folder / name).write_text("x")
    mixed_app._apply_input_folder(str(folder))
    mixed_app.file_listbox.selection_set(1)
    mixed_app._remove_selected()
    assert [Path(p).name for p in mixed_app.file_paths] == ["1.txt", "3.txt"]
    assert str(folder / "2.txt") not in mixed_app.import_roots
    mixed_app._clear_all()
    assert mixed_app.file_paths == [] and mixed_app.import_roots == {}
    assert mixed_app.count_var.get() == "No files queued"


def test_list_keyboard_shortcuts_are_bound_to_the_list_only(mixed_app):
    box = mixed_app.file_listbox
    bound = set(box.bind())
    mod = "Command" if mixed_app.tk.call("tk", "windowingsystem") == "aqua" else "Control"
    assert {f"<{mod}-Key-a>", "<Key-Delete>", "<Key-BackSpace>", "<Alt-Key-Up>", "<Alt-Key-Down>"} <= bound
    # Text-entry shortcuts are not intercepted globally.
    assert not any("Delete" in seq or "BackSpace" in seq for seq in mixed_app.bind_all())
    mixed_app.file_paths = ["a.txt", "b.txt", "c.txt"]
    mixed_app._refresh_file_list()
    assert mixed_app._select_all_sources() == "break"
    assert mixed_app.file_listbox.curselection() == (0, 1, 2)


# --------------------------------------------------------------------------- run control

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


def test_empty_queue_warns_and_starts_nothing(mixed_app, tmp_path, monkeypatch):
    from gui import app as appmod
    calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
    warnings = []
    monkeypatch.setattr(appmod.messagebox, "showwarning", lambda *a: warnings.append(a))
    mixed_app._start_batch()
    assert warnings and calls == [] and not mixed_app._running
    assert not (tmp_path / "DL").exists()


def test_close_during_pause_requests_stop_without_destroying_tk(mixed_app, monkeypatch):
    from gui import app as appmod
    app = mixed_app
    monkeypatch.setattr(appmod.messagebox, "askyesno", lambda *a, **k: True)
    app._running = True
    app.pause_gate.clear()
    app._on_close()
    assert app.winfo_exists() and app.stop_event.is_set() and app.pause_gate.is_set()
    assert app._exit_when_done


def test_folder_import_start_runs_into_default_downloads_root(mixed_app, tmp_path, monkeypatch):
    from gui import app as appmod
    src = tmp_path / "MyNovel"
    src.mkdir()
    for name in ("10.pdf", "1.pdf"):
        (src / name).write_bytes(b"%PDF-stub")
    calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
    mixed_app._apply_input_folder(str(src))
    mixed_app._start_batch()
    drain(mixed_app)
    assert len(calls) == 1
    call = calls[0]
    assert [os.path.basename(p) for p in call["pdf_paths"]] == ["1.pdf", "10.pdf"]
    assert call["output_dir"] == str(tmp_path / "DL" / "PDF-Editor-Outputs" / "universal-1")
    assert call["import_roots"] == {p: str(src) for p in call["pdf_paths"]}
    assert mixed_app._running is False


def test_direct_files_use_flat_default_output_and_numbering_advances(mixed_app, tmp_path, monkeypatch):
    from gui import app as appmod
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-stub")
    calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
    mixed_app.file_paths = [str(pdf)]
    mixed_app._start_batch()
    drain(mixed_app)
    mixed_app._start_batch()
    drain(mixed_app)
    root = tmp_path / "DL" / "PDF-Editor-Outputs"
    assert [c["output_dir"] for c in calls] == [str(root / "universal-1"), str(root / "universal-2")]
    assert calls[0]["import_roots"] == {}


@pytest.mark.parametrize("label_index,expected_novel,expected_folder", [
    (None, "Universal", "universal-1"), ("marked", "Circle of Inevitability", "circle-of-inevitability-1"),
    ("Shadow Slave", "Shadow Slave", "shadow-slave-1")])
def test_novel_selection_reaches_dispatch_and_folder_as_clean_name(mixed_app, tmp_path, monkeypatch,
                                                                  label_index, expected_novel, expected_folder):
    from gui import app as appmod
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-stub")
    calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
    roster = list(mixed_app.novel_combo.cget("values"))
    if label_index == "marked":
        mixed_app.novel_var.set(next(r for r in roster if r.startswith("Circle of Inevitability")))
    elif label_index:
        mixed_app.novel_var.set(label_index)
    mixed_app.file_paths = [str(pdf)]
    mixed_app._start_batch()
    drain(mixed_app)
    assert calls[0]["novel_name"] == expected_novel
    assert Path(calls[0]["output_dir"]).name == expected_folder


def test_start_passes_only_the_script_only_arguments(mixed_app, tmp_path, monkeypatch):
    """Nothing AI- or checkpoint-shaped is handed to run_batch; the worker gets plain values."""
    from gui import app as appmod
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-stub")
    calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
    mixed_app.file_paths.append(str(pdf))
    mixed_app._start_batch()
    drain(mixed_app)
    assert len(calls) == 1
    assert set(calls[0]) == {
        "pdf_paths", "output_dir", "write_replacement_log", "write_debug_text", "dry_run", "novel_name",
        "pause_gate", "stop_event", "gui_log", "progress", "item_result", "output_formats", "import_roots",
        "resume", "retry_failed", "recover_stale"}
    assert isinstance(calls[0]["output_formats"], tuple) and calls[0]["output_formats"] == ("pdf",)


def test_explicit_resume_uses_frozen_settings_and_original_custom_destination(mixed_app, tmp_path, monkeypatch):
    from gui import app as appmod
    from core.batch_runner import run_batch
    src = tmp_path / "a.txt"
    src.write_text("Short prose.", encoding="utf-8")
    old = tmp_path / "old-run"
    run_batch([str(src)], str(old), output_formats=("txt",), novel_name="Shadow Slave", write_debug_text=True)
    calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
    mixed_app.set_output_root(str(tmp_path / "new-root"))
    mixed_app.opt_dry_run.set(True)
    mixed_app.opt_pdf.set(True)
    mixed_app._resume_run(directory=str(old), retry_failed=True)
    drain(mixed_app)
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
    mixed_app.set_output_root(str(tmp_path / "custom"))
    mixed_app.opt_txt.set(True)
    mixed_app._start_batch()
    drain(mixed_app)
    assert calls[0]["output_dir"] == str(tmp_path / "custom" / "universal-1")
    assert calls[0]["output_formats"] == ("pdf", "txt")
    assert not (tmp_path / "custom" / "PDF-Editor-Outputs").exists()


def test_resume_recent_discovers_runs_under_the_custom_root(mixed_app, tmp_path, monkeypatch):
    from gui import app as appmod
    from core.run_manifest import RunCheckpoint
    src = tmp_path / "a.txt"
    src.write_text("Short.", encoding="utf-8")
    root = tmp_path / "custom"
    cp = RunCheckpoint(root / "universal-1", [str(src)], novel="Universal")
    cp.start(formats=("txt",), rules_digest="x")
    cp.close()
    calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
    mixed_app.set_output_root(str(root))
    mixed_app._resume_recent()
    drain(mixed_app)
    assert calls and calls[0]["output_dir"] == str(root / "universal-1") and calls[0]["resume"]


def test_retry_failed_reuses_the_last_finished_with_errors_run(mixed_app, tmp_path, monkeypatch):
    from gui import app as appmod
    from core.batch_runner import run_batch
    src = tmp_path / "a.txt"
    src.write_text("Short.", encoding="utf-8")
    run = tmp_path / "run"
    run_batch([str(src)], str(run), output_formats=("txt",), novel_name="Universal")
    calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
    monkeypatch.setattr(appmod.filedialog, "askdirectory", lambda **k: pytest.fail("should reuse the last run"))
    mixed_app._last_run_dir, mixed_app._last_run_has_failures = str(run), True
    mixed_app._retry_failed()
    drain(mixed_app)
    assert calls[0]["output_dir"] == str(run) and calls[0]["retry_failed"]


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
    assert "Resume refused" in mixed_app.summary_text.get("1.0", "end")


def test_partial_retry_summary_shows_run_incomplete(mixed_app, monkeypatch):
    from gui import app as appmod
    dialogs = []
    monkeypatch.setattr(appmod.messagebox, "showinfo", lambda *args: dialogs.append(args))
    mixed_app._request = appmod.RunRequest(files=("a",), output_dir="original-run", novel="Universal",
                                           formats=("pdf",), write_replacement_log=False,
                                           write_debug_text=False, dry_run=False)
    mixed_app._on_done({"total": 3, "succeeded": 1, "failed": 0, "skipped": 0,
                        "completed_total": 2, "failed_total": 0, "pending_total": 1,
                        "run_complete": False, "output_dir": "original-run", "outputs": []})
    assert dialogs[0][0] == "Run incomplete"
    assert "pending 1" in mixed_app.summary_text.get("1.0", "end")


def test_pause_continue_stop_state_machine(mixed_app):
    app = mixed_app
    assert str(app.pause_button["state"]) == "disabled" and str(app.stop_button["state"]) == "disabled"
    app._toggle_pause()  # idle: no-op
    assert app.pause_gate.is_set()
    app._running = True
    app._set_run_controls(running=True)
    app._toggle_pause()
    assert not app.pause_gate.is_set() and app.pause_button["text"] == "Continue"
    app._toggle_pause()
    assert app.pause_gate.is_set() and app.pause_button["text"] == "Pause"
    app._toggle_pause()
    app._request_stop()  # stop while paused releases the gate and disables both controls
    assert app.stop_event.is_set() and app.pause_gate.is_set()
    assert str(app.stop_button["state"]) == "disabled" and str(app.pause_button["state"]) == "disabled"
    app._finish_run_ui()
    assert not app.stop_event.is_set() and str(app.run_button["state"]) == "normal"


def test_start_wires_gates_counts_progress_and_resets_controls(mixed_app, tmp_path, monkeypatch):
    from gui import app as appmod
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-stub")
    seen = {}

    def spy(pdf_paths, output_dir, **kwargs):
        seen.update(kwargs)
        assert str(mixed_app.run_button["state"]) == "disabled"
        kwargs["progress"](1)
        kwargs["item_result"](pdf_paths[0], "completed")
        kwargs["gui_log"]("[1/1] a.pdf — done (0 edits)", "success")
        return {"total": 1, "succeeded": 1, "failed": 0, "skipped": 0, "output_dir": output_dir, "outputs": []}
    _wire_batch_spy(appmod, monkeypatch, tmp_path)
    monkeypatch.setattr(appmod, "run_batch", spy)
    mixed_app.file_paths = [str(pdf)]
    mixed_app._start_batch()
    drain(mixed_app)
    assert seen["pause_gate"] is mixed_app.pause_gate and seen["stop_event"] is mixed_app.stop_event
    assert mixed_app.counts_var.get() == "Completed 1 · Failed 0 · Skipped 0"
    assert float(mixed_app.progress["value"]) == 1
    assert str(mixed_app.run_button["state"]) == "normal" and str(mixed_app.stop_button["state"]) == "disabled"
    assert "a.pdf — done" in mixed_app.summary_text.get("1.0", "end")
    # A second run resets counts and progress.
    monkeypatch.setattr(appmod, "run_batch", lambda *a, **k: {"total": 1, "succeeded": 0, "failed": 0,
                                                              "skipped": 0, "output_dir": "x", "outputs": []})
    mixed_app._start_batch()
    drain(mixed_app)
    assert mixed_app.counts_var.get() == "Completed 0 · Failed 0 · Skipped 0"
    assert float(mixed_app.progress["value"]) == 0


def test_progress_updates_publish_a_running_average_and_eta(mixed_app, monkeypatch):
    from gui import app as appmod
    clock = {"now": 1000.0}
    monkeypatch.setattr(appmod.time, "monotonic", lambda: clock["now"])
    mixed_app._begin_rate_tracking(10)
    assert mixed_app.rate_var.get() == ""
    clock["now"] += 20.0
    mixed_app._set_progress(4)
    text = mixed_app.rate_var.get()
    assert text and "5.0" in text
    mixed_app._begin_rate_tracking(3)
    assert mixed_app.rate_var.get() == ""


def test_elapsed_time_is_measured_and_formatted():
    from gui.app import format_elapsed
    assert format_elapsed(0) == "0:00" and format_elapsed(65) == "1:05" and format_elapsed(3725) == "1:02:05"


# ------------------------------------------------------------------------------ layout

def test_four_numbered_groups_activity_pane_and_status_bar(mixed_app):
    from tkinter import ttk
    app = mixed_app
    panes = app.paned.panes()
    assert len(panes) == 2 and str(app.paned.cget("orient")) == "horizontal"
    controls = app.nametowidget(panes[0])
    groups = [w.cget("text") for w in controls.winfo_children() if isinstance(w, ttk.Labelframe)]
    assert groups == ["1. Sources", "2. Novel & Editing", "3. Output", "4. Run"]
    activity = app.nametowidget(panes[1])
    assert app.activity_tabs in _all_descendants(activity)
    assert [app.activity_tabs.tab(t, "text") for t in app.activity_tabs.tabs()] == ["Summary", "Detailed"]
    texts = _texts(app)
    for label in ("Add Files…", "Add Folder…", "Move Up", "Move Down", "Remove", "Clear All", "Include subfolders",
                  "PDF", "TXT", "Open Output Folder", "Start", "Pause", "Stop", "Resume Run…", "Retry Failed",
                  "Clear Log", "Dark mode", "Preferences & Data…", "Open Log Folder"):
        assert label in texts, label
    # Destination changes go through Preferences & Data; there is no browse control in Output.
    assert "Output root…" not in texts and "Browse…" not in texts


def test_the_window_has_no_ai_or_cloud_controls(mixed_app):
    banned = ("ai ", " ai", "provider", "ollama", "gemini", "groq", "api key", "model", "cloud", "consent",
              "quota")
    offenders = [t for t in (s.lower() for s in _texts(mixed_app)) if t and any(b in f" {t} " for b in banned)]
    assert offenders == []
    for attr in ("ai_model_combo", "ai_provider_combo", "ai_key_button", "opt_ai_enabled", "ai_status_var"):
        assert not hasattr(mixed_app, attr)


def test_novel_combo_shows_the_longest_roster_entry_in_full(mixed_app):
    roster = list(mixed_app.novel_combo.cget("values"))
    assert int(mixed_app.novel_combo.cget("width")) >= max(len(r) for r in roster)


def test_minimum_window_keeps_every_control_and_the_status_bar_visible(mixed_app):
    from gui import app as appmod
    app = mixed_app
    app.deiconify()
    app.geometry(f"{appmod.MIN_WIDTH}x{appmod.MIN_HEIGHT}+0+0")
    app.update()
    deadline = time.monotonic() + 5
    while (app.winfo_width(), app.winfo_height()) != (appmod.MIN_WIDTH, appmod.MIN_HEIGHT) and time.monotonic() < deadline:
        app.update()
    bottom, right = app.winfo_rooty() + app.winfo_height(), app.winfo_rootx() + app.winfo_width()
    for widget in (app.run_button, app.retry_button, app.progress, app.theme_toggle, app.activity_tabs,
                   app.clear_button):
        assert widget.winfo_ismapped()
        assert widget.winfo_rooty() + widget.winfo_height() <= bottom + 1, widget
        assert widget.winfo_rootx() + widget.winfo_width() <= right + 1, widget
    assert appmod.MIN_HEIGHT <= 700  # fits a 768-pixel laptop display with taskbar


def test_activity_detailed_view_gets_routine_lines_summary_does_not(mixed_app):
    from gui.activity import bridge_event
    mixed_app.activity.emit(bridge_event("Output mapping: a.pdf → a.pdf", "muted"))
    mixed_app.activity.emit(bridge_event("[1/1] a.pdf — done (2 edits)", "success"))
    drain(mixed_app)
    summary = mixed_app.summary_text.get("1.0", "end")
    detailed = mixed_app.detailed_text.get("1.0", "end")
    assert "Output mapping" not in summary and "Output mapping" in detailed
    assert "a.pdf — done" in summary and "a.pdf — done" in detailed
