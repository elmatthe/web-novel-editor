"""Extend the ordered file list for mixed PDF/TXT imports.

Folder snapshots keep own files first, then naturally ordered subdirectories.
Upload scanning preserves caller order so existing manual order is never undone.
Directory links/reparse points are never traversed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable
import os
import stat

from natsort import natsort_keygen, ns

# One shared key: numeric-aware and case-insensitive, so "chapter 2" sorts before
# "Chapter 10" regardless of filename casing (Windows filenames are case-insensitive).
_NATURAL_KEY = natsort_keygen(alg=ns.IGNORECASE)


def is_link(path: Path) -> bool:
    """Include Windows junctions/reparse points, including on Python 3.10."""
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400
    )


def check_no_links(path: Path) -> None:
    for part in (path, *path.parents):
        if os.path.lexists(part) and is_link(part):
            raise ValueError(f"Symlink/junction paths are not supported: {part}")


def _eligible(path: Path) -> bool:
    return path.suffix.lower() in {".pdf", ".txt"}


def natural_order(paths: Iterable[Path]) -> list[Path]:
    return sorted(paths, key=lambda p: (_NATURAL_KEY(p.name), p.name))


def scan_upload(paths: Iterable[str | Path]) -> list[Path]:
    """Return distinct eligible paths in caller order; reject link traversal."""
    ordered = []
    seen = set()
    for value in paths:
        path = Path(value)
        if not _eligible(path):
            continue
        check_no_links(path.absolute())
        identity = os.path.normcase(str(path.resolve()))
        if identity not in seen:
            ordered.append(path)
            seen.add(identity)
    return ordered


def scan_folder(root: str | Path, *, recursive: bool = True,
                exclude: str | Path | None = None,
                warn: Callable[[str], None] | None = None) -> list[Path]:
    """Recursively collect every PDF under ``root`` in the contract order.

    Raises ``NotADirectoryError`` if ``root`` is not an existing directory.
    Unreadable subdirectories are skipped rather than aborting the whole scan.
    """
    root = Path(root)
    check_no_links(root.absolute())
    if not root.is_dir():
        raise NotADirectoryError(f"Not a folder: {root}")

    ordered: list[Path] = []

    def _walk(directory: Path) -> None:
        if exclude and directory.resolve().is_relative_to(Path(exclude).resolve()):
            return
        try:
            entries = list(directory.iterdir())
        except OSError as exc:
            if warn:
                warn(f"Could not read folder {directory}: {exc}")
            return
        files, subdirs = [], []
        for entry in entries:
            try:
                if is_link(entry):
                    continue
                if entry.is_file() and _eligible(entry):
                    files.append(entry)
                elif recursive and entry.is_dir():
                    subdirs.append(entry)
            except OSError as exc:
                if warn:
                    warn(f"Could not inspect {entry}: {exc}")
        ordered.extend(natural_order(files))
        for sub in natural_order(subdirs):
            _walk(sub)

    _walk(root)
    return ordered
