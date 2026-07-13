"""Filename/path helpers (Phase 3).

`sanitize_output_filename` strips characters illegal on Windows/macOS and bounds length.
`unique_output_path` implements the EDITED_<name>.pdf collision rule: append a numeric
suffix (EDITED_<name>_2.pdf, _3.pdf, ...) so a re-run never overwrites a prior output.
`debug_text_path` derives the paired DEBUG_<name>.txt sidecar from a chosen EDITED_ output
path, keeping the same numeric suffix so the debug file matches its PDF.
`open_in_file_manager` opens a folder in the OS file manager cross-platform, never raising.
"""

from __future__ import annotations

import os
import subprocess
import sys

# Characters illegal in filenames on Windows (superset of macOS restrictions).
_ILLEGAL = '<>:"/\\|?*'
_MAX_STEM = 150  # keep well under the 255-char path-component limit


def sanitize_output_filename(name: str) -> str:
    """Return a filesystem-safe version of `name` (stem only, no directory)."""
    name = os.path.basename(name)
    cleaned = "".join("_" if ch in _ILLEGAL or ord(ch) < 32 else ch for ch in name)
    cleaned = cleaned.strip(" .")  # trailing dots/spaces are invalid on Windows
    if len(cleaned) > _MAX_STEM:
        cleaned = cleaned[:_MAX_STEM].rstrip(" .")
    return cleaned or "untitled"


def unique_output_path(output_dir: str, base_name: str) -> str:
    """Return a non-colliding 'EDITED_<base_name>.pdf' path inside output_dir.

    base_name is the original PDF's name (with or without extension). If the target
    already exists, a numeric suffix is inserted before the extension: _2, _3, ...
    """
    stem = sanitize_output_filename(base_name)
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]
    candidate = os.path.join(output_dir, f"EDITED_{stem}.pdf")
    if not os.path.exists(candidate):
        return candidate
    n = 2
    while True:
        candidate = os.path.join(output_dir, f"EDITED_{stem}_{n}.pdf")
        if not os.path.exists(candidate):
            return candidate
        n += 1


def debug_text_path(output_path: str) -> str:
    """Return the DEBUG_<name>.txt sidecar path for an EDITED_<name>.pdf output path.

    Keeps the same directory and numeric collision suffix as the PDF, only swapping the
    ``EDITED_`` prefix for ``DEBUG_`` and the extension for ``.txt`` (matches the spec and
    the GUI option label). If the basename has no ``EDITED_`` prefix, the prefix is added.
    """
    directory = os.path.dirname(output_path)
    stem = os.path.splitext(os.path.basename(output_path))[0]
    if stem.startswith("EDITED_"):
        stem = "DEBUG_" + stem[len("EDITED_"):]
    elif not stem.startswith("DEBUG_"):
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
