"""Launcher safety guards — static inspection only.

Phase 6 (M4 regression): a failed dependency install must STOP the launcher with a clear
message, not fall through to launching the app (which would crash a non-technical user
with a raw ModuleNotFoundError on a fresh machine). Those tests assert the exit-on-failure
guard exists and is positioned AFTER the requirements install but BEFORE the app launch,
in both launchers — so the ordering can't silently regress.

Phase 9 (single hardened launcher per OS, built from the study templates): the remaining
tests assert the hardened structure — ordered numbered `[Step N of 4]` banners, the
self-healing venv rebuild, the deliberate BLOCK (not warn) on Python below the 3.10 floor,
the consent-gated base-runtime install, the health-checked idempotent install, and the
windowless-launch preflight. All of these use pure static inspection plus `bash -n`: they
must never install Python, rebuild the developer's real `.venv`, or launch the real GUI.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BAT = os.path.join(_REPO_ROOT, "Setup_and_Run.bat")
_CMD = os.path.join(_REPO_ROOT, "Setup_and_Run.command")


def _read(path: str) -> str:
    return open(path, encoding="utf-8", errors="ignore").read()


def _index_of(lines, predicate, start: int = 0) -> int:
    for i in range(max(start, 0), len(lines)):
        if predicate(lines[i]):
            return i
    return -1


def test_bat_stops_when_pip_install_fails():
    lines = open(_BAT, encoding="utf-8", errors="ignore").read().splitlines()
    install = _index_of(lines, lambda l: "pip install -r" in l)
    assert install != -1, "no 'pip install -r' line found"
    # The errorlevel guard must come AFTER the install (not the earlier venv guard).
    guard = _index_of(lines, lambda l: "!errorlevel!" in l and "neq 0" in l, install + 1)
    assert guard != -1, "no errorlevel guard after the pip install"
    exit_after_guard = _index_of(lines, lambda l: "exit /b 1" in l, guard + 1)
    assert exit_after_guard != -1, "guard does not exit on failure"
    launch = _index_of(lines, lambda l: "%MAIN_SCRIPT%" in l and "python" in l.lower())
    # The guard exits before the app is ever launched.
    assert exit_after_guard < launch, "failure exit must come before launching main.py"


def test_command_stops_when_pip_install_fails():
    lines = open(_CMD, encoding="utf-8", errors="ignore").read().splitlines()
    install = _index_of(lines, lambda l: "pip install -r" in l)
    assert install != -1, "no 'pip install -r' line found"
    guard = _index_of(lines, lambda l: "$?" in l and "-ne 0" in l, install + 1)
    assert guard != -1, "no '$? -ne 0' guard after the pip install"
    exit_after_guard = _index_of(lines, lambda l: l.strip() == "exit 1", guard + 1)
    assert exit_after_guard != -1, "guard does not exit on failure"
    launch = _index_of(lines, lambda l: "$MAIN_SCRIPT" in l and "python" in l.lower())
    assert exit_after_guard < launch, "failure exit must come before launching main.py"


def test_launchers_stop_when_python_is_below_3_10():
    bat = open(_BAT, encoding="utf-8", errors="ignore").read()
    command = open(_CMD, encoding="utf-8", errors="ignore").read()

    assert "lss 10" in bat
    assert "Python 3.10 or later is required" in bat
    assert "sys.version_info >= (3, 10)" in command
    assert "Python 3.10 or later is required" in command


def test_command_is_valid_bash():
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash not available to syntax-check the .command launcher")
    try:
        probe = subprocess.run([bash, "--version"], capture_output=True, text=True)
    except OSError:
        pytest.skip("No usable bash found")
    if probe.returncode != 0 or "bash" not in probe.stdout.lower():
        pytest.skip("No usable bash found")
    result = subprocess.run([bash, "-n", _CMD], capture_output=True, text=True)
    assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"


# ---------------------------------------------------------------------------
# Phase 9 — hardened single-launcher structure (static inspection).
# ---------------------------------------------------------------------------


def test_bat_has_ordered_numbered_step_banners():
    text = _read(_BAT)
    idx = [text.find(f"[Step {n} of 4]") for n in (1, 2, 3, 4)]
    assert all(i != -1 for i in idx), f"missing step banners: {idx}"
    assert idx == sorted(idx), "step banners are out of order"


def test_command_has_ordered_numbered_step_banners():
    text = _read(_CMD)
    idx = [text.find(f"[Step {n} of 4]") for n in (1, 2, 3, 4)]
    assert all(i != -1 for i in idx), f"missing step banners: {idx}"
    assert idx == sorted(idx), "step banners are out of order"


def test_bat_self_healing_venv():
    text = _read(_BAT)
    # Detects an incomplete venv via its activation script and rebuilds it.
    assert "activate.bat" in text
    assert 'rmdir /s /q "%VENV_DIR%"' in text
    # The Windows "a previous run still holds .venv open" case is called out.
    assert "Task Manager" in text


def test_command_self_healing_venv():
    text = _read(_CMD)
    assert "/bin/activate" in text
    assert 'rm -rf "$VENV_DIR"' in text


def test_bat_blocks_old_python_and_does_not_merely_warn():
    text = _read(_BAT)
    assert "Python 3.10 or later is required" in text
    assert "lss 10" in text
    # The study template only WARNED and continued; the editor deliberately blocks.
    assert "WARNING" not in text


def test_command_blocks_old_python_and_does_not_merely_warn():
    text = _read(_CMD)
    assert "Python 3.10 or later is required" in text
    assert "sys.version_info >= (3, 10)" in text
    assert "WARNING" not in text


def test_bat_consent_gates_base_runtime_install():
    text = _read(_BAT)
    consent = text.find("set /p do_py")
    winget = text.find("winget install --id")
    assert consent != -1, "no Y/N consent prompt before installing Python"
    assert winget != -1, "no winget install of Python"
    assert consent < winget, "consent prompt must precede the winget install"
    # User scope (no admin) is the safe default the plan requires.
    assert "--scope user" in text


def test_command_consent_gates_base_runtime_install():
    text = _read(_CMD)
    consent = text.find("Install Python now?")
    assert consent != -1, "no Y/N consent prompt before installing Python"
    assert "brew install" in text, "no Homebrew (user-scope) Python install path"


def test_launchers_use_health_checked_idempotent_install():
    for path in (_BAT, _CMD):
        text = _read(path)
        assert "requirements.lock" in text, f"{path}: no requirements lock/sentinel"
        assert "pip check" in text, f"{path}: no pip-check health gate"
        assert "import pdfplumber, reportlab" in text, f"{path}: no import smoke check"


def test_bat_preflights_before_windowless_launch():
    text = _read(_BAT)
    check = text.find('--check')
    pyw = text.find('start "" pythonw')
    assert check != -1, "no console preflight (--check) before the windowless launch"
    assert pyw != -1, "GUI is not launched windowless with pythonw"
    assert check < pyw, "preflight must run before detaching to pythonw"


def test_command_preflights_startup():
    text = _read(_CMD)
    assert '--check' in text, "no startup preflight (--check) in the macOS launcher"


def test_bat_calls_only_defined_subroutines():
    """Every `call :label` resolves to a defined `:label` — a cheap parse sanity check."""
    text = _read(_BAT)
    import re

    defined = set(re.findall(r"(?m)^:(\w+)", text))
    called = set(re.findall(r"call :(\w+)", text))
    missing = called - defined
    assert not missing, f"call to undefined subroutine(s): {sorted(missing)}"
