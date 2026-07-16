"""Phase 8 — per-novel edit-details loader (universal base + novel-specific layer).

Covers the novel-name -> markdown lookup and, critically, the fallback-to-universal case
when no matching novel file exists. Uses a synthetic edit-details folder in tmp_path for
the lookup/fallback logic, plus a light check against the real committed
`files/Novel-Edits-Details/` so the shipped files stay wired.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.edit_details import (
    EDIT_DETAILS_DIR,
    UNIVERSAL_FILENAME,
    load_edit_details,
    novel_md_filename,
    resolve_novel_md_path,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def details_dir(tmp_path: Path) -> Path:
    """A synthetic Novel-Edits-Details folder: UNIVERSAL.md + Shadow-Slave.md."""
    (tmp_path / UNIVERSAL_FILENAME).write_text(
        "# UNIVERSAL\nbaseline rules\n", encoding="utf-8"
    )
    (tmp_path / "Shadow-Slave.md").write_text(
        "# Shadow Slave\nss-specific edits\n", encoding="utf-8"
    )
    return tmp_path


# -- filename mapping -------------------------------------------------------------------

@pytest.mark.parametrize(
    "name, expected",
    [
        ("Shadow Slave", "Shadow-Slave.md"),
        ("shadow slave", "Shadow-Slave.md"),
        ("shadow-slave", "Shadow-Slave.md"),
        ("Shadow_Slave", "Shadow-Slave.md"),
        ("Lord of the Mysteries", "Lord-Of-The-Mysteries.md"),
    ],
)
def test_novel_md_filename_maps_name_to_file(name: str, expected: str) -> None:
    assert novel_md_filename(name) == expected


# -- lookup -----------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["Shadow Slave", "shadow slave", "shadow-slave", "Shadow_Slave"])
def test_resolve_finds_novel_file_case_and_separator_insensitive(
    details_dir: Path, name: str
) -> None:
    resolved = resolve_novel_md_path(name, base_dir=details_dir)
    assert resolved is not None
    assert resolved.name == "Shadow-Slave.md"


def test_resolve_returns_none_for_unknown_novel(details_dir: Path) -> None:
    assert resolve_novel_md_path("Reverend Insanity", base_dir=details_dir) is None


def test_resolve_never_returns_universal_as_a_match(details_dir: Path) -> None:
    # Asking for "Universal" must not resolve to the base file — it is not a novel layer.
    assert resolve_novel_md_path("Universal", base_dir=details_dir) is None


def test_resolve_handles_missing_folder_without_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    assert resolve_novel_md_path("Shadow Slave", base_dir=missing) is None


def test_resolve_handles_empty_or_none_name(details_dir: Path) -> None:
    assert resolve_novel_md_path(None, base_dir=details_dir) is None
    assert resolve_novel_md_path("", base_dir=details_dir) is None
    assert resolve_novel_md_path("   ", base_dir=details_dir) is None


# -- load: universal base + novel layer -------------------------------------------------

def test_load_layers_novel_on_top_of_universal(details_dir: Path) -> None:
    d = load_edit_details("Shadow Slave", base_dir=details_dir)
    assert d.used_universal_only is False
    assert d.novel_path is not None and d.novel_path.name == "Shadow-Slave.md"
    assert "baseline rules" in d.universal
    assert "ss-specific edits" in d.novel
    # Combined applies universal first, then the novel layer on top.
    assert d.combined.index("baseline rules") < d.combined.index("ss-specific edits")


def test_load_falls_back_to_universal_only_for_unknown_novel(details_dir: Path) -> None:
    d = load_edit_details("Renegade Immortal", base_dir=details_dir)
    assert d.used_universal_only is True
    assert d.novel is None and d.novel_path is None
    assert "baseline rules" in d.combined        # universal still applied as the base
    assert "ss-specific edits" not in d.combined  # no novel layer leaked in


def test_load_with_no_novel_selected_is_universal_only(details_dir: Path) -> None:
    d = load_edit_details(None, base_dir=details_dir)
    assert d.used_universal_only is True
    assert d.combined.strip() == "# UNIVERSAL\nbaseline rules"


def test_load_does_not_crash_when_universal_missing(tmp_path: Path) -> None:
    # Only a novel file, no UNIVERSAL.md -> still loads the novel layer, universal empty.
    (tmp_path / "Shadow-Slave.md").write_text("ss-specific edits\n", encoding="utf-8")
    d = load_edit_details("Shadow Slave", base_dir=tmp_path)
    assert d.universal == ""
    assert d.used_universal_only is False
    assert "ss-specific edits" in d.combined


# -- real shipped files -----------------------------------------------------------------

def test_shipped_universal_file_exists_and_is_the_base() -> None:
    assert (EDIT_DETAILS_DIR / UNIVERSAL_FILENAME).is_file()
    d = load_edit_details(None)
    assert d.universal.strip()  # the committed UNIVERSAL.md has content


def test_shipped_shadow_slave_file_resolves_and_layers() -> None:
    d = load_edit_details("Shadow Slave")
    assert d.used_universal_only is False
    assert d.novel_path == EDIT_DETAILS_DIR / "Shadow-Slave.md"
    assert d.universal.strip() and (d.novel or "").strip()
