"""Per-user runtime paths and atomic JSON persistence (``utils.settings``).

Re-homed from ``test_ai_foundation`` / ``test_cloud_keys_and_consent`` in Phase 01A. The
platform contracts are asserted on path *components* (``Path.parts``), never on host-native
string separators, so a Windows contract passes on a POSIX host and vice versa.
"""

from __future__ import annotations

import json
import os
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


def test_importing_the_utilities_has_no_filesystem_side_effects(tmp_path, offline_python):
    """Run in a fresh interpreter from an empty directory: nothing may be created."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "scripts")
    completed = offline_python.run(
        ["-c", "import utils.settings, utils.pace"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert list(tmp_path.iterdir()) == []


def test_the_module_exposes_no_secret_or_provider_helpers():
    """The settings module is for preferences only; keys are not its business."""
    public = {name for name in dir(settings) if not name.startswith("_")}
    assert not any("secret" in n.lower() or "key" in n.lower() for n in public)


# --- Desktop preferences (Phase 02B) ------------------------------------------------------

def test_preferences_default_when_absent_and_override_points_at_isolated_file(tmp_path, monkeypatch):
    from utils.settings import DEFAULT_PREFERENCES, load_preferences, preferences_path
    target = tmp_path / "isolated" / "settings.json"
    monkeypatch.setenv("WNE_SETTINGS_FILE", str(target))
    assert preferences_path() == target
    prefs, notes = load_preferences()
    assert prefs == DEFAULT_PREFERENCES and notes == []
    assert DEFAULT_PREFERENCES == {"appearance": "light", "novel": "Universal", "output_formats": ["pdf"],
                                   "include_subfolders": True, "output_root": None}


@pytest.mark.parametrize("raw,key", [
    ({"appearance": "blue"}, "appearance"), ({"output_formats": []}, "output_formats"),
    ({"output_formats": ["pdf", "pdf"]}, "output_formats"), ({"output_formats": ["epub"]}, "output_formats"),
    ({"include_subfolders": "yes"}, "include_subfolders"), ({"output_root": "relative/dir"}, "output_root"),
    ({"novel": ""}, "novel")])
def test_invalid_saved_values_fall_back_with_a_note(tmp_path, raw, key):
    from utils.settings import DEFAULT_PREFERENCES, load_preferences
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    prefs, notes = load_preferences(path)
    assert prefs[key] == DEFAULT_PREFERENCES[key]
    assert notes == [f"Saved preference '{key}' was invalid; the default is in use."]


def test_corrupt_settings_are_reported_not_raised(tmp_path):
    from utils.settings import DEFAULT_PREFERENCES, load_preferences
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    prefs, notes = load_preferences(path)
    assert prefs == DEFAULT_PREFERENCES and "could not be read" in notes[0]


def test_save_validates_and_preserves_unrelated_legacy_keys(tmp_path):
    from utils.settings import load_preferences, save_preferences
    path = tmp_path / "settings.json"
    legacy = {"ai_provider": "groq", "cloud_consent": True, "nested": {"keep": [1, 2]}}
    path.write_text(json.dumps(legacy), encoding="utf-8")
    absolute = str((tmp_path / "out").absolute())
    save_preferences({"appearance": "dark", "output_root": absolute, "output_formats": ["txt", "pdf"]}, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert {k: data[k] for k in legacy} == legacy
    prefs, notes = load_preferences(path)
    assert notes == [] and prefs["appearance"] == "dark" and prefs["output_root"] == absolute
    with pytest.raises(ValueError):
        save_preferences({"appearance": "neon"}, path)
    with pytest.raises(ValueError):
        save_preferences({"api_key": "x"}, path)
    assert json.loads(path.read_text(encoding="utf-8"))["appearance"] == "dark"


def test_reset_removes_only_the_exact_settings_file(tmp_path):
    from utils.settings import reset_preferences
    folder = tmp_path / "WebNovelEditor"
    folder.mkdir()
    settings_file = folder / "settings.json"
    settings_file.write_text('{"appearance": "dark"}', encoding="utf-8")
    sentinels = {"secrets.json": b'{"GEMINI_API_KEY": "sentinel"}', "notes.txt": b"user",
                 "settings.json.bak": b"backup"}
    for name, data in sentinels.items():
        (folder / name).write_bytes(data)
    assert reset_preferences(settings_file) is True
    assert not settings_file.exists() and folder.is_dir()
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == sentinels
    assert reset_preferences(settings_file) is False


def test_reset_refuses_a_directory_in_place_of_the_settings_file(tmp_path):
    from utils.settings import reset_preferences
    weird = tmp_path / "settings.json"
    weird.mkdir()
    (weird / "inside.txt").write_text("keep")
    with pytest.raises(OSError):
        reset_preferences(weird)
    assert (weird / "inside.txt").read_text() == "keep"
