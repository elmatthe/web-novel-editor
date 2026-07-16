"""Phase 3 batch round-trip tests against the REAL committed fixtures.

Runs several Shadow Slave chapter PDFs through extract -> rebuild (no rules yet) and
confirms: outputs are generated and correctly named, land in the chosen folder, the
originals are byte-for-byte untouched, and the chapter text survives the round-trip.
Skips cleanly if the fixtures are not present.
"""

from __future__ import annotations

import hashlib
import os

import pdfplumber
import pytest

from core.batch_runner import run_batch

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FIXTURES = os.path.join(_REPO_ROOT, "files", "test-files", "shadow_slave")


def _fixture_pdfs(limit=3):
    if not os.path.isdir(_FIXTURES):
        return []
    pdfs = sorted(
        os.path.join(_FIXTURES, f)
        for f in os.listdir(_FIXTURES) if f.lower().endswith(".pdf")
    )
    return pdfs[:limit]


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def test_batch_round_trip(tmp_path):
    pdfs = _fixture_pdfs(3)
    if not pdfs:
        pytest.skip("fixtures not present (files/test-files/shadow_slave)")

    before = {p: (_sha(p), os.path.getmtime(p)) for p in pdfs}
    out_dir = str(tmp_path / "out")

    logs = []
    progress = []
    summary = run_batch(
        pdfs, out_dir,
        novel_name="Shadow Slave",  # explicit: exercise the real SS pipeline (default is universal-only)
        gui_log=lambda m, level="info": logs.append((level, m)),
        progress=progress.append,
    )

    # Every file processed; none failed.
    assert summary["total"] == len(pdfs)
    assert summary["failed"] == 0
    assert summary["succeeded"] + summary["skipped"] == len(pdfs)
    assert summary["succeeded"] >= 1
    assert progress == list(range(1, len(pdfs) + 1))

    # Outputs exist, are named EDITED_*, and live in the chosen folder.
    for out in summary["outputs"]:
        assert os.path.isfile(out)
        assert os.path.basename(out).startswith("EDITED_")
        assert os.path.dirname(out) == out_dir

    # Originals untouched (hash + mtime unchanged).
    for p in pdfs:
        assert _sha(p) == before[p][0], f"original modified: {p}"
        assert os.path.getmtime(p) == before[p][1]

    # Text survives the round-trip: a chunk of the source appears in the output.
    src0 = pdfs[0]
    matching_out = summary["outputs"][0]
    with pdfplumber.open(src0) as pdf:
        src_text = "\n".join((pg.extract_text(x_tolerance=5, y_tolerance=3) or "")
                             for pg in pdf.pages)
    with pdfplumber.open(matching_out) as pdf:
        out_text = "\n".join((pg.extract_text() or "") for pg in pdf.pages)

    # Compare on alphanumerics only (layout/justification reflow whitespace).
    def alnum(s):
        return "".join(ch for ch in s.lower() if ch.isalnum())

    src_a, out_a = alnum(src_text), alnum(out_text)
    assert len(out_a) >= 0.9 * len(src_a), "round-trip lost too much text"
    # A solid contiguous slice from the middle of the source survives.
    probe = src_a[len(src_a) // 3: len(src_a) // 3 + 100]
    assert probe and probe in out_a


def test_batch_collision_suffix(tmp_path):
    pdfs = _fixture_pdfs(1)
    if not pdfs:
        pytest.skip("fixtures not present")
    out_dir = str(tmp_path / "out")
    s1 = run_batch(pdfs, out_dir)
    s2 = run_batch(pdfs, out_dir)            # same file again -> numeric suffix
    assert s1["succeeded"] == 1 and s2["succeeded"] == 1
    n1 = os.path.basename(s1["outputs"][0])
    n2 = os.path.basename(s2["outputs"][0])
    assert n1 != n2
    assert n2.rsplit(".", 1)[0].endswith("_2")


def test_batch_dry_run_writes_nothing(tmp_path):
    pdfs = _fixture_pdfs(1)
    if not pdfs:
        pytest.skip("fixtures not present")
    out_dir = str(tmp_path / "out")
    summary = run_batch(pdfs, out_dir, dry_run=True)
    assert summary["outputs"] == []
    assert not os.path.isdir(out_dir) or os.listdir(out_dir) == []


def test_batch_missing_file_is_skipped(tmp_path):
    out_dir = str(tmp_path / "out")
    summary = run_batch([str(tmp_path / "does_not_exist.pdf")], out_dir,
                        gui_log=lambda *a, **k: None)
    assert summary["skipped"] == 1
    assert summary["failed"] == 0
    assert summary["succeeded"] == 0


# --- Phase 6: heading-only page detection wiring (log-only, never deletes) ---
_P6_BODY = ("The traveller walked the ashen road as the gate dimmed behind him, "
            "and the cold wind carried the scent of old rain across the broken "
            "hills while the caravan waited for the light to fade over the pass.")


def _make_source_pdf(path, text):
    from pdf.builder import build_pdf
    build_pdf(text, str(path))
    return str(path)


def test_batch_flags_heading_only_page_without_deleting_it(tmp_path):
    # A multi-chapter source whose chapter 2 has no body: the pipeline re-inserts
    # \f before each later heading, so the output legitimately contains a
    # heading-only page. Phase 6 behavior: detect + warn + JSONL integrity_flag,
    # and NEVER delete the page (no positive proof it is an erroneous orphan).
    src = _make_source_pdf(
        tmp_path / "multi.pdf",
        f"Chapter 1: The Long Walk.\n\n{_P6_BODY}\n\f"
        "Chapter 2: Missing.\n\f"
        f"Chapter 3: The Return.\n\n{_P6_BODY}",
    )
    out_dir = str(tmp_path / "out")
    logs = []
    summary = run_batch(
        [src], out_dir, write_replacement_log=True,
        gui_log=lambda m, level="info": logs.append((level, m)),
    )
    assert summary["succeeded"] == 1

    # The heading-only page is still in the output (detection never deletes).
    with pdfplumber.open(summary["outputs"][0]) as pdf:
        page_texts = [(pg.extract_text() or "").strip() for pg in pdf.pages]
    heading_only = [t for t in page_texts if t.startswith("Chapter 2: Missing")]
    assert heading_only, "the heading-only chapter page was removed or lost"

    # GUI warning was emitted.
    assert any("heading-only" in m.lower() for _lvl, m in logs)

    # JSONL carries the integrity_flag record.
    import json
    jsonl = os.path.splitext(summary["outputs"][0])[0] + "_replacements.jsonl"
    with open(jsonl, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh]
    flags = [r for r in records
             if r.get("rule") == "pdf.heading_only_page_flag"
             and r.get("category") == "integrity_flag"]
    assert flags, "no heading-only integrity_flag record in the JSONL log"


def test_batch_single_chapter_skips_detection(tmp_path, monkeypatch):
    # Today's normal case (single-chapter input, no \f in the edited text) must
    # not pay for a post-build detection pass — the detector isn't even called.
    import core.batch_runner as batch_runner_mod
    calls = []

    def spy(path):
        calls.append(path)
        return []

    monkeypatch.setattr(batch_runner_mod, "detect_heading_only_pages", spy)
    src = _make_source_pdf(
        tmp_path / "single.pdf",
        f"Chapter 1: The Long Walk.\n\n{_P6_BODY}",
    )
    out_dir = str(tmp_path / "out")
    summary = run_batch([src], out_dir, gui_log=lambda *a, **k: None)
    assert summary["succeeded"] == 1
    assert calls == [], "detector ran on a single-chapter build"
