"""Phase 7 — multi-novel architecture validation.

Proves the universal/profile-data seam holds: the Lord of the Mysteries stub pipeline
(empty placeholder profile) reuses the universal rules in the Shadow Slave order and runs
end-to-end on a real committed fixture without crashing and without mangling protected
terms. Also confirms the novel-index loader handles the empty LOTM placeholder cleanly.

Skips cleanly if pdfplumber or the fixtures are unavailable.
"""

from __future__ import annotations

import os
import re

import pytest

from core.protected_lexicon import ProtectedLexicon, load_protected_lexicon
from pipelines import lord_of_mysteries
from profiles.lord_of_mysteries.canonical_names import LOTM_CANONICAL_NAMES

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FIXTURES = os.path.join(_REPO_ROOT, "test-files", "shadow_slave")
_LOTM_INDEX = os.path.join(
    _REPO_ROOT, "files", "novel-index", "lord-of-the-mysteries.txt"
)


def _first_fixture():
    if not os.path.isdir(_FIXTURES):
        return None
    pdfs = sorted(f for f in os.listdir(_FIXTURES) if f.lower().endswith(".pdf"))
    return os.path.join(_FIXTURES, pdfs[0]) if pdfs else None


def test_empty_placeholder_profile_data_is_genuinely_empty():
    """The stub profile carries no novel-specific data (proves it is a clean seam)."""
    assert LOTM_CANONICAL_NAMES == frozenset()
    from profiles.lord_of_mysteries.special_fixes import LOTM_SPECIAL_FIXES

    assert LOTM_SPECIAL_FIXES == {}


def test_loader_handles_empty_lotm_placeholder_without_error():
    """The empty LOTM index loads cleanly and falls back to the (empty) built-in floor."""
    assert os.path.isfile(_LOTM_INDEX)
    lex = load_protected_lexicon(_LOTM_INDEX, LOTM_CANONICAL_NAMES)
    assert isinstance(lex, ProtectedLexicon)
    assert lex.terms == ()  # empty placeholder + empty floor -> no protected terms


def test_stub_pipeline_runs_end_to_end_on_real_fixture():
    """The second pipeline processes a real chapter without crashing or leaking junk."""
    pytest.importorskip("pdfplumber")
    from pdf.extractor import extract_text_from_pdf

    fx = _first_fixture()
    if not fx:
        pytest.skip("no committed fixtures available")

    raw = extract_text_from_pdf(fx)
    lex = load_protected_lexicon(_LOTM_INDEX, LOTM_CANONICAL_NAMES)
    out = lord_of_mysteries.run_pipeline(raw, lex)

    assert isinstance(out, str)
    assert len(out.strip()) > 100              # produced real cleaned text
    assert "__WE_" not in out                  # no placeholder leak
    assert not re.search(r"\s[–—―⸺]\s", out)   # mandatory spaced em-dash sweep ran


def test_stub_pipeline_preserves_a_user_protected_term(tmp_path):
    """A term added to the LOTM index survives the stub pipeline unchanged."""
    pytest.importorskip("pdfplumber")
    from pdf.extractor import extract_text_from_pdf

    fx = _first_fixture()
    if not fx:
        pytest.skip("no committed fixtures available")

    raw = extract_text_from_pdf(fx)
    # Inject a probe term whose numeric-slash form a universal rule would otherwise touch.
    lines = raw.split("\n")
    lines.insert(1, "The 6/7 Sequence pathway was sealed.")
    seeded = "\n".join(lines)

    # Protect "6/7 Sequence" via a user index file -> the slash rule must not rewrite it.
    user_index = tmp_path / "lord-of-the-mysteries.txt"
    user_index.write_text("6/7 Sequence\n", encoding="utf-8")
    lex = load_protected_lexicon(str(user_index), LOTM_CANONICAL_NAMES)
    assert "6/7 Sequence" in lex.terms

    out = lord_of_mysteries.run_pipeline(seeded, lex)
    assert "6/7 Sequence" in out
    assert "6 out of 7 Sequence" not in out
