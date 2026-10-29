"""Preflight mappings are portable, stable and never truncate chapter names."""
from pathlib import Path
import pytest
from core.output_plan import plan_outputs, reserve_run_dir, validate_path


def test_same_stem_formats_and_companions_share_one_collision_suffix(tmp_path):
    paths = [tmp_path / n for n in ("Chapter 1.pdf", "chapter 1.txt", "DEBUG_Chapter 1.txt")]
    items = plan_outputs(paths, tmp_path / "out", formats=("pdf", "txt"), debug=True)
    assert items[0]["outputs"]["txt"] == "Chapter 1.txt"
    assert items[1]["outputs"]["pdf"] == "chapter 1_2.pdf"
    assert items[2]["outputs"]["txt"] == "DEBUG_Chapter 1_3.txt"


def test_unicode_and_duplicate_import_roots_disambiguate(tmp_path):
    a, b = tmp_path / "a" / "Book", tmp_path / "b" / "book"
    paths = [a / "Caf\u00e9.pdf", a / "Cafe\u0301.txt", b / "x.txt"]
    items = plan_outputs(paths, tmp_path / "out", formats=("txt",),
                         import_roots={str(p): str(a if i < 2 else b) for i, p in enumerate(paths)})
    assert items[0]["outputs"]["txt"] == "Book/Caf\u00e9.txt"
    assert items[1]["outputs"]["txt"] == "Book/Cafe\u0301_2.txt"
    assert items[2]["outputs"]["txt"] == "book_2/x.txt"


def test_preflight_rejects_duplicates_overlap_and_existing_files(tmp_path):
    src = tmp_path / "a.txt"
    with pytest.raises(ValueError, match="Duplicate"):
        plan_outputs([src, src], tmp_path / "out")
    with pytest.raises(ValueError, match="overlap"):
        plan_outputs([src], tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.pdf").write_bytes(b"private-existing")
    with pytest.raises(FileExistsError):
        plan_outputs([src], out)
    assert (out / "a.pdf").read_bytes() == b"private-existing"


def test_long_stems_are_preserved_or_explicitly_refused(tmp_path):
    name = "x" * 160
    # A short-enough destination keeps the full stem; never the old 150-char truncation.
    try:
        item = plan_outputs([tmp_path / (name + ".txt")], tmp_path / "out")[0]
    except ValueError as exc:
        assert "shorter" in str(exc)
    else:
        assert item["outputs"]["pdf"] == name + ".pdf"
    with pytest.raises(ValueError, match="shorter"):
        validate_path(tmp_path / ("x" * 230), budget=240)


def test_numbered_directory_is_reserved_exclusively(tmp_path):
    one = reserve_run_dir(tmp_path, "universal")
    two = reserve_run_dir(tmp_path, "universal")
    assert one.is_dir() and two.is_dir() and one != two


def test_format_selection_validates_before_allocation(tmp_path):
    with pytest.raises(ValueError, match="format"):
        plan_outputs([tmp_path / "a.txt"], tmp_path / "out", formats=())
    assert not (tmp_path / "out").exists()
