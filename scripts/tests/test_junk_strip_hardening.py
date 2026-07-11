"""Phase 2 junk-strip hardening — committed regression suite.

Grounded in the Phase-1 evidence from the real Noble Queen (novelfire.net inline splice
watermarks, 17+ mangled spellings) and Supreme Magus (multi-site inline watermarks,
spaced-out domains, one NFKC-foldable homoglyph watermark, Cloudflare error-1015 pages)
corpora. Every junk fragment here is the shortest redacted real fragment that reproduces
the defect — never full chapter text (copyright guardrail). Synthetic strings are used
only for architecture-isolation / adversarial / boundary cases.

These tests run in every clone with no local corpus. The optional corpus-backed layer
lives in test_junk_strip_corpus.py.
"""

from __future__ import annotations

import pytest

from core.replacement_log import ReplacementLog
from rules import junk_strip


def strip(text: str, **kw) -> str:
    return junk_strip.strip_junk(text, **kw)


# =========================================================================
# Task 1 — domain-token matcher (exact mangled variants + structural fuzzy)
# =========================================================================

# Every distinct mangled spelling recorded in the Phase-1 Noble Queen scan.
NOVELFIRE_EXACT_VARIANTS = [
    "novelfirenet",
    "novelfire.net",
    "novelFire.net",
    "novel-fire.net",
    "n0velfire.net",
    "Nove1Fire.net",
    "NoveIFire.net",
    "NoveIire.net",
    "noelfire.net",
    "novlfire.net",
    "nvelfire.net",
    "novelire.net",
    "ovelfire.net",
    "novelFre.net",
    "NovlFre.net",
    "velFire.net",
    "ire.net",
    "Fie.net",
    "NoveI[F]ire.net",
    "NoveI(F)ire.net",
    "novel[f]ire.net",
    "novel()ire.net",
]

# Supreme Magus inline-watermark domains recorded in the Phase-1 scan.
SM_EXACT_VARIANTS = [
    "NiceNovel.com",
    "NovelWell.com",
    "NovelsToday.com",
    "Libread.com",
    "lightsnovel.com",
    "lightsNovel.com",
    "andasnovel.com",
    "raPdasNovel.com",
    "randasnovel.com",
]


@pytest.mark.parametrize("token", NOVELFIRE_EXACT_VARIANTS + SM_EXACT_VARIANTS)
def test_exact_mangled_domain_token_removed_inline(token):
    # Surrounding words are deliberately NOT template vocabulary, so this pins
    # minimum-span token removal: prose on both sides must survive verbatim.
    text = f"Kelia stuttered {token} embarrassment held her."
    out = strip(text)
    assert token not in out
    assert out == "Kelia stuttered embarrassment held her."


@pytest.mark.parametrize(
    "token",
    [
        # Synthetic near-variants NOT on the exact list: proves the fuzzy matcher
        # generalizes over future random degradation (fold + bounded edit distance).
        "novelfrie.net",     # transposition, distance 2
        "nvelfre.net",       # two dropped letters, distance 2
        "novelfirre.net",    # doubled letter, distance 1
        "pandsnovel.com",    # dropped letter, distance 1
        "lightsnvel.com",    # dropped letter, distance 1
        "n0velf1re.com",     # digit homoglyphs fold to novelfire
    ],
)
def test_fuzzy_matcher_catches_unlisted_degradations(token):
    text = f"Aldo blinked {token} at the horizon."
    out = strip(text)
    assert token not in out
    assert out == "Aldo blinked at the horizon."


@pytest.mark.parametrize(
    "domain",
    [
        # English-word stems + TLD that the FUZZY path must reject (guard set /
        # length gates). None of these spellings was observed as junk.
        "novel.com",
        "novels.com",
        "today.com",
        "well.net",
        "read.com",
        "bread.com",
        "fire.com",
        "free.net",
        "web.com",
        "campfire.net",
        # The legitimate official source site must never be treated as pirate junk.
        "webnovel.com",
        # Excluded-by-design stems (error-page / support classes, not Tier 1 domains).
        "cloudflare.com",
        "ko-fi.com",
        "paypal.me",
    ],
)
def test_legitimate_or_excluded_domains_survive(domain):
    text = f"She mentioned {domain} in passing."
    assert strip(text) == text


def test_zero_false_positives_on_legit_prose_word_list():
    # Required guard: legitimate-prose words sharing letters with the target
    # domains are untouched — bare, sentence-final, plural, and possessive forms.
    words = (
        "novel novels novelist novelty web website weber free freedom read reading "
        "reader bread breadth today well wells wellness fire firelight campfire ire "
        "irene admire empire light lights lightning panda pandas nice nicely library "
        "libretto velvet marvel gravel travel firearm net com nets fired hire wire "
        "shire spire dire mire sire novella firefly welfare farewell"
    )
    text = (
        f"{words}. The novelist read a novel today. Her ire flared well. "
        "The novelist's novels, the reader's bread, a fire. Novels. Fire. Ire."
    )
    log = ReplacementLog()
    out = strip(text, repl_log=log)
    assert out == text
    assert len(log) == 0


def test_word_boundaries_block_partial_matches():
    # Tokens embedded in longer words must not match.
    text = "The fire.network hummed; novelfirenets was her nickname."
    assert strip(text) == text


def test_domain_removals_are_logged():
    log = ReplacementLog()
    strip("Aldo blinked noelfire.net at the horizon.", repl_log=log)
    assert len(log) == 1
    entry = log.entries[0]
    assert "noelfire.net" in entry.original
    assert entry.rule.startswith("junk_strip.")
    assert entry.category == "fingerprint"


# =========================================================================
# Task 2 — inline template+domain splice removal (minimum-span, leftward
# template expansion anchored on a confirmed domain token)
# =========================================================================

# (junk_line, expected_cleaned_line) — every shape observed in the Phase-1
# Noble Queen / Supreme Magus scans, as the shortest redacted real fragment.
SPLICE_CASES = [
    # template after prose, space-separated, domain at line end
    (
        "Her blonde companion nodded. Check latest chapters at novelfirenet",
        "Her blonde companion nodded.",
    ),
    (
        '"I\'ll help her," Noble smiled at Helie. Google search novelfirenet',
        '"I\'ll help her," Noble smiled at Helie.',
    ),
    (
        "flinch. Newest update provded by novelfirenet",
        "flinch.",
    ),
    (
        "Roan tapped his chin. Updates are released by novelfirenet",
        "Roan tapped his chin.",
    ),
    (
        "And fell right into her trap. Read full story at novelfirenet",
        "And fell right into her trap.",
    ),
    (
        "head, ready to make the sacrifice. For more chapters vist novelfirenet",
        "head, ready to make the sacrifice.",
    ),
    (
        "Seb turned to look at Noble-the real Noble. For more chapters vist novelfirenet",
        "Seb turned to look at Noble-the real Noble.",
    ),
    (
        "The palace's throne room. Fnd the newest release on novelfirenet",
        "The palace's throne room.",
    ),
    (
        "without her big brother. New chapters are published on novelfirenet",
        "without her big brother.",
    ),
    (
        "energy and taking to the sky. Nw ovel chaptrs are published on novelfirenet",
        "energy and taking to the sky.",
    ),
    (
        "Noble bit her lip. Get full chapters from ovelfire.net",
        "Noble bit her lip.",
    ),
    (
        "them fairies, but hostages. Dscover more novels at NoveIFire.net",
        "them fairies, but hostages.",
    ),
    (
        "swayed. This update s available on novlfire.net",
        "swayed.",
    ),
    (
        '"Mercy! Mercy!" The third man cried. Official source s novelfire.net',
        '"Mercy! Mercy!" The third man cried.',
    ),
    (
        "her forehead absentmindedly. Newest update provded by novelfire.net",
        "her forehead absentmindedly.",
    ),
    (
        "They looked at Mae. Nw ovel chaptrs are published on n0velfire.net",
        "They looked at Mae.",
    ),
    (
        "best use of their time. Follow current s on Nove1Fire.net",
        "best use of their time.",
    ),
    # degraded letter-skeleton templates, still anchored on the domain token
    (
        'see you in the morning." crs r s novelfirenet',
        'see you in the morning."',
    ),
    (
        "days or weeks was happening before their eyes in seconds. crs r s novelfire.net",
        "days or weeks was happening before their eyes in seconds.",
    ),
    (
        '"Outrageousthat was outrageous." Flint crossed his arms. crs r s NoveIire.net',
        '"Outrageousthat was outrageous." Flint crossed his arms.',
    ),
    (
        "opening.r s crs novelfirenet",
        "opening.",
    ),
    (
        '"About you, Flint? Whynothing that I recall." r novelfirenet',
        '"About you, Flint? Whynothing that I recall."',
    ),
    (
        "which would color her perception of the glass's power.\"s cr s novelire.net",
        "which would color her perception of the glass's power.\"",
    ),
    # template glued directly onto prose (no space after sentence punctuation)
    (
        "simply moved locations, but to where?The most update n0vels are published on novelfirenet",
        "simply moved locations, but to where?",
    ),
    (
        'back to camp."Read full story at novelfirenet',
        'back to camp."',
    ),
    (
        "work, won't it?\"Googl search novelfirenet",
        "work, won't it?\"",
    ),
    (
        'You nearly lost your life."For orignal chapters go to novelfirenet',
        'You nearly lost your life."',
    ),
    (
        'not to be entertained, but to be amazed!"Th link to the orign of this information rsts n novelfirenet',
        'not to be entertained, but to be amazed!"',
    ),
    (
        '"Cover me!" Noble told Helie. "I\'m going down."Fnd the newest release on novelfirenet',
        '"Cover me!" Noble told Helie. "I\'m going down."',
    ),
    (
        'please hold this right here?"Ths chapter is updated by novelfire.net',
        'please hold this right here?"',
    ),
    (
        "'The saying is The lady doth protest too much, methinks.'his chapter is pdated by novelfire.net",
        "'The saying is The lady doth protest too much, methinks.'",
    ),
    (
        "If only Flint hadn't died for them to make the discovery!Follow current novls on novel-fire.net",
        "If only Flint hadn't died for them to make the discovery!",
    ),
    (
        '"You have said more than enough, Titus. Speak no more."The rghtful source is novelFire.net',
        '"You have said more than enough, Titus. Speak no more."',
    ),
    # two-token mangled domain: digit-mangled vocab word carries its own period
    (
        "fortress. The rghtful source is N0v3l. Fie.net",
        "fortress.",
    ),
    (
        "term that she had heard. Googl search novel()ire.net",
        "term that she had heard.",
    ),
    (
        "how to deal with the aftermath.'Google search nvelfire.net",
        "how to deal with the aftermath.'",
    ),
    # Supreme Magus: domain at line START with legitimate prose following
    (
        'andasnovel.com "I don\'t even know how to turn this thing on." Friya pointed at the circle.',
        '"I don\'t even know how to turn this thing on." Friya pointed at the circle.',
    ),
    (
        'raPdasNovel.com "Fine. I forgive you only because at least this time" She said.',
        '"Fine. I forgive you only because at least this time" She said.',
    ),
    # Supreme Magus: template+domain with trailing sentence period — consumed
    (
        '"That said, where\'s your amulet?" Follow current novels on Libread.com.',
        '"That said, where\'s your amulet?"',
    ),
    (
        "droves and then have the corpses join his ever-growing army. NiceNovel.com",
        "droves and then have the corpses join his ever-growing army.",
    ),
    (
        "meeting his equal had shown Morok how annoying he was. NovelWell.com",
        "meeting his equal had shown Morok how annoying he was.",
    ),
    (
        "Then, she left before they could reply. All nnnnn full.com",
        "Then, she left before they could reply.",
    ),
    (
        "heart had lessened. All nnnnn full.com",
        "heart had lessened.",
    ),
    (
        "'Did… you hear that?' Kelia stuttered lightsNovel ?om even in her mind.",
        "'Did… you hear that?' Kelia stuttered even in her mind.",
    ),
]


@pytest.mark.parametrize("junk_line,expected", SPLICE_CASES)
def test_inline_splice_removed_minimum_span(junk_line, expected):
    assert strip(junk_line) == expected


def test_domain_alone_on_line_drops_line_without_fusing_paragraph_stream():
    # The watermark was injected mid-paragraph in the wrapped single-\n stream,
    # so dropping the emptied line rejoins the stream (documented convention).
    text = "and the mirror shattered\nnovelfirenet\ninto a thousand pieces."
    assert strip(text) == "and the mirror shattered\ninto a thousand pieces."


def test_template_and_domain_alone_on_line_drops_line():
    text = "first prose line\ncomes from novelfirenet\nlast prose line"
    assert strip(text) == "first prose line\nlast prose line"


def test_short_template_fragment_line_drops_line():
    text = "held the door\nrelease on novelfire.net\nfor the queen"
    assert strip(text) == "held the door\nfor the queen"


def test_template_words_alone_without_domain_anchor_are_never_removed():
    # The expansion is anchored on a confirmed domain token; template-vocabulary
    # words in ordinary prose must never be touched on their own.
    text = "Check the latest chapters for more story updates published this morning."
    assert strip(text) == text


def test_non_vocab_prose_word_stops_leftward_expansion():
    # "lantern" is not template vocabulary: expansion must stop there even though
    # "on" is vocabulary, preserving the prose words.
    out = strip("She hung the lantern on novelfirenet")
    assert out == "She hung the lantern"


def test_plain_word_with_sentence_punctuation_stops_expansion():
    # A plain (unmangled) vocabulary word carrying sentence punctuation belongs
    # to the preceding real sentence — it must survive ("read." stays).
    out = strip("She loved to read. Google search novelfirenet")
    assert out == "She loved to read."


# =========================================================================
# Task 3 — spaced-out domains ("f r e e w e b n o v e l. c o m")
# =========================================================================


def test_spaced_freewebnovel_with_template_removed():
    line = (
        '"Thanks, Trion." Lith said. The source of this content is '
        "f r e e w e b n o v e l. c o m"
    )
    assert strip(line) == '"Thanks, Trion." Lith said.'


def test_spaced_freewebnovel_bracketed_line_dropped():
    text = "prose before\n[Updated from F r e e w e b n o v e l. c o m]\nprose after"
    assert strip(text) == "prose before\nprose after"


def test_spaced_freewebnovel_spaced_brackets_line_dropped():
    text = (
        "prose before\n"
        "This chapter is updated by [ f r e e w e b n o v e l. c o m ]\n"
        "prose after"
    )
    assert strip(text) == "prose before\nprose after"


def test_spaced_panda_promo_with_trailing_prose_keeps_prose():
    line = (
        "Want to see more chapters? Please visit p a n d a -n o v e l .c o m "
        "His fury was almost tangible"
    )
    assert strip(line) == "His fury was almost tangible"


def test_spaced_panda_promo_alone_drops_line():
    text = "held on\nWant to see more chapters? Please visit p a n d a -n o v e l .c o m\nlet go"
    assert strip(text) == "held on\nlet go"


def test_preexisting_blank_lines_are_preserved():
    # Only a line that a junk removal itself emptied may be dropped; blank
    # lines already present in the input (paragraph breaks) must survive.
    text = "paragraph one.\n\nparagraph two."
    assert strip(text) == text


def test_spaced_letters_of_ordinary_words_survive():
    # Spelling out ordinary words with spaces (stylistic emphasis) is not junk.
    text = "He spelled it out: n o v e l. Then he grinned. F r e e, she said."
    assert strip(text) == text
