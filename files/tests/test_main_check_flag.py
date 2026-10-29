"""Phase 9 — the `--check` startup preflight on `scripts/Universal/main.py`.

The launchers run `python <main> --check` with the console interpreter *before* detaching
to `pythonw` (Windows) / launching the GUI (macOS), so a fatal startup error is visible
instead of vanishing behind a windowless launch. `--check` must exercise the real startup
import chain (tkinter + `gui.app`) and then exit 0 WITHOUT opening a window; the same call
without the flag must proceed to `launch()`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

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


def test_release_shaped_startup_needs_no_dev_tree_and_no_ai_sdk(tmp_path):
    """Copy only the shipped scripts tree (no ``files/``, no ``.git``) and run ``--check``.

    Re-homed from the Ollama test in Phase 01A. If ordinary startup ever imports one of
    the retired provider SDKs, the shadow modules below make it fail loudly.
    """
    _require_tkinter()
    root = Path(__file__).resolve().parents[2]
    universal = tmp_path / "release" / "scripts" / "Universal"
    shutil.copytree(
        root / "scripts" / "Universal", universal,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    for sdk in ("ollama", "groq"):
        (universal / f"{sdk}.py").write_text(
            f"raise ImportError('{sdk} intentionally absent')\n", encoding="utf-8"
        )
    (universal / "google").mkdir()
    (universal / "google" / "__init__.py").write_text(
        "raise ImportError('google SDK intentionally absent')\n", encoding="utf-8"
    )
    assert not (tmp_path / "release" / "files").exists()
    assert not (tmp_path / "release" / ".git").exists()
    completed = subprocess.run(
        [sys.executable, str(universal / "main.py"), "--check"],
        cwd=tmp_path / "release",
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Startup check passed." in completed.stdout
