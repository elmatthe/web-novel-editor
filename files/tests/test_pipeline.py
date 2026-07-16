"""Phase 4 — protected lexicon, replacement log, and full-pipeline smoke tests.

The pipeline test runs the real Shadow Slave editorial pipeline over genuine committed
fixture PDFs and asserts the Phase-4 outcomes: the chapter heading is isolated as its own
paragraph, paragraph breaks (\\n\\n) are reconstructed, protected names survive, and no
spaced em-dash remains. Skips cleanly if fixtures/pdfplumber are unavailable.
"""

from __future__ import annotations

import json
import os
import re

import pytest

from core.protected_lexicon import (
    ProtectedLexicon,
    for_non_placeholder_segments,
    load_protected_lexicon,
    mask_chapter_lines,
    mask_protected_terms,
    unmask_placeholders,
)
from core.replacement_log import ReplacementLog
from pipelines import shadow_slave
from profiles.shadow_slave.canonical_names import SS_CANONICAL_NAMES

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FIXTURES = os.path.join(_REPO_ROOT, "files", "test-files", "shadow_slave")
_INDEX = os.path.join(_REPO_ROOT, "scripts", "Universal", "resources", "novel-index", "shadow-slave.txt")


def _first_fixture():
    if not os.path.isdir(_FIXTURES):
        return None
    pdfs = sorted(f for f in os.listdir(_FIXTURES) if f.lower().endswith(".pdf"))
    return os.path.join(_FIXTURES, pdfs[0]) if pdfs else None


# --- ReplacementLog ---------------------------------------------------------
def test_replacement_log_record_and_write(tmp_path):
    log = ReplacementLog()
    log.record("Obers", "Obels", "special_fixes", "forced", "the Obers shelf")
    log.record("same", "same", "noop", "x")  # dropped (no-op)
    assert len(log) == 1
    path = str(tmp_path / "r.jsonl")
    log.write_jsonl(path)
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(ln) for ln in fh]
    assert rows == [{
        "original": "Obers", "replacement": "Obels",
        "rule": "special_fixes", "category": "forced", "context": "the Obers shelf",
    }]


# --- protected_lexicon ------------------------------------------------------
def test_lexicon_load_builtin_floor():
    lex = load_protected_lexicon("does-not-exist.txt", SS_CANONICAL_NAMES)
    assert "Sunny" in lex.terms
    # multi-word phrases sort before single words
    multi = [t for t in lex.terms if " " in t]
    first_single = next(i for i, t in enumerate(lex.terms) if " " not in t)
    last_multi = max((i for i, t in enumerate(lex.terms) if " " in t), default=-1)
    assert multi == [] or last_multi < first_single


def test_mask_unmask_round_trip_preserves_terms():
    lex = ProtectedLexicon(terms=("Sunny",), term_set_lower=frozenset({"sunny"}))
    text = "Chapter 1: A.\nSunny ran fast."
    masked, ch_map = mask_chapter_lines(text)
    masked, prot_map = mask_protected_terms(masked, lex)
    assert "Sunny" not in masked and "__WE_P_" in masked and "__WE_CH_" in masked
    restored = unmask_placeholders(masked, prot_map, ch_map)
    assert restored == text


def test_masking_shields_term_from_mutating_rule():
    # A rule that would lowercase everything must not touch a masked term.
    lex = ProtectedLexicon(terms=("Sunny",), term_set_lower=frozenset({"sunny"}))
    masked, prot_map = mask_protected_terms("Sunny shouted", lex)
    mutated = for_non_placeholder_segments(masked, str.upper)
    restored = unmask_placeholders(mutated, prot_map, {})
    assert restored == "Sunny SHOUTED"


# --- full pipeline smoke (real fixture) -------------------------------------
def test_pipeline_on_real_chapter():
    pytest.importorskip("pdfplumber")
    fx = _first_fixture()
    if not fx:
        pytest.skip("fixtures not present")
    from pdf.extractor import extract_text_from_pdf

    raw = extract_text_from_pdf(fx)
    lex = load_protected_lexicon(_INDEX, SS_CANONICAL_NAMES)
    log = ReplacementLog()
    out = shadow_slave.run_pipeline(raw, lex, repl_log=log)

    # paragraph structure was reconstructed
    assert "\n\n" in out
    # heading is isolated as the first paragraph
    assert re.match(r"^Chapter\s+[\d,]+:.*\.$", out.split("\n\n")[0].strip())
    # no spaced em/en dash survives the mandatory final sweep
    assert re.search(r"\S\s+[–—―]\s+\S", out) is None
    # output is substantial (no lossy collapse)
    assert len(out) > 0.5 * len(raw)


def test_audit_log_replacement_field_is_a_description_not_rule_name():
    # M1 regression: bulk-transform summary rows must put a human-readable description
    # in `replacement` (and the rule name only in `rule`), so the JSONL audit is trustworthy.
    lex = ProtectedLexicon()
    log = ReplacementLog()
    # Curly doubles + a numeric ratio + a spaced em-dash -> all bulk-summary transforms.
    text = 'Chapter 1: Test.\n\n“He scored 6/7 today — Then he left.”'
    shadow_slave.run_pipeline(text, lex, repl_log=log)

    rows = {e.rule: e for e in log.entries}
    assert "quote_normalize" in rows, "quote-normalize summary row missing"
    q = rows["quote_normalize"]
    assert q.replacement != q.rule, "replacement must not be the rule name"
    assert q.replacement and not q.replacement.startswith("__"), q.replacement
    assert q.original.endswith("occurrence(s)")
    # The description is meaningful prose, not a token.
    assert "->" in q.replacement or "straight" in q.replacement


def test_pipeline_preserves_protected_name():
    pytest.importorskip("pdfplumber")
    fx = os.path.join(_FIXTURES, "Chapter 1_ Nightmare Begins.pdf")
    if not os.path.isfile(fx):
        pytest.skip("Chapter 1 fixture not present")
    from pdf.extractor import extract_text_from_pdf

    raw = extract_text_from_pdf(fx)
    lex = load_protected_lexicon(_INDEX, SS_CANONICAL_NAMES)
    out = shadow_slave.run_pipeline(raw, lex)
    assert "Sunny" in out  # the protagonist's name survives the full pipeline


def test_pipeline_preserves_protected_special_fix_target_byte_for_byte():
    """C2 regression: protected terms remain masked through special fixes."""
    lex = ProtectedLexicon(
        terms=("Almanach",), term_set_lower=frozenset({"almanach"})
    )
    text = "Almanach is protected."

    assert shadow_slave.run_pipeline(text, lex) == text
