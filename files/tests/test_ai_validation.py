from __future__ import annotations

import json

import pytest

from ai.prompt import build_system_prompt
from ai.provenance import MAX_SNIPPET, build_provenance
from ai.validation import RejectionReason as R
from ai.validation import validate_candidate

BASE = "Chapter 7: Arrival.\n\nSunny walks to the gate. He sees Nephis there."


def reasons(candidate, **kwargs):
    return set(validate_candidate(BASE, candidate, protected_terms=("Sunny", "Nephis"), **kwargs).reasons)


def test_unchanged_and_clean_minor_correction_accepted():
    assert validate_candidate(BASE, BASE, protected_terms=("Sunny", "Nephis")).accepted
    bad = BASE.replace("He sees", "He see")
    fixed = bad.replace("He see", "He sees")
    assert validate_candidate(bad, fixed, protected_terms=("Sunny", "Nephis")).accepted


def test_broad_paraphrase_rejected():
    candidate = "Chapter 7: Arrival.\n\nSunny travels toward the entrance. Nephis is waiting nearby."
    assert R.BROAD_REWRITE in reasons(candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        BASE.replace("Sunny", "Sunless"),
        BASE.replace("Sunny", "sunny"),
        BASE.replace("Sunny walks", "Nephis walks").replace("Nephis there", "Sunny there"),
    ],
)
def test_protected_term_change_case_or_movement_rejected(candidate):
    assert R.PROTECTED_TERM_CHANGED in reasons(candidate)


def test_placeholder_damage_rejected():
    baseline = BASE + " __WE_P_00001__"
    result = validate_candidate(baseline, baseline.replace("00001", "00002"))
    assert R.PLACEHOLDER_DAMAGED in result.reasons


def test_heading_change_rejected():
    assert R.HEADING_CHANGED in reasons(BASE.replace("Chapter 7", "Chapter 8"))


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (BASE.replace(" He sees Nephis there.", ""), R.DELETION),
        (BASE + " He sees Nephis there.", R.DUPLICATION),
        ("Chapter 7: Arrival.\n\nHe sees Nephis there. Sunny walks to the gate.", R.REORDERED),
        (BASE.replace("\n\n", "\n"), R.STRUCTURE_CHANGED),
    ],
)
def test_integrity_guards(candidate, expected):
    assert expected in reasons(candidate)


def test_truncation_rejected():
    assert R.TRUNCATED in reasons(BASE, truncated=True)


def test_empty_nontext_and_explanatory_preamble_rejected():
    assert R.EMPTY in validate_candidate(BASE, None).reasons
    assert R.NON_BARE_TEXT in reasons("Here is the corrected text:\n" + BASE)


def test_new_url_or_domain_rejected():
    candidate = BASE.replace("there.", "there at spam.example.com.")
    assert R.JUNK_ADDED in reasons(candidate)


def test_exact_outer_fence_is_unwrapped_and_recorded():
    result = validate_candidate(BASE, f"```text\n{BASE}\n```", protected_terms=("Sunny", "Nephis"))
    assert result.accepted
    assert result.outer_fence_unwrapped
    assert result.candidate == BASE


@pytest.mark.parametrize("candidate", [f"Here:\n```\n{BASE}\n```", f"<think>fix</think>{BASE}"])
def test_commentary_fence_and_thinking_rejected(candidate):
    result = reasons(candidate)
    assert R.NON_BARE_TEXT in result or R.REASONING in result


def test_unspaced_em_dash_accepted_but_canonical_spaced_form_rejected():
    base = "Chapter 1: Dash.\n\nA word—word form remains."
    assert validate_candidate(base, base).accepted
    spaced = base.replace("word—word", "word — word")
    assert R.SPACED_EM_DASH in validate_candidate(base, spaced).reasons


def test_prompt_uses_runtime_lexicon_and_only_logs_hash(tmp_path):
    resource = tmp_path / "prompt.md"
    resource.write_text("PROMPT VERSION: 1.0\nMechanical only.", encoding="utf-8")
    bundle = build_system_prompt(("Sunny", "Nephis"), resource=resource)
    assert "Sunny" in bundle.system_prompt
    assert len(bundle.lexicon_hash) == 64
    assert "Sunny" not in bundle.lexicon_hash


def test_provenance_is_bounded_and_excludes_full_text_and_secret():
    secret = "FAKE_API_KEY_SHOULD_NEVER_APPEAR"
    baseline = BASE + (" old" * 100)
    candidate = BASE + (" new" * 100)
    record = build_provenance(
        baseline,
        candidate,
        provider="fake",
        model_id="fake-1",
        prompt_version="1.0",
        gate_version="1.0",
        status="rejected",
        rejection_reasons=("broad",),
    )
    serialized = json.dumps(record.to_dict())
    assert baseline not in serialized and candidate not in serialized
    assert secret not in serialized
    assert all(len(h["before"]) <= MAX_SNIPPET and len(h["after"]) <= MAX_SNIPPET for h in record.diff_hunks)
