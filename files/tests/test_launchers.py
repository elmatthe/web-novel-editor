"""Root launchers: fixed names/line endings, thin bootstrap delegation, and executed control flow.

The Windows ``.bat`` really runs (cmd.exe) inside a contained sandbox whose path contains
spaces, parentheses and non-ASCII characters. ``scripts/bootstrap.py`` there is a stub that
records which interpreter ran it, with which arguments, and exits with a chosen code. PATH,
LOCALAPPDATA and ProgramFiles are replaced so interpreter discovery is controlled: these are
simulations of missing/alias-only Python, not evidence from a genuinely Python-free machine.
The macOS ``.command`` control flow is executed with Git Bash and stub interpreters; that is
not macOS execution. No test installs Python, touches the real ``.venv`` or opens the GUI.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BAT = REPO / "Setup_and_Run-Web-Novel-Editor.bat"
CMD = REPO / "Setup_and_Run-Web-Novel-Editor.command"

STUB_BOOTSTRAP = r'''
import json, os, sys
from pathlib import Path
here = Path(__file__).resolve().parent
codes = json.loads((here / "codes.json").read_text())
mode = sys.argv[1] if len(sys.argv) > 1 else "setup"
with open(here / "calls.jsonl", "a", encoding="utf-8") as log:
    log.write(json.dumps({"exe": sys.executable, "args": sys.argv[1:]}) + "\n")
print("stub bootstrap ran:", mode)
sys.exit(codes.get(mode, 0))
'''


# ------------------------------------------------------------------------------- static

def test_launcher_names_line_endings_and_mode_are_preserved():
    assert BAT.is_file() and CMD.is_file()
    attrs = subprocess.run(["git", "ls-files", "--eol", "-s", BAT.name, CMD.name], cwd=REPO,
                           capture_output=True, text=True).stdout
    assert "attr/text eol=crlf" in attrs and "attr/text eol=lf" in attrs
    stage = subprocess.run(["git", "ls-files", "-s", CMD.name], cwd=REPO, capture_output=True, text=True).stdout
    assert stage.startswith("100755"), "the .command launcher must stay executable"
    assert b"\r\n" not in CMD.read_bytes()


def test_launchers_are_thin_wrappers_that_never_upgrade_pip_or_install_homebrew():
    for path in (BAT, CMD):
        text = path.read_text(encoding="utf-8")
        assert "scripts" in text and "bootstrap.py" in text and "--launch-only" in text
        assert "pip install" not in text and "--upgrade pip" not in text
        assert "requirements.txt" not in text  # dependency work belongs to bootstrap.py
    command = CMD.read_text(encoding="utf-8")
    import re
    assert "Homebrew/install" not in command and not re.search(r"^\s*brew\s+install", command, re.M)
    assert '"$1" = "/usr/bin/python3"' in command  # Apple's CLT stub is never used
    bat = BAT.read_text(encoding="utf-8")
    assert "\\WindowsApps\\" in bat and "--scope user" in bat and "INSTALL_ANSWER" in bat
    assert "setx" not in bat.lower() and "reg add" not in bat.lower()


def test_bat_jumps_and_calls_only_defined_labels():
    import re
    text = BAT.read_text(encoding="utf-8")
    labels = {m.group(1).lower() for m in re.finditer(r"(?m)^:([A-Za-z_]\w*)[ \t]*\r?$", text)}
    targets = {m.group(1).lower() for m in re.finditer(r"(?i)\bgoto\s+:?([A-Za-z_]\w*)", text)}
    targets |= {m.group(1).lower() for m in re.finditer(r"(?i)\bcall\s+:([A-Za-z_]\w*)", text)}
    targets.discard("eof")
    assert targets and targets <= labels, sorted(targets - labels)


def test_both_launchers_enforce_the_python_3_10_floor_by_execution():
    for path in (BAT, CMD):
        assert "sys.version_info >= (3, 10)" in path.read_text(encoding="utf-8")


def test_command_is_valid_bash():
    bash = _usable_bash()
    result = subprocess.run([bash, "-n", str(CMD)], capture_output=True, text=True)
    assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"


# ------------------------------------------------------------------- executed .bat (Windows)

def _bat_sandbox(tmp_path, *, venv: bool, codes: dict) -> Path:
    root = tmp_path / "Web Novel (copy) \u00dcnicode"
    (root / "scripts").mkdir(parents=True)
    shutil.copyfile(BAT, root / BAT.name)
    data = (root / BAT.name).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    (root / BAT.name).write_bytes(data)
    (root / "scripts" / "bootstrap.py").write_text(STUB_BOOTSTRAP, encoding="utf-8")
    (root / "scripts" / "codes.json").write_text(json.dumps(codes), encoding="utf-8")
    if venv:
        subprocess.run([_base_python(), "-m", "venv", "--without-pip", str(root / ".venv")], check=True,
                       capture_output=True, timeout=180)
    return root


def _base_python() -> str:
    import bootstrap
    return bootstrap.find_base_python((3, 10))[0]


def _fake_store_alias(tmp_path) -> tuple[Path, Path]:
    """A Store-alias look-alike first on PATH; it writes a marker if anyone executes it."""
    apps = tmp_path / "fake-local" / "Microsoft" / "WindowsApps"
    apps.mkdir(parents=True)
    marker = tmp_path / "alias-was-executed.txt"
    (apps / "python.bat").write_text(f'@echo off\r\necho executed> "{marker}"\r\nexit /b 0\r\n', encoding="utf-8")
    return apps, marker


def _run_bat(root, *, path_dirs, stdin="\n\n\n", local=None, tmp_path=None):
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    empty = (tmp_path or root.parent) / "empty-dir"
    empty.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k.upper() not in {"PATH", "PYTHONPATH", "PYTHONHOME"}}
    env.update(PATH=os.pathsep.join([*map(str, path_dirs), str(system32)]),
               LOCALAPPDATA=str(local or empty), ProgramFiles=str(empty))
    done = subprocess.run(["cmd", "/d", "/c", str(root / BAT.name)], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env, cwd=str(tmp_path or root.parent),
                          timeout=180)
    calls_file = root / "scripts" / "calls.jsonl"
    calls = [json.loads(line) for line in calls_file.read_text(encoding="utf-8").splitlines()] \
        if calls_file.exists() else []
    return done, calls


windows_only = pytest.mark.skipif(sys.platform != "win32", reason="executes cmd.exe; Windows launcher only")


@windows_only
def test_bat_healthy_fast_path_runs_only_the_offline_check(tmp_path):
    root = _bat_sandbox(tmp_path, venv=True, codes={"--launch-only": 0})
    apps, marker = _fake_store_alias(tmp_path)
    done, calls = _run_bat(root, path_dirs=[apps], tmp_path=tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert [c["args"] for c in calls] == [["--launch-only"]]
    assert Path(calls[0]["exe"]).parent.parent.name == ".venv"
    assert "running in its own window" in done.stdout and "Press Enter to close" in done.stdout
    assert not marker.exists()


@windows_only
def test_bat_never_executes_a_py_launcher_that_lives_in_windowsapps(tmp_path):
    """Codex review 8d93186: the `py` probe must apply the same Store-location exclusion."""
    root = _bat_sandbox(tmp_path, venv=True, codes={"--launch-only": 3, "setup": 0})
    apps, marker = _fake_store_alias(tmp_path)
    py_marker = tmp_path / "py-alias-was-executed.txt"
    (apps / "py.bat").write_text(f'@echo off\r\necho executed> "{py_marker}"\r\nexit /b 0\r\n', encoding="utf-8")
    base = Path(_base_python())
    done, calls = _run_bat(root, path_dirs=[apps, base.parent], tmp_path=tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert not py_marker.exists(), "a py launcher inside WindowsApps was executed"
    assert not marker.exists()
    assert Path(calls[-1]["exe"]).resolve() == base.resolve()


@windows_only
def test_bat_launch_failure_is_reported_without_setup(tmp_path):
    root = _bat_sandbox(tmp_path, venv=True, codes={"--launch-only": 4})
    done, calls = _run_bat(root, path_dirs=[], tmp_path=tmp_path)
    assert done.returncode == 4 and [c["args"] for c in calls] == [["--launch-only"]]
    assert "could not start" in done.stdout and "runtime-data" in done.stdout


@windows_only
def test_bat_repair_uses_an_external_python_and_skips_the_store_alias(tmp_path):
    root = _bat_sandbox(tmp_path, venv=True, codes={"--launch-only": 3, "setup": 0})
    apps, marker = _fake_store_alias(tmp_path)
    base = Path(_base_python())
    done, calls = _run_bat(root, path_dirs=[apps, base.parent], tmp_path=tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert [c["args"] for c in calls] == [["--launch-only"], []]
    assert Path(calls[1]["exe"]).resolve() == base.resolve()
    assert not marker.exists(), "the Store alias look-alike was executed"
    assert "Using Python:" in done.stdout


@windows_only
def test_bat_without_any_python_repairs_in_place_with_the_existing_venv(tmp_path):
    root = _bat_sandbox(tmp_path, venv=True, codes={"--launch-only": 3, "setup": 10})
    apps, marker = _fake_store_alias(tmp_path)
    done, calls = _run_bat(root, path_dirs=[apps], tmp_path=tmp_path)
    assert done.returncode == 10
    assert [c["args"] for c in calls] == [["--launch-only"], []]
    assert Path(calls[1]["exe"]).parent.parent.name == ".venv"
    assert "repairing in place" in done.stdout and "Setup did not complete (code 10)" in done.stdout
    assert not marker.exists()


@windows_only
def test_bat_missing_python_simulation_asks_first_and_installs_nothing_when_declined(tmp_path):
    root = _bat_sandbox(tmp_path, venv=False, codes={})
    apps, marker = _fake_store_alias(tmp_path)
    done, calls = _run_bat(root, path_dirs=[apps], stdin="N\n\n\n", tmp_path=tmp_path)
    assert done.returncode == 10 and calls == []
    assert "Install Python 3.13 for your user account now with winget? (Y/N)" in done.stdout
    assert "Python 3.10 or newer is required and was not found" in done.stdout
    assert "python.org" in done.stdout and not marker.exists()
    assert not (root / ".venv").exists()


@windows_only
def test_bat_missing_bootstrap_is_a_clear_error(tmp_path):
    root = _bat_sandbox(tmp_path, venv=False, codes={})
    (root / "scripts" / "bootstrap.py").unlink()
    done, _calls = _run_bat(root, path_dirs=[], tmp_path=tmp_path)
    assert done.returncode == 10 and "setup helper is missing" in done.stdout


# ----------------------------------------------------- executed .command (Git Bash, stubs)

def _usable_bash() -> str:
    candidates = [shutil.which("bash")]
    if sys.platform == "win32":
        candidates.append(r"C:\Program Files\Git\bin\bash.exe")
    for bash in candidates:
        if not bash or "system32" in bash.lower():
            continue  # the WSL launcher is not a usable POSIX shell for these checks
        try:
            probe = subprocess.run([bash, "--version"], capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0 and "bash" in probe.stdout.lower():
            return bash
    pytest.skip("no usable bash on this host to execute the .command launcher")


STUB_PY = """#!/bin/bash
echo "$0 $*" >> "$CALLS"
for arg in "$@"; do [ "$arg" = "-c" ] && exit 0; done
for arg in "$@"; do [ "$arg" = "--launch-only" ] && exit "$LAUNCH_RC"; done
exit "$SETUP_RC"
"""


def _run_command(tmp_path, *, venv: bool, base: bool, launch_rc=0, setup_rc=0, stdin="\n\n\n"):
    bash = _usable_bash()
    root = tmp_path / "Web Novel (copy)"
    (root / "scripts").mkdir(parents=True)
    shutil.copyfile(CMD, root / CMD.name)
    (root / "scripts" / "bootstrap.py").write_text("# not executed by the stub interpreters\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    stubs = []
    if venv:
        stubs.append(root / ".venv" / "bin" / "python")
    if base:
        stubs.append(bin_dir / "python3")
    for stub in stubs:
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text(STUB_PY, encoding="utf-8", newline="\n")
        stub.chmod(0o755)
    to_posix = lambda p: subprocess.run([bash, "-c", f'cygpath -u "{p}" 2>/dev/null || echo "{p}"'],
                                        capture_output=True, text=True).stdout.strip()
    # Only the stub directory and the shell's own coreutils: no real python3 is reachable.
    coreutils = Path(bash).parent if (Path(bash).parent / ("sort.exe" if sys.platform == "win32" else "sort")).exists()         else Path(bash).parent.parent / "usr" / "bin"
    env = dict(os.environ, CALLS=to_posix(calls), LAUNCH_RC=str(launch_rc), SETUP_RC=str(setup_rc),
               PATH=os.pathsep.join([str(bin_dir), str(coreutils)]))
    done = subprocess.run([bash, to_posix(root / CMD.name)], input=stdin, capture_output=True, text=True,
                          env=env, timeout=120)
    recorded = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return done, recorded


def test_command_healthy_fast_path(tmp_path):
    done, calls = _run_command(tmp_path, venv=True, base=True, launch_rc=0)
    assert done.returncode == 0, done.stdout + done.stderr
    assert len(calls) == 1 and calls[0].endswith("--launch-only")
    assert "running in its own window" in done.stdout


def test_command_launch_failure_is_reported_without_setup(tmp_path):
    done, calls = _run_command(tmp_path, venv=True, base=True, launch_rc=4)
    assert done.returncode == 4 and len(calls) == 1 and "could not start" in done.stdout


def test_command_repair_uses_an_external_python(tmp_path):
    done, calls = _run_command(tmp_path, venv=True, base=True, launch_rc=3, setup_rc=0)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "/bin/python3 " in calls[-1] and calls[-1].endswith("scripts/bootstrap.py")
    assert "Using Python:" in done.stdout


def test_command_missing_python_simulation_guides_and_installs_nothing(tmp_path):
    done, calls = _run_command(tmp_path, venv=False, base=False, stdin="N\n\n\n")
    assert done.returncode == 10 and calls == []
    # (bash prints read -p prompts only on a terminal; the echoed guidance is asserted instead)
    assert "Python 3.10 or newer is needed" in done.stdout and "python.org" in done.stdout
    assert "required and was not found" in done.stdout
