"""Build the ordered input-file list for both GUI input modes (Plan 1, Phase 1).

Two entry points, one per input mode:

* :func:`scan_upload` — Upload-PDFs mode. A flat list preserving the caller's order
  exactly (the user's upload order is meaningful and must never be re-sorted).
* :func:`scan_folder` — Select-Folder mode. A recursive scan following the ordering
  contract: depth-first traversal; at each directory level the directory's OWN PDFs
  come first in natural order, then its subfolders are descended into, themselves in
  natural order.

"Natural order" is numeric-aware, case-insensitive ordering via ``natsort``
(1, 2, 10 — not 1, 10, 2), matching how a person numbers chapter files. Non-PDF
files are ignored in both modes; the extension match is case-insensitive.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from natsort import natsort_keygen, ns

# One shared key: numeric-aware and case-insensitive, so "chapter 2" sorts before
# "Chapter 10" regardless of filename casing (Windows filenames are case-insensitive).
_NATURAL_KEY = natsort_keygen(alg=ns.IGNORECASE)


def _is_pdf(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"


def scan_upload(paths: Iterable[str | Path]) -> list[Path]:
    """Return the uploaded files as Paths, order preserved, non-PDFs dropped."""
    return [Path(p) for p in paths if _is_pdf(Path(p))]


def scan_folder(root: str | Path) -> list[Path]:
    """Recursively collect every PDF under ``root`` in the contract order.

    Raises ``NotADirectoryError`` if ``root`` is not an existing directory.
    Unreadable subdirectories are skipped rather than aborting the whole scan.
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a folder: {root}")

    ordered: list[Path] = []

    def _walk(directory: Path) -> None:
        try:
            entries = list(directory.iterdir())
        except OSError:
            return
        files = [e for e in entries if e.is_file() and _is_pdf(e)]
        subdirs = [e for e in entries if e.is_dir()]
        ordered.extend(sorted(files, key=lambda p: _NATURAL_KEY(p.name)))
        for sub in sorted(subdirs, key=lambda p: _NATURAL_KEY(p.name)):
            _walk(sub)

    _walk(root)
    return ordered
