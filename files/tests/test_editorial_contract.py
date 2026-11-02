"""Editorial-delta attribution contract (``files/qa-tools/editorial_contract.py``).

The contract decides whether every difference between a Phase 00-style baseline and a candidate
output is one the approved Phase 03 rules would make. Codex's re-review of ``0989804`` showed the
earlier checker accepting changes production refuses (OCR beside a protected word; reoriented or
mixed source quotes). Every negative case below is first anchored to real production behaviour,
then the contract must reject it; positive controls must still pass. Synthetic text only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qa-tools"))

from editorial_contract import NONSTANDARD_DOUBLES, Contract, attribute, phase03_rules_disabled  # noqa: E402

from core.protected_lexicon import (  # noqa: E402
    load_protected_lexicon, mask_chapter_lines, mask_protected_terms, unmask_placeholders)
from rules import typography, unicode_cleanup  # noqa: E402

O, C, A = "“", "”", "’"


@pytest.fixture(scope="module")
def shadow():
    return Contract.for_novel("Shadow Slave")


@pytest.fixture(scope="module")
def universal():
    return Contract.for_novel("Universal")


def production_ocr(text, contract):
    """Stage 9b exactly as the pipeline runs it: inside the chapter-line and protected-term mask."""
    from pipelines.universal import _apply_pronoun_l
    masked, chapters = mask_chapter_lines(text)
    masked, mapping = mask_protected_terms(masked, contract.lexicon)
    return unmask_placeholders(_apply_pronoun_l(masked, None), mapping, chapters)


def production_quotes(source, contract):
    """Stage 1a (keeps “ ”, folds non-standard doubles) then the final typography stage."""
    return typography.apply_typography(unicode_cleanup.normalize_quotes(source), contract.lexicon)


def rejected(result):
    return bool(result.unexplained)


def accepted(result, **rules):
    return not result.unexplained and dict(result.rules) == rules


# --------------------------------------------------------------------- exploit A: OCR l -> I

def test_codex_exploit_a_ocr_beside_protected_hope_is_rejected(shadow, universal):
    base, cur = "He left. l hope he returns.", "He left. I hope he returns."
    assert production_ocr(base, shadow) == base          # Shadow Slave protects Hope
    assert rejected(attribute(base, cur, base, shadow))
    assert production_ocr(base, universal) == cur        # no protection in Universal
    assert accepted(attribute(base, cur, base, universal), **{"ocr:pronoun-l": 1})


@pytest.mark.parametrize("base,cur", [
    ("He left. l Know the way.", "He left. I Know the way."),     # attested words are exact case
    ("and l know more.", "and I know more."),                     # mid-clause
    ("Fine, l know.", "Fine, I know."),                           # after a comma
    ("l walked away.", "I walked away."),                         # unattested verb
    ("l knowledge is power.", "I knowledge is power."),           # word must end at a boundary
    ("Bell'd stay.", "BelI'd stay."),                             # attached to a word
    ("l. First item", "I. First item"),                           # list label
    ("Chapter 12 - l know the way", "Chapter 12 - I know the way"),  # chapter lines are masked
    ("1 was the first.", "I was the first."),                     # digit one is never repaired
    ("L know nothing.", "I know nothing."),                       # capital L is out of scope
])
@pytest.mark.parametrize("novel", ["Universal", "Shadow Slave"])
def test_ocr_changes_production_never_makes_are_rejected(base, cur, novel):
    contract = Contract.for_novel(novel)
    assert production_ocr(base, contract) == base
    assert rejected(attribute(base, cur, base, contract))


def test_ocr_after_a_protected_term_ending_in_punctuation_is_rejected():
    """The clause-start context itself is masked, so production cannot see the sentence end."""
    contract = Contract(load_protected_lexicon("", frozenset({"Dr."})))
    base, cur = "Ask Dr. l know him.", "Ask Dr. I know him."
    assert production_ocr(base, contract) == base
    assert rejected(attribute(base, cur, base, contract))


def test_unglued_ocr_beside_protected_word_is_rejected(shadow, universal):
    """Phase 00 glued a lone ``l`` to the next word; un-gluing is only valid where repair is."""
    assert rejected(attribute("He left. lhope he returns.", "He left. I hope he returns.",
                              "He left. l hope he returns.", shadow))
    assert accepted(attribute("He left. lhope he returns.", "He left. I hope he returns.",
                              "He left. l hope he returns.", universal), **{"ocr:pronoun-l-unglued": 1})


@pytest.mark.parametrize("base,cur,rules", [
    ("He left. l think he returns.", "He left. I think he returns.", {"ocr:pronoun-l": 1}),
    ("l'm sure.", "I’m sure.", {"ocr:pronoun-l": 1, "apostrophe:contraction": 1}),
    ("l've seen it.", "I’ve seen it.", {"ocr:pronoun-l": 1, "apostrophe:contraction": 1}),
    ("Wait—l can explain.", "Wait—I can explain.", {"ocr:pronoun-l": 1}),
    ("(l was there.)", "(I was there.)", {"ocr:pronoun-l": 1}),
    ('"l thought so," he said.', f"{O}I thought so,{C} he said.", {"ocr:pronoun-l": 1, "quotes:paired": 2}),
    ("He left. lthink he returns.", "He left. I think he returns.", {"ocr:pronoun-l-unglued": 1}),
])
def test_legitimate_ocr_corrections_are_accepted(shadow, base, cur, rules):
    assert accepted(attribute(base, cur, base, shadow), **rules)


# ----------------------------------------------------------- exploit B: source quote provenance

def test_codex_exploit_b_reoriented_source_quotes_are_rejected(universal):
    base, source, cur = '"Go."', f"{C}Go.{O}", f"{O}Go.{C}"
    assert production_quotes(source, universal) == source
    assert rejected(attribute(base, cur, source, universal))


def test_codex_exploit_b_mixed_source_line_is_not_converted(universal):
    base = '"Stay," he said. "Go."'
    source = f'{O}Stay,{C} he said. "Go."'
    cur = f"{O}Stay,{C} he said. {O}Go.{C}"
    assert production_quotes(source, universal) == source
    assert rejected(attribute(base, cur, source, universal))
    assert accepted(attribute(base, source, source, universal), **{"quotes:preserved-source-glyph": 2})


@pytest.mark.parametrize("cur", [
    '"Stay," he said.',                 # both source glyphs disappeared (identical to baseline)
    f'"Stay,{C} he said.',              # opening glyph disappeared
    f"{O}Stay,{O} he said.",            # closing glyph replaced
    f"{C}Stay,{O} he said.",            # both reoriented
])
def test_changes_to_existing_curly_glyphs_are_rejected(universal, cur):
    base, source = '"Stay," he said.', f"{O}Stay,{C} he said."
    assert production_quotes(source, universal) == source
    assert rejected(attribute(base, cur, source, universal))


@pytest.mark.parametrize("cur", [
    f"{C}Go,{O} he said.",              # reversed orientation
    f'{O}Go," he said.',                # partial conversion
    f"{O}Go,{O} he said.",              # two openings
])
def test_misoriented_new_conversions_are_rejected(universal, cur):
    base = source = '"Go," he said.'
    assert production_quotes(source, universal) == f"{O}Go,{C} he said."
    assert rejected(attribute(base, cur, source, universal))


@pytest.mark.parametrize("line", [
    '"" is empty. "Go."',                # empty pair
    'He is 6" tall and "big".',          # a quote after a digit
    'Odd "quote with no close.',         # odd count
])
def test_conversion_of_uncertain_lines_is_rejected(universal, line):
    converted = line.replace('"', O, 1).replace('"', C, 1).replace('"', O, 1).replace('"', C, 1)
    assert production_quotes(line, universal) == line
    assert rejected(attribute(line, converted, line, universal))


@pytest.mark.parametrize("line", [
    '"Sunny," she called.',              # protected name in the token
    '"Sunnys" was all she said.',        # protected plural variant (masked as a whole)
    'She said "Sunny\'s".',              # protected possessive variant
])
def test_conversion_touching_protected_names_is_rejected(shadow, universal, line):
    converted = line.replace('"', O, 1).replace('"', C, 1)
    assert production_quotes(line, shadow) == line
    assert rejected(attribute(line, converted, line, shadow))
    produced = production_quotes(line, universal)       # nothing protected in Universal
    assert produced != line and not rejected(attribute(line, produced, line, universal))


def test_conversion_without_source_text_is_unverifiable(universal):
    assert rejected(attribute('"Go," he said.', f"{O}Go,{C} he said.", None, universal))


# ------------------------------------------------------------------- quote positive controls

@pytest.mark.parametrize("base,source,cur,rules", [
    ('"Go," he said.', '"Go," he said.', f"{O}Go,{C} he said.", {"quotes:paired": 2}),
    ('"Go," he said.', f"{O}Go,{C} he said.", f"{O}Go,{C} he said.", {"quotes:preserved-source-glyph": 2}),
    ('"Go," he said.', '„Go," he said.', f"{O}Go,{C} he said.", {"quotes:paired": 2}),
    ('"Go," he said.', "«Go,» he said.", f"{O}Go,{C} he said.", {"quotes:paired": 2}),
    ('"Wait—" "What?"', '"Wait—" "What?"', f"{O}Wait—{C} {O}What?{C}", {"quotes:paired": 4}),
])
def test_legitimate_quote_changes_are_accepted(universal, base, source, cur, rules):
    assert production_quotes(source, universal) == cur
    assert accepted(attribute(base, cur, source, universal), **rules)


def test_source_curly_survives_legacy_rewrites_of_the_surrounding_text(universal):
    """The spaced-dash rule rewrote the words after the source quote; provenance still holds."""
    source = f"{O}Listen — all of them — must go,{C} she said.\nThen she left."
    base = '"Listen, all of them, must go," she said.\nThen she left.'
    cur = f"{O}Listen, all of them, must go,{C} she said.\nThen she left."
    assert accepted(attribute(base, cur, source, universal), **{"quotes:preserved-source-glyph": 2})
    assert rejected(attribute(base, cur.replace(O, "#").replace(C, O).replace("#", C), source, universal))


# ------------------------------------------------------------------------- apostrophes

def test_apostrophes_follow_the_contract_and_protection(shadow, universal):
    base = "It's Sunny's day; don't. 'Em and dogs' bones."
    cur = f"It{A}s Sunny's day; don{A}t. 'Em and dogs' bones."
    assert accepted(attribute(base, cur, base, shadow), **{"apostrophe:contraction": 2})
    assert rejected(attribute(base, cur.replace("Sunny's", f"Sunny{A}s"), base, shadow))
    assert accepted(attribute(base, cur.replace("Sunny's", f"Sunny{A}s"), base, universal),
                    **{"apostrophe:contraction": 3})
    for wrong in (f"{A}Em", f"dogs{A} "):
        assert rejected(attribute(base, cur.replace(wrong.replace(A, "'"), wrong), base, universal))


def test_clean_unchanged_prose_has_nothing_to_attribute(shadow):
    text = "The wind rose. Nobody spoke, and the night went on.\nMorning came."
    result = attribute(text, text, text, shadow)
    assert accepted(result)


# --------------------------------------------- full pipeline: production passes, mutations fail

CHAPTER = (
    "Chapter 7: Proof\n\n"
    f"{O}Listen — all of them — must go,{C} she said. He didn't answer.\n\n"
    '"Stay," he said. "Go now."\n\n'
    f'{O}Mixed,{C} he said. "Left alone."\n\n'
    f"{C}Reversed,{O} she said.\n\n"
    "He left. l think he returns. l'm sure of it.\n\n"
    "He left. l hope he returns.\n\n"
    "It's Sunny's sword. \"Sunny,\" she called. It was 5'10\" tall.\n\n"
    "'Em and the dogs' bones stayed. She said 'fine' quietly.\n"
)


def _pipeline(text, contract):
    from core.replacement_log import ReplacementLog
    from pipelines.universal import run_pipeline
    log = ReplacementLog()
    return run_pipeline(text, contract.lexicon, repl_log=log, input_kind="txt"), log


def _mutations(text):
    swaps = {'"': (O, C), O: ('"', C), C: ('"', O), "'": (A, "‘"), A: ("'", "‘"), "l": ("I",)}
    for i, ch in enumerate(text):
        for other in swaps.get(ch, ()):
            yield i, text[:i] + other + text[i + 1:]


@pytest.mark.parametrize("novel", ["Universal", "Shadow Slave"])
def test_production_output_is_fully_attributed_and_every_glyph_mutation_is_caught(novel):
    contract = Contract.for_novel(novel)
    cur, log = _pipeline(CHAPTER, contract)
    with phase03_rules_disabled():
        base, _ = _pipeline(CHAPTER, contract)
    assert _pipeline(CHAPTER, contract)[0] == cur          # the switch restores production
    assert base != cur
    result = attribute(base, cur, CHAPTER, contract)
    assert result.unexplained == []
    counts = {e.rule: int(e.original.split()[0]) for e in log.entries
              if e.rule in ("typography.paired_double_quotes", "typography.apostrophe_contraction",
                            "ocr_repair.pronoun_l")}
    assert result.rules["quotes:paired"] == counts.get("typography.paired_double_quotes", 0)
    assert result.rules["apostrophe:contraction"] == counts.get("typography.apostrophe_contraction", 0)
    assert result.rules["ocr:pronoun-l"] + result.rules["ocr:pronoun-l-unglued"] == counts["ocr_repair.pronoun_l"]
    assert result.rules["quotes:preserved-source-glyph"] == 6
    missed = [(i, mutated[max(0, i - 15):i + 15]) for i, mutated in _mutations(cur)
              if not attribute(base, mutated, CHAPTER, contract).unexplained]
    assert missed == []


def test_contract_folds_exactly_the_doubles_production_folds():
    assert set(unicode_cleanup._DOUBLE_QUOTE_RE.pattern.strip("[]")) == set(NONSTANDARD_DOUBLES)


# ------------------------------------------- provenance where a legacy rule edited beside a quote

@pytest.mark.parametrize("source_line,expected", [
    ('".. He left the room quietly, didn\'t he?"', {0: "other", -1: "other"}),
    ("“.. He left the room quietly, didn't he?”", {0: "open", -1: "close"}),
    ("”.. He left the room quietly, didn't he?“", {0: "close", -1: "open"}),
    ('"“.. He left the room quietly, didn\'t he?"', {0: None, -1: "other"}),   # two candidates: unresolved
])
def test_quote_next_to_a_legacy_edit_is_resolved_only_when_unambiguous(source_line, expected):
    """The legacy punctuation rule turns ``..`` into ``.`` right after the opening quote."""
    from editorial_contract import SourceAligner
    aligner = SourceAligner(f"She said “Fine.”\n{source_line}\nEnd.")
    line = '". He left the room quietly, didn\'t he?"'
    last = len(line) - 1
    classes = aligner.quote_classes(line, [0, last])
    assert classes == {0: expected[0], last: expected[-1]}


def test_legacy_punctuation_edit_beside_a_quote_is_attributed_end_to_end(universal):
    source = "Chapter 1: Doors\n\n“Fine,” she said.\n\n\".. He left, didn't he?\"\n"
    cur, _ = _pipeline(source, universal)
    with phase03_rules_disabled():
        base, _ = _pipeline(source, universal)
    assert f"{O}. He left, didn{A}t he?{C}" in cur
    assert accepted(attribute(base, cur, source, universal), **{
        "quotes:preserved-source-glyph": 2, "quotes:paired": 2, "apostrophe:contraction": 1})
    assert rejected(attribute(base, cur.replace(f"{O}. He", f"{C}. He"), source, universal))
