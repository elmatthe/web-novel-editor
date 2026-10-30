"""Single-writer ownership uses kernel exclusion and process creation identity."""
import json
import os
import pytest
from core import run_lock
from core.run_lock import RunLock, LockConflict, StaleLock
from utils.atomic_io import sharing_retry


def test_live_owner_blocks_even_a_second_handle_in_same_process(tmp_path):
    with RunLock(tmp_path, "run") as owner:
        owner.assert_owned()
        with pytest.raises(LockConflict):
            RunLock(tmp_path, "run").acquire(recover=True)
    assert not (tmp_path / run_lock.LOCK_NAME).exists()


@pytest.mark.parametrize("probe", [("dead", None), ("live", "reused-pid")])
def test_stale_or_reused_pid_needs_confirmation_and_preserves_record(tmp_path, monkeypatch, probe):
    with RunLock(tmp_path, "run") as owner:
        record = dict(owner.metadata)
    path = tmp_path / run_lock.LOCK_NAME
    path.write_text(json.dumps(record), encoding="utf-8")
    real = run_lock.process_identity
    # Probe the saved owner as stale, but give this new owner its real identity.
    record["pid"] = os.getpid() + 123456
    path.write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(run_lock, "process_identity", lambda pid: probe if pid == record["pid"] else real(pid))
    before = path.read_bytes()
    with pytest.raises(StaleLock):
        RunLock(tmp_path, "run").acquire()
    assert path.read_bytes() == before
    with RunLock(tmp_path, "run").acquire(recover=True):
        assert len(list(tmp_path.glob(".run-lock.stale-*.json"))) == 1
        with pytest.raises(LockConflict):
            RunLock(tmp_path, "run").acquire(recover=True)


@pytest.mark.parametrize("mutation", ["malformed", "foreign", "unknown", "unverifiable_live", "missing_time", "ancient_live", "live"])
def test_uncertain_or_foreign_metadata_is_preserved(tmp_path, monkeypatch, mutation):
    with RunLock(tmp_path, "run") as owner:
        record = dict(owner.metadata)
    if mutation == "foreign":
        record["host"] = "another-host"
    elif mutation == "unknown":
        monkeypatch.setattr(run_lock, "process_identity", lambda pid: ("unknown", None))
    elif mutation == "unverifiable_live":
        monkeypatch.setattr(run_lock, "process_identity", lambda pid: ("live", None))
    elif mutation == "missing_time":
        record.pop("acquired_utc")
        record["process_creation"] = "proven-reused"
    elif mutation == "ancient_live":
        record["acquired_utc"] = "1900-01-01T00:00:00+00:00"
    path = tmp_path / run_lock.LOCK_NAME
    path.write_text("{" if mutation == "malformed" else json.dumps(record), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(LockConflict):
        RunLock(tmp_path, "run").acquire(recover=True)
    assert path.read_bytes() == before


def test_release_preserves_changed_owner_metadata(tmp_path):
    owner = RunLock(tmp_path, "run").acquire()
    path = tmp_path / run_lock.LOCK_NAME
    record = dict(owner.metadata, owner_token="someone-else")
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(LockConflict):
        owner.release()
    assert json.loads(path.read_text())["owner_token"] == "someone-else"


def test_real_child_crash_releases_kernel_guard_but_requires_stale_confirmation(tmp_path, offline_python):
    script = (
        "from core.run_lock import RunLock; import os,sys; "
        "lock=RunLock(sys.argv[1], 'crashed').acquire(); os._exit(0)"
    )
    env = dict(os.environ, PYTHONPATH=str(__import__('pathlib').Path(__file__).resolve().parents[2] / 'scripts'))
    child = offline_python.run(["-c", script, str(tmp_path)], env=env, capture_output=True, text=True)
    assert child.returncode == 0, child.stderr
    before = (tmp_path / run_lock.LOCK_NAME).read_bytes()
    with pytest.raises(StaleLock):
        RunLock(tmp_path, "crashed").acquire()
    assert (tmp_path / run_lock.LOCK_NAME).read_bytes() == before
    with RunLock(tmp_path, "crashed").acquire(recover=True):
        pass


def test_simultaneous_stale_recoveries_have_exactly_one_owner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    with RunLock(tmp_path, "run") as owner:
        record = dict(owner.metadata, process_creation="reused-creation")
    (tmp_path / run_lock.LOCK_NAME).write_text(json.dumps(record), encoding="utf-8")
    begin, hold = threading.Barrier(2), threading.Barrier(2)
    def recover():
        begin.wait(timeout=5)
        try:
            with RunLock(tmp_path, "run").acquire(recover=True):
                hold.wait(timeout=5)
                return "owned"
        except LockConflict:
            hold.wait(timeout=5)
            return "blocked"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: recover(), range(2)))
    assert sorted(results) == ["blocked", "owned"]


def test_real_child_cannot_mutate_a_parent_owned_run(tmp_path, offline_python):
    from pathlib import Path
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "scripts"))
    with RunLock(tmp_path, "run") as owner:
        before = (tmp_path / run_lock.LOCK_NAME).read_bytes()
        child = offline_python.run(["-c", "from core.run_lock import RunLock; import sys; RunLock(sys.argv[1], 'run').acquire(recover=True)", str(tmp_path)],
                                   env=env, capture_output=True, text=True)
        assert child.returncode != 0 and "Another writer" in child.stderr
        assert (tmp_path / run_lock.LOCK_NAME).read_bytes() == before
        owner.assert_owned()


@pytest.mark.parametrize("winerror,failures,calls", [(32, 2, 3), (5, 4, 5), (32, 6, 5), (112, 1, 1), (None, 1, 1)])
def test_sharing_retry_is_bounded_and_only_retries_windows_transients(winerror, failures, calls):
    attempts, delays, validations = [], [], []
    def operation():
        attempts.append(1)
        if len(attempts) <= failures:
            exc = OSError("injected")
            exc.winerror = winerror
            raise exc
        return "ok"
    if failures >= calls:
        with pytest.raises(OSError):
            sharing_retry(operation, validate=lambda: validations.append(1), sleep=delays.append)
    else:
        assert sharing_retry(operation, validate=lambda: validations.append(1), sleep=delays.append) == "ok"
    assert len(attempts) == len(validations) == calls
    assert len(delays) <= 4 and sum(delays) <= 2


@pytest.mark.parametrize("platform", ["nt", "posix"])
def test_no_clobber_publication_and_archiving_preserve_existing_files(tmp_path, monkeypatch, platform):
    from types import SimpleNamespace
    import utils.atomic_io as atomic_io
    source, destination = tmp_path / "staged", tmp_path / "external"
    source.write_bytes(b"owned staged output")
    destination.write_bytes(b"unrelated file")
    # NTFS supports hard links, so the POSIX no-clobber branch is exercised for real.
    if platform == "posix":
        monkeypatch.setattr(atomic_io, "os", SimpleNamespace(name="posix", link=os.link, rename=os.rename))
    elif os.name != "nt":
        pytest.skip("Windows no-clobber rename requires Windows")
    with pytest.raises(FileExistsError):
        atomic_io.rename_no_clobber(source, destination)
    assert source.read_bytes() == b"owned staged output"
    assert destination.read_bytes() == b"unrelated file"
    destination.unlink()
    atomic_io.rename_no_clobber(source, destination)
    assert not source.exists() and destination.read_bytes() == b"owned staged output"
