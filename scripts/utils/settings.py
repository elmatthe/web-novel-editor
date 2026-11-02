"""Per-user runtime paths and atomic JSON persistence.

Extracted from the retired ``ai.settings`` (Phase 01A) with no behaviour change: the
per-user application-data location is kept exactly where earlier releases put it, so
existing ``settings.json`` files (and any legacy key files that sit beside them, which
this application never reads) are untouched.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping
from utils.atomic_io import sharing_retry


def runtime_dir(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    platform = platform or sys.platform
    environ = environ or os.environ
    home = home or Path.home()
    if platform == "win32":
        base = environ.get("LOCALAPPDATA")
        if not base:
            base = str(home / "AppData" / "Local")
        return Path(base) / "WebNovelEditor"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "WebNovelEditor"
    raise OSError(f"Unsupported platform: {platform}")


def settings_path(**kwargs) -> Path:
    return runtime_dir(**kwargs) / "settings.json"


def write_settings_atomic(path: Path, settings: Mapping[str, Any], *, validate=None) -> None:
    """Write ``settings`` as JSON via tempfile + fsync + ``os.replace``.

    The file on disk is always a complete, valid document: a crash leaves either the
    old version or the new one, never a partial write, and no temp file is left behind
    on failure.
    """
    if validate:
        validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dict(settings), indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(
        prefix=".m-", suffix=".tmp", dir=str(path.parent)
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        sharing_retry(lambda: os.replace(temp_path, path), validate=validate or (lambda: None))
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Desktop preferences (Phase 02B)
# ---------------------------------------------------------------------------
# Stored in the existing per-user settings.json. Only the keys below are read or written by
# this application; any other key already in the file (for example obsolete AI preferences
# from earlier releases) is ignored and preserved verbatim on save. Legacy key files beside
# settings.json are never opened. Audit/debug/dry-run choices are deliberately session-only:
# they can write chapter text and must be opted into for each session.

APPEARANCES = ("light", "dark")
DEFAULT_PREFERENCES: dict[str, Any] = {
    "appearance": "light",
    "novel": "Universal",
    "output_formats": ["pdf"],
    "include_subfolders": True,
    "output_root": None,  # None = Downloads/PDF-Editor-Outputs
}
#: Development/test override so automated runs never touch the user's real settings.
SETTINGS_FILE_ENV = "WNE_SETTINGS_FILE"


def preferences_path() -> Path:
    override = os.environ.get(SETTINGS_FILE_ENV)
    return Path(override) if override else settings_path()


def _valid(key: str, value: Any) -> bool:
    if key == "appearance":
        return value in APPEARANCES
    if key == "novel":
        return isinstance(value, str) and 0 < len(value) <= 200
    if key == "output_formats":
        return (isinstance(value, list) and 0 < len(value) <= 2
                and all(isinstance(v, str) and v in ("pdf", "txt") for v in value)
                and len(set(value)) == len(value))
    if key == "include_subfolders":
        return type(value) is bool
    if key == "output_root":
        return value is None or (isinstance(value, str) and Path(value).is_absolute())
    return False


def _read_raw(path: Path) -> tuple[dict, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, ""
    except (OSError, ValueError) as exc:
        return {}, f"Saved preferences could not be read ({type(exc).__name__}); defaults are in use."
    if not isinstance(data, dict):
        return {}, "Saved preferences were not a settings object; defaults are in use."
    return data, ""


def load_preferences(path: Path | None = None) -> tuple[dict[str, Any], list[str]]:
    """Return (validated preferences, notes). Invalid values fall back to defaults."""
    path = preferences_path() if path is None else path
    raw, problem = _read_raw(path)
    notes = [problem] if problem else []
    prefs = {key: (list(value) if isinstance(value, list) else value)
             for key, value in DEFAULT_PREFERENCES.items()}
    for key in DEFAULT_PREFERENCES:
        if key in raw:
            if _valid(key, raw[key]):
                prefs[key] = list(raw[key]) if isinstance(raw[key], list) else raw[key]
            else:
                notes.append(f"Saved preference '{key}' was invalid; the default is in use.")
    return prefs, notes


def save_preferences(prefs: Mapping[str, Any], path: Path | None = None) -> None:
    """Validate and atomically save; unrelated existing keys are preserved verbatim."""
    path = preferences_path() if path is None else path
    for key, value in prefs.items():
        if key not in DEFAULT_PREFERENCES or not _valid(key, value):
            raise ValueError(f"Invalid preference: {key}")
    raw, _problem = _read_raw(path)
    raw.update({key: (list(value) if isinstance(value, list) else value) for key, value in prefs.items()})
    write_settings_atomic(path, raw)


def reset_preferences(path: Path | None = None) -> bool:
    """Delete exactly the settings file (never its directory or siblings). Returns True if removed."""
    path = preferences_path() if path is None else path
    if path.is_symlink() or path.is_dir():
        raise OSError(f"Refusing to reset: settings path is not a regular file: {path}")
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
