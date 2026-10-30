"""Schema-3 replacement of the schema-2 checkpoint contracts.

Prepared crash windows are in test_publication; locks in test_run_lock. These tests
retain state shape/privacy, strict refusal, atomic persistence, discovery and resume.
"""
import json
import os
from pathlib import Path
import pytest
from core.batch_runner import run_batch
from core.run_manifest import (
    ENTRY_KEYS, MANIFEST_NAME, SCHEMA_VERSION, ResumeOffer, RunCheckpoint,
    ManifestError, CheckpointError, find_resumable_run, load_manifest,
    manifest_path, plan_resume, read_manifest,
)
from core.output_plan import reserve_run_dir


def make_queue(tmp_path, count=3):
    paths = []
    for index in range(count):
        path = tmp_path / "inbox" / f"{index}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("A quiet synthetic chapter.\n\nClan Valor waited.", encoding="utf-8")
        paths.append(str(path))
    return paths


@pytest.fixture
def checkpoint(tmp_path):
    cp = RunCheckpoint(tmp_path / "out", make_queue(tmp_path), novel="Universal", clock=lambda: 1234.0)
    cp.start(formats=("txt",), rules_digest="rules")
    yield cp
    cp.close()


def complete(cp, source):
    cp.stage(source, "txt", lambda path: path.write_text("Synthetic corrected text.\n", encoding="utf-8"))
    cp.prepare(source)
    cp.publish(source)


def test_manifest_is_durable_before_processing_and_lives_in_original_run(checkpoint):
    assert checkpoint.path == Path(checkpoint.output_dir) / MANIFEST_NAME
    assert checkpoint.path == manifest_path(checkpoint.output_dir)
    data = read_manifest(checkpoint.path)
    assert data["schema_version"] == SCHEMA_VERSION == 3
    assert data["queue"] == checkpoint.queue and data["next_index"] == 0
    assert all(e["status"] == "pending" for e in data["entries"])


def test_every_completed_file_is_persisted_and_has_all_hashes(checkpoint):
    for index, source in enumerate(checkpoint.queue, 1):
        complete(checkpoint, source)
        data = read_manifest(checkpoint.path)
        assert data["next_index"] == index
        entry = data["entries"][index - 1]
        assert entry["status"] == "completed"
        assert entry["expected"]["txt"]["sha256"]
        assert entry["source_identity"]["sha256"]
        assert set(entry) == set(ENTRY_KEYS)


def test_manifest_contains_no_chapter_text_provider_or_credentials(checkpoint):
    complete(checkpoint, checkpoint.queue[0])
    checkpoint.record_failed(checkpoint.queue[1], "Private prose must never be persisted or logged.")
    raw = checkpoint.path.read_text(encoding="utf-8")
    for prohibited in ("quiet synthetic", "Clan Valor waited", "Synthetic corrected", "Private prose", "provider", "quota", "api_key"):
        assert prohibited not in raw
    assert read_manifest(checkpoint.path)["entries"][1]["attempts"][-1]["code"] == "processing_error"


def test_single_word_private_failure_details_are_not_written_to_manifest(checkpoint):
    checkpoint.record_failed(checkpoint.queue[0], "PrivateChapterWord")
    assert "PrivateChapterWord" not in checkpoint.path.read_text(encoding="utf-8")
    assert checkpoint.entry(checkpoint.queue[0])["attempts"][-1]["code"] == "processing_error"


def test_failed_skipped_and_completed_items_have_terminal_state_without_inflated_totals(checkpoint):
    cp = checkpoint
    complete(cp, cp.queue[0])
    cp.record_failed(cp.queue[1], "PermissionError")
    cp.record_failed(cp.queue[1], "PermissionError")
    cp.record_skipped(cp.queue[2], "empty")
    cp.finish()
    data = read_manifest(cp.path)
    assert data["next_index"] == 3 and data["complete"]
    assert data["stopped_reason"] == "finished_with_errors"
    assert [e["status"] for e in data["entries"]] == ["completed", "failed", "skipped"]
    assert len(data["entries"][1]["attempts"]) == 2
    assert not data["entries"][1]["expected"]


def test_stopped_run_retains_full_queue_and_completed_history(checkpoint):
    cp = checkpoint
    complete(cp, cp.queue[0])
    cp.finish(stopped=True)
    cp.close()
    offer = find_resumable_run(cp.output_dir)
    assert offer.available and offer.completed_count == 1
    assert offer.remaining == tuple(cp.queue[1:])
    assert offer.stopped_reason == "user_stop"
    plan = plan_resume(offer)
    assert plan["pdf_paths"] == cp.queue  # full queue, never the unprocessed slice
    assert plan["output_dir"] == cp.output_dir and plan["resume"]
    before = cp.path.read_bytes()
    with pytest.raises(ManifestError):
        RunCheckpoint(cp.output_dir, cp.queue, start_index=1)
    assert cp.path.read_bytes() == before


def test_declining_discovery_does_not_mutate_the_run(checkpoint, tmp_path):
    checkpoint.finish(stopped=True)
    before = checkpoint.path.read_bytes()
    assert find_resumable_run(tmp_path).available
    assert reserve_run_dir(tmp_path, "new").is_dir()
    assert checkpoint.path.read_bytes() == before


@pytest.mark.parametrize("raw", ["{", "[]", "null", '{"schema_version":99}', '{"schema_version":true}',
                                  '{"schema_version":1,"provider":"old-cloud"}', '{"schema_version":2}'])
def test_corrupt_future_and_legacy_manifests_are_refused_without_modification(tmp_path, raw):
    path = tmp_path / MANIFEST_NAME
    path.write_text(raw, encoding="utf-8")
    before = path.read_bytes()
    assert load_manifest(path) is None
    with pytest.raises(ManifestError):
        RunCheckpoint.resume(tmp_path, rules_digest="rules")
    assert path.read_bytes() == before
    assert not find_resumable_run(tmp_path).available


@pytest.mark.parametrize("mutation", ["queue", "digest", "entry", "output", "destination", "index", "options", "hash"])
def test_structurally_invalid_manifests_are_refused(checkpoint, mutation):
    data = checkpoint.payload()
    if mutation == "queue":
        data["queue"] = [1]
    elif mutation == "digest":
        data["queue_digest"] = "changed"
    elif mutation == "entry":
        data["entries"][0]["status"] = "unknown"
    elif mutation == "output":
        data["entries"][0]["outputs"]["txt"] = "../escaped.txt"
    elif mutation == "destination":
        data["output_dir"] = str(Path(checkpoint.output_dir).parent)
    elif mutation == "index":
        data["next_index"] = True
    elif mutation == "options":
        data["run"]["options"]["formats"] = []
    elif mutation == "hash":
        data["entries"][0]["source_identity"]["sha256"] = "invalid"
    checkpoint.path.write_text(json.dumps(data), encoding="utf-8")
    assert load_manifest(checkpoint.path) is None


def test_missing_unreadable_and_orphan_manifests_are_not_offered(tmp_path):
    assert load_manifest(tmp_path / MANIFEST_NAME) is None
    assert load_manifest(tmp_path) is None
    (tmp_path / ".m-orphan.tmp").write_text("{}")
    assert not find_resumable_run(tmp_path).available
    assert not find_resumable_run(tmp_path / "missing").available
    with pytest.raises(ManifestError):
        plan_resume(ResumeOffer(False, "none"))


@pytest.mark.parametrize("boundary", ["replace", "fsync"])
def test_failed_atomic_persistence_preserves_old_manifest_and_memory(checkpoint, monkeypatch, boundary):
    before = checkpoint.path.read_bytes()
    snapshot = checkpoint.payload()
    def fail(*args):
        raise OSError("injected permanent persistence failure")
    monkeypatch.setattr("utils.settings.os." + boundary, fail)
    with pytest.raises(CheckpointError):
        checkpoint.record_failed(checkpoint.queue[0], "OSError")
    assert checkpoint.path.read_bytes() == before and checkpoint.payload() == snapshot
    assert not list(checkpoint.path.parent.glob(".m-*.tmp"))


def test_source_hash_detects_same_size_same_timestamp_replacement(checkpoint):
    source = Path(checkpoint.queue[0])
    info = source.stat()
    source.write_bytes(source.read_bytes().replace(b"quiet", b"still"))
    os.utime(source, ns=(info.st_atime_ns, info.st_mtime_ns))
    checkpoint.close()
    with pytest.raises(ManifestError, match="Source bytes"):
        RunCheckpoint.resume(checkpoint.output_dir, rules_digest="rules")


@pytest.mark.parametrize("completed", [False, True])
def test_missing_original_source_refuses_resume_and_is_reported(checkpoint, completed):
    if completed:
        complete(checkpoint, checkpoint.queue[0])
    Path(checkpoint.queue[0]).unlink()
    checkpoint.close()
    with pytest.raises(ManifestError, match="missing"):
        RunCheckpoint.resume(checkpoint.output_dir, rules_digest="rules")


def test_finished_successful_run_is_not_offered(checkpoint):
    for source in checkpoint.queue:
        complete(checkpoint, source)
    checkpoint.finish()
    assert read_manifest(checkpoint.path)["complete"]
    assert not find_resumable_run(checkpoint.output_dir).available


def test_finished_skipped_only_run_is_not_offered_as_retryable(checkpoint):
    for source in checkpoint.queue:
        checkpoint.record_skipped(source, "empty")
    checkpoint.finish()
    assert not find_resumable_run(checkpoint.output_dir).available


def test_newest_incomplete_run_is_discovered(tmp_path):
    for name, stamp in [("older", 1000000), ("newer", 2000000)]:
        cp = RunCheckpoint(tmp_path / name, make_queue(tmp_path / (name + "-inputs")), novel=name)
        cp.start(formats=("txt",), rules_digest="rules")
        cp.finish(stopped=True)
        cp.close()
        os.utime(cp.path, (stamp, stamp))
    assert find_resumable_run(tmp_path).novel == "newer"


def test_default_batch_is_durable_and_dry_run_creates_nothing(tmp_path):
    queue = make_queue(tmp_path)
    result = run_batch(queue, str(tmp_path / "out"), output_formats=("txt",))
    assert result["succeeded"] == 3
    assert read_manifest(tmp_path / "out" / MANIFEST_NAME)["complete"]
    result = run_batch(queue, str(tmp_path / "dry"), dry_run=True)
    assert result["succeeded"] == 3 and not (tmp_path / "dry").exists()
