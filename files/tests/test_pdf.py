"""Phase 3 PDF tests: extractor, builder, and output-path helpers.

The builder test re-opens its own output with pdfplumber and inspects rendered glyphs to
confirm the reportlab-5.0 formatting (Times-Roman body, Helvetica-Bold #134252 headings,
0.5in margins, page breaks) — not just that a file exists.
"""

from __future__ import annotations

import os

import pdfplumber
import pytest

from pdf import builder, extractor
from utils import file_utils

HEADING_RGB = (0.07451, 0.258824, 0.321569)  # #134252


# --- file_utils -------------------------------------------------------------
def test_sanitize_strips_illegal_chars():
    # Illegal-on-Windows characters become underscores. (Drive/path separators like
    # ':' and '/' are stripped first by basename, which is intended.)
    assert file_utils.sanitize_output_filename('chap*1?"<>|.pdf') == "chap_1_____.pdf"
    assert file_utils.sanitize_output_filename("   ") == "untitled"


def test_unique_output_path_collision(tmp_path):
    # Phase 2 (v0.11.0): outputs keep the ORIGINAL filename — no EDITED_ prefix. The
    # numeric collision suffix (_2, _3, ...) still guards against overwriting.
    out = str(tmp_path)
    p1 = file_utils.unique_output_path(out, "Chapter 1.pdf")
    assert os.path.basename(p1) == "Chapter 1.pdf"
    open(p1, "w").close()                      # simulate an existing output
    p2 = file_utils.unique_output_path(out, "Chapter 1.pdf")
    assert os.path.basename(p2) == "Chapter 1_2.pdf"
    open(p2, "w").close()
    p3 = file_utils.unique_output_path(out, "Chapter 1.pdf")
    assert os.path.basename(p3) == "Chapter 1_3.pdf"


def test_debug_text_path_uses_debug_prefix(tmp_path):
    # The debug sidecar is DEBUG_<name>.txt (matches the GUI label + spec), keeping the
    # same directory and numeric collision suffix as its prefix-less output PDF.
    pdf = os.path.join(str(tmp_path), "Chapter 1_2.pdf")
    dbg = file_utils.debug_text_path(pdf)
    assert os.path.basename(dbg) == "DEBUG_Chapter 1_2.txt"
    assert os.path.dirname(dbg) == str(tmp_path)


def test_open_in_file_manager_is_safe_on_bad_path(tmp_path):
    # Never raises; returns False for a non-existent / non-directory path.
    assert file_utils.open_in_file_manager(str(tmp_path / "nope")) is False
    assert file_utils.open_in_file_manager("") is False


def test_open_in_file_manager_success_on_real_dir(tmp_path, monkeypatch):
    # Patch the actual OS launcher so the test never pops a real window, and confirm a
    # valid directory returns True.
    calls = []
    monkeypatch.setattr(file_utils.os, "startfile", lambda p: calls.append(p),
                        raising=False)
    monkeypatch.setattr(file_utils.subprocess, "run",
                        lambda *a, **k: calls.append(a))
    assert file_utils.open_in_file_manager(str(tmp_path)) is True
    assert calls  # the platform launcher was invoked exactly once


# --- extractor --------------------------------------------------------------
def test_is_low_confidence():
    assert extractor.is_low_confidence("") is True
    assert extractor.is_low_confidence("   short   ") is True
    assert extractor.is_low_confidence("x" * 200) is False


# --- builder ----------------------------------------------------------------
def test_builder_recognizes_comma_formatted_chapter_heading():
    assert builder._is_chapter_heading("Chapter 1,000: The End.") is True


def test_builder_recognizes_question_or_bang_terminated_heading():
    # Phase-3 QA: Stage 12 now keeps a title's own terminal ?/! (no appended
    # period), so the builder must style those headings too (Noble Queen ch. 649).
    assert builder._is_chapter_heading("Chapter 649: Did Someone Say Cats?") is True
    assert builder._is_chapter_heading("Chapter 3: Enough!") is True


def test_build_pdf_question_heading_styles_as_heading(tmp_path):
    body = ("A look passed across the room, and for a long moment nobody there "
            "was willing to be the first one to answer the question aloud.")
    out = os.path.join(str(tmp_path), "q.pdf")
    builder.build_pdf(f"Chapter 649: Did Someone Say Cats?\n\n{body}", out)
    with pdfplumber.open(out) as pdf:
        p0 = pdf.pages[0]
        head = [c for c in p0.chars
                if isinstance(c.get("non_stroking_color"), (tuple, list))
                and len(c["non_stroking_color"]) == 3
                and max(abs(a - b) for a, b in zip(c["non_stroking_color"], HEADING_RGB)) < 0.02]
        assert head, "?-terminated heading was not styled as a heading"
        assert "Helvetica" in head[0]["fontname"]
        text = p0.extract_text()
    assert "Cats?" in text
    assert "Cats?." not in text


def test_build_pdf_merged_question_heading_gains_no_period(tmp_path):
    # The merged heading+dialogue split path must not append "." after ?/!.
    # (No terminal period on the line, so it reaches the merged split — a
    # period-terminated line is consumed whole by the exact-heading match.)
    out = os.path.join(str(tmp_path), "mq.pdf")
    builder.build_pdf('Chapter 5: What Now? "Run," she said and kept moving', out)
    with pdfplumber.open(out) as pdf:
        text = pdf.pages[0].extract_text()
    assert "What Now?" in text
    assert "What Now?." not in text


def test_build_pdf_formatting(tmp_path):
    body = ("The traveller walked the ashen road as the gate dimmed behind him, and "
            "the cold wind carried the scent of old rain across the broken hills.")
    text = (
        "Chapter 1: The Nightmare Begins.\n\n"
        f"{body}\n\n{body}\n\f"
        "Chapter 2: The Second Trial.\n\n"
        f"{body}"
    )
    out = os.path.join(str(tmp_path), "out.pdf")
    builder.build_pdf(text, out)
    assert os.path.exists(out)

    with pdfplumber.open(out) as pdf:
        assert len(pdf.pages) == 2          # form-feed produced a page break
        p0 = pdf.pages[0]
        fonts = {c["fontname"] for c in p0.chars}
        assert any("Times" in f for f in fonts)        # body font
        assert any("Helvetica" in f for f in fonts)    # heading font

        # Heading glyphs are the non-black ones; confirm color + bold font.
        head = [c for c in p0.chars
                if isinstance(c.get("non_stroking_color"), (tuple, list))
                and len(c["non_stroking_color"]) == 3
                and max(abs(a - b) for a, b in zip(c["non_stroking_color"], HEADING_RGB)) < 0.02]
        assert head, "no #134252 heading glyphs found"
        assert "Helvetica" in head[0]["fontname"]

        # Left margin ~0.5in (36pt); allow small glyph-bearing slack.
        assert 30 <= min(c["x0"] for c in p0.chars) <= 45

        text0 = p0.extract_text() or ""
        text1 = pdf.pages[1].extract_text() or ""
        assert "Chapter 1: The Nightmare Begins" in text0
        assert "Chapter 2: The Second Trial" in text1


def test_build_pdf_escapes_markup(tmp_path):
    out = os.path.join(str(tmp_path), "esc.pdf")
    builder.build_pdf("A & B were <here> long enough to be a paragraph body line.", out)
    with pdfplumber.open(out) as pdf:
        txt = pdf.pages[0].extract_text() or ""
    assert "&" in txt and "<here>" in txt   # entities round-trip back to literals


def test_build_pdf_empty_is_safe(tmp_path):
    out = os.path.join(str(tmp_path), "empty.pdf")
    builder.build_pdf("", out)              # must not raise / must produce a file
    assert os.path.exists(out)


# --- Phase 6: orphan-heading prevention (keepWithNext) -----------------------
_P6_FILLER = ("The traveller walked the ashen road as the gate dimmed behind him, "
              "and the cold wind carried the scent of old rain across the broken "
              "hills while the caravan waited.")
_P6_HEADING = "Chapter 2: The Hidden Door."
_P6_BODY = ("Beyond the door the stair fell away into the dark, and she counted "
            "the steps aloud until the number stopped meaning anything at all.")


@pytest.mark.parametrize("n_filler", [17, 18, 19, 36, 37, 38])
def test_heading_never_stranded_alone_at_page_bottom(tmp_path, n_filler):
    # Phase 6 prevention: a mid-page-group heading must never be the last text
    # on a page while its body starts the next page (keepWithNext binds the
    # heading to its first body paragraph). Filler counts 18 and 37 reproduced
    # the stranding with the pre-Phase-6 builder; neighbours pin stability.
    text = "\n\n".join([_P6_FILLER] * n_filler + [_P6_HEADING, _P6_BODY])
    out = os.path.join(str(tmp_path), f"strand{n_filler}.pdf")
    builder.build_pdf(text, out)
    with pdfplumber.open(out) as pdf:
        for i, page in enumerate(pdf.pages):
            ptxt = (page.extract_text() or "").strip()
            if "The Hidden Door" in ptxt:
                stranded = (ptxt.endswith(_P6_HEADING)
                            and "counted" not in ptxt
                            and i + 1 < len(pdf.pages))
                assert not stranded, (
                    f"heading stranded alone at bottom of page {i + 1} "
                    f"with {n_filler} filler paragraphs")
        # The document must still contain both heading and body.
        all_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    assert "The Hidden Door" in all_text and "counted" in all_text


def test_single_heading_only_document_is_preserved(tmp_path):
    # Phase 6 zero-page guard: a document whose entire content is one heading
    # must build to exactly one page with the heading intact — never deleted,
    # never a zero-page PDF (a legitimate title-only chapter looks like this).
    out = os.path.join(str(tmp_path), "only.pdf")
    builder.build_pdf("Chapter 12: Silence.", out)
    with pdfplumber.open(out) as pdf:
        assert len(pdf.pages) == 1
        assert "Chapter 12: Silence" in (pdf.pages[0].extract_text() or "")


def test_multi_chapter_with_empty_body_chapter_builds_and_keeps_page(tmp_path):
    # A \f-separated chapter with no body (heading-only page group) must build
    # without error and keep its heading page (keepWithNext on a heading that
    # is followed by a PageBreak / ends the story must not break layout).
    body = _P6_FILLER
    text = (f"Chapter 1: The Long Walk.\n\n{body}\n\f"
            "Chapter 2: Missing.\n\f"
            f"Chapter 3: The Return.\n\n{body}")
    out = os.path.join(str(tmp_path), "emptybody.pdf")
    builder.build_pdf(text, out)
    with pdfplumber.open(out) as pdf:
        assert len(pdf.pages) == 3
        assert "Missing" in (pdf.pages[1].extract_text() or "")


def test_trailing_heading_only_chapter_builds(tmp_path):
    # keepWithNext on the very last flowable of the story must not raise.
    text = f"Chapter 1: The Long Walk.\n\n{_P6_FILLER}\n\fChapter 2: The End."
    out = os.path.join(str(tmp_path), "trailing.pdf")
    builder.build_pdf(text, out)
    with pdfplumber.open(out) as pdf:
        assert len(pdf.pages) == 2
        assert "The End" in (pdf.pages[1].extract_text() or "")


def test_extremely_long_heading_still_renders_lossless(tmp_path):
    # >MAX_HEADING_LENGTH heading-shaped text is body-classified (existing
    # lossless fallback) and must survive keepWithNext unchanged.
    long_title = "Chapter 9: " + ("Endless Title " * 40).strip() + "."
    assert len(long_title) > builder.MAX_HEADING_LENGTH
    out = os.path.join(str(tmp_path), "long.pdf")
    builder.build_pdf(long_title, out)
    with pdfplumber.open(out) as pdf:
        all_text = " ".join((p.extract_text() or "") for p in pdf.pages)
    assert "Endless Title" in all_text


# --- Phase 6: heading-only page detection (log-only, never deletes) ----------
def test_detect_heading_only_pages_flags_only_heading_pages(tmp_path):
    body = _P6_FILLER
    text = (f"Chapter 1: The Long Walk.\n\n{body}\n\f"
            "Chapter 2: Missing.\n\f"
            f"Chapter 3: The Return.\n\n{body}")
    out = os.path.join(str(tmp_path), "detect.pdf")
    builder.build_pdf(text, out)
    assert builder.detect_heading_only_pages(out) == [2]   # 1-based page numbers
    with pdfplumber.open(out) as pdf:                       # detection never deletes
        assert len(pdf.pages) == 3


def test_detect_heading_only_pages_clean_document_is_empty(tmp_path):
    text = f"Chapter 1: The Long Walk.\n\n{_P6_FILLER}\n\fChapter 2: Back.\n\n{_P6_BODY}"
    out = os.path.join(str(tmp_path), "clean.pdf")
    builder.build_pdf(text, out)
    assert builder.detect_heading_only_pages(out) == []


def test_detect_heading_only_pages_ignores_non_heading_single_line(tmp_path):
    # A page whose single line is NOT heading-shaped is not flagged.
    text = f"Chapter 1: The Long Walk.\n\n{_P6_FILLER}\n\fA lone closing sentence."
    out = os.path.join(str(tmp_path), "nonheading.pdf")
    builder.build_pdf(text, out)
    assert builder.detect_heading_only_pages(out) == []
