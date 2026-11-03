#!/usr/bin/env python3
"""Web Novel Editor setup / self-healing bootstrap (standard library only).

Adapted (Phase 02B) from the author's PDF-Splitter ``scripts/Setup-and-Run/bootstrap.py`` at
``edcbd4fe6db96bb7515e719172fbd4172fe3ef19``: ASSESS -> RECONCILE/REPAIR -> PROVE -> LAUNCH ->
REPORT, bounded probes, external-interpreter repair, a health-state record and detached launch
with an immediate-failure check. Changed for this project: Python >= 3.10 (no fixed upper bound;
tested versions are preferred), a stdlib config reader that also works on 3.10, direct
verification of every exact pin (so an already-satisfied environment never needs the network),
Microsoft Store alias exclusion, and a stricter ``.venv`` deletion guard.

Launch chain (no recursion): root ``Setup_and_Run-Web-Novel-Editor`` -> this file ->
``scripts/launcher.py`` (detached). ``launcher.py`` never calls back into this file.

* ``--launch-only`` (healthy fast path, run with the project ``.venv`` interpreter): proves health
  read-only and launches. It never installs, never queries a package index, never upgrades pip
  and never touches the network. Exit 3 means setup/repair is needed.
* default (setup): run by an external base Python found by the root launcher. Repairs missing
  packages in place; rebuilds a broken ``.venv`` only from an external interpreter.
* ``--venv-check``: read-only health gate. ``--setup-only``: repair/prove without launching.
  ``--repair-venv``: force a rebuild (external interpreter only).

First setup or repair may need internet access to download packages unless they are already
available; that is never described as guaranteed offline installation.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

PROJECT_NAME = "Web Novel Editor"
DEFAULT_MIN_PYTHON = (3, 10)
#: Versions this release was verified on, preferred (in order) when several are installed.
TESTED_PYTHONS = ((3, 13), (3, 12), (3, 11), (3, 10))
LAUNCH_GRACE_SECONDS = 3.0
STATE_SCHEMA = 1
PYTHON_DOWNLOAD_URL = "https://www.python.org/downloads/"

EXIT_OK = 0
EXIT_CANCELLED = 2
EXIT_VENV_UNHEALTHY = 3
EXIT_LAUNCH_FAILED = 4
EXIT_SETUP_FAILED = 10

#: Only these may appear at the top of a ``.venv`` the bootstrap is allowed to delete.
VENV_SHAPED_NAMES = frozenset({"Scripts", "Lib", "Include", "bin", "lib", "lib64", "include", "share",
                               "etc", "pyvenv.cfg", ".gitignore", "requirements.lock"})


def _set_root(root: Path) -> None:
    """(Re)compute every repository path; tests point this at a contained sandbox."""
    global REPO_ROOT, CONFIG_PATH, VENV_DIR, REQUIREMENTS_PATH, ENTRY_POINT, RUNTIME_DIR
    global STATE_PATH, LOG_DIR, SETUP_LOG_PATH, LAUNCH_LOG_PATH, APP_OUTPUT_LOG_PATH, VENV_PYTHON, VENV_PYTHONW
    REPO_ROOT = Path(root)
    CONFIG_PATH = REPO_ROOT / "config.toml"
    VENV_DIR = REPO_ROOT / ".venv"
    REQUIREMENTS_PATH = REPO_ROOT / "scripts" / "requirements.txt"
    ENTRY_POINT = REPO_ROOT / "scripts" / "launcher.py"
    RUNTIME_DIR = REPO_ROOT / "files" / "runtime-data"
    STATE_PATH = RUNTIME_DIR / "bootstrap" / "bootstrap-state.json"
    LOG_DIR = RUNTIME_DIR / "logs"
    SETUP_LOG_PATH = LOG_DIR / "setup-latest.log"
    LAUNCH_LOG_PATH = LOG_DIR / "launch-latest.log"
    APP_OUTPUT_LOG_PATH = LOG_DIR / "app-output-latest.log"
    if os.name == "nt":
        VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
        VENV_PYTHONW = VENV_DIR / "Scripts" / "pythonw.exe"
    else:
        VENV_PYTHON = VENV_DIR / "bin" / "python"
        VENV_PYTHONW = VENV_PYTHON


_set_root(Path(__file__).resolve().parents[1])

_LOG_HANDLE = None
_LOG_PATH: Path | None = None

BASE_PYTHON_PROBE = r"""
import json, sys
ok = True
try:
    import ssl, venv, tkinter
    tkinter.Tcl()
except Exception:
    ok = False
print(json.dumps({"exe": sys.executable, "v": list(sys.version_info[:3]), "ok": ok}))
"""

# Runs inside the project .venv. PINS is injected as a JSON list of [name, version].
VENV_HEALTH_PROBE = r"""
import json, sys
errors, mismatched = [], []
modules = ["pdfplumber", "reportlab", "natsort", "tomllib" if sys.version_info >= (3, 11) else "tomli"]
for name in modules:
    try:
        __import__(name)
    except Exception as exc:
        errors.append("import %s failed: %s" % (name, type(exc).__name__))
try:
    import tkinter
    tkinter.Tcl().eval("info patchlevel")
except Exception as exc:
    errors.append("tkinter/Tcl failed: %s" % type(exc).__name__)
try:
    import pip
except Exception as exc:
    errors.append("pip is missing: %s" % type(exc).__name__)
from importlib import metadata
for name, version in PINS:
    try:
        installed = metadata.version(name)
    except Exception:
        installed = None
    if installed != version:
        mismatched.append("%s==%s (installed: %s)" % (name, version, installed or "missing"))
print(json.dumps({"v": list(sys.version_info[:3]), "venv": sys.prefix != sys.base_prefix,
                  "errors": errors, "pins": mismatched}))
"""


class BootstrapError(RuntimeError):
    """Expected setup failure with a user-readable message."""


# ---------------------------------------------------------------------------- logging/processes

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def open_log(path: Path) -> None:
    global _LOG_HANDLE, _LOG_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _LOG_HANDLE = path.open("w", encoding="utf-8", newline="\n")
    except OSError as exc:
        print(f"Note: the setup log could not be written ({type(exc).__name__}); continuing.", flush=True)
        _LOG_HANDLE = None
        return
    _LOG_PATH = path
    _LOG_HANDLE.write(f"{PROJECT_NAME} bootstrap\nStarted: {utc_now()}\nRepository: {REPO_ROOT}\n"
                      f"Bootstrap Python: {sys.version.split()[0]}\n")
    _LOG_HANDLE.flush()


def close_log() -> None:
    global _LOG_HANDLE
    if _LOG_HANDLE is not None:
        _LOG_HANDLE.close()
        _LOG_HANDLE = None


def log_only(message: str) -> None:
    if _LOG_HANDLE is not None:
        _LOG_HANDLE.write(message + "\n")
        _LOG_HANDLE.flush()


def say(message: str = "") -> None:
    print(message, flush=True)
    log_only(message)


def stage(name: str) -> None:
    say()
    say(f"[{name}]")


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(PYTHONIOENCODING="utf-8", PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INPUT="1")
    env.pop("PYTHONHOME", None)
    return env


def run_bounded(args, *, timeout: float = 30.0) -> subprocess.CompletedProcess:
    try:
        return subprocess.run([os.fspath(a) for a in args], cwd=os.fspath(REPO_ROOT), text=True,
                              encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                              env=child_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BootstrapError(f"A required process could not be executed: {type(exc).__name__}.") from exc


def run_streamed(args) -> int:
    try:
        proc = subprocess.Popen([os.fspath(a) for a in args], cwd=os.fspath(REPO_ROOT), text=True,
                                encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                                env=child_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as exc:
        raise BootstrapError(f"A required process could not be started: {type(exc).__name__}.") from exc
    assert proc.stdout is not None
    for line in proc.stdout:
        say("    " + line.rstrip())
    return proc.wait()


def last_json_line(text: str) -> dict | None:
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                return None
            return data if isinstance(data, dict) else None
    return None


# ---------------------------------------------------------------------------- configuration

def parse_project_table(text: str) -> dict:
    """``[project]`` from config.toml: ``tomllib`` when present, else a strict string-only reader.

    The fallback keeps this file stdlib-only on Python 3.10 (where ``tomli`` may not be
    installed yet). It accepts only ``key = "string"`` lines in ``[project]`` and rejects
    anything else there, so it can never silently misread the file.
    """
    try:
        import tomllib
    except ModuleNotFoundError:
        tomllib = None
    if tomllib is not None:
        table = tomllib.loads(text).get("project", {})
        return table if isinstance(table, dict) else {}
    table, inside = {}, False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            inside = line == "[project]"
            continue
        if inside:
            match = re.fullmatch(r'([A-Za-z0-9_-]+)\s*=\s*"([^"\\]*)"\s*(?:#.*)?', line)
            if not match:
                raise ValueError(f"Unsupported config.toml [project] line: {line}")
            table[match.group(1)] = match.group(2)
    return table


def read_config() -> dict:
    if not CONFIG_PATH.is_file():
        raise BootstrapError(f"config.toml is missing: {CONFIG_PATH}")
    try:
        return parse_project_table(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BootstrapError(f"config.toml could not be read: {exc}") from exc


def minimum_python(config: dict) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)", str(config.get("python_minimum", "")))
    return (int(match.group(1)), int(match.group(2))) if match else DEFAULT_MIN_PYTHON


def check_entry_point() -> Path:
    if not ENTRY_POINT.is_file():
        raise BootstrapError(f"Application entry point is missing: {ENTRY_POINT}")
    return ENTRY_POINT


def requirement_pins() -> list[tuple[str, str]]:
    """Exact ``name==version`` pins; any other requirement form is refused (pins are mandatory)."""
    if not REQUIREMENTS_PATH.is_file():
        raise BootstrapError(f"Required dependency file is missing: {REQUIREMENTS_PATH}")
    pins = []
    for raw in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9.+!_-]+)", line)
        if not match:
            raise BootstrapError(f"Unsupported (unpinned) requirement: {line}")
        pins.append((match.group(1), match.group(2)))
    return pins


def requirements_hash() -> str:
    return hashlib.sha256(REQUIREMENTS_PATH.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------- health state record

def write_state(*, python_version: str) -> None:
    """Record a passed full proof. Health is always re-proven directly, so a stale record can
    never cause a false healthy launch; it documents what was proven and when."""
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp = STATE_PATH.with_suffix(".json.tmp")
        temp.write_text(json.dumps({"schema": STATE_SCHEMA, "result": "pass", "timestamp_utc": utc_now(),
                                    "python_version": python_version,
                                    "requirements_sha256": requirements_hash()}, indent=2, sort_keys=True)
                        + "\n", encoding="utf-8", newline="\n")
        os.replace(temp, STATE_PATH)
    except OSError as exc:
        say(f"Note: the health record could not be saved ({type(exc).__name__}).")


def clear_state() -> None:
    try:
        STATE_PATH.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------- base Python discovery

def inside_venv_dir(path: Path) -> bool:
    try:
        Path(path).resolve().relative_to(VENV_DIR.resolve())
        return True
    except (OSError, ValueError):
        return False


def running_from_project_venv() -> bool:
    return inside_venv_dir(Path(sys.executable))


def is_store_alias(path: str) -> bool:
    """Microsoft Store aliases/installs live under WindowsApps; never execute or rely on them."""
    return "\\windowsapps\\" in os.path.normcase(str(path)).replace("/", "\\") + "\\"


def _py_launcher_paths() -> list[str]:
    py = shutil.which("py")
    if not py or is_store_alias(py):
        return []
    try:
        result = run_bounded([py, "-0p"], timeout=10.0)
    except BootstrapError:
        return []
    return [m.group(1).strip() for m in re.finditer(r"(?m)\s((?:[A-Za-z]:|\\\\)\S.*python\.exe)\s*$",
                                                     result.stdout or "")]


def base_python_candidates(min_version: tuple[int, int]) -> list[str]:
    found: list[str] = []
    if not running_from_project_venv():
        found.append(sys.executable)
    if os.name == "nt":
        found.extend(_py_launcher_paths())
        local, program_files = os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles")
        if local:
            found.extend(sorted(glob.glob(os.path.join(local, "Programs", "Python", "Python3*", "python.exe")),
                                reverse=True))
        if program_files:
            found.extend(sorted(glob.glob(os.path.join(program_files, "Python3*", "python.exe")), reverse=True))
        for command in ("python", "python3"):
            resolved = shutil.which(command)
            if resolved:
                found.append(resolved)
    else:
        found.extend(sorted(glob.glob("/Library/Frameworks/Python.framework/Versions/3.*/bin/python3"),
                            reverse=True))
        for prefix in ("/opt/homebrew/bin", "/usr/local/bin"):
            found.extend(sorted(glob.glob(f"{prefix}/python3.[0-9]*"), reverse=True))
        resolved = shutil.which("python3")
        # Apple's /usr/bin/python3 is a Command Line Tools stub with an unsupported Tk.
        if resolved and resolved != "/usr/bin/python3":
            found.append(resolved)
    unique, seen = [], set()
    for path in found:
        key = os.path.normcase(os.path.abspath(path))
        if key not in seen and not is_store_alias(path):
            seen.add(key)
            unique.append(path)
    return unique


def probe_base_python(executable: str, min_version: tuple[int, int]) -> tuple[int, int, int] | None:
    if is_store_alias(executable) or not Path(executable).is_file():
        return None
    try:
        result = run_bounded([executable, "-c", BASE_PYTHON_PROBE], timeout=20.0)
    except BootstrapError:
        return None
    payload = last_json_line(result.stdout) if result.returncode == 0 else None
    if not payload or not payload.get("ok"):
        return None
    try:
        version = tuple(int(x) for x in payload["v"][:3])
        resolved = Path(payload["exe"]).resolve()
    except (KeyError, TypeError, ValueError, OSError):
        return None
    if len(version) != 3 or version[:2] < min_version or inside_venv_dir(resolved):
        return None
    return version  # type: ignore[return-value]


def _preference(version: tuple[int, int, int]) -> tuple:
    major_minor = version[:2]
    rank = TESTED_PYTHONS.index(major_minor) if major_minor in TESTED_PYTHONS else len(TESTED_PYTHONS)
    return (rank, tuple(-v for v in version))


def find_base_python(min_version: tuple[int, int]) -> tuple[str, tuple[int, int, int]]:
    usable = []
    for candidate in base_python_candidates(min_version):
        version = probe_base_python(candidate, min_version)
        if version is not None:
            usable.append((candidate, version))
    if not usable:
        raise BootstrapError(
            f"No separate Python {min_version[0]}.{min_version[1]} or newer with venv and Tk support was "
            f"found to build the project environment. Install Python from {PYTHON_DOWNLOAD_URL} "
            "(Windows: tick \"Add python.exe to PATH\"), then run the Setup_and_Run launcher again.")
    usable.sort(key=lambda item: _preference(item[1]))
    return usable[0]


# ---------------------------------------------------------------------------- environment health

def venv_health(min_version: tuple[int, int]) -> tuple[str | None, list[str], list[str]]:
    """Return (python_version_text, fatal problems, pin mismatches) for the project .venv."""
    if not VENV_PYTHON.is_file():
        return None, ["project .venv is missing"], []
    try:
        pins = requirement_pins()
    except BootstrapError as exc:
        return None, [str(exc)], []
    code = f"PINS = {json.dumps(pins)}\n{VENV_HEALTH_PROBE}"
    try:
        result = run_bounded([VENV_PYTHON, "-c", code], timeout=90.0)
    except BootstrapError as exc:
        return None, [f"project .venv Python could not run ({exc})"], []
    payload = last_json_line(result.stdout)
    if result.returncode != 0 or payload is None:
        return None, ["project .venv Python did not complete its health probe"], []
    try:
        version = [int(x) for x in payload["v"][:3]]
    except (KeyError, TypeError, ValueError):
        return None, ["project .venv health probe returned no version"], []
    text = ".".join(str(x) for x in version)
    if not payload.get("venv"):
        return None, ["project .venv is not a virtual environment"], []
    if tuple(version[:2]) < min_version:
        return None, [f"project .venv uses Python {text}; {min_version[0]}.{min_version[1]}+ is required"], []
    return text, [str(e) for e in payload.get("errors", [])], [str(p) for p in payload.get("pins", [])]


def pip_check_problem() -> str | None:
    try:
        result = run_bounded([VENV_PYTHON, "-m", "pip", "check", "--disable-pip-version-check"], timeout=90.0)
    except BootstrapError as exc:
        return f"pip check could not run ({exc})"
    if result.returncode != 0:
        details = (result.stdout or result.stderr or "").strip()
        return "pip check failed" + (f": {details}" if details else "")
    return None


def entry_smoke_problem() -> str | None:
    try:
        result = run_bounded([VENV_PYTHON, check_entry_point(), "--check"], timeout=90.0)
    except BootstrapError as exc:
        return f"startup check could not run ({exc})"
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip().splitlines()
        return f"startup check failed (exit {result.returncode}): {details[-1] if details else 'no output'}"
    return None


def full_health_problems(min_version: tuple[int, int]) -> tuple[str | None, list[str]]:
    """Complete read-only proof: interpreter, imports, Tk, pip, exact pins, pip check, entry smoke."""
    version, problems, pins = venv_health(min_version)
    if version is None:
        return None, problems
    problems = problems + [f"dependency not at its exact pin: {p}" for p in pins]
    if not problems:
        problem = pip_check_problem()
        if problem:
            problems.append(problem)
    if not problems:
        problem = entry_smoke_problem()
        if problem:
            problems.append(problem)
    return version, problems


def fast_health_check() -> tuple[bool, str]:
    """Read-only gate for the healthy fast path. Never repairs, installs or uses the network."""
    try:
        config = read_config()
        check_entry_point()
        version, problems = full_health_problems(minimum_python(config))
        if version is None or problems:
            return False, "; ".join(problems) or "project .venv is unhealthy"
        return True, f"healthy (Python {version})"
    except BootstrapError as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------- repair

def _is_link_or_junction(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def assert_safe_venv_target() -> None:
    """Prove the deletion target is this repository's own venv-shaped ``.venv``."""
    if VENV_DIR != REPO_ROOT / ".venv" or VENV_DIR.parent.resolve() != REPO_ROOT.resolve():
        raise BootstrapError("Refusing to delete: the environment path is not this project's .venv.")
    if _is_link_or_junction(VENV_DIR):
        raise BootstrapError(f"Refusing to delete {VENV_DIR}: it is a link or junction to another location. "
                             "Remove that link yourself, then run the launcher again.")
    if not VENV_DIR.is_dir():
        raise BootstrapError(f"Refusing to delete {VENV_DIR}: it is not a folder.")
    unexpected = sorted(p.name for p in VENV_DIR.iterdir() if p.name not in VENV_SHAPED_NAMES)
    if unexpected:
        raise BootstrapError(f"Refusing to delete {VENV_DIR}: it contains files that are not part of a Python "
                             f"environment ({', '.join(unexpected[:5])}). Move them, then run the launcher again.")
    if running_from_project_venv():
        raise BootstrapError("The project environment must be rebuilt, but this setup is running from inside "
                             "it. Install a separate Python from " + PYTHON_DOWNLOAD_URL +
                             " and run the Setup_and_Run launcher again.")


def remove_venv() -> None:
    if not os.path.lexists(VENV_DIR):
        return
    assert_safe_venv_target()
    say("Removing the unhealthy project .venv...")
    try:
        shutil.rmtree(VENV_DIR)
    except OSError as exc:
        raise BootstrapError("The old .venv could not be removed (a file is in use). Close Web Novel Editor "
                             "and any program using this folder, then run the launcher again.") from exc


def create_venv(min_version: tuple[int, int]) -> None:
    base, version = find_base_python(min_version)
    say(f"Creating project .venv with Python {'.'.join(map(str, version))} ({base})...")
    if run_streamed([base, "-m", "venv", VENV_DIR]) != 0 or not VENV_PYTHON.is_file():
        raise BootstrapError("Python could not create the project .venv.")


def ensure_pip() -> None:
    try:
        ok = run_bounded([VENV_PYTHON, "-m", "pip", "--version"], timeout=60.0).returncode == 0
    except BootstrapError:
        ok = False
    if ok:
        return
    say("Repairing pip inside the project .venv (bundled copy, no download)...")
    if run_streamed([VENV_PYTHON, "-m", "ensurepip", "--default-pip"]) != 0:
        raise BootstrapError("pip is missing or damaged and could not be repaired.")


def install_requirements() -> None:
    say("Installing the exact project dependencies into .venv (this may need internet access)...")
    rc = run_streamed([VENV_PYTHON, "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
                       "--progress-bar", "off", "-r", REQUIREMENTS_PATH])
    if rc != 0:
        raise BootstrapError("Project dependencies could not be installed. Check the internet connection and "
                             "run the launcher again; the pip output is in the setup log. If this Python is "
                             "newer than 3.13, installing Python 3.13 may be required.")


def reconcile(min_version: tuple[int, int], *, force_rebuild: bool) -> str:
    """Bring the .venv to a proven-healthy state; returns its Python version."""
    rebuilt = False
    if force_rebuild:
        say("A full .venv rebuild was requested.")
    else:
        version, problems, _pins = venv_health(min_version)
        if version is None:
            say(f"Project .venv needs rebuilding: {'; '.join(problems)}")
            force_rebuild = True
        else:
            say(f"Reusing the existing project .venv (Python {version}).")
    if force_rebuild:
        clear_state()
        remove_venv()
        create_venv(min_version)
        rebuilt = True
    while True:
        ensure_pip()
        _version, _problems, pins = venv_health(min_version)
        if rebuilt or pins:
            for pin in pins:
                say(f"  needs install: {pin}")
            install_requirements()
        else:
            say("Every dependency is already at its exact pin; nothing to install.")
        stage("PROVE")
        version, problems = full_health_problems(min_version)
        if version is not None and not problems:
            write_state(python_version=version)
            say(f"Environment proven healthy with Python {version}.")
            return version
        for problem in problems:
            say(f"  - {problem}")
        if rebuilt:
            raise BootstrapError("The rebuilt project environment still failed its health proof.")
        say("Health proof failed; rebuilding the project .venv once...")
        clear_state()
        remove_venv()
        create_venv(min_version)
        rebuilt = True


# ---------------------------------------------------------------------------- launch

def tail_text(path: Path, lines: int = 15) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    return "\n".join(content.splitlines()[-lines:])


def launch_application() -> int:
    """Start the GUI detached and confirm it did not fail immediately."""
    target = check_entry_point()
    python = VENV_PYTHONW if VENV_PYTHONW.is_file() else VENV_PYTHON
    kwargs: dict = {"cwd": os.fspath(REPO_ROOT), "stdin": subprocess.DEVNULL, "stderr": subprocess.STDOUT,
                    "close_fds": True, "env": child_env()}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    say(f"Launching {PROJECT_NAME}...")
    try:
        APP_OUTPUT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        app_log = APP_OUTPUT_LOG_PATH.open("w", encoding="utf-8", newline="\n")
    except OSError as exc:
        say(f"ERROR: the application output log could not be created ({type(exc).__name__}).")
        return EXIT_LAUNCH_FAILED
    with app_log:
        app_log.write(f"{PROJECT_NAME} application output - started {utc_now()}\n")
        app_log.flush()
        try:
            proc = subprocess.Popen([os.fspath(python), os.fspath(target)], stdout=app_log, **kwargs)
        except OSError as exc:
            say(f"ERROR: {PROJECT_NAME} could not be started: {exc}")
            return EXIT_LAUNCH_FAILED
    try:
        rc = proc.wait(timeout=LAUNCH_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        say(f"{PROJECT_NAME} started in its own window.")
        return EXIT_OK
    if rc == 0:
        say(f"{PROJECT_NAME} opened and closed again straight away (exit code 0).")
        return EXIT_OK
    say(f"ERROR: {PROJECT_NAME} stopped immediately after starting (exit code {rc}).")
    tail = tail_text(APP_OUTPUT_LOG_PATH)
    if tail:
        say("Last application output:")
        for line in tail.splitlines():
            say("    " + line)
    say(f"Application output log: {APP_OUTPUT_LOG_PATH}")
    return EXIT_LAUNCH_FAILED


# ---------------------------------------------------------------------------- modes

def setup(*, force_rebuild: bool, launch: bool) -> int:
    open_log(SETUP_LOG_PATH)
    stage("ASSESS")
    config = read_config()
    min_version = minimum_python(config)
    check_entry_point()
    requirement_pins()
    say(f"Required Python: {min_version[0]}.{min_version[1]} or newer "
        f"(running setup with {sys.version.split()[0]}"
        + (", inside the project .venv" if running_from_project_venv() else "") + ")")
    stage("RECONCILE / REPAIR")
    reconcile(min_version, force_rebuild=force_rebuild)
    if not launch:
        stage("REPORT")
        say("Setup completed successfully; launch was skipped (--setup-only).")
        return EXIT_OK
    stage("LAUNCH")
    rc = launch_application()
    stage("REPORT")
    say("Setup and launch completed." if rc == EXIT_OK else "Launch failed.")
    return rc


def launch_only() -> int:
    open_log(LAUNCH_LOG_PATH)
    healthy, reason = fast_health_check()
    if not healthy:
        log_only(f"Fast path refused: {reason}")
        print(f"Setup or repair is needed: {reason}", flush=True)
        return EXIT_VENV_UNHEALTHY
    log_only(f"Fast path health proof passed: {reason}")
    version = reason.split("Python ", 1)[-1].rstrip(")")
    write_state(python_version=version)
    return launch_application()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"{PROJECT_NAME} setup / self-healing bootstrap")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--venv-check", action="store_true",
                      help="read-only health gate; exit 0=healthy, 3=setup/repair needed")
    mode.add_argument("--launch-only", action="store_true",
                      help="prove the existing environment, then launch; exit 3 if repair is needed")
    mode.add_argument("--repair-venv", action="store_true",
                      help="force a .venv rebuild from an external Python, prove it, then launch")
    mode.add_argument("--setup-only", action="store_true", help="assess/repair/prove without launching")
    parser.add_argument("--debug", action="store_true", help="show a traceback for unexpected errors")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.venv_check:
        healthy, reason = fast_health_check()
        print(reason)
        return EXIT_OK if healthy else EXIT_VENV_UNHEALTHY
    try:
        if args.launch_only:
            return launch_only()
        return setup(force_rebuild=args.repair_venv, launch=not args.setup_only)
    except KeyboardInterrupt:
        say()
        say("Setup cancelled.")
        return EXIT_CANCELLED
    except BootstrapError as exc:
        say()
        say(f"ERROR: {exc}")
        if _LOG_PATH is not None:
            say(f"Setup log: {_LOG_PATH}")
        return EXIT_SETUP_FAILED
    except Exception as exc:  # noqa: BLE001 - visible last-resort report
        say()
        say(f"ERROR: Unexpected bootstrap failure: {exc}")
        if args.debug:
            traceback.print_exc()
        log_only(traceback.format_exc())
        if _LOG_PATH is not None:
            say(f"Full details saved to: {_LOG_PATH}")
        return EXIT_SETUP_FAILED
    finally:
        close_log()


if __name__ == "__main__":
    raise SystemExit(main())
