"""Phase 4 — unit tests for each rule module (pure string -> string functions).

Each test asserts a known input produces the exact expected output, and (where it
matters) that clean prose is left UNCHANGED so the conservative "insurance" rules can
never corrupt an already-clean corpus.
"""

from __future__ import annotations

from rules import (
    chapter_titles,
    em_dash,
    grammar,
    junk_strip,
    ligature_cleanup,
    ocr_repair,
    punctuation,
    slash_replace,
    spacing_cleanup,
    unicode_cleanup,
)
from core.protected_lexicon import ProtectedLexicon


# --- unicode_cleanup --------------------------------------------------------
def test_normalize_unicode_spaces_and_invisibles():
    assert unicode_cleanup.normalize_unicode("a b​c") == "a bc"
    assert unicode_cleanup.normalize_unicode("keep\nnewline\fff") == "keep\nnewline\fff"


def test_normalize_quotes_doubles_only():
    assert unicode_cleanup.normalize_quotes("“Hi”") == '"Hi"'
    # apostrophes / single quotes are preserved
    assert unicode_cleanup.normalize_quotes("It’s ‘x’") == "It’s ‘x’"


def test_remove_scanner_junk():
    assert unicode_cleanup.remove_scanner_junk("a■b�c") == "abc"


def test_collapse_spaces():
    assert unicode_cleanup.collapse_spaces("a   b\t\tc") == "a b c"
    assert unicode_cleanup.collapse_spaces("trail   \nnext") == "trail\nnext"


# --- ligature_cleanup -------------------------------------------------------
def test_ligatures():
    assert ligature_cleanup.normalize_ligatures("oﬁce ﬂow") == "ofice flow"
    assert ligature_cleanup.normalize_ligatures("clean") == "clean"


# --- spacing_cleanup: paragraph reconstruction (the core new work) ----------
def test_reconstruct_joins_wrapped_lines_and_breaks_paragraphs():
    src = (
        "A frail young man sat on a bench across from the\n"
        "police station. He cradled a cup of coffee.\n"
        "After all, his life was ending."
    )
    out = spacing_cleanup.reconstruct_paragraphs(src)
    assert out == (
        "A frail young man sat on a bench across from the police station. "
        "He cradled a cup of coffee.\n\n"
        "After all, his life was ending."
    )


def test_reconstruct_isolates_chapter_heading():
    src = "Chapter 1: Nightmare Begins.\nA frail young man sat down\nand waited."
    out = spacing_cleanup.reconstruct_paragraphs(src)
    paras = out.split("\n\n")
    assert paras[0] == "Chapter 1: Nightmare Begins."
    assert paras[1] == "A frail young man sat down and waited."


def test_reconstruct_heading_isolated_even_without_terminal_punct():
    # Heading not ending in '.', next line lowercase -> still its own paragraph.
    src = "Chapter 7 The Gate\nthe gate stood open before them."
    out = spacing_cleanup.reconstruct_paragraphs(src)
    paras = out.split("\n\n")
    assert paras[0] == "Chapter 7 The Gate"
    assert paras[1] == "the gate stood open before them."


def test_dehyphenate():
    assert spacing_cleanup.dehyphenate("sur-\nface") == "surface"
    assert spacing_cleanup.dehyphenate("well-\nknown") == "well-known"
    assert spacing_cleanup.dehyphenate("self-\naware") == "self-aware"
    # capitalized continuation (proper compound) is not joined
    assert spacing_cleanup.dehyphenate("North-\nGate") == "North-\nGate"


def test_fix_spurious_spaces():
    # needs leading context (the rejoin only fires after a space, not at string start)
    assert spacing_cleanup.fix_spurious_spaces("He was d efending the w all") == (
        "He was defending the wall"
    )
    # the article 'a ' must not be merged into the next word
    assert "a spell" in spacing_cleanup.fix_spurious_spaces("cast a spell now")


def test_remove_headers_footers_is_safe_noop_without_page_positions():
    src = "Come on\nBody.\nCome on\nBody.\nCome on"
    assert spacing_cleanup.remove_headers_footers(src) == src


# --- ocr_repair (conservative; must not touch clean prose) ------------------
def test_ocr_repairs_artifacts():
    assert ocr_repair.repair_ocr("tbe b0dy") == "the body"
    assert ocr_repair.repair_ocr("V|adion") == "Vladion"
    assert ocr_repair.repair_ocr("Lith’swill") == "Lith’s will"


def test_ocr_leaves_clean_prose_unchanged():
    clean = "The body of the warrior fell to the floor without a sound."
    assert ocr_repair.repair_ocr(clean) == clean


# --- chapter_titles ---------------------------------------------------------
def test_normalize_titles():
    assert chapter_titles.normalize_chapter_titles("chapter 1 Awakening").startswith(
        "Chapter 1: Awakening."
    )
    assert chapter_titles.normalize_chapter_titles("CHAPTER 1,000 - The End").startswith(
        "Chapter 1,000: The End."
    )


def test_normalize_titleless_heading_has_no_invented_punctuation():
    assert chapter_titles.normalize_chapter_titles("Chapter 1").splitlines()[0] == "Chapter 1"


def test_normalize_title_peels_body_fused_onto_heading():
    # Extraction sometimes fuses the first body sentence onto the heading line; the
    # title is kept and the body is split back off onto its own line.
    out = chapter_titles.normalize_chapter_titles(
        "Chapter 12: The Gate Sunny stood before the gate."
    )
    lines = [ln for ln in out.split("\n") if ln.strip()]
    assert lines[0] == "Chapter 12: The Gate."
    assert lines[1].startswith("Sunny stood before the gate")


def test_normalize_title_keeps_part_suffix():
    out = chapter_titles.normalize_chapter_titles("chapter 8 The Trial (Part 2)")
    assert out.split("\n")[0] == "Chapter 8: The Trial (Part 2)."


def test_normalize_title_keeps_interrogative_or_exclamatory_terminal():
    # Phase-3 QA finding (Noble Queen ch. 649): a "?"-terminated title must not
    # gain a trailing period — "Cats?." is the duplicate-terminal form Stage 15
    # and TTS criterion 5 forbid. The title's own ?/! already ends the heading.
    out = chapter_titles.normalize_chapter_titles("Chapter 649: Did Someone Say Cats?")
    assert out.split("\n")[0] == "Chapter 649: Did Someone Say Cats?"
    out = chapter_titles.normalize_chapter_titles("chapter 3 Enough!")
    assert out.split("\n")[0] == "Chapter 3: Enough!"
    # An already-damaged "?." raw heading collapses to the bare "?" form.
    out = chapter_titles.normalize_chapter_titles("Chapter 649: Did Someone Say Cats?.")
    assert out.split("\n")[0] == "Chapter 649: Did Someone Say Cats?"


def test_validate_headings_accepts_terminal_question_or_bang():
    # ?- and !-terminated normalized headings are valid, not malformed.
    assert chapter_titles.validate_headings("Chapter 649: Did Someone Say Cats?") == []
    assert chapter_titles.validate_headings("Chapter 3: Enough!") == []


def test_remove_duplicate_titles():
    src = "Chapter 5: A.\n\nbody one\n\nChapter 5: A.\n\nbody two"
    out = chapter_titles.remove_duplicate_chapter_titles_global(src)
    assert out.count("Chapter 5: A.") == 1


def test_insert_page_breaks():
    src = "Chapter 1: A.\n\nbody\n\nChapter 2: B.\n\nbody"
    out = chapter_titles.insert_chapter_page_breaks(src)
    assert out.count("\f") == 1  # break before 2nd heading only


def test_validate_headings_flags_malformed():
    assert chapter_titles.validate_headings("Chapter 9 no colon no period") != []
    assert chapter_titles.validate_headings("Chapter 9: Fine.") == []


# --- punctuation (ellipsis-safe) --------------------------------------------
def test_punctuation_fixes():
    assert punctuation.repair_punctuation("Well.It was good ,really") == "Well. It was good, really"


def test_punctuation_preserves_ellipsis_and_numbers():
    assert "..." in punctuation.repair_punctuation("Wait... what")
    assert "1,000" in punctuation.repair_punctuation("It cost 1,000 marks")


def test_punctuation_collapses_duplicate_terminal_after_question_or_bang():
    # Stage 15's documented "?!." -> "?!" collapse: a lone period directly after
    # ? or ! is duplicate terminal punctuation (Phase-3 QA, Noble Queen ch. 649).
    assert punctuation.repair_punctuation("Say Cats?.") == "Say Cats?"
    assert punctuation.repair_punctuation("Enough!.") == "Enough!"


def test_punctuation_preserves_question_ellipsis_style():
    # Real Shadow Slave prose style (ch. 500 / ch. 1500): "lifetimes?..." and
    # "right?..." are deliberate question-plus-ellipsis and must stay verbatim.
    src = "years, lifetimes?... spent traversing"
    assert punctuation.repair_punctuation(src) == src


# --- grammar (unambiguous a/an only) ----------------------------------------
def test_grammar_articles():
    assert grammar.repair_grammar("a explosion") == "an explosion"
    assert grammar.repair_grammar("an book") == "a book"


def test_grammar_leaves_hard_cases():
    assert grammar.repair_grammar("a university") == "a university"
    assert grammar.repair_grammar("a one-time deal") == "a one-time deal"


def test_grammar_leaves_consonant_sound_eu_ew_words():
    # Phase-3 QA finding (Noble Queen ch. 621): "a euphoria" is correct English
    # (eu- = "you" sound) — the a->an rule must not flip vowel-letter words with
    # a consonant sound. eu-/ew- words are the whole class (euphoria, ewe, ...).
    src = "a euphoria when a soldier finds their stride"
    assert grammar.repair_grammar(src) == src
    assert grammar.repair_grammar("a ewe") == "a ewe"


# --- em_dash (mandatory removal) --------------------------------------------
def test_em_dash_removal():
    # lowercase next word -> comma; capitalized next word -> period (sentence break)
    assert em_dash.remove_spaced_em_dashes("ran — and fell") == "ran, and fell"
    assert em_dash.remove_spaced_em_dashes("stopped — Then ran") == "stopped. Then ran"
    # unspaced dash untouched
    assert em_dash.remove_spaced_em_dashes("rip—off") == "rip—off"


def test_em_dash_en_dash_and_nbsp_variants_all_removed():
    # The spec calls the spaced-dash sweep non-negotiable and lists en-dash and NBSP
    # combinations explicitly. None may survive into output.
    assert "–" not in em_dash.remove_spaced_em_dashes("walked – then stopped")
    assert "—" not in em_dash.remove_spaced_em_dashes("walked — then")  # NBSP
    assert "–" not in em_dash.remove_spaced_em_dashes("walked – then")  # NBSP+en


# --- slash_replace ----------------------------------------------------------
def test_slash_replace():
    # Numeric slash is the ONLY case that converts.
    assert slash_replace.replace_slashes("rank 6/7") == "rank 6 out of 7"
    assert slash_replace.replace_slashes("10/20") == "10 out of 20"
    # Every other slash is preserved verbatim.
    assert slash_replace.replace_slashes("and/or") == "and/or"
    assert slash_replace.replace_slashes("his/her") == "his/her"
    assert slash_replace.replace_slashes("yes/no") == "yes/no"
    assert slash_replace.replace_slashes("input/output") == "input/output"


# --- junk_strip -------------------------------------------------------------
def test_junk_strip_tier1_removes_markers_and_urls():
    out = junk_strip.strip_junk("text @@novelbin@@ visit https://pirate.site now")
    assert "@@novelbin@@" not in out
    assert "https://pirate.site" not in out
    assert "text" in out and "now" in out


def test_junk_strip_tier2_off_by_default_but_shields_terms():
    lex = ProtectedLexicon(terms=("Sunny",), term_set_lower=frozenset({"sunny"}))
    line = "Sunny went to read the latest chapter"
    # Tier 2 default OFF -> line kept; and it contains a protected term anyway.
    assert junk_strip.strip_junk(line, lexicon=lex) == line
