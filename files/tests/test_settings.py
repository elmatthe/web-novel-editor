"""Per-user runtime paths and atomic JSON persistence (``utils.settings``).

Re-homed from ``test_ai_foundation`` / ``test_cloud_keys_and_consent`` in Phase 01A. The
platform contracts are asserted on path *components* (``Path.parts``), never on host-native
string separators, so a Windows contract passes on a POSIX host and vice versa.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from utils import settings
from utils.settings import runtime_dir, settings_path, write_settings_atomic

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_windows_runtime_dir_is_under_localappdata():
    path = settings_path(
        platform="win32", environ={"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}
    )
    # Normalise through the pure Windows flavour so the assertion is host-independent.
    parts = PureWindowsPath(str(path)).parts
    assert parts[-2:] == ("WebNovelEditor", "settings.json")
    assert parts[:2] == ("C:\\", "Users")


def test_windows_runtime_dir_falls_back_to_the_home_appdata_folder():
    # NB: a non-empty mapping on purpose - `runtime_dir` treats an empty one as "use the
    # real os.environ" (carried over unchanged from ai.settings; noted in the P01 report).
    path = runtime_dir(platform="win32", environ={"OTHER": "1"}, home=Path("home"))
    assert path.parts[-4:] == ("home", "AppData", "Local", "WebNovelEditor")


def test_macos_runtime_dir_is_application_support():
    path = settings_path(platform="darwin", home=Path("/Users/test"))
    assert path.parts[-4:] == (
        "Library", "Application Support", "WebNovelEditor", "settings.json",
    )
    assert PurePosixPath("/Users/test/Library/Application Support/WebNovelEditor").name == (
        path.parent.name
    )


def test_an_unsupported_platform_is_refused_not_guessed():
    with pytest.raises(OSError):
        runtime_dir(platform="linux")


def test_atomic_write_round_trips_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    write_settings_atomic(path, {"theme": "light", "n": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"theme": "light", "n": 1}
    assert list(path.parent.glob("*.tmp")) == []
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_a_failed_replace_keeps_the_old_file_and_leaves_no_residue(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    write_settings_atomic(path, {"v": 1})

    def boom(*_args, **_kwargs):
        raise OSError("simulated kill between temp write and rename")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        write_settings_atomic(path, {"v": 2})
    monkeypatch.undo()

    assert json.loads(path.read_text(encoding="utf-8")) == {"v": 1}
    assert list(tmp_path.glob("*.tmp")) == []


def test_importing_the_utilities_has_no_filesystem_side_effects(tmp_path):
    """Run in a fresh interpreter from an empty directory: nothing may be created."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "scripts" / "Universal")
    completed = subprocess.run(
        [sys.executable, "-c", "import utils.settings, utils.pace"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert list(tmp_path.iterdir()) == []


def test_the_module_exposes_no_secret_or_provider_helpers():
    """The settings module is for preferences only; keys are not its business."""
    public = {name for name in dir(settings) if not name.startswith("_")}
    assert not any("secret" in n.lower() or "key" in n.lower() for n in public)
