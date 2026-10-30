"""Durable output publication and recovery at every logical commit boundary."""
import json
from pathlib import Path
import pytest
from core.run_manifest import RunCheckpoint, read_manifest, ManifestError, CheckpointError


class Crash(BaseException):
    pass


def create(tmp_path, *, hook=None):
    src = tmp_path / "chapter.txt"
    src.write_text("Clan Valor remained.\n\nValor Clan waited.", encoding="utf-8")
    cp = RunCheckpoint(tmp_path / "out", [str(src)], novel="Universal", fault_hook=hook)
    cp.start(formats=("pdf", "txt"), rules_digest="rules")
    return cp, src


def stage(cp, src):
    from pdf.builder import build_pdf
    cp.stage(src, "pdf", lambda path: build_pdf("Chapter 1: Test\n\nClan Valor remained.", str(path)))
    cp.stage(src, "txt", lambda path: path.write_text("Clan Valor remained.\n", encoding="utf-8"))


@pytest.mark.parametrize("point", ["after_stage:pdf", "after_stage:txt", "before_prepared", "after_prepared",
                                    "before_publish:pdf", "after_publish:pdf", "before_publish:txt",
                                    "after_publish:txt", "before_completed", "after_completed"])
def test_crash_boundaries_never_false_complete_and_resume_same_mapping(tmp_path, point):
    def fault(at):
        if at == point:
            raise Crash()
    cp, src = create(tmp_path, hook=fault)
    original = cp.payload()
    try:
        with pytest.raises(Crash):
            stage(cp, src)
            cp.prepare(src)
            cp.publish(src)
    finally:
        cp.close()
    saved = read_manifest(cp.path)
    item = saved["entries"][0]
    if point != "after_completed":
        assert item["status"] != "completed"
    restored = RunCheckpoint.resume(cp.output_dir, rules_digest="rules")
    try:
        if item["status"] == "prepared":
            restored.publish(src)
        elif item["status"] != "completed":
            stage(restored, src)
            restored.prepare(src)
            restored.publish(src)
        restored.finish()
        final = restored.payload()
        assert final["entries"][0]["status"] == "completed"
        assert final["queue"] == original["queue"]
        assert final["entries"][0]["outputs"] == original["entries"][0]["outputs"]
        assert final["run"]["id"] == original["run"]["id"]
        assert len(list(Path(cp.output_dir).glob("chapter.*"))) == 2
    finally:
        restored.close()


@pytest.mark.parametrize("target", ["source", "completed_output", "prepared_output", "options", "rules"])
def test_resume_conflicts_preserve_external_files_and_manifest(tmp_path, target):
    cp, src = create(tmp_path)
    stage(cp, src)
    cp.prepare(src)
    if target != "prepared_output":
        cp.publish(src)
    else:
        (Path(cp.output_dir) / "chapter.txt").write_text("external file", encoding="utf-8")
    cp.close()
    if target == "source":
        src.write_text("Changed source", encoding="utf-8")
    if target == "completed_output":
        (Path(cp.output_dir) / "chapter.txt").write_text("modified output", encoding="utf-8")
    before = cp.path.read_bytes()
    kwargs = {"rules_digest": "changed" if target == "rules" else "rules"}
    if target == "options":
        kwargs["expected_options"] = {"formats": ["txt"]}
    with pytest.raises(ManifestError):
        resumed = RunCheckpoint.resume(cp.output_dir, **kwargs)
        try:
            resumed.publish(src)
        finally:
            resumed.close()
    assert cp.path.read_bytes() == before


def test_manifest_persistence_failure_does_not_advance_in_memory_or_publish(tmp_path, monkeypatch):
    cp, src = create(tmp_path)
    try:
        stage(cp, src)
        before = cp.path.read_bytes()
        def fail(*args, **kwargs):
            raise OSError("injected disk full")
        monkeypatch.setattr("core.run_manifest.write_settings_atomic", fail)
        with pytest.raises(CheckpointError):
            cp.prepare(src)
        assert cp.payload()["entries"][0]["status"] == "pending"
        assert cp.path.read_bytes() == before
        assert not (Path(cp.output_dir) / "chapter.pdf").exists()
    finally:
        cp.close()


def test_exhausted_second_rename_preserves_prepared_pair_for_retry(tmp_path, monkeypatch):
    import os
    import utils.atomic_io
    cp, src = create(tmp_path)
    stage(cp, src)
    cp.prepare(src)
    rename = os.rename
    attempts, delays = [], []
    def held(source, target):
        if Path(target).name == "chapter.txt":
            attempts.append(1)
            exc = PermissionError("sharing")
            exc.winerror = 32
            raise exc
        return rename(source, target)
    monkeypatch.setattr(os, "rename", held)
    monkeypatch.setattr(utils.atomic_io.time, "sleep", delays.append)
    try:
        with pytest.raises(PermissionError):
            cp.publish(src)
        cp.record_failed(src, "PermissionError")
        assert cp.entry(src)["status"] == "prepared"
        assert (Path(cp.output_dir) / "chapter.pdf").exists()
        assert not (Path(cp.output_dir) / "chapter.txt").exists()
        assert len(attempts) == 5 and sum(delays) <= 2
    finally:
        cp.close()
    monkeypatch.setattr(os, "rename", rename)
    resumed = RunCheckpoint.resume(cp.output_dir, rules_digest="rules")
    try:
        resumed.publish(src)
        assert resumed.entry(src)["status"] == "completed"
    finally:
        resumed.close()


@pytest.mark.parametrize("failure_kind", ["debug", "audit"])
def test_enabled_companion_failure_never_prepares_or_completes(tmp_path, failure_kind):
    src = tmp_path / "a.txt"
    src.write_text("A short chapter.", encoding="utf-8")
    cp = RunCheckpoint(tmp_path / "out", [str(src)])
    cp.start(formats=("txt",), write_debug_text=True, write_replacement_log=True, rules_digest="rules")
    try:
        cp.stage(src, "txt", lambda p: p.write_text("A short chapter.\n", encoding="utf-8"))
        cp.stage(src, "audit" if failure_kind == "debug" else "debug",
                 lambda p: p.write_text('{}\n' if failure_kind == "debug" else "text\n", encoding="utf-8"))
        with pytest.raises(ManifestError):
            cp.prepare(src)
        assert cp.entry(src)["status"] == "pending"
        assert not (Path(cp.output_dir) / "a.txt").exists()
    finally:
        cp.close()


@pytest.mark.parametrize("failures", [2, 6])
def test_atomic_manifest_publication_uses_same_bounded_windows_retries(tmp_path, monkeypatch, failures):
    import os
    import utils.atomic_io
    cp, src = create(tmp_path)
    before = cp.path.read_bytes()
    replace = os.replace
    attempts, delays = [], []
    def sharing(source, target):
        attempts.append(1)
        if len(attempts) <= failures:
            exc = PermissionError("injected sharing hold")
            exc.winerror = 5
            raise exc
        return replace(source, target)
    monkeypatch.setattr(os, "replace", sharing)
    monkeypatch.setattr(utils.atomic_io.time, "sleep", delays.append)
    try:
        if failures == 6:
            with pytest.raises(CheckpointError):
                cp.record_failed(src, "PermissionError")
            assert cp.path.read_bytes() == before
        else:
            cp.record_failed(src, "PermissionError")
            assert read_manifest(cp.path)["entries"][0]["status"] == "failed"
        assert len(attempts) == (5 if failures == 6 else 3)
        assert sum(delays) <= 2
    finally:
        cp.close()
