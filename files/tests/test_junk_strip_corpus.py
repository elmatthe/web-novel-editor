"""Optional local-corpus integration layer for the Phase-2 junk-strip hardening.

These tests run against the REAL gitignored corpora under
`files/pdf-example-chapters/` — they are clearly marked `local_corpus`, resolve
their corpus paths at test time (never hardcoded to exist), skip with an
explicit visible reason when a corpus is absent, and become mandatory
(fail loudly instead of skipping) under `pytest --require-local-corpora`.

Corpus resolution (Phase 01A): the original `-v2` directories are tried first, then
the current re-scrapes (`the-noble-queen-1`, `supreme-magus-1`, `shadow-slave-1`).
For a current directory the sample comes from `corpus_pins.json` and every file's
SHA-256 is verified before use (see `corpus_pins.py`), so the 8 tests that used to skip
now run against verified fixtures rather than a silently different corpus.

Coverage is a deterministic bounded sample per the Phase-1 §8 sampling rule:
every file the Phase-1 scan recorded as carrying a junk marker, plus the
first/middle/last file of each corpus by sorted filename. All work is
in-memory; nothing is ever written into a corpus folder.
"""

from __future__ import annotations

import os
from difflib import SequenceMatcher

import pytest

from pdf import extractor
from rules import junk_strip

from . import corpus_pins


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CORPUS_ROOT = os.path.join(_REPO_ROOT, "files", "pdf-example-chapters")


def _resolve_corpus(name: str):
    """Path of a corpus folder (legacy name first, then the current re-scrape), else None."""
    path = corpus_pins.resolve(name)
    return str(path) if path is not None else None


def _gate(path, strict: bool, name: str):
    """Skip (normal mode) or fail loudly (strict mode) when a corpus is absent."""
    if path is None:
        msg = f"local corpus '{name}' not present under files/pdf-example-chapters/"
        if strict:
            pytest.fail(f"--require-local-corpora given but {msg}", pytrace=False)
        pytest.skip(msg)
    return path


def require_corpus(request, name: str):
    return _gate(
        _resolve_corpus(name),
        request.config.getoption("--require-local-corpora"),
        name,
    )


# --- The gate mechanism itself, proven both ways (runs everywhere) -----------


def test_gate_skips_with_explicit_reason_when_corpus_absent_normal_mode():
    with pytest.raises(pytest.skip.Exception) as excinfo:
        _gate(None, strict=False, name="no-such-corpus")
    assert "no-such-corpus" in str(excinfo.value)
    assert "not present" in str(excinfo.value)


def test_gate_fails_loudly_when_corpus_absent_strict_mode():
    with pytest.raises(pytest.fail.Exception) as excinfo:
        _gate(None, strict=True, name="no-such-corpus")
    assert "--require-local-corpora" in str(excinfo.value)


def test_gate_passes_through_when_corpus_present(tmp_path):
    assert _gate(str(tmp_path), strict=True, name="x") == str(tmp_path)


# --- Deterministic sample: files the Phase-1 scan recorded as junk-carrying --

NQ = "The_Noble_Queen-v2"
SM = "Supreme_Magus-v2"

NQ_KNOWN_DIRTY = [
    "Chapter 611 - Chapter 611_ Aurelia.pdf",
    "Chapter 612 - Chapter 612_ Capitol Recap.pdf",
    "Chapter 613 - Chapter 613_ Strategy Meeting.pdf",
    "Chapter 614 - Chapter 614_ Broken Relic.pdf",
    "Chapter 615 - Chapter 615_ Spark.pdf",
    "Chapter 619 - Chapter 619_ Five vs One.pdf",
    "Chapter 621 - Chapter 621_ Lioness.pdf",
    "Chapter 624 - Chapter 624_ Dull Moment.pdf",
    "Chapter 626 - Chapter 626_ Stay that Way.pdf",
    "Chapter 628 - Chapter 628_ Starlight_ Star Bright.pdf",
    "Chapter 629 - Chapter 629_ Sealed In.pdf",
    "Chapter 630 - Chapter 630_ Maze of Mirrors.pdf",
    "Chapter 634 - Chapter 634_ Upside Down.pdf",
    "Chapter 638 - Chapter 638_ Unlucky Thirteen.pdf",
    "Chapter 640 - Chapter 640_ No_ I Don_t Speak Bear.pdf",
    "Chapter 642 - Chapter 642_ Both.pdf",
    "Chapter 644 - Chapter 644_ Apologies.pdf",
    "Chapter 649 - Chapter 649_ Did Someone Say Cats_.pdf",
    "Chapter 650 - Chapter 650_ A Tale of Skill and Savagery.pdf",
    "Chapter 653 - Chapter 653_ Water Cooler Talk.pdf",
    "Chapter 657 - Chapter 657_ Unexpected Arrival.pdf",
    "Chapter 658 - Chapter 658_ Careless Words.pdf",
    "Chapter 660 - Chapter 660_ If You Don_t Have Anything Nice to Say.pdf",
    "Chapter 662 - Chapter 662_ Advisor.pdf",
    "Chapter 668 - Chapter 668_ Big Trouble.pdf",
    "Chapter 669 - Chapter 669_ Four vs One.pdf",
    "Chapter 673 - Chapter 673_ Never Gonna Give You Up.pdf",
    "Chapter 677 - Chapter 677_ Polite Dinner Conversation.pdf",
    "Chapter 678 - Chapter 678_ Don_t Cry Over Spilt Wine.pdf",
    "Chapter 680 - Chapter 680_ Vision of the Past.pdf",
    "Chapter 683 - Chapter 683_ Three Sisters.pdf",
    "Chapter 684 - Chapter 684_ Big Problem.pdf",
]

SM_KNOWN_DIRTY = [
    "Chapter 1163_ Puppeteer Abominations Part 1.pdf",
    "Chapter 1182_ Inner Demons Part 2.pdf",
    "Chapter 1184_ Magic and Superstition Part 2.pdf",
    "Chapter 1291_ The Three Branches of Magic (Part 1).pdf",
    "Chapter 1853_ Water to a Fish (Part 1).pdf",
    "Chapter 1854_ Water to a Fish (Part 2).pdf",
    "Chapter 1858_ Empty Shell (Part 2).pdf",
    "Chapter 1861_ Broken Mind (Part 1).pdf",
    "Chapter 1950_ Stepping into the Light (Part 2).pdf",
    "Chapter 1957_ The Die is Cast (Part 1).pdf",
    "Chapter 1958_ The Die is Cast (Part 2).pdf",
    "Chapter 1959_ Blight Flames (Part 1).pdf",
    "Chapter 1960_ Blight Flames (Part 2).pdf",
    "Chapter 2133_ Honored Guest (Part 1).pdf",
    "Chapter 2151_ Big Guns (Part 1).pdf",
    "Chapter 2562_ Counter Offer (Part 2).pdf",
    "Chapter 2563_ Poisoned Chalices (Part 1).pdf",
    "Chapter 2567_ Blood Bonds (Part 1).pdf",
    "Chapter 2568_ Blood Bonds (Part 2).pdf",
    "Chapter 2635_ Tipping The Scales (Part 1).pdf",
    "Chapter 2637_ Thorny Ways (Part 1).pdf",
    "Chapter 2638_ Thorny Ways (Part 2).pdf",
    "Chapter 2639_ Pulling The Leash (Part 1).pdf",
    "Chapter 2827_ Two Minds (Part 1).pdf",
    "Chapter 2828_ Two Minds (Part 2).pdf",
    "Chapter 2829_ More than Flesh (Part 1).pdf",
    "Chapter 2830_ More than Flesh (Part 2).pdf",
]

# The whole-file Cloudflare error-1015 pages (detect-and-flag class).
SM_ERROR_PAGES = [
    "Chapter 1423_.pdf",
    "Chapter 1424_.pdf",
    "Chapter 1427_.pdf",
]


def _sample_files(corpus_path: str, known_dirty: list[str]) -> list[str]:
    """Deterministic sample: recorded dirty files + first/middle/last by name.

    A current (re-scrape) directory uses the hash-verified pins instead of the legacy
    recorded list, which names files that only existed in the old `-v2` corpora.
    """
    if corpus_pins.is_pinned(corpus_path):
        return sorted(corpus_pins.pinned_entries(
            corpus_path, "sample", "dirty", "modified"))
    all_pdfs = sorted(f for f in os.listdir(corpus_path) if f.lower().endswith(".pdf"))
    picks = {all_pdfs[0], all_pdfs[len(all_pdfs) // 2], all_pdfs[-1]}
    missing = [f for f in known_dirty if not os.path.isfile(os.path.join(corpus_path, f))]
    assert not missing, (
        f"corpus at {corpus_path} does not match the Phase-1 scan record; "
        f"missing recorded dirty files: {missing[:5]}"
    )
    picks.update(known_dirty)
    return sorted(picks)


def _residual_junk_lines(text: str) -> list[str]:
    """Lines of cleaned output that still contain a detectable junk domain."""
    residual = []
    for line in text.split("\n"):
        m, _rule = junk_strip._find_junk_match(line)
        if m is not None:
            residual.append(line[:120])
    return residual


# The pinned Noble Queen re-scrape has no remaining domain markers. Supplement (never
# replace) its real sample with a labelled synthetic positive so removal is non-vacuous.
_CONFIRMED_JUNK_FIXTURE = "A * note and # sigil.\nnovelfire.net\nThe road continued."


def test_synthetic_junk_fixture_has_a_confirmed_marker_and_preserves_prose():
    assert _residual_junk_lines(_CONFIRMED_JUNK_FIXTURE)
    cleaned = junk_strip.strip_junk(_CONFIRMED_JUNK_FIXTURE)
    assert not _residual_junk_lines(cleaned)
    assert cleaned == "A * note and # sigil.\nThe road continued."


@pytest.mark.local_corpus
@pytest.mark.parametrize(
    "corpus,known_dirty",
    [(NQ, NQ_KNOWN_DIRTY), (SM, SM_KNOWN_DIRTY)],
    ids=[NQ, SM],
)
def test_no_confirmed_marker_survives_strip_junk(request, corpus, known_dirty):
    path = require_corpus(request, corpus)
    sample = _sample_files(path, known_dirty)
    inputs = [(name, extractor.extract_text_from_pdf(os.path.join(path, name))) for name in sample]
    if corpus == NQ and corpus_pins.is_pinned(path):
        inputs.append(("synthetic-confirmed-domain", _CONFIRMED_JUNK_FIXTURE))
    processed, dirty_before, residuals = 0, 0, []
    synthetic_dirty = 0
    for name, raw in inputs:
        if junk_strip.detect_error_page(raw):
            continue  # error pages are the flag class, covered separately
        cleaned = junk_strip.strip_junk(raw)
        processed += 1
        if _residual_junk_lines(raw):
            dirty_before += 1
            synthetic_dirty += int(name == "synthetic-confirmed-domain")
        leftover = _residual_junk_lines(cleaned)
        if leftover:
            residuals.append((name, leftover[:2]))
    print(
        f"\n[{corpus}] sampled={len(sample)} processed={processed} "
        f"confirmed-corpus={dirty_before - synthetic_dirty} "
        f"confirmed-synthetic={synthetic_dirty} residual-after-clean={len(residuals)}"
    )
    assert processed > synthetic_dirty, "corpus sample unexpectedly empty"
    assert dirty_before, "sample must contain a confirmed junk marker before stripping"
    assert not residuals, f"junk survived strip_junk: {residuals[:5]}"


@pytest.mark.local_corpus
def test_error_page_files_are_flagged_and_never_stripped_empty(request):
    path = require_corpus(request, SM)
    error_pages = (
        sorted(corpus_pins.pinned_entries(path, "error_page"))
        if corpus_pins.is_pinned(path) else SM_ERROR_PAGES
    )
    found = 0
    for name in error_pages:
        full = os.path.join(path, name)
        if not os.path.isfile(full):
            continue
        raw = extractor.extract_text_from_pdf(full)
        assert junk_strip.detect_error_page(raw) is not None, name
        cleaned = junk_strip.strip_junk(raw)
        # detect-and-flag only: content is not auto-stripped to nothing
        assert "Cloudflare Ray ID" in cleaned, name
        found += 1
    print(f"\n[{SM}] error pages verified: {found}/{len(error_pages)}")
    assert found, "no recorded error-page files found in the corpus"


def _is_watermark_line(line: str) -> bool:
    # Exact standalone templates observed in the hash-pinned Supreme Magus fixtures.
    # A domain match or a mention in prose does not establish a removable whole line.
    return line.strip() in {
        "*** This chapter is updated by FreeWebnovel.Com",
        "*** Enjoy exclusive adventures from freewebnovel",
    }


def _unexplained_loss(raw: str, cleaned: str, char: str) -> int:
    """Count unexplained punctuation changes in aligned line ranges.

    A DELETE range can exempt an exact standalone watermark. A one-to-one line edit
    can exempt its complete decorative prefix only when the entire remainder is
    unchanged. Sequence alignment retains duplicate occurrences; each aligned line
    is checked separately so other edits cannot spend a watermark's punctuation.
    """
    before, after = raw.splitlines(), cleaned.splitlines()
    unexplained = 0
    for tag, i, j, k, end in SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        removed, inserted = before[i:j], after[k:end]
        if tag == "replace" and len(removed) == len(inserted):
            for old, new in zip(removed, inserted):
                if _is_watermark_line(old) and new == old.removeprefix("*** "):
                    continue  # exactly the whole decorative watermark prefix was removed
                unexplained += abs(old.count(char) - new.count(char))
            continue
        explained = (
            sum(line.count(char) for line in removed if _is_watermark_line(line))
            if tag == "delete" else 0
        )
        unexplained += abs(
            sum(line.count(char) for line in removed)
            - sum(line.count(char) for line in inserted) - explained
        )
    return unexplained


_WATERMARK = "*** This chapter is updated by FreeWebnovel.Com"


@pytest.mark.parametrize(
    "raw,broken",
    [
        (_WATERMARK, _WATERMARK.replace("***", "**")),
        ('He said, "On freewebnovel, # means rank and * means note."',
         'He said, "On freewebnovel,  means rank and  means note."'),
        ("freewebnovel #\nThe # sigil remained.",
         "freewebnovel # \nThe  sigil remained."),
        (_WATERMARK + "\nThe * sigil remained.", "The  sigil remained."),
        ("A * note.\nA * note.", "A * note."),
        (_WATERMARK + "\n" + _WATERMARK + "\nA * note.",
         _WATERMARK + "\nA  note."),
    ],
    ids=["partial-watermark", "legitimate-site-mention", "loss-elsewhere",
         "removed-watermark-and-prose-loss", "duplicate-prose", "duplicate-watermark-and-loss"],
)
def test_punctuation_check_rejects_unexplained_deletions(raw, broken):
    assert any(_unexplained_loss(raw, broken, char) > 0 for char in "*#")


@pytest.mark.parametrize("copies", [1, 2, 3])
def test_punctuation_check_counts_completely_removed_duplicate_watermarks(copies):
    raw = "\n".join([_WATERMARK] * copies + ["A * note and # sigil."])
    cleaned = "\n".join([_WATERMARK] * (copies - 1) + ["A * note and # sigil."])
    assert all(_unexplained_loss(raw, cleaned, char) == 0 for char in "*#")


def test_punctuation_check_accepts_only_the_complete_decorative_watermark_span():
    watermark = "*** Enjoy exclusive adventures from freewebnovel"
    raw = watermark + "\nA * note and # sigil."
    cleaned = watermark.removeprefix("*** ") + "\nA * note and # sigil."
    assert junk_strip.strip_junk(raw) == cleaned
    assert all(_unexplained_loss(raw, cleaned, char) == 0 for char in "*#")
    assert _unexplained_loss(raw, cleaned.replace("A * note", "A  note"), "*") == 1


@pytest.mark.local_corpus
@pytest.mark.parametrize(
    "corpus,known_dirty",
    [(NQ, NQ_KNOWN_DIRTY), (SM, SM_KNOWN_DIRTY)],
    ids=[NQ, SM],
)
def test_corpus_asterisks_and_hashes_survive_strip_junk(request, corpus, known_dirty):
    # Phase-4 TTS sweep: the corpora carry ~810 legitimate asterisks (censored
    # profanity / authored emphasis / footnote markers) plus authored raw `#`
    # (Rule #1, #TeamLith). The Plan-1 Phase-5 decorative-run rule must leave
    # every one untouched — only `*`/`#` are compared because the domain pass
    # legitimately removes `~`/`-` inside junk like novel~fire~net.
    path = require_corpus(request, corpus)
    sample = _sample_files(path, known_dirty)
    checked = 0
    for name in sample:
        raw = extractor.extract_text_from_pdf(os.path.join(path, name))
        if junk_strip.detect_error_page(raw):
            continue
        cleaned = junk_strip.strip_junk(raw)
        assert _unexplained_loss(raw, cleaned, "*") == 0, name
        assert _unexplained_loss(raw, cleaned, "#") == 0, name
        checked += 1
    print(f"\n[{corpus}] asterisk/hash preservation verified on {checked} files")
    assert checked, "sample unexpectedly empty"


@pytest.mark.local_corpus
def test_clean_shadow_slave_sample_is_untouched(request):
    # The SS corpus is confirmed clean: strip_junk must be a byte no-op on it.
    path = require_corpus(request, "webscraped_shadow_slave")
    if corpus_pins.is_pinned(path):
        sample = sorted(corpus_pins.pinned_entries(path, "sample"))
    else:
        all_pdfs = sorted(f for f in os.listdir(path) if f.lower().endswith(".pdf"))
        sample = [all_pdfs[0], all_pdfs[len(all_pdfs) // 2], all_pdfs[-1]]
    for name in sample:
        raw = extractor.extract_text_from_pdf(os.path.join(path, name))
        assert junk_strip.strip_junk(raw) == raw, f"clean SS chapter altered: {name}"
    print(f"\n[webscraped_shadow_slave] clean no-op verified on: {sample}")
