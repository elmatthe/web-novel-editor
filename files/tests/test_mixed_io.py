"""Mixed data paths through real extraction, rules, rendering and durable state."""
import os
from pathlib import Path
import pytest
from core.batch_runner import run_batch
from core.run_manifest import read_manifest, ManifestError
from pdf.builder import build_pdf


TEXT = "Chapter 1: Arrival\n\nClan Valor waited beside Valor Clan. Valor's banner remained.\n\nThe gate was still."


@pytest.mark.parametrize("input_kind", ["pdf", "txt"])
@pytest.mark.parametrize("formats", [("pdf",), ("txt",), ("pdf", "txt")])
def test_all_six_combinations_and_source_immutability(tmp_path, input_kind, formats, monkeypatch):
    src = tmp_path / ("Chapter 1." + input_kind)
    if input_kind == "pdf":
        build_pdf(TEXT, str(src))
    else:
        src.write_text(TEXT, encoding="utf-8-sig")
    before = (src.read_bytes(), src.stat().st_mtime_ns)
    rendered = []
    def render(text, path):
        rendered.append(text)
        build_pdf(text, path)
    monkeypatch.setattr("core.batch_runner.build_pdf", render)
    out = tmp_path / "out"
    result = run_batch([str(src)], str(out), output_formats=formats, novel_name="Shadow Slave")
    assert result["succeeded"] == 1 and result["failed"] == 0
    assert {Path(p).suffix for p in result["outputs"]} == {"." + fmt for fmt in formats}
    data = read_manifest(out / "run-manifest.json")
    assert data["entries"][0]["status"] == "completed"
    assert set(data["entries"][0]["expected"]) == set(formats)
    assert (src.read_bytes(), src.stat().st_mtime_ns) == before
    if "txt" in formats:
        text = (out / "Chapter 1.txt").read_text(encoding="utf-8")
        assert "Clan Valor waited beside Valor Clan. Valor's banner remained." in text
        assert "\n\n" in text and "\f" not in text
    assert (out / "Chapter 1.pdf").exists() == ("pdf" in formats)
    if len(formats) == 2:
        from core.batch_runner import serialize_txt
        assert (out / "Chapter 1.txt").read_text(encoding="utf-8") == serialize_txt(rendered[0])


@pytest.mark.parametrize("raw,status", [(b"Short.", "completed"), (b"", "skipped"),
                                         (b"\xef\xbb\xbf\r\n", "skipped"), (b"\xffbad", "failed")])
def test_strict_txt_short_empty_and_invalid(tmp_path, raw, status, monkeypatch):
    src = tmp_path / "chapter.txt"
    src.write_bytes(raw)
    monkeypatch.setattr("core.batch_runner.build_pdf", lambda *a: pytest.fail("TXT-only built a PDF"))
    monkeypatch.setattr("core.batch_runner.detect_heading_only_pages", lambda *a: pytest.fail("TXT-only scanned a PDF"))
    result = run_batch([str(src)], str(tmp_path / "out"), output_formats=("txt",))
    item = read_manifest(tmp_path / "out" / "run-manifest.json")["entries"][0]
    assert item["status"] == status
    assert result["succeeded"] == int(status == "completed")


def test_txt_explicit_paragraphs_and_readable_chapter_separators(tmp_path):
    src = tmp_path / "chapter.txt"
    src.write_text("Chapter 1: First\r\n\r\nA fragment\r\n\r\na second fragment.\r\n\r\nChapter 2: Next\r\n\r\nThe end.", encoding="utf-8")
    run_batch([str(src)], str(tmp_path / "out"), output_formats=("txt",))
    text = (tmp_path / "out" / "chapter.txt").read_text(encoding="utf-8")
    assert "A fragment\n\na second fragment." in text
    assert "\f" not in text and "\r" not in text
    assert "\n\nChapter 2" in text


def test_txt_heading_does_not_absorb_following_prose_without_a_blank_line(tmp_path):
    src = tmp_path / "chapter.txt"
    src.write_text("Chapter 1: Arrival\nClan Valor waited.\nThe gate remained.\n\nA fragment\ncontinued here.", encoding="utf-8")
    run_batch([str(src)], str(tmp_path / "out"), output_formats=("txt",))
    text = (tmp_path / "out" / "chapter.txt").read_text(encoding="utf-8")
    assert "Chapter 1: Arrival.\n\nClan Valor waited. The gate remained." in text
    assert "A fragment continued here." in text


def test_repeated_resume_and_retry_preserve_queue_mapping_and_completed_hashes(tmp_path, monkeypatch):
    paths = [tmp_path / f"{i}.txt" for i in range(3)]
    for src in paths:
        src.write_text("Short clean prose.", encoding="utf-8")
    import threading
    stop = threading.Event()
    def tick(value):
        stop.set()
    run_batch([str(p) for p in paths], str(tmp_path / "out"), output_formats=("txt",), stop_event=stop, progress=tick)
    original = read_manifest(tmp_path / "out" / "run-manifest.json")
    first_bytes = (tmp_path / "out" / "0.txt").read_bytes()
    for _ in range(2):
        run_batch([str(p) for p in paths], str(tmp_path / "out"), resume=True, stop_event=stop)
    stop.clear()
    result = run_batch([str(p) for p in paths], str(tmp_path / "out"), resume=True)
    assert result["succeeded"] == 2
    final = read_manifest(tmp_path / "out" / "run-manifest.json")
    assert final["queue"] == original["queue"] and final["queue_digest"] == original["queue_digest"]
    assert (tmp_path / "out" / "0.txt").read_bytes() == first_bytes
    assert [len(e["attempts"]) for e in final["entries"]] == [1, 1, 1]
    assert run_batch(final["queue"], str(tmp_path / "out"), resume=True, retry_failed=True)["succeeded"] == 0


def test_retry_failed_reprocesses_only_failed_items_and_preserves_completed(tmp_path, monkeypatch):
    import core.batch_runner as batch
    from pdf.builder import build_pdf as real_build
    paths = [tmp_path / f"{i}.txt" for i in range(2)]
    for path in paths:
        path.write_text("Short prose.", encoding="utf-8")
    fail = True
    def build(text, path):
        if fail and Path(path).name == "1.pdf":
            raise PermissionError("temporary destination failure")
        real_build(text, path)
    monkeypatch.setattr(batch, "build_pdf", build)
    out = tmp_path / "out"
    first = run_batch([str(p) for p in paths], str(out), output_formats=("pdf", "txt"))
    assert first["succeeded"] == first["failed"] == 1
    before = (out / "0.pdf").read_bytes()
    fail = False
    retry = run_batch([str(p) for p in paths], str(out), resume=True, retry_failed=True)
    assert retry["succeeded"] == 1 and retry["failed"] == 0
    data = read_manifest(out / "run-manifest.json")
    assert [len(e["attempts"]) for e in data["entries"]] == [1, 2]
    assert (out / "0.pdf").read_bytes() == before
    assert {p.name for p in out.glob("*.pdf")} == {"0.pdf", "1.pdf"}


@pytest.mark.parametrize("boundary", ["initial", "prepared", "completed", "finish"])
def test_persistence_failure_stops_worker_without_processing_further_files(tmp_path, monkeypatch, boundary):
    import core.run_manifest as manifests
    from core.run_manifest import CheckpointError
    import core.batch_runner as batch
    paths = [tmp_path / f"{i}.txt" for i in range(2)]
    for path in paths:
        path.write_text("Short clean prose.", encoding="utf-8")
    real_write = manifests.write_settings_atomic
    built = []
    real_serialize = batch.serialize_txt
    monkeypatch.setattr(batch, "serialize_txt", lambda text: (built.append(text), real_serialize(text))[1])
    def write(path, data, **kwargs):
        state = data["entries"][0]["status"]
        trigger = ((boundary == "initial" and state == "pending")
                   or (boundary == "prepared" and state == "prepared")
                   or (boundary == "completed" and state == "completed")
                   or (boundary == "finish" and data["complete"]))
        if trigger:
            raise OSError("injected persistence failure")
        real_write(path, data, **kwargs)
    monkeypatch.setattr(manifests, "write_settings_atomic", write)
    with pytest.raises(CheckpointError):
        run_batch([str(p) for p in paths], str(tmp_path / "out"), output_formats=("txt",))
    assert len(built) == (0 if boundary == "initial" else 2 if boundary == "finish" else 1)
    manifest = tmp_path / "out" / "run-manifest.json"
    if boundary != "initial":
        saved = read_manifest(manifest)
        assert not saved["complete"]
        if boundary in {"prepared", "completed"}:
            assert saved["entries"][0]["status"] != "completed"


def test_source_changed_during_render_is_never_completed(tmp_path, monkeypatch):
    src = tmp_path / "a.txt"
    src.write_text("Original chapter.", encoding="utf-8")
    def render(text, path):
        build_pdf(text, path)
        src.write_text("Modified chapter.", encoding="utf-8")
    monkeypatch.setattr("core.batch_runner.build_pdf", render)
    result = run_batch([str(src)], str(tmp_path / "out"))
    assert result["succeeded"] == 0 and result["failed"] == 1
    item = read_manifest(tmp_path / "out" / "run-manifest.json")["entries"][0]
    assert item["status"] == "failed" and not (tmp_path / "out" / "a.pdf").exists()


def test_retry_failed_does_not_report_entire_run_complete_with_pending_items(tmp_path, monkeypatch):
    import threading
    from core.run_manifest import RunCheckpoint
    paths = [tmp_path / f"{i}.txt" for i in range(3)]
    for path in paths:
        path.write_text("Short prose.", encoding="utf-8")
    real_stage = RunCheckpoint.stage
    failed = False
    def stage(self, source, kind, writer):
        nonlocal failed
        if not failed and Path(source).name == "0.txt":
            failed = True
            raise PermissionError("injected destination failure")
        return real_stage(self, source, kind, writer)
    monkeypatch.setattr(RunCheckpoint, "stage", stage)
    stop = threading.Event()
    out = str(tmp_path / "out")
    queue = [str(p) for p in paths]
    run_batch(queue, out, output_formats=("txt",), stop_event=stop,
              progress=lambda i: stop.set() if i == 2 else None)
    result = run_batch(queue, out, resume=True, retry_failed=True)
    assert result["succeeded"] == 1 and result["completed_total"] == 2
    assert result["pending_total"] == 1 and result["run_complete"] is False
    assert read_manifest(Path(out) / "run-manifest.json")["stopped_reason"] == "pending_remaining"
    finished = run_batch(queue, out, resume=True)
    assert finished["succeeded"] == 1 and finished["run_complete"] is True
