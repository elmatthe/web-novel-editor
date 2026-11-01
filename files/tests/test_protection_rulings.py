"""Phase 03 protection floor: mandatory name rulings, safe correction data, bounded matching.

All prose here is authored synthetic text (no corpus content). The mandatory rulings (Master
Plan §8.2 and the 2026-11-01 directive) must survive the complete pipeline verbatim for every
profile: Clan Valor, Valor Clan, Valor, possessives, neighbouring words and punctuation.
"""

from __future__ import annotations

import re

import pytest

from core.novel_registry import NOVEL_INDEX_DIR, available_novels, clean_novel_name, resolve_dispatch
from core.protected_lexicon import load_protected_lexicon
from core.replacement_log import ReplacementLog
from pipelines.universal import UNIVERSAL_LITERAL_FIXES, _apply_special_fixes
from profiles.loader import CorrectionsError, parse_corrections, validate_against_protection

MANDATORY = [
    "Clan Valor sent the Valor Clan elders, and the proud Valor knights followed.",
    "The Valor Clan's heir bowed to Clan Valor's oldest elder.",
    "The Valor Clan’s heir bowed to Clan Valor’s oldest elder.",
    "Clan Valor, Valor Clan; Valor! (Valor) Valor? the Valor.",
    "A loyal Clan Valor captain, the elder Valor Clan scout and young Valor's sword waited.",
    "The Grey Wolf Tribe howled at the border.",
    "An ember glowed beside the amber stone while the Ember Queen watched.",
    "She prayed to the God of Peace and cursed the Demon of Desire.",
    "The War God smiled because she had always loved her people.",
    "War God, the Goddess of Life, wept.",
]
PROFILES = [clean_novel_name(label) for label in available_novels()]


def _lexicon(novel):
    dispatch = resolve_dispatch(novel)
    index = str(NOVEL_INDEX_DIR / dispatch.index_filename) if dispatch.index_filename else ""
    return dispatch, load_protected_lexicon(index, dispatch.canonical_names)


@pytest.mark.parametrize("novel", PROFILES)
def test_mandatory_rulings_survive_the_full_pipeline_verbatim(novel):
    dispatch, lexicon = _lexicon(novel)
    text = "Chapter 40: Names\n\n" + "\n\n".join(MANDATORY)
    out = dispatch.run_pipeline(text, lexicon, repl_log=ReplacementLog())
    flat = " ".join(out.split())
    for sentence in MANDATORY:
        assert sentence in flat, (novel, sentence)
    assert flat.count("Clan Valor") == text.count("Clan Valor")
    assert flat.count("Valor Clan") == text.count("Valor Clan")
    assert flat.count("Valor") == text.count("Valor")  # nothing deleted, nothing shortened
    assert flat.count("Clan") == text.count("Clan")


@pytest.mark.parametrize("novel", PROFILES)
def test_quoted_and_possessive_rulings_keep_the_name_text(novel):
    dispatch, lexicon = _lexicon(novel)
    text = 'Chapter 41: Quotes\n\n"Clan Valor," she said, "is not the Valor Clan."\n\n"Valor\'s banner," he said.'
    out = " ".join(dispatch.run_pipeline(text, lexicon, repl_log=ReplacementLog()).split())
    assert "Clan Valor," in out and "the Valor Clan." in out and "Valor's banner," in out
    assert "Clan" in out.split("Valor")[0]


# --------------------------------------------------------------------- correction data rules

@pytest.mark.parametrize("key,value", [("Clan Valor", "Valor"), ("the Valor Clan", "Valor Clan"),
                                       ("Grey Wolf Tribe", "Wolf Tribe"), ("Valor Clan elders", "Valor")])
def test_word_deleting_corrections_are_refused(key, value):
    with pytest.raises(CorrectionsError, match="shortening"):
        parse_corrections(f'[corrections]\n"{key}" = "{value}"\n')


@pytest.mark.parametrize("key,value", [("F riya", "Friya"), ("Silven/ving", "Silverwing"), ("Thmd", "Thrud"),
                                       ("Ligou", "Liguo")])
def test_joins_and_misspelling_repairs_remain_valid(key, value):
    assert parse_corrections(f'[corrections]\n"{key}" = "{value}"\n') == {key: value}


def test_cycles_and_unicode_duplicate_keys_are_refused():
    with pytest.raises(CorrectionsError, match="cascade"):
        parse_corrections('[corrections]\n"Ligo" = "Liguo"\n"Liguo" = "Ligo"\n')
    with pytest.raises(CorrectionsError, match="conflict"):
        parse_corrections('[corrections]\n"Caféx" = "Cafe"\n"Caféx" = "Cafe"\n')


@pytest.mark.parametrize("key,terms", [("Valor", ("Valor",)), ("valor", ("Valor",)), ("Clan Valor", ("Valor",)),
                                       ("Valor", ("Clan Valor",)), ("Sunny", ("Sunny",))])
def test_corrections_overlapping_protected_terms_are_refused(key, terms):
    with pytest.raises(CorrectionsError, match="overlaps protected term"):
        validate_against_protection({key: "Something"}, terms)


def test_non_overlapping_corrections_pass_and_partial_words_are_not_overlaps():
    validate_against_protection({"Obers": "Obels", "Valorx": "Valor"}, ("Valor", "Clan Valor"))


@pytest.mark.parametrize("novel", PROFILES)
def test_every_shipped_profile_correction_is_clear_of_its_protected_terms(novel):
    dispatch, lexicon = _lexicon(novel)
    fixes = {**UNIVERSAL_LITERAL_FIXES, **dict(dispatch.run_pipeline.profile.special_fixes)}
    validate_against_protection(fixes, lexicon.terms, source=novel)


def test_run_refuses_overlapping_data_before_any_file_is_processed(tmp_path, monkeypatch):
    from core import batch_runner
    import pipelines.universal as universal
    src = tmp_path / "a.txt"
    src.write_text("Clan Valor waited.", encoding="utf-8")
    monkeypatch.setattr(universal, "UNIVERSAL_LITERAL_FIXES", {"Clan Valor": "Valor"})
    monkeypatch.setattr(batch_runner, "UNIVERSAL_LITERAL_FIXES", {"Sunny": "Sun"})
    with pytest.raises(CorrectionsError, match="overlaps protected term"):
        batch_runner.run_batch([str(src)], str(tmp_path / "out"), novel_name="Shadow Slave",
                               output_formats=("txt",))
    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------------- bounded application

@pytest.mark.parametrize("text,expected", [
    ("Obers waited.", "Obels waited."),
    ("Obers's coat, Obers, (Obers) and “Obers”.", "Obels's coat, Obels, (Obels) and “Obels”."),
    ("Robers and Obersford stayed; OBERS too.", "Robers and Obersford stayed; OBERS too."),
    ("Xu Ligou met Ligo, and Ligou's blade shone.", "Xu Liguo met Liguo, and Liguo's blade shone."),
    ("Ligoun is a different word.", "Ligoun is a different word."),
])
def test_special_fixes_apply_on_token_boundaries_only(text, expected):
    fixes = {"Obers": "Obels", "Ligou": "Liguo", "Ligo": "Liguo"}
    assert _apply_special_fixes(text, None, fixes) == expected


def test_special_fixes_never_touch_masked_protected_terms():
    from core.protected_lexicon import mask_protected_terms, unmask_placeholders
    lexicon = load_protected_lexicon("", frozenset({"Obers Clan"}))
    masked, mapping = mask_protected_terms("The Obers Clan met Obers.", lexicon)
    fixed = _apply_special_fixes(masked, None, {"Obers": "Obels"})
    assert unmask_placeholders(fixed, mapping, {}) == "The Obers Clan met Obels."
