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
