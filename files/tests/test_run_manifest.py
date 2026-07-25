"""Plan 2b Phase 5 — checkpointed runs: the atomic run manifest and resume.

Offline and hermetic. No provider SDK, no key, no network, and nothing waits: the
checkpoint takes an injected clock, and the quota-stop path is driven by a fake limiter
signal rather than a real limiter.

**Every ``ai.*`` / ``core.*`` import in this file is at module level**, for the reason
recorded in ``test_rate_limiting.py``: ``test_ai_foundation`` pops and re-imports the
``ai`` package, and a module holding two generations of the same class fails only in the
full-suite run.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

import core.batch_runner as batch_runner
from ai.editor import AIEditor, EditorOptions
from ai.errors import DailyQuotaExhausted, ProviderUnavailable
from ai.models import (
    CompletionResult,
    ProviderCapabilities,
    ProviderStatus,
    RunPolicy,
)
from ai.rate_limits import LimitKind, QuotaStop
from ai.redaction import forget_secrets, register_secret
from core.batch_runner import run_batch
from core.novel_registry import NovelDispatch
from pdf.extractor import extract_text_from_pdf
from utils.file_utils import next_numbered_output_dir
from core.run_manifest import (
    MANIFEST_NAME,
    SCHEMA_VERSION,
    ResumeOffer,
    RunCheckpoint,
    find_resumable_run,
    load_manifest,
    manifest_path,
    plan_resume,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "files" / "test-files" / "shadow_slave"


class FakeClock:
    def __init__(self, start: float = 1_800_000_000.0):
        self.now = start

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


def make_queue(tmp_path: Path, count: int = 3) -> list[str]:
    """Real files on disk, so existence and identity checks are exercised."""
    paths = []
    for index in range(count):
        path = tmp_path / "inbox" / f"chapter-{index + 1}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 fake chapter " + str(index).encode())
        paths.append(str(path))
    return paths


def make_checkpoint(tmp_path: Path, queue=None, **overrides) -> RunCheckpoint:
    queue = queue if queue is not None else make_queue(tmp_path)
    options = {
        "novel": "Shadow Slave",
        "provider": "groq",
        "model_id": "llama-3.3-70b-versatile",
        "prompt_version": "1.0",
        "gate_version": "1.0",
        "ai_policy": "prefer_ai",
        "clock": FakeClock(),
    }
    options.update(overrides)
    return RunCheckpoint(str(tmp_path / "out"), queue, **options)


# --------------------------------------------------------------------------
# The manifest: where it lives, what it holds
# --------------------------------------------------------------------------
def test_the_manifest_lives_in_the_run_output_folder(tmp_path):
    checkpoint = make_checkpoint(tmp_path)
    assert checkpoint.path == tmp_path / "out" / MANIFEST_NAME
    assert manifest_path(tmp_path / "out") == tmp_path / "out" / MANIFEST_NAME


def test_no_manifest_exists_before_the_first_file_completes(tmp_path):
    checkpoint = make_checkpoint(tmp_path)
    assert not checkpoint.path.exists()


def test_a_manifest_is_written_after_each_completed_file(tmp_path):
    queue = make_queue(tmp_path, 3)
    checkpoint = make_checkpoint(tmp_path, queue)
    for index, source in enumerate(queue, start=1):
        checkpoint.record_completed(source, f"{tmp_path}/out/chapter-{index}.pdf")
        payload = load_manifest(checkpoint.path)
        assert payload is not None
        assert payload["next_index"] == index
        assert len(payload["entries"]) == index


def test_the_manifest_carries_every_field_the_plan_requires(tmp_path):
    queue = make_queue(tmp_path, 2)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_completed(queue[0], f"{tmp_path}/out/one.pdf", ai_status="accepted")
    payload = load_manifest(checkpoint.path)

    # run identity
    assert payload["run"]["provider"] == "groq"
    assert payload["run"]["model_id"] == "llama-3.3-70b-versatile"
    assert payload["run"]["prompt_version"] == "1.0"
    assert payload["run"]["gate_version"] == "1.0"
    assert payload["run"]["novel"] == "Shadow Slave"
    # queue position
    assert payload["queue"] == queue
    assert payload["next_index"] == 1
    # per-file record
    entry = payload["entries"][0]
    assert entry["source"] == queue[0]
    assert entry["status"] == "completed"
    assert entry["output"] == f"{tmp_path}/out/one.pdf"
    assert entry["ai_status"] == "accepted"
    assert entry["size"] == os.path.getsize(queue[0])


def test_the_manifest_records_accepted_and_fallback_separately(tmp_path):
    queue = make_queue(tmp_path, 2)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_completed(queue[0], "a.pdf", ai_status="accepted")
    checkpoint.record_completed(queue[1], "b.pdf", ai_status="fallback")
    statuses = [e["ai_status"] for e in load_manifest(checkpoint.path)["entries"]]
    assert statuses == ["accepted", "fallback"]


def test_a_failed_file_is_recorded_as_failed_and_still_advances_the_queue(tmp_path):
    """Otherwise a resumed run would retry a corrupt PDF forever."""
    queue = make_queue(tmp_path, 3)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_failed(queue[0], "PdfReadError: not a PDF")
    payload = load_manifest(checkpoint.path)
    assert payload["entries"][0]["status"] == "failed"
    assert payload["next_index"] == 1


def test_a_skipped_file_is_recorded_as_skipped_and_still_advances_the_queue(tmp_path):
    queue = make_queue(tmp_path, 3)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_skipped(queue[0], "image-only/empty")
    payload = load_manifest(checkpoint.path)
    assert payload["entries"][0]["status"] == "skipped"
    assert payload["next_index"] == 1


def test_only_a_completed_status_ever_names_an_output_file(tmp_path):
    queue = make_queue(tmp_path, 2)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_failed(queue[0], "boom")
    checkpoint.record_skipped(queue[1], "not found")
    for entry in load_manifest(checkpoint.path)["entries"]:
        assert entry["output"] == ""


def test_a_run_that_reaches_the_end_of_its_queue_is_marked_complete(tmp_path):
    queue = make_queue(tmp_path, 2)
    checkpoint = make_checkpoint(tmp_path, queue)
    for source in queue:
        checkpoint.record_completed(source, "x.pdf")
    checkpoint.finish()
    assert load_manifest(checkpoint.path)["complete"] is True


def test_a_stopped_run_is_not_marked_complete(tmp_path):
    queue = make_queue(tmp_path, 3)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_completed(queue[0], "x.pdf")
    checkpoint.finish(stopped=True)
    payload = load_manifest(checkpoint.path)
    assert payload["complete"] is False
    assert payload["stopped_reason"] == "user_stop"


# --------------------------------------------------------------------------
# No key, no chapter text
# --------------------------------------------------------------------------
def test_the_manifest_holds_no_api_key_and_no_chapter_text(tmp_path):
    """A real key is registered and real prose is passed through the recording calls;
    neither may reach the file."""
    key = "gsk_LIVEKEYSHAPED000000000000000000000000000000000000"
    prose = "Sunny opened his eyes and the Nightmare Spell burned on his palm."
    register_secret(key)
    try:
        queue = make_queue(tmp_path, 2)
        checkpoint = make_checkpoint(tmp_path, queue, model_id=f"llama-{key[:8]}")
        checkpoint.record_completed(queue[0], "out.pdf", ai_status="accepted")
        checkpoint.record_failed(queue[1], f"InvalidResponse: rejected near '{prose}'")
        raw = checkpoint.path.read_text(encoding="utf-8")
    finally:
        forget_secrets()
    assert key not in raw
    assert prose not in raw
    assert "Nightmare Spell" not in raw


def test_the_manifest_has_no_field_that_could_carry_chapter_text(tmp_path):
    queue = make_queue(tmp_path, 1)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_completed(queue[0], "out.pdf")
    payload = load_manifest(checkpoint.path)
    allowed_entry_keys = {
        "source", "status", "output", "ai_status", "size", "mtime_ns", "recorded_at",
    }
    for entry in payload["entries"]:
        assert set(entry) <= allowed_entry_keys, "an unexpected field could carry text"


def test_a_failure_reason_is_accepted_and_deliberately_not_persisted(tmp_path):
    """A provider failure message can quote the candidate text, which is precisely how
    chapter text would leak into a manifest. The reason is taken (so call sites read
    naturally) and dropped; the JSONL sidecar and the GUI log already carry the detail."""
    queue = make_queue(tmp_path, 1)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_failed(queue[0], "InvalidResponse: rejected 'the candidate text'")
    raw = checkpoint.path.read_text(encoding="utf-8")
    assert "candidate text" not in raw
    assert "InvalidResponse" not in raw


# --------------------------------------------------------------------------
# load_manifest never raises and never repairs
# --------------------------------------------------------------------------
def test_a_missing_manifest_loads_as_none(tmp_path):
    assert load_manifest(tmp_path / "nope" / MANIFEST_NAME) is None


def test_a_truncated_manifest_loads_as_none(tmp_path):
    path = tmp_path / MANIFEST_NAME
    path.write_text('{"schema_version": 1, "queue": [', encoding="utf-8")
    assert load_manifest(path) is None


def test_a_manifest_that_is_not_an_object_loads_as_none(tmp_path):
    path = tmp_path / MANIFEST_NAME
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_manifest(path) is None


def test_a_manifest_from_a_newer_build_is_refused_rather_than_half_read(tmp_path):
    path = tmp_path / MANIFEST_NAME
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION + 1, "queue": ["a"],
                    "next_index": 0, "entries": []}),
        encoding="utf-8",
    )
    assert load_manifest(path) is None


@pytest.mark.parametrize(
    "payload",
    [
        {"queue": ["a"], "next_index": 0, "entries": []},                  # no version
        {"schema_version": "1", "queue": ["a"], "next_index": 0, "entries": []},
        {"schema_version": SCHEMA_VERSION, "next_index": 0, "entries": []},  # no queue
        {"schema_version": SCHEMA_VERSION, "queue": [], "next_index": 0, "entries": []},
        {"schema_version": SCHEMA_VERSION, "queue": [1, 2], "next_index": 0, "entries": []},
        {"schema_version": SCHEMA_VERSION, "queue": ["a"], "entries": []},   # no index
        {"schema_version": SCHEMA_VERSION, "queue": ["a"], "next_index": -1, "entries": []},
        {"schema_version": SCHEMA_VERSION, "queue": ["a"], "next_index": 9, "entries": []},
        {"schema_version": SCHEMA_VERSION, "queue": ["a"], "next_index": 0, "entries": {}},
    ],
)
def test_a_structurally_invalid_manifest_loads_as_none(tmp_path, payload):
    path = tmp_path / MANIFEST_NAME
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_manifest(path) is None


def test_an_unreadable_manifest_loads_as_none_rather_than_raising(tmp_path):
    """A directory where the file should be is the portable way to make a read fail."""
    path = tmp_path / MANIFEST_NAME
    path.mkdir()
    assert load_manifest(path) is None


# --------------------------------------------------------------------------
# Atomic writes and safe-to-close
# --------------------------------------------------------------------------
def test_the_manifest_is_written_by_temp_file_and_rename_not_in_place(tmp_path):
    """Proven by observation: the real file is only ever created by os.replace."""
    queue = make_queue(tmp_path, 2)
    checkpoint = make_checkpoint(tmp_path, queue)
    renames: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy(src, dst, *args, **kwargs):
        renames.append((str(src), str(dst)))
        return real_replace(src, dst, *args, **kwargs)

    original = os.replace
    os.replace = spy
    try:
        checkpoint.record_completed(queue[0], "one.pdf")
    finally:
        os.replace = original
    assert renames, "the manifest was written without a rename"
    assert renames[-1][1] == str(checkpoint.path)
    assert renames[-1][0] != str(checkpoint.path)


def test_a_kill_between_the_temp_write_and_the_rename_leaves_the_old_manifest_intact(
    tmp_path, monkeypatch
):
    """The dangerous instant: the new payload is on disk but not yet in place."""
    queue = make_queue(tmp_path, 3)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_completed(queue[0], "one.pdf")
    before = checkpoint.path.read_bytes()

    def die(_src, _dst, *args, **kwargs):
        raise OSError("killed between write and rename")

    monkeypatch.setattr(os, "replace", die)
    with pytest.raises(OSError):
        checkpoint.record_completed(queue[1], "two.pdf")
    monkeypatch.undo()

    assert checkpoint.path.read_bytes() == before, "the previous manifest was damaged"
    payload = load_manifest(checkpoint.path)
    assert payload is not None and payload["next_index"] == 1


def test_a_kill_between_the_temp_write_and_the_rename_leaves_no_temp_residue(
    tmp_path, monkeypatch
):
    queue = make_queue(tmp_path, 3)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_completed(queue[0], "one.pdf")

    monkeypatch.setattr(
        os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("killed"))
    )
    with pytest.raises(OSError):
        checkpoint.record_completed(queue[1], "two.pdf")
    monkeypatch.undo()

    assert list(checkpoint.path.parent.glob("*.tmp")) == []


def test_an_orphaned_temp_file_is_never_mistaken_for_a_manifest(tmp_path):
    queue = make_queue(tmp_path, 3)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_completed(queue[0], "one.pdf")
    orphan = checkpoint.path.parent / f".{MANIFEST_NAME}.abc123.tmp"
    orphan.write_text("{ this is a half written payload", encoding="utf-8")

    offer = find_resumable_run(tmp_path)
    assert offer.available is True
    assert offer.manifest_path == checkpoint.path


def test_a_kill_after_the_rename_leaves_a_complete_loadable_manifest(tmp_path):
    queue = make_queue(tmp_path, 3)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_completed(queue[0], "one.pdf")
    checkpoint.record_completed(queue[1], "two.pdf")
    # No finish() call at all — this is what an abrupt close looks like.
    payload = load_manifest(checkpoint.path)
    assert payload is not None
    assert payload["next_index"] == 2
    assert payload["complete"] is False


def test_closing_mid_run_leaves_a_manifest_that_resumes_from_the_right_place(tmp_path):
    queue = make_queue(tmp_path, 5)
    checkpoint = make_checkpoint(tmp_path, queue)
    for index in range(2):
        checkpoint.record_completed(queue[index], f"{index}.pdf")
    offer = find_resumable_run(tmp_path)
    assert offer.available is True
    assert offer.remaining == tuple(queue[2:])
    assert offer.completed_count == 2


# --------------------------------------------------------------------------
# Resume: offered, declined, absent, corrupt
# --------------------------------------------------------------------------
def test_resume_is_offered_when_the_manifest_and_its_inputs_both_exist(tmp_path):
    queue = make_queue(tmp_path, 4)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_completed(queue[0], "one.pdf")

    offer = find_resumable_run(tmp_path)
    assert offer.available is True
    assert offer.output_dir == str(tmp_path / "out")
    assert offer.novel == "Shadow Slave"
    assert offer.missing_inputs == ()


def test_resuming_continues_into_the_same_output_folder_not_a_fresh_one(tmp_path):
    queue = make_queue(tmp_path, 4)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_completed(queue[0], "one.pdf")

    plan = plan_resume(find_resumable_run(tmp_path))
    assert plan["output_dir"] == str(tmp_path / "out")
    assert plan["pdf_paths"] == queue[1:]
    assert plan["novel_name"] == "Shadow Slave"


def test_declining_a_resume_leaves_the_manifest_untouched_for_a_fresh_run(tmp_path):
    """Declining is not a call — the caller simply takes the normal fresh-run path.
    What must hold is that nothing was mutated by merely *offering*."""
    queue = make_queue(tmp_path, 4)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_completed(queue[0], "one.pdf")
    before = checkpoint.path.read_bytes()

    offer = find_resumable_run(tmp_path)
    assert offer.available is True
    # ... the user says no. A fresh run allocates its own folder and never touches this.
    fresh = next_numbered_output_dir(tmp_path, "shadow-slave")
    assert Path(fresh) != Path(offer.output_dir)
    assert checkpoint.path.read_bytes() == before


def test_a_fresh_run_after_declining_gets_the_next_numbered_folder(tmp_path):
    (tmp_path / "shadow-slave-1").mkdir()
    (tmp_path / "shadow-slave-2").mkdir()
    assert next_numbered_output_dir(tmp_path, "shadow-slave").name == "shadow-slave-3"


def test_no_manifest_anywhere_means_no_offer(tmp_path):
    (tmp_path / "shadow-slave-1").mkdir()
    offer = find_resumable_run(tmp_path)
    assert offer.available is False
    assert "No previous run" in offer.reason


def test_a_missing_search_directory_means_no_offer_rather_than_a_crash(tmp_path):
    offer = find_resumable_run(tmp_path / "does-not-exist")
    assert offer.available is False


def test_a_corrupt_manifest_falls_back_to_a_fresh_run_rather_than_raising(tmp_path):
    folder = tmp_path / "shadow-slave-1"
    folder.mkdir()
    (folder / MANIFEST_NAME).write_text('{"schema_version": 1, "queue": [', encoding="utf-8")
    offer = find_resumable_run(tmp_path)
    assert offer.available is False


def test_a_wrong_schema_manifest_falls_back_to_a_fresh_run(tmp_path):
    folder = tmp_path / "shadow-slave-1"
    folder.mkdir()
    (folder / MANIFEST_NAME).write_text(
        json.dumps({"schema_version": 99, "queue": ["a"], "next_index": 0, "entries": []}),
        encoding="utf-8",
    )
    assert find_resumable_run(tmp_path).available is False


def test_a_finished_run_is_not_offered_for_resume(tmp_path):
    queue = make_queue(tmp_path, 2)
    checkpoint = make_checkpoint(tmp_path, queue)
    for source in queue:
        checkpoint.record_completed(source, "x.pdf")
    checkpoint.finish()
    offer = find_resumable_run(tmp_path)
    assert offer.available is False
    assert "finished" in offer.reason


def test_a_run_whose_remaining_inputs_all_vanished_is_not_offered(tmp_path):
    queue = make_queue(tmp_path, 3)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_completed(queue[0], "one.pdf")
    for source in queue[1:]:
        os.remove(source)
    offer = find_resumable_run(tmp_path)
    assert offer.available is False
    assert offer.missing_inputs == tuple(queue[1:])


def test_a_run_with_some_inputs_missing_is_still_offered_and_reports_them(tmp_path):
    """Refusing a 2,000-chapter resume because one file moved is a worse outcome than
    letting the runner skip it, which it already does honestly."""
    queue = make_queue(tmp_path, 4)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.record_completed(queue[0], "one.pdf")
    os.remove(queue[2])
    offer = find_resumable_run(tmp_path)
    assert offer.available is True
    assert offer.missing_inputs == (queue[2],)


def test_planning_a_resume_that_is_not_available_is_refused_outright(tmp_path):
    with pytest.raises(ValueError):
        plan_resume(ResumeOffer(False, "nothing to resume"))


def test_the_newest_incomplete_run_is_the_one_offered(tmp_path):
    old_queue = make_queue(tmp_path / "a", 3)
    new_queue = make_queue(tmp_path / "b", 3)
    older = RunCheckpoint(str(tmp_path / "shadow-slave-1"), old_queue, novel="Old",
                          clock=FakeClock())
    older.record_completed(old_queue[0], "x.pdf")
    newer = RunCheckpoint(str(tmp_path / "shadow-slave-2"), new_queue, novel="New",
                          clock=FakeClock())
    newer.record_completed(new_queue[0], "x.pdf")
    os.utime(older.path, (1_000_000, 1_000_000))
    os.utime(newer.path, (2_000_000, 2_000_000))

    offer = find_resumable_run(tmp_path)
    assert offer.novel == "New"


# --------------------------------------------------------------------------
# The Phase 4 seam: QuotaStop
# --------------------------------------------------------------------------
def make_quota_stop(*, is_daily=True, kind="tokens_per_day", reset_known=False,
                    reset_seconds=None, reason="daily quota used up (TPD)"):
    """A real Phase 4 QuotaStop, built without a limiter."""
    return QuotaStop(
        provider="groq",
        model_id="llama-3.3-70b-versatile",
        kind=LimitKind(kind),
        reason=reason,
        reset_seconds=reset_seconds,
        reset_known=reset_known,
        is_daily=is_daily,
        observed_monotonic=1234.5,
        observed_wall=1_800_000_500.0,
    )


def test_a_daily_quota_stop_writes_the_manifest_immediately(tmp_path):
    queue = make_queue(tmp_path, 5)
    checkpoint = make_checkpoint(tmp_path, queue)
    checkpoint.on_quota_stop(make_quota_stop())
    payload = load_manifest(checkpoint.path)
    assert payload is not None
    assert payload["stopped_reason"] == "daily_quota"
    assert payload["quota_stop"]["kind"] == "tokens_per_day"
    assert payload["quota_stop"]["is_daily"] is True


def test_a_quota_stop_sets_the_runs_stop_event_so_the_batch_halts_at_the_safe_seam(
    tmp_path,
):
    stop = threading.Event()
    checkpoint = make_checkpoint(tmp_path, stop_event=stop)
    assert not stop.is_set()
    checkpoint.on_quota_stop(make_quota_stop())
    assert stop.is_set()


def test_a_quota_stop_never_waits(tmp_path):
    """No sleep of any kind: the run stops and the app can close."""
    import time as real_time

    checkpoint = make_checkpoint(tmp_path, stop_event=threading.Event())
    started = real_time.monotonic()
    checkpoint.on_quota_stop(make_quota_stop(reset_seconds=86_400.0, reset_known=True))
    assert real_time.monotonic() - started < 1.0


def test_an_unknown_reset_time_is_carried_through_as_unknown(tmp_path):
    checkpoint = make_checkpoint(tmp_path)
    checkpoint.on_quota_stop(make_quota_stop(reset_known=False, reset_seconds=None))
    payload = load_manifest(checkpoint.path)
    assert payload["quota_stop"]["reset_known"] is False
    assert payload["quota_stop"]["reset_seconds"] is None


def test_an_over_long_wait_stop_is_recorded_but_not_as_a_daily_quota(tmp_path):
    checkpoint = make_checkpoint(tmp_path)
    checkpoint.on_quota_stop(
        make_quota_stop(is_daily=False, kind="requests_per_minute", reset_seconds=4_000.0)
    )
    payload = load_manifest(checkpoint.path)
    assert payload["stopped_reason"] == "long_wait"
    assert payload["quota_stop"]["is_daily"] is False


def test_the_quota_stop_survives_the_next_files_checkpoint_write(tmp_path):
    """The in-flight chapter finishes and checkpoints AFTER the quota stop fires; that
    later whole-file write must carry the quota stop forward, not erase it."""
    queue = make_queue(tmp_path, 5)
    checkpoint = make_checkpoint(tmp_path, queue, stop_event=threading.Event())
    checkpoint.on_quota_stop(make_quota_stop())
    checkpoint.record_completed(queue[0], "one.pdf", ai_status="fallback")
    payload = load_manifest(checkpoint.path)
    assert payload["quota_stop"] is not None
    assert payload["stopped_reason"] == "daily_quota"
    assert payload["next_index"] == 1


def test_the_quota_stop_record_in_the_manifest_carries_no_key(tmp_path):
    key = "gsk_LIVEKEYSHAPED000000000000000000000000000000000000"
    register_secret(key)
    try:
        checkpoint = make_checkpoint(tmp_path)
        checkpoint.on_quota_stop(make_quota_stop(reason=f"quota gone for {key}"))
        raw = checkpoint.path.read_text(encoding="utf-8")
    finally:
        forget_secrets()
    assert key not in raw


def test_a_foreign_object_on_the_quota_seam_does_not_crash_the_run(tmp_path):
    checkpoint = make_checkpoint(tmp_path, stop_event=threading.Event())
    checkpoint.on_quota_stop(object())
    assert load_manifest(checkpoint.path) is not None


def test_the_manifest_module_imports_no_rate_limits_module():
    """QuotaStop is consumed duck-typed, so Phase 4's public shape stays untouched."""
    source = (
        REPO_ROOT / "scripts" / "Universal" / "core" / "run_manifest.py"
    ).read_text(encoding="utf-8")
    imports = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from ")) and "rate_limits" in line
    ]
    assert imports == []


# --------------------------------------------------------------------------
# The batch_runner seam — additive, inert when absent
# --------------------------------------------------------------------------
BASELINE = (
    "Chapter 1: Test.\n\n"
    "After the very long journey through the silent city, he walk home alone. "
    "The lamps remained bright while the quiet road stretched toward the distant gate."
)


class SeamProvider:
    """Minimal 2a provider; optionally raises on the Nth chapter."""

    def __init__(self, *, transform=None, error_on=None, error=None):
        self.transform = transform or (lambda text: text)
        self.error_on = error_on
        self.error = error
        self.complete_calls = 0

    def capabilities(self):
        return ProviderCapabilities("fake", True, ("fake-1",), 5000, 2000)

    def health_check(self):
        return ProviderStatus.OK

    def list_models(self):
        return ["fake-1"]

    def complete(self, request):
        self.complete_calls += 1
        if self.error_on is not None and self.complete_calls == self.error_on:
            raise self.error
        return CompletionResult(self.transform(request.text), "fake-1", 0.01, "stop", False)


def seam_editor(provider, policy=RunPolicy.PREFER_AI):
    return AIEditor(
        lambda: provider,
        EditorOptions("fake-1", policy, request_overhead_tokens=0, safety_margin_tokens=0),
    )


def seam_dispatch():
    return NovelDispatch(
        display_name="Universal",
        run_pipeline=lambda text, lexicon, **kwargs: text,
        canonical_names=frozenset(),
        index_filename="",
        has_profile=False,
    )


def wire(monkeypatch, built, *, baseline=BASELINE, build=None):
    monkeypatch.setattr(batch_runner, "extract_text_from_pdf", lambda _path: baseline)
    monkeypatch.setattr(batch_runner, "resolve_dispatch", lambda _name: seam_dispatch())
    monkeypatch.setattr(
        batch_runner,
        "build_pdf",
        build or (lambda text, path: built.append((text, path))),
    )


def seam_inputs(tmp_path: Path, count=3):
    paths = []
    for index in range(count):
        path = tmp_path / "src" / f"{index}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-source")
        paths.append(str(path))
    return paths


def test_a_run_without_a_checkpoint_writes_no_manifest_and_is_unchanged(
    tmp_path, monkeypatch
):
    """The seam must be inert by omission, exactly as the 2a ai_editor seam is."""
    built = []
    wire(monkeypatch, built)
    inputs = seam_inputs(tmp_path, 2)

    summary = run_batch(inputs, str(tmp_path / "out"))

    assert summary["succeeded"] == 2
    assert [text for text, _path in built] == [BASELINE, BASELINE]
    assert not (tmp_path / "out" / MANIFEST_NAME).exists()


def test_the_manifest_is_written_after_each_completed_file_in_a_real_run(
    tmp_path, monkeypatch
):
    built = []
    wire(monkeypatch, built)
    inputs = seam_inputs(tmp_path, 3)
    seen: list[int] = []

    def spy_build(text, path):
        built.append((text, path))
        payload = load_manifest(tmp_path / "out" / MANIFEST_NAME)
        seen.append(-1 if payload is None else payload["next_index"])

    monkeypatch.setattr(batch_runner, "build_pdf", spy_build)
    checkpoint = RunCheckpoint(str(tmp_path / "out"), inputs, clock=FakeClock())

    run_batch(inputs, str(tmp_path / "out"), checkpoint=checkpoint)

    # At each build the manifest still reflects only the FILES ALREADY FINISHED.
    assert seen == [-1, 1, 2]
    assert load_manifest(checkpoint.path)["next_index"] == 3


def test_the_manifest_records_the_ai_outcome_of_each_file(tmp_path, monkeypatch):
    built = []
    wire(monkeypatch, built)
    inputs = seam_inputs(tmp_path, 2)
    provider = SeamProvider(
        transform=lambda text: text.replace("he walk home", "he walks home"),
        error_on=2,
        error=ProviderUnavailable("provider down", retryable=False),
    )
    checkpoint = RunCheckpoint(str(tmp_path / "out"), inputs, clock=FakeClock())

    run_batch(
        inputs,
        str(tmp_path / "out"),
        ai_editor=seam_editor(provider),
        checkpoint=checkpoint,
    )

    statuses = [e["ai_status"] for e in load_manifest(checkpoint.path)["entries"]]
    assert statuses == ["accepted", "fallback"]


def test_a_dry_run_writes_no_manifest(tmp_path, monkeypatch):
    built = []
    wire(monkeypatch, built)
    inputs = seam_inputs(tmp_path, 2)
    checkpoint = RunCheckpoint(str(tmp_path / "out"), inputs, clock=FakeClock())

    run_batch(inputs, str(tmp_path / "out"), dry_run=True, checkpoint=checkpoint)

    assert not checkpoint.path.exists()


def test_a_file_whose_build_fails_is_never_checkpointed_as_complete(
    tmp_path, monkeypatch
):
    """The checkpoint sits on the far side of build_pdf, so a file that never produced
    an output cannot be recorded as done."""
    inputs = seam_inputs(tmp_path, 3)

    def exploding_build(text, path):
        if "1.pdf" in str(path):
            raise OSError("disk full halfway through the PDF")

    wire(monkeypatch, [], build=exploding_build)
    checkpoint = RunCheckpoint(str(tmp_path / "out"), inputs, clock=FakeClock())

    summary = run_batch(inputs, str(tmp_path / "out"), checkpoint=checkpoint)

    payload = load_manifest(checkpoint.path)
    statuses = [(e["status"], e["output"]) for e in payload["entries"]]
    assert statuses[1] == ("failed", "")
    assert statuses[0][0] == "completed" and statuses[2][0] == "completed"
    assert summary["failed"] == 1
    assert payload["next_index"] == 3


def test_a_missing_input_is_checkpointed_as_skipped_not_completed(tmp_path, monkeypatch):
    built = []
    wire(monkeypatch, built)
    inputs = seam_inputs(tmp_path, 2)
    inputs.append(str(tmp_path / "src" / "gone.pdf"))
    checkpoint = RunCheckpoint(str(tmp_path / "out"), inputs, clock=FakeClock())

    run_batch(inputs, str(tmp_path / "out"), checkpoint=checkpoint)

    payload = load_manifest(checkpoint.path)
    assert payload["entries"][2]["status"] == "skipped"
    assert payload["next_index"] == 3


def test_a_finished_run_marks_the_manifest_complete(tmp_path, monkeypatch):
    built = []
    wire(monkeypatch, built)
    inputs = seam_inputs(tmp_path, 2)
    checkpoint = RunCheckpoint(str(tmp_path / "out"), inputs, clock=FakeClock())

    run_batch(inputs, str(tmp_path / "out"), checkpoint=checkpoint)

    assert load_manifest(checkpoint.path)["complete"] is True
    assert find_resumable_run(tmp_path).available is False


# --------------------------------------------------------------------------
# Quota stop through the real batch loop
# --------------------------------------------------------------------------
def test_a_daily_quota_stop_mid_run_checkpoints_and_halts_at_the_between_files_seam(
    tmp_path, monkeypatch
):
    """The whole Phase 4 -> Phase 5 path: the limiter's callback fires inside the
    provider call, the in-flight chapter still completes deterministically, it is
    checkpointed, and the batch ends without processing another file."""
    built = []
    wire(monkeypatch, built)
    inputs = seam_inputs(tmp_path, 4)
    stop = threading.Event()
    checkpoint = RunCheckpoint(
        str(tmp_path / "out"), inputs, stop_event=stop, clock=FakeClock()
    )

    quota_error = DailyQuotaExhausted("free daily quota is used up (TPD)")

    class QuotaProvider(SeamProvider):
        def complete(self, request):
            self.complete_calls += 1
            if self.complete_calls == 2:
                # Exactly what RateLimitedProvider does: signal the seam, then raise.
                checkpoint.on_quota_stop(make_quota_stop())
                raise quota_error
            return CompletionResult(request.text, "fake-1", 0.01, "stop", False)

    summary = run_batch(
        inputs,
        str(tmp_path / "out"),
        ai_editor=seam_editor(QuotaProvider()),
        stop_event=stop,
        checkpoint=checkpoint,
    )

    payload = load_manifest(checkpoint.path)
    assert summary.get("stopped") is True
    assert summary["succeeded"] == 2, "the in-flight chapter must still complete"
    assert payload["next_index"] == 2, "the run stopped after the in-flight chapter"
    assert payload["complete"] is False
    assert payload["stopped_reason"] == "daily_quota"
    assert payload["quota_stop"]["is_daily"] is True
    # The chapter that hit the wall fell back to deterministic text, and says so.
    assert payload["entries"][1]["ai_status"] == "fallback"
    assert len(built) == 2


def test_a_run_halted_by_a_daily_quota_is_offered_for_resume_tomorrow(
    tmp_path, monkeypatch
):
    built = []
    wire(monkeypatch, built)
    inputs = seam_inputs(tmp_path, 4)
    stop = threading.Event()
    checkpoint = RunCheckpoint(
        str(tmp_path / "out"), inputs, stop_event=stop, clock=FakeClock(), novel="Universal"
    )
    checkpoint.record_completed(inputs[0], "one.pdf")
    checkpoint.on_quota_stop(make_quota_stop())
    checkpoint.finish(stopped=True)

    offer = find_resumable_run(tmp_path)
    assert offer.available is True
    assert offer.stopped_reason == "daily_quota"
    assert offer.quota_stop["is_daily"] is True
    assert offer.remaining == tuple(inputs[1:])


def test_resuming_processes_exactly_the_files_the_first_run_did_not(
    tmp_path, monkeypatch
):
    built = []
    wire(monkeypatch, built)
    inputs = seam_inputs(tmp_path, 5)
    stop = threading.Event()
    first = RunCheckpoint(
        str(tmp_path / "out"), inputs, stop_event=stop, clock=FakeClock()
    )
    run_batch(inputs[:2], str(tmp_path / "out"), checkpoint=first)
    # Pretend the app closed here: no finish() for the whole queue.
    first.finish(stopped=True)

    offer = find_resumable_run(tmp_path)
    plan = plan_resume(offer)
    assert plan["pdf_paths"] == inputs[2:]

    built.clear()
    resumed = RunCheckpoint(
        plan["output_dir"],
        inputs,
        start_index=len(inputs) - len(plan["pdf_paths"]),
        clock=FakeClock(),
    )
    summary = run_batch(
        plan["pdf_paths"],
        plan["output_dir"],
        novel_name=plan["novel_name"],
        mirror_root=plan["mirror_root"],
        checkpoint=resumed,
    )

    assert summary["succeeded"] == 3
    assert len(built) == 3
    payload = load_manifest(resumed.path)
    assert payload["next_index"] == 5
    assert payload["complete"] is True
    assert find_resumable_run(tmp_path).available is False


# --------------------------------------------------------------------------
# A real corpus chapter, to prove no prose reaches the manifest
# --------------------------------------------------------------------------
def test_a_real_chapter_run_puts_no_prose_and_no_key_in_the_manifest(tmp_path):
    pdfs = sorted(str(p) for p in FIXTURES.glob("*.pdf"))[:2]
    if not pdfs:
        pytest.skip("fixtures not present (files/test-files/shadow_slave)")

    key = "gsk_LIVEKEYSHAPED000000000000000000000000000000000000"
    register_secret(key)
    try:
        checkpoint = RunCheckpoint(
            str(tmp_path / "out"),
            pdfs,
            novel="Shadow Slave",
            provider="groq",
            model_id="llama-3.3-70b-versatile",
            clock=FakeClock(),
        )
        summary = run_batch(
            pdfs, str(tmp_path / "out"), novel_name="Shadow Slave", checkpoint=checkpoint
        )
        raw = checkpoint.path.read_text(encoding="utf-8")
    finally:
        forget_secrets()

    assert summary["succeeded"] >= 1
    assert key not in raw
    # Real extracted prose from the fixture must appear nowhere in the manifest.
    text = extract_text_from_pdf(pdfs[0])
    words = [w for w in text.split() if len(w) > 6][:40]
    assert words, "the fixture produced no usable text to test against"
    for phrase in (" ".join(words[i:i + 5]) for i in range(0, len(words) - 5, 5)):
        assert phrase not in raw
