"""Filename/path helpers.

`sanitize_output_filename` strips characters illegal on Windows/macOS and bounds length.
`unique_output_path` keeps the ORIGINAL filename (v0.11.0: no EDITED_ prefix) and appends
a numeric suffix (<name>_2.pdf, _3.pdf, ...) so a re-run never overwrites a prior output.
`debug_text_path` derives the paired DEBUG_<name>.txt sidecar from a chosen output path,
keeping the same numeric suffix so the debug file matches its PDF.
`open_in_file_manager` opens a folder in the OS file manager cross-platform, never raising.

Forced output location (v0.11.0): batches always write into an auto-numbered folder in
the user's Downloads — `downloads_dir` resolves the real Downloads known folder,
`kebab_case` turns the novel selection into the folder base name, and
`next_numbered_output_dir` picks the next free `<name>-x`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# Characters illegal in filenames on Windows (superset of macOS restrictions).
_ILLEGAL = '<>:"/\\|?*'
_MAX_STEM = 150  # keep well under the 255-char path-component limit

# Windows known-folder ID for Downloads (KNOWNFOLDERID {374DE290-123F-4565-9164-39C4925E467B}).
_FOLDERID_DOWNLOADS = "374DE290-123F-4565-9164-39C4925E467B"


def _windows_known_folder_downloads() -> Path | None:
    """Resolve the real Windows Downloads folder via SHGetKnownFolderPath.

    Honors a user-relocated Downloads (unlike guessing %USERPROFILE%\\Downloads).
    Returns None on any failure or off Windows, so the caller can fall back.
    """
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        import uuid

        class _GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        u = uuid.UUID(_FOLDERID_DOWNLOADS)
        guid = _GUID(u.time_low, u.time_mid, u.time_hi_version,
                     (ctypes.c_ubyte * 8)(*u.bytes[8:]))
        ppath = ctypes.c_wchar_p()
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, ctypes.byref(ppath))
        if hr != 0 or not ppath.value:
            return None
        try:
            return Path(ppath.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(ppath)
    except Exception:
        return None


def downloads_dir() -> Path:
    """Return the user's Downloads folder.

    Windows: the real known folder via SHGetKnownFolderPath. macOS/Linux — and any
    Windows lookup failure — fall back to ~/Downloads (on macOS that IS the standard
    location, so macOS support later is exactly this branch).
    """
    resolved = _windows_known_folder_downloads()
    return resolved if resolved is not None else Path.home() / "Downloads"


def kebab_case(name: str) -> str:
    """Kebab-case a display name for folder naming: 'Shadow Slave' -> 'shadow-slave'.

    Alphanumeric runs are kept lowercased; everything between them collapses to a
    single hyphen; leading/trailing separators are dropped.
    """
    return "-".join(re.findall(r"[a-z0-9]+", name.lower()))


def next_numbered_output_dir(parent: Path, base: str) -> Path:
    """Return `parent/<base>-x` where x = max(N of existing `<base>-N` dirs) + 1.

    Starts at `<base>-1`. The match is case-insensitive (Windows folder semantics)
    and only counts real directories whose suffix is purely numeric. The folder is
    NOT created here — creation happens only when the batch actually starts.
    """
    parent = Path(parent)
    pattern = re.compile(re.escape(base) + r"-(\d+)$", re.IGNORECASE)
    highest = 0
    try:
        for entry in parent.iterdir():
            match = pattern.fullmatch(entry.name)
            if match and entry.is_dir():
                highest = max(highest, int(match.group(1)))
    except OSError:
        pass  # missing/unreadable parent: treat as empty, never crash
    return parent / f"{base}-{highest + 1}"


def sanitize_output_filename(name: str) -> str:
    """Return a filesystem-safe version of `name` (stem only, no directory)."""
    name = os.path.basename(name)
    cleaned = "".join("_" if ch in _ILLEGAL or ord(ch) < 32 else ch for ch in name)
    cleaned = cleaned.strip(" .")  # trailing dots/spaces are invalid on Windows
    if len(cleaned) > _MAX_STEM:
        cleaned = cleaned[:_MAX_STEM].rstrip(" .")
    return cleaned or "untitled"


def unique_output_path(output_dir: str, base_name: str) -> str:
    """Return a non-colliding '<base_name>.pdf' path inside output_dir.

    The original filename is kept as-is (v0.11.0 dropped the EDITED_ prefix — the
    auto-numbered output folder already marks the files as edited copies). base_name
    is the original PDF's name (with or without extension). If the target already
    exists, a numeric suffix is inserted before the extension: _2, _3, ...
    """
    stem = sanitize_output_filename(base_name)
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]
    candidate = os.path.join(output_dir, f"{stem}.pdf")
    if not os.path.exists(candidate):
        return candidate
    n = 2
    while True:
        candidate = os.path.join(output_dir, f"{stem}_{n}.pdf")
        if not os.path.exists(candidate):
            return candidate
        n += 1


def debug_text_path(output_path: str) -> str:
    """Return the DEBUG_<name>.txt sidecar path for a <name>.pdf output path.

    Keeps the same directory and numeric collision suffix as the PDF, adding the
    ``DEBUG_`` prefix and swapping the extension for ``.txt`` (matches the spec and
    the GUI option label).
    """
    directory = os.path.dirname(output_path)
    stem = os.path.splitext(os.path.basename(output_path))[0]
    if not stem.startswith("DEBUG_"):
        stem = "DEBUG_" + stem
    return os.path.join(directory, stem + ".txt")


def open_in_file_manager(path: str) -> bool:
    """Open `path` in the OS file manager. Returns True on success, never raises.

    Windows uses os.startfile; macOS uses `open`; other POSIX uses `xdg-open`. Any
    failure (missing helper, headless session, bad path) returns False so the caller
    can log it instead of crashing.
    """
    try:
        if not path or not os.path.isdir(path):
            return False
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]  # Windows-only
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=True)
        else:
            subprocess.run(["xdg-open", path], check=True)
        return True
    except Exception:
        return False
