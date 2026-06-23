"""Phase 6 — launcher safety guards (M4 regression).

A failed dependency install must STOP the launcher with a clear message, not fall
through to `python scripts/main.py` (which would crash a non-technical user with a raw
ModuleNotFoundError on a fresh machine). These tests assert the exit-on-failure guard
exists and is positioned AFTER the requirements install but BEFORE the app launch, in
both launchers — so the ordering can't silently regress. The `.command` is also run
through `bash -n` to catch shell syntax breakage.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BAT = os.path.join(_REPO_ROOT, "Setup_and_Run.bat")
_CMD = os.path.join(_REPO_ROOT, "Setup_and_Run.command")


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
