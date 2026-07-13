"""Phase 6 — batch robustness on bad / hostile input.

These lock in the continue-on-failure contract the spec requires (Safeguards +
Batch Processing > Error Handling): one bad file must never abort the run, freeze the
GUI worker, or produce a garbage PDF. Each hostile input is generated on the fly in
tmp_path (no committed binaries), so the suite stays fast and self-contained.

Cases covered (each was confirmed by hand during the Phase-6 bug hunt, then pinned here
so it cannot regress):
  - image-only / no-text PDF        -> SKIPPED (low-confidence), no output written
  - 0-byte PDF                      -> FAILED  (caught + logged), batch continues
  - corrupt / truncated PDF         -> FAILED  (caught + logged), batch continues
  - non-PDF bytes with a .pdf name  -> FAILED  (caught + logged), batch continues
  - a bad file BETWEEN two good ones-> both good files still succeed; progress hits all N
  - output write failure (locked /  -> per-file FAILED, batch never crashes
    permission-denied folder)
"""

from __future__ import annotations

import os

import pytest

import core.batch_runner as batch_runner
from core.batch_runner import run_batch

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FIXTURES = os.path.join(_REPO_ROOT, "files", "test-files", "shadow_slave")


# --- helpers: synthesize hostile inputs in tmp_path -------------------------
def _zero_byte_pdf(tmp_path) -> str:
    p = str(tmp_path / "zero.pdf")
    open(p, "wb").close()
    return p


def _corrupt_pdf(tmp_path) -> str:
    p = str(tmp_path / "corrupt.pdf")
    with open(p, "wb") as fh:
        fh.write(b"%PDF-1.4\n garbage bytes that are not a real PDF body \x00\x01")
    return p


def _non_pdf(tmp_path) -> str:
    p = str(tmp_path / "actually_text.pdf")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("This is just a text file someone renamed to .pdf. " * 6)
    return p


def _image_only_pdf(tmp_path) -> str:
    """A real, valid PDF that contains NO extractable text (just a drawn shape).

    This is the spec's 'image-only / scanned PDF' non-goal: extraction yields ~0
    chars, so the batch must SKIP it (low-confidence), not fail or emit garbage.
    """
    reportlab = pytest.importorskip("reportlab")  # noqa: F841
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    p = str(tmp_path / "image_only.pdf")
    c = canvas.Canvas(p, pagesize=letter)
    c.rect(100, 100, 200, 200, fill=1)  # a filled box, zero text
    c.showPage()
    c.save()
    return p


def _real_fixtures(limit=2):
    if not os.path.isdir(_FIXTURES):
        return []
    pdfs = sorted(
        os.path.join(_FIXTURES, f)
        for f in os.listdir(_FIXTURES) if f.lower().endswith(".pdf")
    )
    return pdfs[:limit]


# --- single-bad-input cases -------------------------------------------------
def test_image_only_pdf_is_skipped_not_failed(tmp_path):
    pytest.importorskip("pdfplumber")
    out_dir = str(tmp_path / "out")
    summary = run_batch([_image_only_pdf(tmp_path)], out_dir)
    assert summary["skipped"] == 1
    assert summary["failed"] == 0
    assert summary["succeeded"] == 0
    assert summary["outputs"] == []
    # No garbage PDF written for an unprocessable file.
    assert not os.path.isdir(out_dir) or os.listdir(out_dir) == []


@pytest.mark.parametrize("make_bad", [_zero_byte_pdf, _corrupt_pdf, _non_pdf])
def test_bad_pdf_fails_gracefully_without_crashing(make_bad, tmp_path):
    pytest.importorskip("pdfplumber")
    bad = make_bad(tmp_path)
    out_dir = str(tmp_path / "out")
    logs = []
    summary = run_batch(
        [bad], out_dir, gui_log=lambda m, level="info": logs.append((level, m))
    )
    assert summary["failed"] == 1
    assert summary["succeeded"] == 0
    assert summary["outputs"] == []
    # The failure was reported on the error channel (thread-safe path in the GUI).
    assert any(level == "error" for level, _ in logs)
    # No garbage PDF written.
    assert not os.path.isdir(out_dir) or os.listdir(out_dir) == []


# --- mid-batch continuation -------------------------------------------------
def test_bad_file_between_good_files_does_not_abort_batch(tmp_path):
    pytest.importorskip("pdfplumber")
    reals = _real_fixtures(2)
    if len(reals) < 2:
        pytest.skip("need two real fixtures (files/test-files/shadow_slave)")

    sequence = [reals[0], _corrupt_pdf(tmp_path), reals[1]]
    out_dir = str(tmp_path / "out")
    progress = []
    summary = run_batch(sequence, out_dir, progress=progress.append)

    # The bad file in the middle did not stop the two good ones.
    assert summary["succeeded"] == 2
    assert summary["failed"] == 1
    assert summary["total"] == 3
    # Progress advanced for every file (success OR failure), so the GUI bar completes.
    assert progress == [1, 2, 3]
    assert len(summary["outputs"]) == 2


# --- output write failure (locked / permission-denied folder) ---------------
def test_output_write_failure_is_caught_per_file(tmp_path, monkeypatch):
    """A locked/permission-denied output folder must fail per file, never crash.

    Simulated by making the PDF builder raise (as it would on a read-only target),
    which exercises the same per-file try/except the real PermissionError hits.
    """
    pytest.importorskip("pdfplumber")
    reals = _real_fixtures(2)
    if len(reals) < 2:
        pytest.skip("need two real fixtures (files/test-files/shadow_slave)")

    def _deny(_text, _path):
        raise PermissionError("output folder is read-only")

    monkeypatch.setattr(batch_runner, "build_pdf", _deny)

    out_dir = str(tmp_path / "out")
    logs = []
    summary = run_batch(
        reals, out_dir, gui_log=lambda m, level="info": logs.append((level, m))
    )
    # Both files failed gracefully; the run still completed and returned a summary.
    assert summary["failed"] == len(reals)
    assert summary["succeeded"] == 0
    assert summary["outputs"] == []
    assert any(level == "error" for level, _ in logs)


def test_empty_file_list_returns_clean_summary(tmp_path):
    """An empty queue is a no-op run, not a crash (GUI guards this too, but verify)."""
    summary = run_batch([], str(tmp_path / "out"))
    assert summary == {
        "total": 0, "succeeded": 0, "failed": 0, "skipped": 0,
        "output_dir": str(tmp_path / "out"), "outputs": [],
        # Phase-5 dispatch provenance: no novel_name -> universal-only by design (#3).
        "novel": "Universal", "profile_applied": False,
    }
