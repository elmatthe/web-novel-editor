"""Phase 03 conservative typography (TYPO-DQ-PAIR, TYPO-APOS): positives, negative controls,
protected names, full pipeline, idempotence and PDF/TXT glyph round-trips. Synthetic text only.
"""

from __future__ import annotations

import pytest

from core.protected_lexicon import load_protected_lexicon
from core.replacement_log import ReplacementLog
from rules import typography
from rules.typography import apply_typography, curl_apostrophes, pair_line

O, C, A = "“", "”", "’"


# --------------------------------------------------------------------------- double quotes

@pytest.mark.parametrize("line,expected", [
    ('"Good morning," she said.', f"{O}Good morning,{C} she said."),
    ('He said "yes" and left.', f"He said {O}yes{C} and left."),
    ('"Wait—" "What?"', f"{O}Wait—{C} {O}What?{C}"),
    ('—"Run!" he shouted.', f"—{O}Run!{C} he shouted."),
    ('"...I see," she whispered.', f"{O}...I see,{C} she whispered."),
    ('"*sigh*" was all.', f"{O}*sigh*{C} was all."),
    ('("Quiet.")', f"({O}Quiet.{C})"),
])
def test_clearly_paired_quotes_in_one_paragraph_become_curly(line, expected):
    new, count, uncertain = pair_line(line)
    assert (new, uncertain) == (expected, False) and count == line.count('"')


@pytest.mark.parametrize("line", [
    '"I went home. Then I slept.',               # multi-paragraph speech: opening only
    'Odd "quote with no close.',                  # odd count
    '"He said "no" to me."',                      # nested doubles: ambiguous roles
    'It was 5\'10" tall and 12" wide.',            # inch marks after digits
    'A 12" board and a 6" one.',                  # even inch marks are still measurements
    'He said "yes"and left.',                     # closing quote glued to a word
    'She said " hi" softly.',                     # spaced opening quote
    'An empty "" pair.',                          # empty pair
    f'Mixed {O}curly{C} and "straight" quotes.',  # mixed glyphs: preserve as written
    'fragment" from the previous page "and',      # unmatched extracted fragments
])
def test_uncertain_lines_are_left_exactly_as_written(line):
    new, count, uncertain = pair_line(line)
    assert new == line and count == 0 and uncertain


def test_existing_curly_quotes_are_never_changed_and_no_cross_line_pairing():
    text = f'{O}Already correct,{C} he said.\n\n"Opened here\n\nand closed here."'
    new, count, uncertain = typography.curl_double_quotes(text)
    assert new == text and count == 0 and uncertain == 2


# ------------------------------------------------------------------------------ apostrophes

@pytest.mark.parametrize("text,expected", [
    ("don't can't won't isn't", f"don{A}t can{A}t won{A}t isn{A}t"),
    ("it's the dog's bone; James's cart", f"it{A}s the dog{A}s bone; James{A}s cart"),
    ("they're we've you'll she'd I'm", f"they{A}re we{A}ve you{A}ll she{A}d I{A}m"),
    ("DON'T I'LL", f"DON{A}T I{A}LL"),
    ("café's menu", f"café{A}s menu"),
])
def test_unambiguous_contractions_and_possessives_become_curly(text, expected):
    assert curl_apostrophes(text)[0] == expected


@pytest.mark.parametrize("text", [
    "'em and 'twas and 'tis",          # leading elisions
    "the dogs' bowls and the Smiths' house",  # plural possessives
    "He was 5' tall and 6'2\" broad.",  # feet marks
    "Xi'an, rock'n'roll, o'clock",      # in-word apostrophes that are not contractions
    "'Hello,' she said. 'Go.'",          # single quotation marks
    "the 'quoted' word",
    "it’s already curly",
])
def test_ambiguous_single_quotes_are_preserved(text):
    assert curl_apostrophes(text) == (text, 0)


# ------------------------------------------------------------------------ protected names

@pytest.mark.parametrize("terms", [frozenset(), frozenset({"Sunny"})])
def test_rulings_floor_and_lexicon_protect_names_possessives_and_touching_quotes(terms):
    lexicon = load_protected_lexicon("", terms)
    text = ("The Valor Clan's heir bowed to Clan Valor's oldest elder.\n"
            '"Valor!" he cried.\n'
            "Sunny's cloak and the cat's tail.\n"
            '"Clan Valor," she said.')
    out = apply_typography(text, lexicon)
    lines = out.split("\n")
    assert lines[0] == "The Valor Clan's heir bowed to Clan Valor's oldest elder."
    assert lines[1] == '"Valor!" he cried.'          # quote touches a protected name: uncertain
    assert lines[3] == '"Clan Valor," she said.'
    assert lines[2] == ("Sunny's cloak and the cat’s tail." if terms
                        else "Sunny’s cloak and the cat’s tail.")


def test_name_with_internal_apostrophe_keeps_its_protected_spelling():
    lexicon = load_protected_lexicon("", frozenset({"Ka'd"}))
    assert apply_typography("Ka'd smiled. He'd won.", lexicon) == f"Ka'd smiled. He{A}d won."


def test_audit_rows_record_counts_and_uncertainty_without_text():
    log = ReplacementLog()
    apply_typography('"Hi," she said. It\'s fine.\n"Unclosed', None, log)
    rows = {e.rule: e for e in log.entries}
    assert rows[typography.RULE_DOUBLE].original == "2 straight double quote(s)"
    assert rows[typography.RULE_APOSTROPHE].original == "1 straight apostrophe(s)"
    assert rows[typography.RULE_UNCERTAIN].category == "integrity_flag"


def test_rules_are_idempotent():
    text = '"Don\'t go," she said. "It\'s late."\nOdd "one.\nThe dogs\' bowls.'
    once = apply_typography(text, None)
    assert apply_typography(once, None) == once


# --------------------------------------------------------------------------- full pipeline

def _run(text, novel="Universal"):
    from core.novel_registry import NOVEL_INDEX_DIR, resolve_dispatch
    dispatch = resolve_dispatch(novel)
    index = str(NOVEL_INDEX_DIR / dispatch.index_filename) if dispatch.index_filename else ""
    lexicon = load_protected_lexicon(index, dispatch.canonical_names)
    return dispatch.run_pipeline(text, lexicon, repl_log=ReplacementLog())


def test_full_pipeline_keeps_curly_input_and_pairs_straight_dialogue():
    text = (f"Chapter 30: Words.\n\n{O}Curly doubles stay,{C} he said. It{A}s fine.\n\n"
            '"Straight doubles pair," she replied. "It\'s the cat\'s bowl."\n\n'
            "Odd “quote with no close.")
    out = _run(text)
    assert f"{O}Curly doubles stay,{C} he said. It{A}s fine." in out
    assert f"{O}Straight doubles pair,{C} she replied. {O}It{A}s the cat{A}s bowl.{C}" in out
    assert "Odd “quote with no close." in out
    assert out.splitlines()[0].startswith("Chapter 30: Words")


def test_full_pipeline_heading_merge_and_paragraphs_are_unchanged_by_quote_shape():
    straight = 'Chapter 5: The Gate\n"Hello," he said.\nShe nodded.'
    curly = f"Chapter 5: The Gate\n{O}Hello,{C} he said.\nShe nodded."
    assert _run(straight) == _run(curly)


@pytest.mark.parametrize("novel", ["Universal", "Shadow Slave", "Supreme Magus", "The Noble Queen",
                                   "Renegade Immortal", "Reverend Insanity"])
def test_typography_changes_only_quote_glyphs_in_every_profile(novel, monkeypatch):
    text = ('Chapter 9: Talk.\n\n"I don\'t know," Sunny said. "It\'s the Valor Clan\'s call."\n\n'
            "The War God smiled because she had always loved her people. The dogs' bowls, 5'10\".")
    with_typography = _run(text, novel)
    monkeypatch.setattr(typography, "apply_typography", lambda t, lexicon, repl_log=None: t)
    without = _run(text, novel)
    assert with_typography != without
    assert with_typography.replace(O, '"').replace(C, '"').replace(A, "'") == without
    assert "Valor Clan's call" in with_typography and "War God smiled because she" in with_typography


def test_pdf_and_txt_outputs_carry_the_curly_glyphs(tmp_path):
    pytest.importorskip("pdfplumber")
    from core.batch_runner import run_batch
    src = tmp_path / "Chapter 3.txt"
    src.write_text('Chapter 3: Glyphs\n\n"Don\'t stop," she said. It\'s the dog\'s bone.\n', encoding="utf-8")
    summary = run_batch([str(src)], str(tmp_path / "out"), output_formats=("pdf", "txt"), novel_name="Universal")
    assert summary["succeeded"] == 1
    txt = (tmp_path / "out" / "Chapter 3.txt").read_text(encoding="utf-8")
    assert f"{O}Don{A}t stop,{C} she said. It{A}s the dog{A}s bone." in txt
    import pdfplumber
    with pdfplumber.open(tmp_path / "out" / "Chapter 3.pdf") as pdf:
        extracted = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert O in extracted and C in extracted and A in extracted and "Don" in extracted


# --- Codex review 8d93186: punctuation touching protected names, through suffixes ----------

@pytest.mark.parametrize("line", [
    'He said "the Clan Valor\'s".',
    '"Valor," he said.',
    '"Clan Valor!" she cried, "go."',
    '"(Valor)" was carved.',
    'They chanted "Valor Clan\'s pride" loudly.',
])
def test_quotes_in_a_token_with_a_protected_name_are_left_as_written(line):
    assert apply_typography(line, None) == line


def test_apostrophes_in_a_token_with_a_protected_name_are_left_as_written():
    out = apply_typography("A Clan Valor-man's oath and the cat's tail.", None)
    assert out == "A Clan Valor-man's oath and the cat\u2019s tail."


@pytest.mark.parametrize("novel", ["Universal", "Shadow Slave", "Supreme Magus", "The Noble Queen",
                                   "Renegade Immortal", "Reverend Insanity", "Re Monster",
                                   "Lord of the Mysteries", "Circle of Inevitability"])
def test_protected_possessive_with_quotes_is_verbatim_in_every_profile(novel):
    out = _run('Chapter 9: Names.\n\nHe said "the Clan Valor\'s". "Valor," she said.', novel)
    assert 'He said "the Clan Valor\'s". "Valor," she said.' in out
