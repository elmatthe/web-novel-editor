"""Batch seam safety: exact build text, dry-run output policy, safe stop and pause.

Descended from ``test_plan2a_phase5`` (Plan 2a Phase 5). Phase 01A removed the optional AI
editor, so the provider-seam tests there have no surviving responsibility; what remains
are the script-only guarantees that were always the point of that module:

  * ``run_batch`` hands the pipeline's output to the PDF builder byte for byte;
  * a dry run builds nothing;
  * Stop and Pause are honoured only at the safe between-files seam, and a Stop that
    releases a paused worker begins no further file;
  * a source PDF is never modified;
  * one file's build failure never aborts the batch;
  * the condensed per-file line reports the real edit count.
"""

from __future__ import annotations

import threading
from pathlib import Path

import core.batch_runner as batch_runner
from core.batch_runner import run_batch
from core.novel_registry import NovelDispatch

BASELINE = (
    "Chapter 1: Test.\n\n"
    "After the very long journey through the silent city, he walk home alone. "
    "The lamps remained bright while the quiet road stretched toward the distant gate."
)


def _dispatch(pipeline=None):
    return NovelDispatch(
        display_name="Universal",
        run_pipeline=pipeline or (lambda text, lexicon, **kwargs: text),
        canonical_names=frozenset(),
        index_filename="",
        has_profile=False,
    )


def _wire(monkeypatch, built, pipeline=None):
    monkeypatch.setattr(batch_runner, "extract_text_from_pdf", lambda _path: BASELINE)
    monkeypatch.setattr(
        batch_runner, "resolve_dispatch", lambda _name: _dispatch(pipeline)
    )
    monkeypatch.setattr(
        batch_runner, "build_pdf", lambda text, path: built.append((text, path))
    )


def _inputs(tmp_path: Path, count=1):
    paths = []
    for index in range(count):
        path = tmp_path / f"{index}.pdf"
        path.write_bytes(b"%PDF-source")
        paths.append(str(path))
    return paths


def test_the_pipeline_output_reaches_build_pdf_exactly(tmp_path, monkeypatch):
    built = []
    seen = []

    def pipeline(text, lexicon, **kwargs):
        seen.append(text)
        return text.replace("he walk home", "he walks home")

    _wire(monkeypatch, built, pipeline)
    summary = run_batch(_inputs(tmp_path), str(tmp_path / "out"))

    assert summary["succeeded"] == 1
    assert seen == [BASELINE]
    assert built[0][0] == BASELINE.replace("he walk home", "he walks home")


def test_a_dry_run_builds_no_pdf_and_creates_no_output_folder(tmp_path, monkeypatch):
    built = []
    _wire(monkeypatch, built)
    out = tmp_path / "out"
    summary = run_batch(_inputs(tmp_path, 2), str(out), dry_run=True)
    assert summary["succeeded"] == 2 and built == []
    assert not out.exists()


def test_stop_during_pdf_write_finishes_current_then_stops(tmp_path, monkeypatch):
    built = []
    stop = threading.Event()
    _wire(monkeypatch, built)

    def build(text, path):
        built.append((text, path))
        stop.set()

    monkeypatch.setattr(batch_runner, "build_pdf", build)
    summary = run_batch(
        _inputs(tmp_path, 3), str(tmp_path / "out"), stop_event=stop
    )
    assert len(built) == 1
    assert summary["succeeded"] == 1 and summary["stopped"] is True


def test_stop_already_requested_begins_no_file(tmp_path, monkeypatch):
    built = []
    _wire(monkeypatch, built)
    stop = threading.Event()
    stop.set()
    summary = run_batch(
        _inputs(tmp_path, 2), str(tmp_path / "out"), stop_event=stop
    )
    assert built == [] and summary["succeeded"] == 0 and summary["stopped"] is True


def test_stop_releasing_paused_worker_begins_no_next_file(tmp_path, monkeypatch):
    """Mirror the GUI sequence: Pause holds between files, then Stop sets both
    stop_event and pause_gate. The release may only let run_batch observe Stop."""
    paths = _inputs(tmp_path, 2)
    pause_gate = threading.Event()
    pause_gate.set()
    stop_event = threading.Event()
    paused_reached = threading.Event()
    extraction_calls = []
    pipeline_calls = []
    built = []
    logs = []
    result = {}
    errors = []

    def extract(path):
        extraction_calls.append(Path(path).name)
        return BASELINE

    def pipeline(text, lexicon, **kwargs):
        pipeline_calls.append(text)
        return text

    def build(text, path):
        built.append(Path(path).name)
        # Simulate Pause being requested while file 1 is finishing. The worker
        # will observe the cleared gate only after this complete PDF write returns.
        pause_gate.clear()

    def gui_log(message, level="info"):
        logs.append((level, message))
        if message.startswith("Paused after chapter 1"):
            paused_reached.set()

    monkeypatch.setattr(batch_runner, "extract_text_from_pdf", extract)
    monkeypatch.setattr(batch_runner, "resolve_dispatch", lambda _name: _dispatch(pipeline))
    monkeypatch.setattr(batch_runner, "build_pdf", build)

    def worker():
        try:
            result["summary"] = run_batch(
                paths,
                str(tmp_path / "out"),
                pause_gate=pause_gate,
                stop_event=stop_event,
                gui_log=gui_log,
            )
        except BaseException as exc:  # surfaced in the main test thread
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    assert paused_reached.wait(timeout=5), "worker never reached between-file pause"

    # Real GUI Stop ordering: request stop, then release Pause solely so the
    # worker can observe the request.
    stop_event.set()
    pause_gate.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert errors == []
    assert extraction_calls == ["0.pdf"]
    assert len(pipeline_calls) == 1
    assert built == ["0.pdf"]
    assert result["summary"]["succeeded"] == 1
    assert result["summary"]["stopped"] is True
    assert any(
        "batch ended before chapter 2 of 2" in message for _, message in logs
    )
    assert not any("Continuing with chapter 2" in message for _, message in logs)


def test_pause_is_consulted_only_between_files(tmp_path, monkeypatch):
    built = []
    _wire(monkeypatch, built)

    class Gate:
        def __init__(self):
            self.checks = 0
            self.waits = 0

        def is_set(self):
            self.checks += 1
            return False

        def wait(self):
            self.waits += 1

    gate = Gate()
    run_batch(_inputs(tmp_path, 2), str(tmp_path / "out"), pause_gate=gate)
    assert gate.checks == 1 and gate.waits == 1 and len(built) == 2


def test_source_pdf_bytes_and_mtime_are_unchanged(tmp_path, monkeypatch):
    built = []
    _wire(monkeypatch, built)
    source = Path(_inputs(tmp_path)[0])
    before = (source.read_bytes(), source.stat().st_mtime_ns)
    run_batch([str(source)], str(tmp_path / "out"))
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


def test_one_pdf_build_failure_is_isolated_from_the_rest_of_the_batch(
    tmp_path, monkeypatch
):
    built = []
    _wire(monkeypatch, built)

    def build(text, path):
        if Path(path).name == "1.pdf":
            raise OSError("locked")
        built.append((text, path))

    monkeypatch.setattr(batch_runner, "build_pdf", build)
    summary = run_batch(_inputs(tmp_path, 3), str(tmp_path / "out"))
    assert summary["succeeded"] == 2 and summary["failed"] == 1
    assert [Path(path).name for _, path in built] == ["0.pdf", "2.pdf"]


def test_the_condensed_line_reports_the_real_edit_count(tmp_path, monkeypatch):
    """The per-file line states how many real edits the pipeline recorded."""
    built = []

    def pipeline(text, lexicon, repl_log=None, **kwargs):
        repl_log.record("he walk home", "he walks home", "test_rule", "grammar")
        return text

    _wire(monkeypatch, built, pipeline)
    logs = []
    run_batch(
        _inputs(tmp_path, 1),
        str(tmp_path / "out"),
        gui_log=lambda message, level="info": logs.append((level, message)),
    )
    done = [m for _, m in logs if "— done (" in m]
    assert len(done) == 1
    assert "1 edit" in done[0] and "edits" not in done[0]
    assert "AI" not in done[0]
