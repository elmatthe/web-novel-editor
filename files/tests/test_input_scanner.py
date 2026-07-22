"""Tests for core.input_scanner — the ordered-file-list builder (Plan 1, Phase 1).

The ordering contract (pinned here):
  * Folder mode is a depth-first traversal. At each directory level the directory's
    OWN PDFs are processed first in natural (numeric-aware, case-insensitive) order,
    then its subfolders are descended into, themselves in natural order.
  * Natural order means 1, 2, 10 — not 1, 10, 2.
  * Non-PDF files are ignored everywhere; the .pdf extension match is case-insensitive.
  * Upload mode is a flat list preserving the caller's order exactly.

All tests are pure filesystem tests on tmp_path — no GUI, no corpora, deterministic.
"""

from __future__ import annotations

from pathlib import Path

from core.input_scanner import scan_folder, scan_upload


def _touch(root: Path, *relatives: str) -> None:
    for rel in relatives:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-stub")


def _names(paths: list[Path], root: Path) -> list[str]:
    """Relative POSIX-style paths, for readable ordering assertions."""
    return [p.relative_to(root).as_posix() for p in paths]


# ---------------------------------------------------------------------------
# Folder mode — natural order
# ---------------------------------------------------------------------------

def test_numeric_names_sort_naturally(tmp_path):
    _touch(tmp_path, "10.pdf", "1.pdf", "2.pdf")
    assert _names(scan_folder(tmp_path), tmp_path) == ["1.pdf", "2.pdf", "10.pdf"]


def test_mixed_prefix_names_sort_naturally_and_case_insensitively(tmp_path):
    _touch(tmp_path, "Chapter 10.pdf", "chapter 2.pdf", "Chapter 1.pdf")
    assert _names(scan_folder(tmp_path), tmp_path) == [
        "Chapter 1.pdf", "chapter 2.pdf", "Chapter 10.pdf",
    ]


# ---------------------------------------------------------------------------
# Folder mode — depth-first traversal contract
# ---------------------------------------------------------------------------

def test_own_pdfs_first_then_subfolders_in_natural_order(tmp_path):
    _touch(
        tmp_path,
        "b.pdf",
        "a.pdf",
        "10/x.pdf",
        "2/y.pdf",
        "1/z.pdf",
    )
    assert _names(scan_folder(tmp_path), tmp_path) == [
        "a.pdf", "b.pdf", "1/z.pdf", "2/y.pdf", "10/x.pdf",
    ]


def test_depth_first_descends_fully_before_next_sibling(tmp_path):
    _touch(
        tmp_path,
        "vol1/1.pdf",
        "vol1/arc2/2.pdf",
        "vol1/arc10/3.pdf",
        "vol2/4.pdf",
    )
    assert _names(scan_folder(tmp_path), tmp_path) == [
        "vol1/1.pdf", "vol1/arc2/2.pdf", "vol1/arc10/3.pdf", "vol2/4.pdf",
    ]


def test_nested_mixed_numeric_ordering(tmp_path):
    _touch(
        tmp_path,
        "root10.pdf",
        "root2.pdf",
        "Book 2/ch10.pdf",
        "Book 2/ch2.pdf",
        "Book 10/ch1.pdf",
    )
    assert _names(scan_folder(tmp_path), tmp_path) == [
        "root2.pdf", "root10.pdf",
        "Book 2/ch2.pdf", "Book 2/ch10.pdf",
        "Book 10/ch1.pdf",
    ]


# ---------------------------------------------------------------------------
# Folder mode — edge cases
# ---------------------------------------------------------------------------

def test_empty_folder_returns_empty_list(tmp_path):
    assert scan_folder(tmp_path) == []


def test_folder_with_only_non_pdfs_returns_empty_list(tmp_path):
    _touch(tmp_path, "notes.txt", "cover.jpg", "sub/data.csv")
    assert scan_folder(tmp_path) == []


def test_non_pdf_files_are_ignored_among_pdfs(tmp_path):
    _touch(tmp_path, "1.pdf", "notes.txt", "2.pdf", "sub/3.pdf", "sub/skip.docx")
    assert _names(scan_folder(tmp_path), tmp_path) == ["1.pdf", "2.pdf", "sub/3.pdf"]


def test_pdf_extension_match_is_case_insensitive(tmp_path):
    _touch(tmp_path, "1.PDF", "2.Pdf", "3.pdf")
    assert _names(scan_folder(tmp_path), tmp_path) == ["1.PDF", "2.Pdf", "3.pdf"]


def test_missing_folder_raises(tmp_path):
    import pytest

    with pytest.raises(NotADirectoryError):
        scan_folder(tmp_path / "does-not-exist")


def test_scan_folder_returns_path_objects(tmp_path):
    _touch(tmp_path, "1.pdf")
    result = scan_folder(tmp_path)
    assert all(isinstance(p, Path) for p in result)


# ---------------------------------------------------------------------------
# Upload mode
# ---------------------------------------------------------------------------

def test_upload_order_preserved_exactly(tmp_path):
    # Deliberately NOT natural order — upload mode must never re-sort.
    ordered = ["z.pdf", "10.pdf", "a.pdf", "2.pdf"]
    _touch(tmp_path, *ordered)
    given = [str(tmp_path / name) for name in ordered]
    assert _names(scan_upload(given), tmp_path) == ordered


def test_upload_ignores_non_pdfs_but_keeps_order(tmp_path):
    _touch(tmp_path, "b.pdf", "notes.txt", "a.pdf")
    given = [str(tmp_path / n) for n in ("b.pdf", "notes.txt", "a.pdf")]
    assert _names(scan_upload(given), tmp_path) == ["b.pdf", "a.pdf"]


def test_upload_returns_path_objects(tmp_path):
    _touch(tmp_path, "1.pdf")
    result = scan_upload([str(tmp_path / "1.pdf")])
    assert result == [tmp_path / "1.pdf"]
