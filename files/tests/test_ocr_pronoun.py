"""OCR-L-PRONOUN (Phase 03, Gate 00 D6): lowercase ``l`` for ``I`` only in attested contexts.

Synthetic sentences shaped like the counted Supreme Magus evidence (no corpus text).
"""

from __future__ import annotations

import pytest

from core.protected_lexicon import load_protected_lexicon
from core.replacement_log import ReplacementLog
from rules.ocr_repair import PRONOUN_L_WORDS, repair_pronoun_l


@pytest.mark.parametrize("text,expected", [
    ("l'm sure. l'll go. l've seen it. l'd stay.", "I'm sure. I'll go. I've seen it. I'd stay."),
    ("l’m here.", "I’m here."),
    ("l know the way.", "I know the way."),
    ("He left. l hope he returns.", "He left. I hope he returns."),
    ('"l don\'t care," she said.', '"I don\'t care," she said.'),
    ("“l thought so.”", "“I thought so.”"),
    ("Wait—l can explain.", "Wait—I can explain."),
    ("(l was there.)", "(I was there.)"),
    ("It's late! l must go.", "It's late! I must go."),
    ("l can’t stop.", "I can’t stop."),
])
def test_attested_contexts_are_repaired(text, expected):
    assert repair_pronoun_l(text)[0] == expected


@pytest.mark.parametrize("text", [
    "1 was the first number.",          # digit 1 is never repaired
    "He measured 1 foot and 1 inch.",
    "1'm not a word either.",           # no evidence for digit contractions
    "and l want more.",                 # mid-clause: excluded (conservative)
    "Fine, l know.",                    # after a comma: excluded
    "the letter l was printed.",        # letter name
    "a l ife of l ike and l ost things",  # split-word OCR, not the pronoun
    "l. First item\nl) Second item",    # list labels
    "Code l23 and l-shaped room.",      # identifiers
    "L know nothing.",                  # capital L is out of scope
    "l walked away.",                   # verb not attested in the evidence
    "Bell'm and Will'd stay.",          # contraction attached to a word
    "l knowledge is power.",            # attested word must end at a word boundary
])
def test_negative_controls_are_unchanged(text):
    assert repair_pronoun_l(text) == (text, 0)


def test_rule_is_idempotent_and_never_touches_capital_I():
    text = "I know. l know. I'm here and l'm here."
    once, count = repair_pronoun_l(text)
    assert once == "I know. I know. I'm here and I'm here." and count == 2
    assert repair_pronoun_l(once) == (once, 0)


def test_word_list_is_the_closed_attested_set():
    assert len(PRONOUN_L_WORDS) == len(set(PRONOUN_L_WORDS)) == 37
    assert "walked" not in PRONOUN_L_WORDS and "know" in PRONOUN_L_WORDS


def _run(text, novel, log=None):
    from core.novel_registry import NOVEL_INDEX_DIR, resolve_dispatch
    dispatch = resolve_dispatch(novel)
    index = str(NOVEL_INDEX_DIR / dispatch.index_filename) if dispatch.index_filename else ""
    lexicon = load_protected_lexicon(index, dispatch.canonical_names)
    return dispatch.run_pipeline(text, lexicon, repl_log=log if log is not None else ReplacementLog())


@pytest.mark.parametrize("novel", ["Universal", "Supreme Magus", "Shadow Slave"])
def test_full_pipeline_repairs_only_the_pronoun_and_records_it(novel):
    log = ReplacementLog()
    text = ("Chapter 12: Morning\n\nl know the way. He measured 1 foot. He left. l think he returns. "
            "l'm sure the Valor Clan's banner stood.")
    out = _run(text, novel, log)
    assert "I know the way." in out and "I’m sure" in out
    # After a sentence end the legacy single-letter rejoin used to glue "l think" -> "lthink".
    assert "He left. I think he returns." in out and "lthink" not in out
    assert "1 foot" in out and "Valor Clan's banner" in out
    rows = [e for e in log.entries if e.rule == "ocr_repair.pronoun_l"]
    assert len(rows) == 1 and rows[0].original.startswith("3 ")


def test_a_protected_name_after_l_blocks_the_repair():
    """Shadow Slave protects the name Hope (masking is case-insensitive): protection wins."""
    text = "Chapter 2: Names\n\nHe left. l hope he returns."
    assert "He left. l hope he returns." in _run(text, "Shadow Slave")
    assert "He left. I hope he returns." in _run(text, "Universal")


def test_legacy_single_letter_rejoin_is_recorded_not_changed():
    """Pre-existing behavior (not a Phase 03 rule): a mid-clause lone consonant is glued to the
    next word by spacing_cleanup.fix_spurious_spaces. Recorded here; changing it needs approval."""
    out = _run("Chapter 1: Letters\n\nThe letter l was faint.", "Universal")
    assert "The letter lwas faint." in out


def test_protected_terms_are_masked_before_the_repair():
    lexicon = load_protected_lexicon("", frozenset({"l know"}))
    from core.protected_lexicon import mask_protected_terms, unmask_placeholders
    from pipelines.universal import _apply_pronoun_l
    masked, mapping = mask_protected_terms("l know. Then: l know.", lexicon)
    assert unmask_placeholders(_apply_pronoun_l(masked, None), mapping, {}) == "l know. Then: l know."
