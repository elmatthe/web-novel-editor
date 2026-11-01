"""Durable output publication and recovery at every logical commit boundary."""
import errno
import json
import os
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


# The publication primitive differs by platform (utils.atomic_io): Windows renames
# (refuses an existing target; sharing holds carry WinError 5/32), POSIX hard-links then
# unlinks (os.rename would clobber). Faults are injected into the primitive the selected
# platform branch really calls; the other primitive must never see the final target.
PLATFORMS = {
    "windows": ("rename", lambda: _winerror(32)),
    # A realistic POSIX hold/denial: errno only, no winerror, so never a sharing retry.
    "posix": ("link", lambda: PermissionError(errno.EACCES, "injected EACCES")),
}


def _winerror(code):
    exc = PermissionError(errno.EACCES, "injected sharing violation")
    exc.winerror = code
    return exc


def _inject(monkeypatch, platform, *, failures, target_name="chapter.txt"):
    """Fail the platform's real publication primitive `failures` times for one target."""
    import utils.atomic_io
    monkeypatch.setattr(utils.atomic_io, "_WINDOWS", platform == "windows")
    op_name, make_error = PLATFORMS[platform]
    other_name = "link" if op_name == "rename" else "rename"
    real_op, real_other = getattr(os, op_name), getattr(os, other_name)
    calls, delays = [], []

    def faulty(source, target, *args, **kwargs):
        if Path(target).name == target_name:
            calls.append(Path(target).name)
            if len(calls) <= failures:
                raise make_error()
        return real_op(source, target, *args, **kwargs)

    def unexpected(source, target, *args, **kwargs):
        assert Path(target).name != target_name, f"{platform} publication must not use os.{other_name}"
        return real_other(source, target, *args, **kwargs)

    monkeypatch.setattr(os, op_name, faulty)
    monkeypatch.setattr(os, other_name, unexpected)
    monkeypatch.setattr(utils.atomic_io.time, "sleep", delays.append)
    return calls, delays


@pytest.mark.parametrize("platform", sorted(PLATFORMS))
def test_exhausted_publication_preserves_prepared_pair_then_recovers(tmp_path, monkeypatch, platform):
    import utils.atomic_io
    cp, src = create(tmp_path)
    out = Path(cp.output_dir)
    stage(cp, src)
    cp.prepare(src)
    prepared = cp.entry(src)
    staged_txt = out / prepared["staged"]["txt"]
    calls, delays = _inject(monkeypatch, platform, failures=99)
    try:
        with pytest.raises(PermissionError):
            cp.publish(src)
        if platform == "windows":
            # Real exhaustion: first attempt plus four bounded retries, exact backoff.
            assert len(calls) == 5
            assert delays == list(utils.atomic_io.SHARING_DELAYS) and sum(delays) <= 2
        else:
            # POSIX has no sharing violations: one attempt, no retry, no sleep.
            assert len(calls) == 1 and delays == []
        cp.record_failed(src, "PermissionError")
        entry = cp.entry(src)
        assert entry["status"] == "prepared" and entry["expected"] == prepared["expected"]
        assert entry["attempts"][-1]["outcome"] == "failed"
        assert (out / "chapter.pdf").exists() and not (out / "chapter.txt").exists()
        # The prepared TXT is preserved byte-for-byte for recovery.
        from core.run_manifest import fingerprint
        assert fingerprint(staged_txt)["sha256"] == prepared["expected"]["txt"]["sha256"]
        assert read_manifest(cp.path)["entries"][0]["status"] == "prepared"
    finally:
        cp.close()
    monkeypatch.undo()
    # Injection removed: the same run recovers into its original reserved paths.
    resumed = RunCheckpoint.resume(cp.output_dir, rules_digest="rules")
    try:
        resumed.publish(src)
        entry = resumed.entry(src)
        assert entry["status"] == "completed"
        resumed.verify_outputs(entry)
        assert sorted(p.name for p in out.glob("chapter*")) == ["chapter.pdf", "chapter.txt"]
        assert not staged_txt.exists()
    finally:
        resumed.close()


def test_windows_transient_sharing_hold_succeeds_on_real_rename(tmp_path, monkeypatch):
    import utils.atomic_io
    cp, src = create(tmp_path)
    try:
        stage(cp, src)
        cp.prepare(src)
        calls, delays = _inject(monkeypatch, "windows", failures=2)
        cp.publish(src)
        assert len(calls) == 3 and delays == list(utils.atomic_io.SHARING_DELAYS[:2])
        assert cp.entry(src)["status"] == "completed"
    finally:
        cp.close()


@pytest.mark.parametrize("platform", sorted(PLATFORMS))
def test_no_clobber_primitive_refuses_existing_destination_without_retry(tmp_path, monkeypatch, platform):
    import utils.atomic_io
    monkeypatch.setattr(utils.atomic_io, "_WINDOWS", platform == "windows")
    source, destination = tmp_path / "staged.txt", tmp_path / "final.txt"
    source.write_bytes(b"prepared")
    destination.write_bytes(b"unrelated external file")
    delays = []
    with pytest.raises(FileExistsError):
        utils.atomic_io.sharing_retry(lambda: utils.atomic_io.rename_no_clobber(source, destination),
                                      sleep=delays.append)
    assert destination.read_bytes() == b"unrelated external file"
    assert source.read_bytes() == b"prepared" and delays == []
    destination.unlink()
    utils.atomic_io.rename_no_clobber(source, destination)
    assert destination.read_bytes() == b"prepared" and not source.exists()


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


@pytest.mark.parametrize("failures,error", [(2, "winerror5"), (6, "winerror5"), (1, "posix")])
def test_atomic_manifest_publication_uses_same_bounded_windows_retries(tmp_path, monkeypatch, failures, error):
    import utils.atomic_io
    cp, src = create(tmp_path)
    before = cp.path.read_bytes()
    replace = os.replace
    attempts, delays = [], []
    def sharing(source, target):
        attempts.append(1)
        if len(attempts) <= failures:
            raise _winerror(5) if error == "winerror5" else PermissionError(errno.EACCES, "injected")
        return replace(source, target)
    monkeypatch.setattr(os, "replace", sharing)
    monkeypatch.setattr(utils.atomic_io.time, "sleep", delays.append)
    try:
        if failures == 2:
            cp.record_failed(src, "PermissionError")
            assert read_manifest(cp.path)["entries"][0]["status"] == "failed"
        else:
            with pytest.raises(CheckpointError):
                cp.record_failed(src, "PermissionError")
            assert cp.path.read_bytes() == before
            assert not list(Path(cp.output_dir).glob(".m-*.tmp"))
        assert len(attempts) == {2: 3, 6: 5, 1: 1}[failures]
        assert sum(delays) <= 2 and (error == "winerror5" or delays == [])
    finally:
        cp.close()
