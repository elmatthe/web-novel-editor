"""Plan 1 Phase 4 — pause/continue between files + the condensed per-file log format.

These drive `run_batch` directly through its callbacks — deterministic, no real sleeps,
no real threading races. The pause gate is exercised with a scripted fake Event (so a
"paused" state never blocks the suite), and the per-file work is monkeypatched at the
same seams the robustness tests use (`batch_runner.extract_text_from_pdf` /
`batch_runner.build_pdf` / `batch_runner.resolve_dispatch`), keeping every case fast and
input-independent.

Contracts pinned here:
  - pause gate: checked BETWEEN files only — the current file always finishes, no check
    before the first file or after the last; "Paused after chapter N of M" is logged on
    hold and a continue line on resume.
  - condensed log: ONE line per file — "[i/N] name — done (X edits)" /
    "— done (dry run, X edits)" / "— skipped (not found)" / "— skipped (image-only/empty)"
    / "— FAILED (Type: reason)" — with the existing color tags.
  - end-of-batch summary block: totals line + Failed:/Skipped: file lists (omitted when
    empty).
  - verbose pipeline detail stays out of the GUI log (JSONL only); pipeline "⚠"
    integrity warnings (error pages) still surface as warnings.
  - the explicit "Universal" selection logs an intentional-choice line, not
    "No novel-specific profile for 'Universal'".
"""

from __future__ import annotations

import os
import re
import threading

import pytest

import core.batch_runner as batch_runner
from core.batch_runner import run_batch
from core.novel_registry import NovelDispatch

_LONG_TEXT = ("Chapter 1: The Beginning.\n\n"
              "Sunny walked through the ruins of the old city for a long time. " * 8)


# --- helpers ----------------------------------------------------------------
class ScriptedGate:
    """Fake pause Event: `is_set()` pops scripted answers (then defaults True = run);
    `wait()` records the hold and returns immediately, so tests never block."""

    def __init__(self, script=()):
        self.script = list(script)
        self.wait_calls = 0

    def is_set(self) -> bool:
        return self.script.pop(0) if self.script else True

    def wait(self) -> None:
        self.wait_calls += 1


def _stub_pdfs(tmp_path, names):
    """Create tiny on-disk stand-in files (content never read — extraction is faked)."""
    paths = []
    for name in names:
        p = tmp_path / name
        p.write_bytes(b"%PDF-stub")
        paths.append(str(p))
    return paths


def _fake_dispatch(edits=0, gui_lines=()):
    """A universal-only NovelDispatch whose pipeline records `edits` replacement events
    and emits `gui_lines` through the pipeline's gui_log channel."""

    def run_pipeline(text, lexicon, *, repl_log=None, gui_log=None, dry_run=False):
        if repl_log is not None:
            for k in range(edits):
                repl_log.record(f"orig{k}", f"new{k}", "fake_rule", "test")
        if gui_log is not None:
            for line in gui_lines:
                gui_log(line)
        return text

    return NovelDispatch(
        display_name="Universal",
        run_pipeline=run_pipeline,
        canonical_names=frozenset(),
        index_filename="",
        has_profile=False,
    )


def _wire_fast_seams(monkeypatch, edits=0, gui_lines=(), fail_names=()):
    """Monkeypatch extraction/dispatch/build so run_batch runs instantly: extraction
    returns long fake text, the pipeline is `_fake_dispatch`, and build_pdf writes a
    stub file (raising for any output whose name is listed in `fail_names`)."""
    monkeypatch.setattr(batch_runner, "extract_text_from_pdf", lambda _p: _LONG_TEXT)
    monkeypatch.setattr(
        batch_runner, "resolve_dispatch",
        lambda _n: _fake_dispatch(edits=edits, gui_lines=gui_lines))

    def _build(_text, path):
        if os.path.basename(path) in fail_names:
            raise ValueError("boom")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("pdf")

    monkeypatch.setattr(batch_runner, "build_pdf", _build)


def _run(paths, tmp_path, monkeypatch=None, **kwargs):
    logs = []
    summary = run_batch(
        paths, str(tmp_path / "out"),
        gui_log=lambda m, level="info": logs.append((level, m)),
        **kwargs,
    )
    return logs, summary


def _messages(logs):
    return [m for _, m in logs]


# --- pause / continue state machine ----------------------------------------
def test_pause_holds_after_current_file_and_before_next(tmp_path, monkeypatch):
    """A pause requested during file 1 takes effect only after file 1's one-line result
    is logged, holds before file 2 starts, and resumes on continue."""
    _wire_fast_seams(monkeypatch, edits=1)
    paths = _stub_pdfs(tmp_path, ["a.pdf", "b.pdf", "c.pdf"])
    gate = ScriptedGate(script=[False])  # first between-files check: paused once

    logs, summary = _run(paths, tmp_path, pause_gate=gate)
    msgs = _messages(logs)

    assert gate.wait_calls == 1
    paused_idx = next(i for i, m in enumerate(msgs)
                      if "Paused after chapter 1 of 3" in m)
    done1_idx = next(i for i, m in enumerate(msgs) if m.startswith("[1/3]"))
    file2_idx = next(i for i, m in enumerate(msgs) if m.startswith("[2/3]"))
    assert done1_idx < paused_idx < file2_idx  # file 1 finished, held before file 2
    assert any("Continuing" in m for m in msgs)
    assert summary["succeeded"] == 3


def test_pause_gate_set_never_pauses(tmp_path, monkeypatch):
    """A real, set Event (the running state) introduces no pause and no log noise."""
    _wire_fast_seams(monkeypatch)
    paths = _stub_pdfs(tmp_path, ["a.pdf", "b.pdf"])
    gate = threading.Event()
    gate.set()

    logs, summary = _run(paths, tmp_path, pause_gate=gate)

    assert summary["succeeded"] == 2
    assert not any("Paused" in m for m in _messages(logs))


def test_no_pause_check_before_first_or_after_last_file(tmp_path, monkeypatch):
    """With a single file, a pause request can never hold: the gate is only consulted
    BETWEEN files (never before the first, never after the last)."""
    _wire_fast_seams(monkeypatch)
    paths = _stub_pdfs(tmp_path, ["only.pdf"])
    gate = ScriptedGate(script=[False, False, False])  # would pause if ever consulted

    logs, summary = _run(paths, tmp_path, pause_gate=gate)

    assert gate.wait_calls == 0
    assert not any("Paused" in m for m in _messages(logs))
    assert summary["succeeded"] == 1


def test_run_batch_without_pause_event_still_works(tmp_path, monkeypatch):
    """The gate is optional: headless/API callers that pass nothing are unaffected."""
    _wire_fast_seams(monkeypatch)
    paths = _stub_pdfs(tmp_path, ["a.pdf"])
    _, summary = _run(paths, tmp_path)
    assert summary["succeeded"] == 1


# --- condensed one-line-per-file format ------------------------------------
def test_condensed_done_line_with_edit_count(tmp_path, monkeypatch):
    _wire_fast_seams(monkeypatch, edits=3)
    paths = _stub_pdfs(tmp_path, ["a.pdf"])

    logs, summary = _run(paths, tmp_path)

    assert ("success", "[1/1] a.pdf — done (3 edits)") in logs
    assert summary["succeeded"] == 1
    # The old multi-line-per-file chatter is gone.
    msgs = _messages(logs)
    assert not any("Extracting" in m for m in msgs)
    assert not any("Wrote:" in m for m in msgs)


def test_condensed_done_line_singular_edit(tmp_path, monkeypatch):
    _wire_fast_seams(monkeypatch, edits=1)
    paths = _stub_pdfs(tmp_path, ["a.pdf"])
    logs, _ = _run(paths, tmp_path)
    assert ("success", "[1/1] a.pdf — done (1 edit)") in logs


def test_condensed_skipped_not_found_line(tmp_path, monkeypatch):
    _wire_fast_seams(monkeypatch)
    logs, summary = _run([str(tmp_path / "missing.pdf")], tmp_path)
    assert ("warn", "[1/1] missing.pdf — skipped (not found)") in logs
    assert summary["skipped"] == 1


def test_condensed_skipped_image_only_line(tmp_path, monkeypatch):
    _wire_fast_seams(monkeypatch)
    monkeypatch.setattr(batch_runner, "extract_text_from_pdf", lambda _p: "")
    paths = _stub_pdfs(tmp_path, ["scan.pdf"])
    logs, summary = _run(paths, tmp_path)
    assert ("warn", "[1/1] scan.pdf — skipped (image-only/empty)") in logs
    assert summary["skipped"] == 1


def test_condensed_failed_line(tmp_path, monkeypatch):
    _wire_fast_seams(monkeypatch, fail_names=("bad.pdf",))
    paths = _stub_pdfs(tmp_path, ["bad.pdf"])
    logs, summary = _run(paths, tmp_path)
    assert ("error", "[1/1] bad.pdf — FAILED (ValueError: boom)") in logs
    assert summary["failed"] == 1


def test_condensed_dry_run_line(tmp_path, monkeypatch):
    _wire_fast_seams(monkeypatch, edits=2)
    paths = _stub_pdfs(tmp_path, ["a.pdf"])
    logs, summary = _run(paths, tmp_path, dry_run=True)
    assert ("info", "[1/1] a.pdf — done (dry run, 2 edits)") in logs
    assert summary["succeeded"] == 1


def test_edit_count_present_without_replacement_log_option(tmp_path, monkeypatch):
    """The edit count is shown even when the JSONL option is off — and no JSONL file
    is written in that case (counting is internal-only)."""
    _wire_fast_seams(monkeypatch, edits=2)
    paths = _stub_pdfs(tmp_path, ["a.pdf"])

    logs, _ = _run(paths, tmp_path, write_replacement_log=False)

    assert ("success", "[1/1] a.pdf — done (2 edits)") in logs
    out = tmp_path / "out"
    assert not list(out.glob("*.jsonl"))


def test_jsonl_still_written_when_option_enabled(tmp_path, monkeypatch):
    _wire_fast_seams(monkeypatch, edits=2)
    paths = _stub_pdfs(tmp_path, ["a.pdf"])
    _run(paths, tmp_path, write_replacement_log=True)
    assert list((tmp_path / "out").glob("*_replacements.jsonl"))


# --- end-of-batch summary block ---------------------------------------------
def test_summary_block_totals_and_failed_skipped_lists(tmp_path, monkeypatch):
    _wire_fast_seams(monkeypatch, edits=1, fail_names=("bad.pdf",))
    paths = _stub_pdfs(tmp_path, ["good.pdf", "bad.pdf"])
    paths.append(str(tmp_path / "missing.pdf"))

    logs, summary = _run(paths, tmp_path)
    msgs = _messages(logs)

    assert summary == {**summary, "succeeded": 1, "failed": 1, "skipped": 1}
    assert any("Batch complete: 1 done, 1 failed, 1 skipped of 3." in m for m in msgs)
    failed_idx = msgs.index("Failed:")
    skipped_idx = msgs.index("Skipped:")
    assert any("bad.pdf (ValueError: boom)" in m for m in msgs[failed_idx + 1:])
    assert any("missing.pdf (not found)" in m for m in msgs[skipped_idx + 1:])
    # List lines carry the semantic tags.
    assert ("error", "  - bad.pdf (ValueError: boom)") in logs
    assert ("warn", "  - missing.pdf (not found)") in logs


def test_summary_block_omits_empty_sections(tmp_path, monkeypatch):
    _wire_fast_seams(monkeypatch, edits=1)
    paths = _stub_pdfs(tmp_path, ["a.pdf", "b.pdf"])

    logs, _ = _run(paths, tmp_path)
    msgs = _messages(logs)

    assert any("Batch complete: 2 done, 0 failed, 0 skipped of 2." in m for m in msgs)
    assert "Failed:" not in msgs
    assert "Skipped:" not in msgs


# --- verbose detail stays in the JSONL, warnings still surface ---------------
def test_verbose_pipeline_lines_stay_out_of_gui_log(tmp_path, monkeypatch):
    _wire_fast_seams(
        monkeypatch, edits=1,
        gui_lines=("  ✓ Block A: cleanup + paragraph reconstruction",
                   "  ⚠ CDN error page — chapter text missing; file needs re-scrape"))
    paths = _stub_pdfs(tmp_path, ["a.pdf"])

    logs, _ = _run(paths, tmp_path)
    msgs = _messages(logs)

    assert not any("Block A" in m for m in msgs)  # verbose stage chatter filtered
    warn_msgs = [m for level, m in logs if level == "warn"]
    assert any("re-scrape" in m for m in warn_msgs)  # integrity warnings kept


# --- the corrected "Universal" selection log line ----------------------------
def test_universal_selection_logs_intentional_choice(tmp_path, monkeypatch):
    """Selecting "Universal" is an explicit choice, not a missing profile — the log
    must say so (Phase-3 deviation fixed here). Universal-only dispatch unchanged."""
    monkeypatch.setattr(batch_runner, "extract_text_from_pdf", lambda _p: _LONG_TEXT)
    paths = _stub_pdfs(tmp_path, ["a.pdf"])

    logs, summary = _run(paths, tmp_path, dry_run=True, novel_name="Universal")
    text = " ".join(_messages(logs))

    assert "Universal editing selected" in text
    assert "universal-only editing" in text          # phrase other tests rely on
    assert "No novel-specific profile for 'Universal'" not in text
    assert summary["profile_applied"] is False


def test_profileless_novel_keeps_no_profile_line(tmp_path, monkeypatch):
    """A genuinely profile-less novel still gets the honest "no profile" wording."""
    monkeypatch.setattr(batch_runner, "extract_text_from_pdf", lambda _p: _LONG_TEXT)
    paths = _stub_pdfs(tmp_path, ["a.pdf"])

    logs, _ = _run(paths, tmp_path, dry_run=True, novel_name="Lord of the Mysteries")
    text = " ".join(_messages(logs))

    assert "No novel-specific profile for 'Lord of the Mysteries'" in text
    assert "universal-only editing" in text
