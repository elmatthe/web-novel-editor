"""TXT inputs keep their paragraphs whatever their line layout (v0.4.0 TXT paragraph fix).

A TXT chapter can arrive with blank-line paragraphs, one paragraph per line, or lines
hard-wrapped at a width. The same story must come out with the same paragraphs, the same
words in the same order and the same protected names in every case. All text here is
synthetic; real chapters stay in ignored local folders.
"""

from __future__ import annotations

import re
import textwrap

import pytest

from core.batch_runner import run_batch, serialize_txt
from core.novel_registry import NOVEL_INDEX_DIR, resolve_dispatch
from core.protected_lexicon import load_protected_lexicon
from pipelines.universal import _txt_paragraphs
from rules.spacing_cleanup import reconstruct_paragraphs

HEADING = "Chapter 7: The Northern Gate"
STORY = [
    "Clan Valor waited beside the northern gate while the wind carried ash across the empty square. Nobody spoke.",
    "Sunny watched the banners. They moved slowly in the grey light, and every thread seemed heavy with old rain.",
    "The gate remained closed.",
    '"How long do we wait?" Cassie asked.',
    '"Until the bell," he said. "Not a moment less."',
    "Valor Clan scouts returned at dusk with news from the river. The bridge had fallen, and the road beyond it was gone.",
    "He listened without a word. Then he turned away from the wall and walked toward the camp, counting each step in silence.",
    "Morning came late.",
    "The soldiers of Valor's house gathered near the fires and talked about the long march home. Some of them laughed. Most did not.",
    "A raven landed on the battlement. It tilted its head, studied the crowd below and flew off toward the hills.",
    '"Did you see that?"',
    "Nobody answered her. The bell rang once, then again, and the gate finally began to open.",
]
SECOND_HEADING = "Chapter 8: Beyond the River"
SECOND = [
    "The river was wider than the maps had promised. Its water was black and very cold.",
    "They crossed at noon.",
    "On the far bank, Clan Valor raised its banner again and the march continued in silence.",
]


def _lexicon(novel: str):
    d = resolve_dispatch(novel)
    path = str(NOVEL_INDEX_DIR / d.index_filename) if d.index_filename else ""
    return load_protected_lexicon(path, d.canonical_names)


def _run(text: str, novel: str = "Shadow Slave") -> str:
    return resolve_dispatch(novel).run_pipeline(text, _lexicon(novel), input_kind="txt")


def _paras(text: str) -> list[str]:
    return [p.strip() for p in text.replace("\f", "").split("\n\n") if p.strip()]


def _blank(paras) -> str:
    return "\n\n".join(paras)


def _per_line(paras) -> str:
    return "\n".join(paras)


def _wrap(paragraph: str, width: int) -> list[str]:
    return textwrap.wrap(paragraph, width, break_on_hyphens=False, break_long_words=False)


def _hard_wrapped(paras, width: int) -> str:
    return "\n".join(line for p in paras for line in _wrap(p, width))


def _stage(text: str) -> list[str]:
    """The TXT paragraph stage exactly as the pipeline runs it (before any editing)."""
    return _paras(reconstruct_paragraphs(_txt_paragraphs(text)))


@pytest.fixture(scope="module")
def reference() -> list[str]:
    """The corrected story from the unambiguous layout: blank-line paragraphs."""
    return _paras(_run(_blank([HEADING, *STORY])))


def _plain(text: str) -> list[str]:
    """Words with glyph-level typography undone, for word-preservation checks."""
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    return text.split()


# --- the reported failure ---------------------------------------------------------

# PDF-extracted chapter text (the real 442 input was this shape): no blank lines, lines
# wrapped at an irregular proportional-font width, short paragraphs and dialogue.
PDF_EXTRACTED_WIDTHS = (96, 118, 104, 111, 87, 115)


def _pdf_extracted(paras) -> str:
    lines = [HEADING]
    for i, p in enumerate(paras):
        lines += _wrap(p, PDF_EXTRACTED_WIDTHS[i % len(PDF_EXTRACTED_WIDTHS)])
    return "\n".join(lines)


def _ends_sentence(line: str) -> bool:
    return line.rstrip("\"'”’)]").endswith((".", "!", "?", "…", ":"))


def _expected_from_wraps(paras, width_of) -> list[str]:
    """The documented policy, restated independently of the code: every real paragraph
    end stays a break, a wrap is joined unless it falls right after a sentence and the
    next line does not start lowercase (then it is a break, as for PDF inputs)."""
    out = [HEADING]
    for i, p in enumerate(paras):
        lines = _wrap(p, width_of(i))
        current = [lines[0]]
        for line, following in zip(lines, lines[1:]):
            if _ends_sentence(line) and not following[:1].islower():
                out.append(" ".join(current))
                current = []
            current.append(following)
        out.append(" ".join(current))
    return out


def _corrected(stage_paras) -> list[str]:
    return _paras(_run(_blank(stage_paras)))


def test_chapter_442_pattern_keeps_every_paragraph():
    expected = _expected_from_wraps(STORY, lambda i: PDF_EXTRACTED_WIDTHS[i % len(PDF_EXTRACTED_WIDTHS)])
    assert _stage(_pdf_extracted(STORY)) == expected
    out = _paras(_run(_pdf_extracted(STORY)))
    assert out == _corrected(expected)
    assert len(out) >= len(STORY) + 1  # before the fix: heading + one paragraph
    assert max(len(p) for p in out) < 200  # no wall of text


def test_pdf_extracted_txt_matches_the_pdf_input_paragraph_stage():
    text = _pdf_extracted(STORY)
    assert _stage(text) == _paras(reconstruct_paragraphs(text))


# --- single layouts ---------------------------------------------------------------


def test_one_paragraph_per_line_without_blank_lines(reference):
    assert _paras(_run(_per_line([HEADING, *STORY]))) == reference


@pytest.mark.parametrize("width", [40, 48, 60, 72])
def test_hard_wrapped_text_keeps_every_paragraph_and_joins_its_wraps(width):
    text = HEADING + "\n" + _hard_wrapped(STORY, width)
    expected = _expected_from_wraps(STORY, lambda i: width)
    assert _stage(text) == expected
    assert _paras(_run(text)) == _corrected(expected)
    # Not one paragraph per line: most wraps are joined.
    assert len(expected) < len(text.splitlines()) * 0.75


def test_mid_sentence_wraps_are_always_joined():
    sentence = ("Clan Valor marched along the river while the rain kept falling on the banners, "
                "the carts and the tired horses, and nobody among them said a single word until dusk.")
    text = "\n".join(_wrap(sentence, 24))
    assert len(text.splitlines()) > 6
    assert _stage(text) == [sentence]


def test_sentence_ending_wrap_in_hard_wrapped_text_is_a_break():
    # Documented ambiguity: a wrap right after a sentence looks exactly like a paragraph
    # end. It becomes a break (as for PDF inputs); a real paragraph is never merged away.
    text = "The gate stood shut.\nCassie waited by the fire\nuntil the bell rang."
    assert _stage(text) == ["The gate stood shut.", "Cassie waited by the fire until the bell rang."]


def test_blank_line_paragraphs_are_unchanged(reference):
    assert _paras(_run(_blank([HEADING, *STORY]))) == reference
    wrapped_blocks = _blank([HEADING, *("\n".join(_wrap(p, 50)) for p in STORY)])
    assert _paras(_run(wrapped_blocks)) == reference


def test_blank_line_wrapped_blocks_keep_the_established_join():
    # A blank-line file: single newlines inside a block are line wraps (unchanged rule).
    text = "Chapter 1: Arrival\nClan Valor waited.\nThe gate remained.\n\nA fragment\ncontinued here."
    assert _stage(text) == ["Chapter 1: Arrival", "Clan Valor waited. The gate remained.", "A fragment continued here."]


# --- mixed layouts, headings, several chapters ---------------------------------------


def test_one_paragraph_per_line_with_blank_scene_breaks(reference):
    text = HEADING + "\n" + "\n".join(STORY[:5]) + "\n\n" + "\n".join(STORY[5:9]) + "\n\n" + "\n".join(STORY[9:])
    assert _paras(_run(text)) == reference


def test_blank_line_half_then_one_paragraph_per_line_half(reference):
    text = _blank([HEADING, *STORY[:6]]) + "\n\n" + _per_line(STORY[6:])
    assert _paras(_run(text)) == reference


def test_heading_without_blank_line_before_or_after():
    text = "\n".join(["Opening line before any heading.", HEADING, *STORY[:3]])
    out = _stage(text)
    assert out == ["Opening line before any heading.", HEADING, *STORY[:3]]


def test_multi_chapter_txt_without_blank_lines():
    text = _per_line([HEADING, *STORY, SECOND_HEADING, *SECOND])
    assert _stage(text) == [HEADING, *STORY, SECOND_HEADING, *SECOND]
    out = _paras(_run(text))
    assert [p for p in out if p.startswith("Chapter")] == [HEADING + ".", SECOND_HEADING + "."]
    assert len(out) == len(STORY) + len(SECOND) + 2


@pytest.mark.parametrize("layout", ["pdf-extracted", "per-line", "wrap-40", "wrap-60", "scenes", "half"])
def test_words_are_never_lost_duplicated_or_reordered(reference, layout):
    texts = {
        "pdf-extracted": _pdf_extracted(STORY),
        "per-line": _per_line([HEADING, *STORY]),
        "wrap-40": HEADING + "\n" + _hard_wrapped(STORY, 40),
        "wrap-60": HEADING + "\n" + _hard_wrapped(STORY, 60),
        "scenes": HEADING + "\n" + "\n".join(STORY[:5]) + "\n\n" + "\n".join(STORY[5:]),
        "half": _blank([HEADING, *STORY[:6]]) + "\n\n" + _per_line(STORY[6:]),
    }
    staged = _stage(texts[layout])
    assert " ".join(staged).split() == " ".join([HEADING, *STORY]).split()
    corrected = " ".join(_paras(_run(texts[layout])))
    expected = " ".join([HEADING + ".", *STORY])
    assert _plain(corrected) == _plain(expected)


# --- end to end: TXT -> PDF and TXT -> TXT, source immutability, protected names ------


@pytest.mark.parametrize("layout", ["per-line", "pdf-extracted", "wrap-60"])
def test_txt_to_pdf_and_txt_outputs_keep_paragraphs_and_names(tmp_path, monkeypatch, reference, layout):
    body = {"per-line": _per_line([HEADING, *STORY]), "pdf-extracted": _pdf_extracted(STORY),
            "wrap-60": HEADING + "\n" + _hard_wrapped(STORY, 60)}[layout]
    src = tmp_path / "Chapter 7.txt"
    src.write_bytes(body.replace("\n", "\r\n").encode("utf-8"))  # CRLF, as Notepad saves
    before = (src.read_bytes(), src.stat().st_mtime_ns)
    rendered = []
    import core.batch_runner as batch
    real_build = batch.build_pdf

    def build(text, path):
        rendered.append(text)
        real_build(text, path)

    monkeypatch.setattr(batch, "build_pdf", build)
    result = run_batch([str(src)], str(tmp_path / "out"), output_formats=("pdf", "txt"), novel_name="Shadow Slave")
    assert result["succeeded"] == 1 and result["failed"] == 0
    txt = (tmp_path / "out" / "Chapter 7.txt").read_text(encoding="utf-8")
    assert txt == serialize_txt(rendered[0])
    expected = {"per-line": reference,
                "pdf-extracted": _corrected(_expected_from_wraps(
                    STORY, lambda i: PDF_EXTRACTED_WIDTHS[i % len(PDF_EXTRACTED_WIDTHS)])),
                "wrap-60": _corrected(_expected_from_wraps(STORY, lambda i: 60))}[layout]
    assert _paras(txt) == expected == _paras(rendered[0])
    assert (tmp_path / "out" / "Chapter 7.pdf").stat().st_size > 0
    assert txt.count("Clan Valor") == 1 and txt.count("Valor Clan") == 1
    assert re.search(r"Valor['’]s house", txt)
    assert not re.search(r"Clan\s+Valor\S|\SValor Clan", txt)
    assert (src.read_bytes(), src.stat().st_mtime_ns) == before
