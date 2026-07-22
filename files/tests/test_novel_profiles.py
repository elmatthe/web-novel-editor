"""Phase 5b — real per-novel profiles: The Noble Queen + Supreme Magus.

Covers the Phase 5b acceptance contract:
  * both novels dispatch to their own registered profile (registry level,
    casing/separator-insensitive) and appear in the dropdown roster;
  * their built-in canonical floors match the ported study-examples data and
    their `files/novel-index/` files are supersets of those floors;
  * their `<Novel-Name>.md` edit-details files resolve and layer;
  * Supreme Magus special fixes apply in SM mode and in **no** other mode;
    Shadow Slave fixes do not leak into the new profiles (cross-novel
    isolation both directions);
  * the spec exclusions hold: no profanity-uncensor was ported, and the
    rejected `rnade` fix cannot corrupt words containing it;
  * protected terms survive each new pipeline (synthetic text built from the
    real index terms);
  * novels intentionally left unauthored (Renegade Immortal, Reverend
    Insanity) still hit the universal-only fallback;
  * Shadow Slave dispatch is untouched by the new registrations.

An optional `local_corpus` layer exercises the real The_Noble_Queen-v2 /
Supreme_Magus-v2 PDFs when present (mandatory under --require-local-corpora).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.novel_registry import (
    NOVEL_INDEX_DIR,
    available_novels,
    resolve_dispatch,
)
from core.edit_details import load_edit_details, resolve_novel_md_path
from core.protected_lexicon import (
    _load_terms_from_file,
    expand_lexicon_variants,
    load_protected_lexicon,
)
from pipelines import lord_of_mysteries, shadow_slave, supreme_magus, the_noble_queen
from profiles.supreme_magus.canonical_names import SM_CANONICAL_NAMES
from profiles.supreme_magus.special_fixes import SM_SPECIAL_FIXES
from profiles.the_noble_queen.canonical_names import NQ_CANONICAL_NAMES
from profiles.the_noble_queen.special_fixes import NQ_SPECIAL_FIXES

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORPUS_ROOT = _REPO_ROOT / "files" / "pdf-example-chapters"

_NQ_INDEX = NOVEL_INDEX_DIR / "the-noble-queen.txt"
_SM_INDEX = NOVEL_INDEX_DIR / "supreme-magus.txt"


def _lexicon_for(novel: str):
    d = resolve_dispatch(novel)
    return d, load_protected_lexicon(
        str(NOVEL_INDEX_DIR / d.index_filename), d.canonical_names
    )


# -- dispatch + roster --------------------------------------------------------------------

@pytest.mark.parametrize(
    "name", ["The Noble Queen", "the-noble-queen", "THE NOBLE QUEEN", "The_Noble_Queen"]
)
def test_resolve_dispatch_noble_queen_uses_real_profile(name: str) -> None:
    d = resolve_dispatch(name)
    assert d.has_profile is True
    assert d.run_pipeline is the_noble_queen.run_pipeline
    assert d.canonical_names is NQ_CANONICAL_NAMES
    assert d.index_filename == "the-noble-queen.txt"


@pytest.mark.parametrize(
    "name", ["Supreme Magus", "supreme-magus", "SUPREME MAGUS", "Supreme_Magus"]
)
def test_resolve_dispatch_supreme_magus_uses_real_profile(name: str) -> None:
    d = resolve_dispatch(name)
    assert d.has_profile is True
    assert d.run_pipeline is supreme_magus.run_pipeline
    assert d.canonical_names is SM_CANONICAL_NAMES
    assert d.index_filename == "supreme-magus.txt"


def test_new_profiles_appear_in_shipped_roster() -> None:
    roster = available_novels(NOVEL_INDEX_DIR)
    assert "The Noble Queen" in roster
    assert "Supreme Magus" in roster
    assert roster[0] == "Universal"  # Plan 1 Phase 3: Universal is the default entry


def test_unauthored_novels_still_fall_back_to_universal_only() -> None:
    """Renegade Immortal / Reverend Insanity stay placeholders by decision (5b scope)."""
    for name in ("Renegade Immortal", "Reverend Insanity"):
        d = resolve_dispatch(name)
        assert d.has_profile is False
        assert d.run_pipeline is lord_of_mysteries.run_pipeline
        assert d.canonical_names == frozenset()


def test_shadow_slave_dispatch_untouched_by_new_registrations() -> None:
    d = resolve_dispatch("Shadow Slave")
    assert d.has_profile is True
    assert d.run_pipeline is shadow_slave.run_pipeline


# -- floors + index supersets ---------------------------------------------------------------

def test_noble_queen_floor_matches_ported_master_index() -> None:
    assert len(NQ_CANONICAL_NAMES) == 26
    for probe in ("Queen Bee", "Noble Queen", "Mongrel", "Lady Morgan", "Dread Lord"):
        assert probe in NQ_CANONICAL_NAMES


def test_supreme_magus_floor_matches_ported_master_index() -> None:
    assert len(SM_CANONICAL_NAMES) == 594
    for probe in ("Lith", "Solus", "Kamila Yehval", "Griffon Kingdom", "Faluel's Lair"):
        assert probe in SM_CANONICAL_NAMES


@pytest.mark.parametrize(
    "index_path, floor",
    [
        (_NQ_INDEX, NQ_CANONICAL_NAMES),
        (_SM_INDEX, SM_CANONICAL_NAMES),
    ],
    ids=["noble-queen", "supreme-magus"],
)
def test_index_is_superset_of_builtin_floor(index_path: Path, floor: frozenset) -> None:
    """Same reconciliation contract test_protection pins for Shadow Slave."""
    assert index_path.is_file()
    idx = set(_load_terms_from_file(index_path))
    missing = sorted(floor - idx)
    assert not missing, f"canonical names missing from {index_path.name}: {missing}"


def test_new_indexes_load_through_the_real_lexicon_loader() -> None:
    _, nq_lex = _lexicon_for("The Noble Queen")
    assert set(NQ_CANONICAL_NAMES).issubset(set(nq_lex.terms))
    _, sm_lex = _lexicon_for("Supreme Magus")
    assert set(SM_CANONICAL_NAMES).issubset(set(sm_lex.terms))


# -- edit-details markdown layer ------------------------------------------------------------

@pytest.mark.parametrize(
    "novel, md_name",
    [
        ("The Noble Queen", "The-Noble-Queen.md"),
        ("Supreme Magus", "Supreme-Magus.md"),
    ],
)
def test_shipped_novel_md_resolves_and_layers(novel: str, md_name: str) -> None:
    path = resolve_novel_md_path(novel)
    assert path is not None and path.name == md_name
    d = load_edit_details(novel)
    assert d.used_universal_only is False
    assert d.novel_path == path
    assert d.novel and novel in d.novel  # the doc names its own novel


# -- Supreme Magus special fixes: apply in SM mode only --------------------------------------

# Shortest-real-fragment bait built from the corpus-validated artifact forms.
_SM_BAIT = (
    "Chapter 1829: Truths and Secrets.\n\n"
    "Thn1d marched while S0lus spoke to lnxialot about Ragnar?k and the war of "
    "Ragnar??k. Silven/ving nodded at Fn'ya and O1pal near L0crias that day.\n"
)


def test_sm_special_fixes_apply_in_sm_mode_and_are_logged() -> None:
    from core.replacement_log import ReplacementLog

    _, lex = _lexicon_for("Supreme Magus")
    log = ReplacementLog()
    out = supreme_magus.run_pipeline(_SM_BAIT, lex, repl_log=log)
    for garbled in ("Thn1d", "S0lus", "lnxialot", "Ragnar?k", "Ragnar??k",
                    "Silven/ving", "Fn'ya", "O1pal", "L0crias"):
        assert garbled not in out
    for fixed in ("Thrud", "Solus", "Inxialot", "Ragnarök", "Silverwing",
                  "Friya", "Orpal", "Locrias"):
        assert fixed in out
    fixes = [e for e in log.entries if e.rule == "special_fixes"]
    assert {e.original for e in fixes} >= {"Thn1d", "Ragnar?k", "Silven/ving"}


def test_sm_special_fixes_do_not_apply_in_universal_or_other_profiles() -> None:
    """Cross-novel isolation: the SM bait passes through every OTHER mode unchanged."""
    for novel, pipeline in (
        ("Renegade Immortal", lord_of_mysteries.run_pipeline),  # universal fallback
        ("Shadow Slave", shadow_slave.run_pipeline),
        ("The Noble Queen", the_noble_queen.run_pipeline),
    ):
        d, lex = _lexicon_for(novel)
        assert d.run_pipeline is pipeline
        out = d.run_pipeline(_SM_BAIT, lex)
        assert "Thn1d" in out and "Ragnar?k" in out  # garbled forms untouched
        assert "Thrud" not in out and "Ragnarök" not in out


def test_ss_special_fixes_do_not_apply_in_new_profiles() -> None:
    """Isolation in the other direction: SS bait survives NQ/SM modes verbatim."""
    bait = (
        "Chapter 2: The Shelf.\n\n"
        "The Almanach sat where the carcassess had been counted the night before, "
        "which is more than enough plain padding text for the extraction floor.\n"
    )
    for novel in ("The Noble Queen", "Supreme Magus"):
        d, lex = _lexicon_for(novel)
        out = d.run_pipeline(bait, lex)
        assert "Almanach" in out and "carcassess" in out


# -- spec exclusions hold ---------------------------------------------------------------------

def test_no_profanity_uncensor_was_ported() -> None:
    """The legacy SM editor's uncensor map is spec-excluded content alteration."""
    assert NQ_SPECIAL_FIXES == {}
    assert all("*" not in k for k in SM_SPECIAL_FIXES), "censor-mask keys were ported"
    # A censored word passes through Supreme Magus mode exactly as printed.
    _, lex = _lexicon_for("Supreme Magus")
    bait = (
        "Chapter 3: The Oath.\n\n"
        '"What the f*ck is this place?" he asked, and nobody in the long quiet '
        "hall had any answer for him that evening at all.\n"
    )
    out = supreme_magus.run_pipeline(bait, lex)
    assert "f*ck" in out and "fuck" not in out.replace("f*ck", "")


def test_rejected_rnade_fix_cannot_corrupt_containing_words() -> None:
    """'rnade'->'made' was rejected (substring FP hazard); prove the hazard stays absent."""
    assert "rnade" not in SM_SPECIAL_FIXES
    _, lex = _lexicon_for("Supreme Magus")
    bait = (
        "Chapter 4: The Guest.\n\n"
        "Bernadette curtsied to the court and the assembled nobles watched her in "
        "complete silence for a long while before anyone spoke a single word.\n"
    )
    out = supreme_magus.run_pipeline(bait, lex)
    assert "Bernadette" in out


# -- protected terms survive the new pipelines ------------------------------------------------

def _survival_check(novel: str, body: str, probes: list[str]) -> None:
    import re

    d, lex = _lexicon_for(novel)
    out = d.run_pipeline(body, lex)
    for term in probes:
        rx = re.compile(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])")
        assert len(rx.findall(out)) >= len(rx.findall(body)), f"{term!r} lost occurrences"


def test_noble_queen_protected_terms_survive_pipeline() -> None:
    body = (
        "Chapter 810: Glory.\n\n"
        "Queen Bee watched the Dreamscape shift as Lady Morgan spoke of Valor. "
        "The Noble Queen answered Mongrel with a smile, and the Dread Lord waited "
        "beyond the Dream Realm while Brock said nothing useful at all.\n"
    )
    _survival_check(
        "The Noble Queen",
        body,
        ["Queen Bee", "Dreamscape", "Lady Morgan", "Valor", "Mongrel", "Dread Lord", "Brock"],
    )


def test_supreme_magus_protected_terms_survive_pipeline() -> None:
    body = (
        "Chapter 100: The Academy.\n\n"
        "Lith Verhen followed Solus into the Griffon Kingdom while Kamila Yehval "
        "and Phloria Ernas argued about the Council of Mages. Faluel's Lair lay "
        "beyond the Blood Desert, and Tyris Griffon watched them all from afar.\n"
    )
    _survival_check(
        "Supreme Magus",
        body,
        ["Lith Verhen", "Solus", "Griffon Kingdom", "Kamila Yehval",
         "Phloria Ernas", "Council of Mages", "Blood Desert", "Tyris Griffon"],
    )


def test_expanded_sm_lexicon_masks_without_placeholder_leak() -> None:
    """594 terms + variants mask and unmask cleanly — no __WE_ token survives."""
    _, lex = _lexicon_for("Supreme Magus")
    assert len(expand_lexicon_variants(lex.terms)) >= len(lex.terms)
    out = supreme_magus.run_pipeline(_SM_BAIT, lex)
    assert "__WE_" not in out


# -- optional local-corpus layer ---------------------------------------------------------------

def _require_corpus(request, name: str) -> Path:
    path = _CORPUS_ROOT / name
    present = path.is_dir() and any(
        f.lower().endswith(".pdf") for f in os.listdir(path)
    )
    if not present:
        msg = f"local corpus '{name}' not present under files/pdf-example-chapters/"
        if request.config.getoption("--require-local-corpora"):
            pytest.fail(f"--require-local-corpora given but {msg}", pytrace=False)
        pytest.skip(msg)
    return path


@pytest.mark.local_corpus
def test_sm_corpus_artifact_chapters_are_fixed_in_sm_mode(request) -> None:
    """The corpus chapters the artifacts were recorded in actually come out fixed."""
    pytest.importorskip("pdfplumber")
    from pdf.extractor import extract_text_from_pdf

    corpus = _require_corpus(request, "Supreme_Magus-v2")
    _, lex = _lexicon_for("Supreme Magus")
    checks = [
        ("Chapter 1829_ Truths and Secrets (Part 1).pdf", "Thn1d", "Thrud"),
        ("Chapter 2678_ From War To... (Part 2).pdf", "Ragnar?k", "Ragnarök"),
    ]
    for filename, garbled, fixed in checks:
        src_path = corpus / filename
        if not src_path.is_file():
            pytest.skip(f"expected corpus file missing: {filename}")
        raw = extract_text_from_pdf(str(src_path))
        assert garbled in raw, f"recorded artifact absent from source {filename}"
        out = supreme_magus.run_pipeline(raw, lex)
        assert garbled not in out
        assert fixed in out


@pytest.mark.local_corpus
def test_nq_corpus_chapter_protected_terms_survive_profile_mode(request) -> None:
    pytest.importorskip("pdfplumber")
    import re

    from pdf.extractor import extract_text_from_pdf

    corpus = _require_corpus(request, "The_Noble_Queen-v2")
    src_path = corpus / "Chapter 621 - Chapter 621_ Lioness.pdf"
    if not src_path.is_file():
        pytest.skip("expected corpus file missing: Chapter 621")
    raw = extract_text_from_pdf(str(src_path))
    _, lex = _lexicon_for("The Noble Queen")
    out = the_noble_queen.run_pipeline(raw, lex)
    assert "__WE_" not in out
    for term in ("Noble", "Honey"):
        rx = re.compile(rf"(?<![A-Za-z]){term}(?![A-Za-z])")
        n_in, n_out = len(rx.findall(raw)), len(rx.findall(out))
        if n_in:
            assert n_out >= n_in, f"{term!r}: source={n_in} output={n_out}"
