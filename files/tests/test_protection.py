"""Phase 5 — novel-index protection: preservation guard + loader fallbacks.

The headline test is the regression guard the build spec calls for: every protected
term that appears in a real source fixture must survive the FULL editorial pipeline
without losing occurrences. Masking is what guarantees this; if a repair pass ever
silently corrupts or splits a protected name, the term's output count drops below its
source count and this test fails. It runs against the genuine committed fixture PDFs,
not hand-crafted strings, so it catches real-corpus regressions.

The loader tests pin the spec's "empty/missing index file falls back to the built-in
canonical floor without erroring" contract — this is what lets the seven intentional
empty placeholder index files (the not-yet-onboarded novels) load cleanly.
"""

from __future__ import annotations

import os
import re

import pytest

from core.protected_lexicon import (
    expand_lexicon_variants,
    load_protected_lexicon,
)
from profiles.shadow_slave.canonical_names import SS_CANONICAL_NAMES

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FIXTURES = os.path.join(_REPO_ROOT, "files", "test-files", "shadow_slave")
_INDEX = os.path.join(_REPO_ROOT, "files", "novel-index", "shadow-slave.txt")


def _term_count(term: str, text: str) -> int:
    """Count occurrences of `term` using the SAME matching the masker uses.

    Multi-word phrases match across flexible whitespace; single words use
    letter-boundary matching (so a name adjacent to punctuation still counts,
    but it is not matched inside a longer word). Case-insensitive, like masking.
    """
    if " " in term:
        inner = r"\s+".join(re.escape(p) for p in term.split())
        rx = re.compile(f"({inner})", re.IGNORECASE)
    else:
        rx = re.compile(rf"(?<![A-Za-z])({re.escape(term)})(?![A-Za-z])", re.IGNORECASE)
    return len(rx.findall(text))


def _fixture_paths() -> list[str]:
    if not os.path.isdir(_FIXTURES):
        return []
    return [
        os.path.join(_FIXTURES, f)
        for f in sorted(os.listdir(_FIXTURES))
        if f.lower().endswith(".pdf")
    ]


# --- the preservation regression guard --------------------------------------
@pytest.mark.parametrize(
    "fixture", _fixture_paths(), ids=lambda p: os.path.basename(p)
)
def test_protected_terms_survive_full_pipeline(fixture):
    """Every protected term present in the source survives the pipeline intact.

    Asserts output count >= source count for each term+variant that appears in the
    chapter. A drop means a repair pass corrupted, split, or dropped a protected
    name despite masking — exactly the silent failure this guard exists to catch.
    """
    pytest.importorskip("pdfplumber")
    from pdf.extractor import extract_text_from_pdf
    from pipelines import shadow_slave

    src = extract_text_from_pdf(fixture)
    lex = load_protected_lexicon(_INDEX, SS_CANONICAL_NAMES)
    terms = expand_lexicon_variants(lex.terms)
    out = shadow_slave.run_pipeline(src, lex)

    reductions = []
    for term in terms:
        c_in = _term_count(term, src)
        if c_in == 0:
            continue
        c_out = _term_count(term, out)
        if c_out < c_in:
            reductions.append(f"{term!r}: source={c_in} output={c_out}")

    assert not reductions, (
        "protected term(s) lost occurrences through the pipeline in "
        f"{os.path.basename(fixture)}:\n  " + "\n  ".join(reductions)
    )


def test_index_is_superset_of_builtin_floor():
    """The shadow-slave index must contain every built-in canonical name.

    Keeps the user-facing index reconciled with the always-loaded floor so the two
    sources never silently drift apart.
    """
    from core.protected_lexicon import _load_terms_from_file
    from pathlib import Path

    idx = set(_load_terms_from_file(Path(_INDEX)))
    missing = sorted(SS_CANONICAL_NAMES - idx)
    assert not missing, f"canonical names missing from index: {missing}"


# --- loader fallback contract (empty / missing index) -----------------------
def test_empty_index_falls_back_to_builtin(tmp_path):
    """An empty (0-byte) index file loads as 'no user terms', not an error.

    This is the case for the seven intentional empty placeholder novel files.
    """
    empty = tmp_path / "empty-novel.txt"
    empty.write_text("", encoding="utf-8")
    lex = load_protected_lexicon(str(empty), SS_CANONICAL_NAMES)
    assert "Sunny" in lex.terms
    assert set(SS_CANONICAL_NAMES).issubset(set(lex.terms))


def test_comments_only_index_falls_back_to_builtin(tmp_path):
    """An index with only comments/blank lines contributes no terms but never errors."""
    f = tmp_path / "comments.txt"
    f.write_text("# just a header\n\n   \n# another comment\n", encoding="utf-8")
    lex = load_protected_lexicon(str(f), SS_CANONICAL_NAMES)
    assert set(lex.terms) == set(SS_CANONICAL_NAMES)


def test_missing_index_falls_back_to_builtin():
    """A non-existent index path falls back to the built-in floor without raising."""
    lex = load_protected_lexicon("definitely/not/a/real/path.txt", SS_CANONICAL_NAMES)
    assert "Sunny" in lex.terms
    assert set(lex.terms) == set(SS_CANONICAL_NAMES)


# --- the spec's Phase 5 scenario: index term shields against a real rule -----
def test_index_term_shields_against_special_fix(tmp_path):
    """A term added to the index file is preserved even when a rule would alter it.

    A user-added term must remain unchanged even when an editorial rule would otherwise
    alter it. `Almanach` is the probe: special fixes normally change it to `Almanac`,
    but masking from the index must prevent that.
    """
    pytest.importorskip("pdfplumber")
    from pdf.extractor import extract_text_from_pdf
    from pipelines import shadow_slave

    fx = os.path.join(_FIXTURES, "Chapter 1_ Nightmare Begins.pdf")
    if not os.path.isfile(fx):
        pytest.skip("Chapter 1 fixture not present")

    raw = extract_text_from_pdf(fx)
    # Inject the probe term into the chapter body (after the heading line).
    lines = raw.split("\n")
    lines.insert(1, "Almanach watched in silence.")
    seeded = "\n".join(lines)

    # Control: with the term NOT protected, special fixes rewrite it.
    base_lex = load_protected_lexicon(_INDEX, SS_CANONICAL_NAMES)
    control = shadow_slave.run_pipeline(seeded, base_lex)
    assert "Almanach" not in control
    assert "Almanac" in control

    # Protected: add the term to a user index file -> it survives unchanged.
    user_index = tmp_path / "shadow-slave.txt"
    user_index.write_text("Almanach\n", encoding="utf-8")
    prot_lex = load_protected_lexicon(str(user_index), SS_CANONICAL_NAMES)
    assert "Almanach" in prot_lex.terms
    protected = shadow_slave.run_pipeline(seeded, prot_lex)
    assert "Almanach" in protected
    assert re.search(r"(?<![A-Za-z])Almanac(?![A-Za-z])", protected) is None
