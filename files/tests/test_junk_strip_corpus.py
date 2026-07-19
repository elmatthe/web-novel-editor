"""Optional local-corpus integration layer for the Phase-2 junk-strip hardening.

These tests run against the REAL gitignored corpora under
`files/pdf-example-chapters/` — they are clearly marked `local_corpus`, resolve
their corpus paths at test time (never hardcoded to exist), skip with an
explicit visible reason when a corpus is absent, and become mandatory
(fail loudly instead of skipping) under `pytest --require-local-corpora`.

Coverage is a deterministic bounded sample per the Phase-1 §8 sampling rule:
every file the Phase-1 scan recorded as carrying a junk marker, plus the
first/middle/last file of each corpus by sorted filename. All work is
in-memory; nothing is ever written into a corpus folder.
"""

from __future__ import annotations

import os

import pytest

from pdf import extractor
from rules import junk_strip


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CORPUS_ROOT = os.path.join(_REPO_ROOT, "files", "pdf-example-chapters")


def _resolve_corpus(name: str):
    """Path of a corpus folder if it exists locally with PDFs inside, else None."""
    path = os.path.join(_CORPUS_ROOT, name)
    if os.path.isdir(path) and any(f.lower().endswith(".pdf") for f in os.listdir(path)):
        return path
    return None


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
    """Deterministic sample: recorded dirty files + first/middle/last by name."""
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


@pytest.mark.local_corpus
@pytest.mark.parametrize(
    "corpus,known_dirty",
    [(NQ, NQ_KNOWN_DIRTY), (SM, SM_KNOWN_DIRTY)],
    ids=[NQ, SM],
)
def test_no_confirmed_marker_survives_strip_junk(request, corpus, known_dirty):
    path = require_corpus(request, corpus)
    sample = _sample_files(path, known_dirty)
    processed, dirty_before, residuals = 0, 0, []
    for name in sample:
        raw = extractor.extract_text_from_pdf(os.path.join(path, name))
        if junk_strip.detect_error_page(raw):
            continue  # error pages are the flag class, covered separately
        cleaned = junk_strip.strip_junk(raw)
        processed += 1
        if _residual_junk_lines(raw):
            dirty_before += 1
        leftover = _residual_junk_lines(cleaned)
        if leftover:
            residuals.append((name, leftover[:2]))
    print(
        f"\n[{corpus}] sampled={len(sample)} processed={processed} "
        f"dirty-before-clean={dirty_before} residual-after-clean={len(residuals)}"
    )
    assert processed, "sample unexpectedly empty"
    assert dirty_before, "sample should contain recorded dirty files"
    assert not residuals, f"junk survived strip_junk: {residuals[:5]}"


@pytest.mark.local_corpus
def test_error_page_files_are_flagged_and_never_stripped_empty(request):
    path = require_corpus(request, SM)
    found = 0
    for name in SM_ERROR_PAGES:
        full = os.path.join(path, name)
        if not os.path.isfile(full):
            continue
        raw = extractor.extract_text_from_pdf(full)
        assert junk_strip.detect_error_page(raw) is not None, name
        cleaned = junk_strip.strip_junk(raw)
        # detect-and-flag only: content is not auto-stripped to nothing
        assert "Cloudflare Ray ID" in cleaned, name
        found += 1
    print(f"\n[{SM}] error pages verified: {found}/{len(SM_ERROR_PAGES)}")
    assert found, "no recorded error-page files found in the corpus"


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
        assert cleaned.count("*") == raw.count("*"), name
        assert cleaned.count("#") == raw.count("#"), name
        checked += 1
    print(f"\n[{corpus}] asterisk/hash preservation verified on {checked} files")
    assert checked, "sample unexpectedly empty"


@pytest.mark.local_corpus
def test_clean_shadow_slave_sample_is_untouched(request):
    # The SS corpus is confirmed clean: strip_junk must be a byte no-op on it.
    path = require_corpus(request, "webscraped_shadow_slave")
    all_pdfs = sorted(f for f in os.listdir(path) if f.lower().endswith(".pdf"))
    sample = [all_pdfs[0], all_pdfs[len(all_pdfs) // 2], all_pdfs[-1]]
    for name in sample:
        raw = extractor.extract_text_from_pdf(os.path.join(path, name))
        assert junk_strip.strip_junk(raw) == raw, f"clean SS chapter altered: {name}"
    print(f"\n[webscraped_shadow_slave] clean no-op verified on: {sample}")
