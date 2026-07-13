"""Phase 9 — the `--check` startup preflight on `scripts/Universal/main.py`.

The launchers run `python <main> --check` with the console interpreter *before* detaching
to `pythonw` (Windows) / launching the GUI (macOS), so a fatal startup error is visible
instead of vanishing behind a windowless launch. `--check` must exercise the real startup
import chain (tkinter + `gui.app`) and then exit 0 WITHOUT opening a window; the same call
without the flag must proceed to `launch()`.
"""

from __future__ import annotations

import pytest


def _require_tkinter():
    try:
        import tkinter  # noqa: F401
    except Exception:
        pytest.skip("tkinter not available in this environment")


def test_check_flag_returns_zero_without_launching(monkeypatch, capsys):
    _require_tkinter()
    import gui.app as app
    import main as main_mod

    called = {"launch": False}
    monkeypatch.setattr(app, "launch", lambda *a, **k: called.__setitem__("launch", True))

    rc = main_mod.main(["--check"])

    assert rc == 0
    assert called["launch"] is False, "--check must NOT open the GUI"
    assert "Startup check passed" in capsys.readouterr().out


def test_without_check_flag_launches(monkeypatch):
    _require_tkinter()
    import gui.app as app
    import main as main_mod

    called = {"launch": False}
    monkeypatch.setattr(app, "launch", lambda *a, **k: called.__setitem__("launch", True))

    rc = main_mod.main([])

    assert rc == 0
    assert called["launch"] is True, "a normal run must reach launch()"
