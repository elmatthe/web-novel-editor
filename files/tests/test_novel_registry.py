"""Phase 9 — novel-selection dropdown + novel -> pipeline dispatch registry.

Covers:
  * roster derivation from the index files (the dropdown source of truth),
  * filename <-> display-name round-tripping,
  * dispatch to a real profile (Shadow Slave) vs. the universal-only fallback,
  * that Shadow Slave's dispatched output is byte-for-byte identical to calling its
    pipeline directly (no behaviour change for the one shipped profile),
  * that a profile-less novel dispatches to universal-only and applies no other novel's
    special-fixes, and
  * run_batch's universal-only default (#3) and explicit-novel logging.

Pipeline/PDF tests skip cleanly if pdfplumber or the committed fixtures are unavailable.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.novel_registry import (
    DEFAULT_NOVEL,
    NOVEL_INDEX_DIR,
    available_novels,
    display_name_from_index_filename,
    index_filename_for,
    resolve_dispatch,
)
from core.protected_lexicon import load_protected_lexicon
from pipelines import lord_of_mysteries, shadow_slave
from profiles.shadow_slave.canonical_names import SS_CANONICAL_NAMES

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _REPO_ROOT / "files" / "test-files" / "shadow_slave"


def _first_fixture() -> str | None:
    if not _FIXTURES.is_dir():
        return None
    pdfs = sorted(p for p in _FIXTURES.glob("*.pdf"))
    return str(pdfs[0]) if pdfs else None


# -- filename <-> display name ----------------------------------------------------------

@pytest.mark.parametrize(
    "filename, expected",
    [
        ("shadow-slave.txt", "Shadow Slave"),
        ("lord-of-the-mysteries.txt", "Lord of the Mysteries"),
        ("re-monster.txt", "Re Monster"),
        ("the-noble-queen.txt", "The Noble Queen"),
        ("circle-of-inevitability.txt", "Circle of Inevitability"),
    ],
)
def test_display_name_from_index_filename(filename: str, expected: str) -> None:
    assert display_name_from_index_filename(filename) == expected


@pytest.mark.parametrize(
    "novel, expected",
    [
        ("Shadow Slave", "shadow-slave.txt"),
        ("Lord of the Mysteries", "lord-of-the-mysteries.txt"),
        ("Lord Of The Mysteries", "lord-of-the-mysteries.txt"),  # casing-insensitive
        ("The Noble Queen", "the-noble-queen.txt"),
        ("", ""),
        (None, ""),
    ],
)
def test_index_filename_for(novel, expected: str) -> None:
    assert index_filename_for(novel) == expected


# -- roster (dropdown source of truth) --------------------------------------------------

def test_available_novels_derived_from_synthetic_index_dir(tmp_path: Path) -> None:
    for fn in ["shadow-slave.txt", "lord-of-the-mysteries.txt", "re-monster.txt"]:
        (tmp_path / fn).write_text("", encoding="utf-8")
    roster = available_novels(tmp_path)
    assert roster == ["Shadow Slave", "Lord of the Mysteries", "Re Monster"]
    assert roster[0] == DEFAULT_NOVEL  # default listed first


def test_available_novels_includes_empty_placeholder_files(tmp_path: Path) -> None:
    # Placeholder (empty) index files are intentionally shown so the roster is visible.
    (tmp_path / "shadow-slave.txt").write_text("real terms\n", encoding="utf-8")
    (tmp_path / "reverend-insanity.txt").write_text("", encoding="utf-8")  # placeholder
    roster = available_novels(tmp_path)
    assert "Reverend Insanity" in roster


def test_available_novels_falls_back_when_folder_missing(tmp_path: Path) -> None:
    assert available_novels(tmp_path / "nope") == [DEFAULT_NOVEL]


def test_shipped_roster_has_known_novels_with_default_first() -> None:
    roster = available_novels(NOVEL_INDEX_DIR)
    assert roster[0] == "Shadow Slave"
    for expected in ["Shadow Slave", "Lord of the Mysteries", "Reverend Insanity"]:
        assert expected in roster
    # One entry per committed *.txt index file.
    assert len(roster) == len(list(NOVEL_INDEX_DIR.glob("*.txt")))


# -- dispatch ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["Shadow Slave", "shadow-slave", "shadow_slave", "SHADOW SLAVE"])
def test_resolve_dispatch_shadow_slave_uses_real_profile(name: str) -> None:
    d = resolve_dispatch(name)
    assert d.has_profile is True
    assert d.run_pipeline is shadow_slave.run_pipeline
    assert d.canonical_names is SS_CANONICAL_NAMES
    assert d.index_filename == "shadow-slave.txt"


@pytest.mark.parametrize("name", ["Lord of the Mysteries", "Reverend Insanity", "Re Monster"])
def test_resolve_dispatch_profileless_novel_is_universal_only(name: str) -> None:
    d = resolve_dispatch(name)
    assert d.has_profile is False
    assert d.run_pipeline is lord_of_mysteries.run_pipeline  # universal-only seam
    assert d.canonical_names == frozenset()                  # no other novel's names
    assert d.index_filename == index_filename_for(name)      # own index still honored


@pytest.mark.parametrize("name", [None, "", "   ", "Some Unlisted Novel"])
def test_resolve_dispatch_unknown_or_empty_is_universal_only(name) -> None:
    d = resolve_dispatch(name)
    assert d.has_profile is False
    assert d.run_pipeline is lord_of_mysteries.run_pipeline
    assert d.canonical_names == frozenset()


def test_universal_fallback_applies_no_special_fixes() -> None:
    """The universal-only seam must not apply any novel's forced substitutions."""
    from profiles.lord_of_mysteries.special_fixes import LOTM_SPECIAL_FIXES

    # Guard the coupling documented in novel_registry: the universal fallback reuses the
    # lord_of_mysteries pipeline precisely because its profile is empty. If this ever
    # gains real fixes, the universal fallback needs its own seam.
    assert LOTM_SPECIAL_FIXES == {}


# -- Shadow Slave output is unchanged through dispatch ----------------------------------

# A representative raw extract: chapter heading, a protected name, a forced typo fix
# target, and a numeric slash. No corpus/pdfplumber needed, so this runs everywhere
# (incl. environments without the gitignored fixtures) and pins the "SS unchanged"
# guarantee directly.
_RAW_SS = (
    "Chapter 1: The Nightmare\n"
    "Sunny opened his eyes. The Almanach lay on the tompost shelf.\n"
    "He counted 6/7 of the carcassess before Nephis spoke - quietly - to Kai.\n"
)


def test_shadow_slave_dispatch_equals_direct_pipeline_on_synthetic_text() -> None:
    """Dispatch must not change SS output vs. calling its pipeline directly (no corpus)."""
    index = str(NOVEL_INDEX_DIR / "shadow-slave.txt")
    lex = load_protected_lexicon(index, SS_CANONICAL_NAMES)
    direct = shadow_slave.run_pipeline(_RAW_SS, lex)

    d = resolve_dispatch("Shadow Slave")
    dlex = load_protected_lexicon(str(NOVEL_INDEX_DIR / d.index_filename), d.canonical_names)
    via_dispatch = d.run_pipeline(_RAW_SS, dlex)

    assert via_dispatch == direct
    # Sanity: the SS profile actually fired (forced typo fix applied, name preserved).
    assert "Almanac" in via_dispatch and "Almanach" not in via_dispatch
    assert "Sunny" in via_dispatch


def test_universal_fallback_does_not_apply_shadow_slave_special_fixes() -> None:
    """A profile-less novel must NOT pick up Shadow Slave's forced substitutions."""
    d = resolve_dispatch("Lord of the Mysteries")
    lex = load_protected_lexicon("", d.canonical_names)  # universal-only, empty floor
    out = d.run_pipeline(_RAW_SS, lex)
    assert "Almanach" in out  # SS's Almanach->Almanac fix did NOT run under universal-only


def test_shadow_slave_dispatch_output_is_byte_for_byte_unchanged() -> None:
    pytest.importorskip("pdfplumber")
    from pdf.extractor import extract_text_from_pdf

    fx = _first_fixture()
    if not fx:
        pytest.skip("no committed fixtures available")

    raw = extract_text_from_pdf(fx)
    index = str(NOVEL_INDEX_DIR / "shadow-slave.txt")
    lex = load_protected_lexicon(index, SS_CANONICAL_NAMES)

    direct = shadow_slave.run_pipeline(raw, lex)

    d = resolve_dispatch("Shadow Slave")
    via_dispatch_lex = load_protected_lexicon(
        str(NOVEL_INDEX_DIR / d.index_filename), d.canonical_names
    )
    via_dispatch = d.run_pipeline(raw, via_dispatch_lex)

    assert via_dispatch == direct  # dispatch changes nothing about SS output


# -- run_batch dispatch + #3 universal-only default -------------------------------------

def _run_batch_logs(novel_kwargs: dict, tmp_path: Path) -> list[tuple[str, str]]:
    pytest.importorskip("pdfplumber")
    from core.batch_runner import run_batch

    fx = _first_fixture()
    if not fx:
        pytest.skip("no committed fixtures available")
    logs: list[tuple[str, str]] = []
    run_batch(
        [fx], str(tmp_path / "out"),
        gui_log=lambda m, level="info": logs.append((level, m)),
        **novel_kwargs,
    )
    return logs


def test_run_batch_default_is_universal_only(tmp_path: Path) -> None:
    logs = _run_batch_logs({}, tmp_path)  # no novel_name -> universal-only (#3)
    text = " ".join(m for _, m in logs)
    assert "universal-only editing" in text
    assert "novel-specific editing layer" not in text


def test_run_batch_explicit_shadow_slave_applies_profile(tmp_path: Path) -> None:
    logs = _run_batch_logs({"novel_name": "Shadow Slave"}, tmp_path)
    text = " ".join(m for _, m in logs)
    assert "novel-specific editing layer for Shadow Slave" in text


def test_run_batch_profileless_novel_logs_universal_only(tmp_path: Path) -> None:
    logs = _run_batch_logs({"novel_name": "Lord of the Mysteries"}, tmp_path)
    text = " ".join(m for _, m in logs)
    assert "universal-only editing" in text
