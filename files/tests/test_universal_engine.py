"""One engine, many profiles (Phase 01C).

Five near-identical orchestrations became `pipelines/universal.py`. These tests pin what
that consolidation must not change - stage order, audit-row policy, protected names - and
what it deliberately changes (Gate 00 decisions, DECISIONS 075): `carcassess` is a bounded
universal fix, and `threestoried` / `tompost shelf` are no longer corrected anywhere.
"""

from __future__ import annotations

import pkgutil

import pytest

import pipelines
from core.novel_registry import (
    NOVEL_INDEX_DIR,
    available_novels,
    clean_novel_name,
    resolve_dispatch,
)
from core.protected_lexicon import ProtectedLexicon, load_protected_lexicon
from core.replacement_log import ReplacementLog
from pipelines import universal
from pipelines.universal import UNIVERSAL_LITERAL_FIXES, UNIVERSAL_PROFILE, PipelineProfile
from profiles.shadow_slave.special_fixes import SS_SPECIAL_FIXES

ROSTER = [clean_novel_name(name) for name in available_novels()]
SUMMARY_PROFILES = ("Shadow Slave", "Supreme Magus", "The Noble Queen")
NO_SUMMARY_PROFILES = [n for n in ROSTER if n not in SUMMARY_PROFILES]


def _lexicon(novel: str) -> ProtectedLexicon:
    d = resolve_dispatch(novel)
    path = str(NOVEL_INDEX_DIR / d.index_filename) if d.index_filename else ""
    return load_protected_lexicon(path, d.canonical_names)


def _run(novel: str, text: str, *, log: ReplacementLog | None = None, lexicon=None) -> str:
    return resolve_dispatch(novel).run_pipeline(
        text, lexicon if lexicon is not None else _lexicon(novel), repl_log=log
    )


# -- one orchestration -------------------------------------------------------------------


def test_there_is_exactly_one_pipeline_module():
    names = {m.name for m in pkgutil.iter_modules(pipelines.__path__)}
    assert names == {"universal"}


@pytest.mark.parametrize("novel", ROSTER)
def test_every_roster_novel_runs_the_one_engine(novel):
    run = resolve_dispatch(novel).run_pipeline
    assert run.__module__ == "pipelines.universal"
    assert isinstance(run.profile, PipelineProfile)


def test_unregistered_novels_use_the_empty_universal_profile():
    for name in ("Universal", "Reverend Insanity", "Circle of Inevitability", "Zz Not A Novel"):
        d = resolve_dispatch(name)
        assert d.has_profile is False
        assert d.run_pipeline.profile is UNIVERSAL_PROFILE
    assert UNIVERSAL_PROFILE.special_fixes == {} and UNIVERSAL_PROFILE.summary_rows is False


# -- stage order -------------------------------------------------------------------------

_EXPECTED_ORDER = [
    "unicode_cleanup.normalize_unicode",
    "unicode_cleanup.normalize_quotes",
    "ligature_cleanup.normalize_ligatures",
    "junk_strip.strip_junk",
    "unicode_cleanup.remove_scanner_junk",
    "spacing_cleanup.remove_headers_footers",
    "spacing_cleanup.collapse_same_line_duplicate_chapters",
    "spacing_cleanup.remove_doubled_chapter_lines",
    "spacing_cleanup.repair_page_boundaries",
    "spacing_cleanup.dehyphenate",
    "spacing_cleanup.reconstruct_paragraphs",
    "ocr_repair.repair_ocr",
    "spacing_cleanup.fix_spurious_spaces",
    "unicode_cleanup.collapse_spaces",
    "slash_replace.replace_slashes",
    "em_dash.remove_spaced_em_dashes",       # first (masked) dash pass
    "chapter_titles.normalize_chapter_titles",
    "punctuation.repair_punctuation",
    "grammar.repair_grammar",
    "em_dash.remove_spaced_em_dashes",       # mandatory final sweep
    "chapter_titles.remove_duplicate_chapter_titles_global",
    "chapter_titles.insert_chapter_page_breaks",
    "chapter_titles.validate_headings",
]


@pytest.mark.parametrize("novel", ["Universal", "Shadow Slave", "Renegade Immortal"])
def test_the_three_block_stage_order_is_preserved(monkeypatch, novel):
    calls: list[str] = []
    for module_name in ("unicode_cleanup", "ligature_cleanup", "junk_strip", "spacing_cleanup",
                        "ocr_repair", "slash_replace", "em_dash", "chapter_titles",
                        "punctuation", "grammar"):
        module = getattr(universal, module_name)
        for fn_name in {e.split(".")[1] for e in _EXPECTED_ORDER if e.startswith(module_name + ".")}:
            original = getattr(module, fn_name)

            def make(orig, label):
                def wrapper(*args, **kwargs):
                    calls.append(label)
                    return orig(*args, **kwargs)
                return wrapper

            monkeypatch.setattr(module, fn_name, make(original, f"{module_name}.{fn_name}"))

    _run(novel, "Chapter 1: Order.\n\nHe walked on, and the road went on.\n")
    # The masked-segment helper may call a rule once per text segment; collapse those
    # consecutive repeats. The two separate dash passes stay distinct entries.
    ordered = [c for i, c in enumerate(calls) if i == 0 or c != calls[i - 1]]
    assert ordered == _EXPECTED_ORDER


# -- audit-row policy (Gate 00: legacy counts unchanged) ---------------------------------

_ROW_TEXT = "Chapter 1: Rows.\n\n“He scored 6/7 today — then he left,” she said.\n"
_SUMMARY_RULES = {"quote_normalize", "slash_replace", "em_dash"}


@pytest.mark.parametrize("novel", SUMMARY_PROFILES)
def test_the_three_legacy_profiles_keep_their_audit_summary_rows(novel):
    log = ReplacementLog()
    _run(novel, _ROW_TEXT, log=log)
    assert {e.rule for e in log.entries} >= _SUMMARY_RULES


@pytest.mark.parametrize("novel", NO_SUMMARY_PROFILES)
def test_the_other_profiles_still_get_no_summary_rows(novel):
    log = ReplacementLog()
    _run(novel, _ROW_TEXT, log=log)
    assert not ({e.rule for e in log.entries} & _SUMMARY_RULES)


def test_the_summary_row_policy_never_changes_the_text():
    lex = ProtectedLexicon()
    with_rows = universal.run_pipeline(_ROW_TEXT, lex, profile=PipelineProfile("a", {}, True))
    without = universal.run_pipeline(_ROW_TEXT, lex, profile=PipelineProfile("b", {}, False))
    assert with_rows == without


# -- the bounded universal fix: carcassess ----------------------------------------------


def test_the_universal_fix_table_is_exactly_the_one_approved_entry():
    assert dict(UNIVERSAL_LITERAL_FIXES) == {"carcassess": "carcasses"}


@pytest.mark.parametrize("novel", ROSTER)
def test_carcassess_is_corrected_for_every_profile(novel):
    log = ReplacementLog()
    out = _run(novel, "Chapter 1: Fix.\n\nThe carcassess lay in the cold hall.\n", log=log)
    assert "carcasses lay in the cold hall" in out and "carcassess" not in out
    assert [(e.original, e.replacement, e.rule) for e in log.entries
            if e.rule == "special_fixes"] == [("carcassess", "carcasses", "special_fixes")]


@pytest.mark.parametrize(
    "text",
    [
        "Chapter 1: Neg.\n\nThe Scarcassess ledger was long.\n",        # inside another word
        "Chapter 1: Neg.\n\nCarcassessing is not a word either.\n",      # longer word
        "Chapter 1: Neg.\n\nThe Carcassess Guild met at noon.\n",        # capitalised: exact only
        "Chapter 1: Neg.\n\nThe carcasses were already spelled right.\n",  # correct form
        "Chapter 1: Neg.\n\nNothing here to fix, only plain prose.\n",
    ],
)
def test_carcassess_negative_fixtures_are_left_exactly_alone(text):
    log = ReplacementLog()
    out = _run("Universal", text, log=log)
    body = text.split("\n\n", 1)[1].strip()
    assert body in out
    assert not [e for e in log.entries if e.rule == "special_fixes"]


def test_carcassess_inside_a_protected_term_is_not_touched():
    lex = ProtectedLexicon(
        terms=("carcassess hall",), term_set_lower=frozenset({"carcassess hall"})
    )
    out = _run("Universal", "Chapter 1: Mask.\n\nThe carcassess hall stood empty.\n", lexicon=lex)
    assert "carcassess hall" in out and "carcasses hall" not in out


def test_carcassess_is_corrected_next_to_punctuation_and_possessives():
    out = _run("Universal", "Chapter 1: Edge.\n\nA carcassess' smell, a carcassess, a carcassess.\n")
    assert "carcasses' smell" in out and "carcassess" not in out


# -- retired Shadow Slave entries --------------------------------------------------------


def test_threestoried_and_tompost_shelf_are_no_longer_corrected_anywhere():
    text = "Chapter 1: Gone.\n\nA threestoried hall near the tompost shelf.\n"
    for novel in ROSTER:
        out = _run(novel, text)
        assert "threestoried hall near the tompost shelf" in out, novel


def test_shadow_slave_keeps_only_its_approved_name_and_term_corrections():
    assert SS_SPECIAL_FIXES == {"Almanach": "Almanac", "Obers": "Obels"}
    text = "Chapter 1: Names.\n\nThe Almanach of Obers lay open.\n"
    assert "The Almanac of Obels lay open." in _run("Shadow Slave", text)
    assert "The Almanach of Obers lay open." in _run("Universal", text)


# -- mandatory name invariants on EVERY profile ------------------------------------------

_MANDATORY = [
    "Clan Valor sent the Valor Clan elders, and the proud Valor knights followed.",
    "The Valor Clan's heir bowed to Clan Valor's oldest elder.",
    "The Grey Wolf Tribe howled at the border.",
    "An ember glowed beside the amber stone while the Ember Queen watched.",
    "She prayed to the God of Peace and cursed the Demon of Desire.",
    "The War God smiled because she had always loved her people.",
    "War God, the Goddess of Life, wept.",
]


@pytest.mark.parametrize("novel", ROSTER)
def test_clan_valor_valor_clan_and_valor_are_never_rewritten(novel):
    text = "Chapter 40: Names.\n\n" + "\n\n".join(_MANDATORY)
    out = " ".join(_run(novel, text).split())
    for sentence in _MANDATORY:
        assert sentence in out, (novel, sentence)
    assert out.count("Clan Valor") == 2 and out.count("Valor Clan") == 2
