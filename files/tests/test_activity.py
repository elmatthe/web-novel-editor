"""Tk-free Activity contract: bounded channel, Summary/Detailed routing, session logs, pump."""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

import pytest

from gui.activity import (ERROR, INFO, WARNING, Activity, ActivityChannel, ActivityEvent, ActivityModel,
                          ActivityPump, SessionLog, bridge_event, prune_session_logs)


def test_progress_coalesces_and_routine_detail_drops_are_counted_but_important_never_drop():
    channel = ActivityChannel(max_pending=3)
    for value in range(50):
        channel.emit(ActivityEvent("batch", kind="job", payload=("progress", value), coalesce_key="progress"))
    assert channel.pending() == 1 and channel.coalesced == 49
    channel.emit(ActivityEvent("batch", "detail 1"))
    channel.emit(ActivityEvent("batch", "detail 2"))
    assert channel.emit(ActivityEvent("batch", "detail 3")) is False and channel.dropped == 1
    for severity in (WARNING, ERROR):
        assert channel.emit(ActivityEvent("batch", "kept", severity))
    assert channel.emit(ActivityEvent("batch", "done", kind="job", payload=("done", {})))
    events = channel.drain(100)
    assert events[0].payload == ("progress", 49)  # newest value, original position
    assert [e.severity for e in events[-3:-1]] == [WARNING, ERROR] and events[-1].payload[0] == "done"


@pytest.mark.parametrize("level,severity,summary,tone", [
    ("success", INFO, True, "success"), ("accent", INFO, True, "accent"), ("info", INFO, True, None),
    ("muted", INFO, False, "muted"), ("warn", WARNING, True, None), ("error", ERROR, True, None),
    ("unexpected", INFO, False, "muted")])
def test_batch_runner_levels_bridge_to_summary_and_detailed(level, severity, summary, tone):
    event = bridge_event("message", level)
    assert (event.severity, event.summary, event.tone) == (severity, summary, tone)
    model = ActivityModel()
    s_line, d_line = model.add(event)
    assert (s_line is not None) == summary and d_line.text.endswith("message")


def test_display_history_is_capped_and_clear_leaves_session_log(tmp_path):
    renders = []
    log = SessionLog(tmp_path)
    activity = Activity(session_log=log, on_render=renders.append, line_cap=5)
    assert log.open()
    for i in range(12):
        activity.report(ActivityEvent("app", f"line {i}", summary=True))
    assert [l.text for l in activity.model.summary] == [f"line {i}" for i in range(7, 12)]
    activity.clear_display()
    assert renders[-1].cleared and not activity.model.detailed
    activity.close()
    text = log.path.read_text(encoding="utf-8")
    assert "line 0" in text and "line 11" in text and "session closed" in text


def test_job_events_render_earlier_lines_first_so_completion_never_reorders(tmp_path):
    order = []
    activity = Activity(on_render=lambda u: order.extend(l.text for l in u.detailed),
                        job_sink=lambda e: order.append(f"JOB {e.payload[0]}"))
    for event in (ActivityEvent("b", "first", summary=True), ActivityEvent("b", kind="job", payload=("done", 1)),
                  ActivityEvent("b", "after")):
        activity.emit(event)
    activity.pump()
    assert order == ["first", "JOB done", "after"]


def test_emit_from_worker_report_only_from_owner_thread():
    activity = Activity()
    errors = []

    def worker():
        assert activity.emit(ActivityEvent("w", "from worker"))
        try:
            activity.report(ActivityEvent("w", "direct"))
        except RuntimeError as exc:
            errors.append(str(exc))
    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert errors and activity.channel.pending() == 1


def test_session_log_failure_is_visible_once_and_stops_writing(tmp_path):
    log = SessionLog(tmp_path)
    renders = []
    activity = Activity(session_log=log, on_render=renders.append)
    assert log.open()
    log._handle.close()  # simulate the disk going away
    activity.report(ActivityEvent("app", "one", summary=True))
    activity.report(ActivityEvent("app", "two", summary=True))
    warnings = [l.text for r in renders for l in r.summary if "session log could not be written" in l.text]
    assert len(warnings) == 1 and log.failed


def test_unwritable_log_directory_reports_once(tmp_path):
    blocker = tmp_path / "logs"
    blocker.write_text("not a directory")
    log = SessionLog(blocker)
    renders = []
    activity = Activity(session_log=log, on_render=renders.append)
    assert not log.open()
    activity.note_log_open_failure()
    activity.note_log_open_failure()
    assert sum("could not be created" in l.text for r in renders for l in r.summary) == 1


def test_retention_prunes_only_old_closed_application_session_logs(tmp_path):
    names = [f"session-202610{d:02d}-120000.log" for d in range(1, 26)]
    for name in names:
        (tmp_path / name).write_text("old")
    keep = {"setup-latest.log": "s", "session-notes.txt": "n", "session-20261001-120000.log.bak": "b",
            "my-session-20261001-120000.log": "m"}
    for name, text in keep.items():
        (tmp_path / name).write_text(text)
    (tmp_path / "session-20261099-999999.log").mkdir()  # a folder that happens to match the pattern
    active = tmp_path / names[0]
    removed = prune_session_logs(tmp_path, keep=20, active=active)
    remaining = sorted(p.name for p in tmp_path.glob("session-2026*.log") if p.is_file())
    assert active.exists()  # the active log is never pruned, even though it is the oldest
    assert [p.name for p in removed] == names[1:5][::-1]
    assert remaining == sorted([names[0]] + names[5:])
    for name, text in keep.items():
        assert (tmp_path / name).read_text() == text
    assert (tmp_path / "session-20261099-999999.log").is_dir()


def test_session_log_names_are_unique_and_opening_prunes(tmp_path):
    stamp = datetime(2026, 11, 1, 9, 30, 0)
    for day in range(1, 24):
        (tmp_path / f"session-202610{day:02d}-000000.log").write_text("x")
    first = SessionLog(tmp_path, keep=20, clock=lambda: stamp)
    second = SessionLog(tmp_path, keep=20, clock=lambda: stamp)
    assert first.open() and second.open()
    assert first.path.name == "session-20261101-093000.log"
    assert second.path.name == "session-20261101-093000-2.log"
    closed = [p for p in tmp_path.glob("session-*.log") if p not in (first.path, second.path)]
    assert len(closed) <= 20
    first.close()
    second.close()


def test_pump_is_bounded_per_tick_and_stops_when_idle():
    scheduled = []
    activity = Activity(drain_limit=10)
    active = {"value": True}
    pump = ActivityPump(activity, lambda ms, fn: scheduled.append((ms, fn)) or len(scheduled),
                        lambda handle: None, lambda: active["value"])
    for i in range(25):
        activity.emit(ActivityEvent("b", f"{i}"))
    pump.start()
    ms, tick = scheduled.pop()
    tick()
    assert activity.channel.pending() == 15 and scheduled[-1][0] == 1  # more pending: reschedule fast
    scheduled.pop()[1]()
    scheduled.pop()[1]()
    assert activity.channel.pending() == 0
    active["value"] = False
    scheduled.pop()[1]()
    assert not pump.running and not scheduled


def test_closed_activity_refuses_events_and_never_renders(tmp_path):
    renders = []
    activity = Activity(on_render=renders.append)
    activity.close()
    assert activity.emit(ActivityEvent("b", "late")) is False
    assert activity.report(ActivityEvent("b", "late")) is False
    assert activity.pump() == 0 and renders == []


def test_default_log_dir_honors_isolation_override(tmp_path, monkeypatch):
    from gui import activity
    monkeypatch.setenv("WNE_LOG_DIR", str(tmp_path / "x"))
    assert activity.default_log_dir() == tmp_path / "x"
    monkeypatch.delenv("WNE_LOG_DIR")
    assert activity.default_log_dir() == Path(activity.__file__).resolve().parents[2] / "files" / "runtime-data" / "logs"


def test_bridged_diagnostics_are_bounded():
    from gui.activity import MAX_MESSAGE_CHARS
    event = bridge_event("x" * 5000, "warn")
    assert len(event.message) == MAX_MESSAGE_CHARS and event.message.endswith("…")
    assert bridge_event("short", "warn").message == "short"


def test_retention_never_removes_another_instances_active_log(tmp_path):
    other = SessionLog(tmp_path, keep=20, clock=lambda: datetime(2026, 1, 1, 0, 0, 0))
    assert other.open()  # an older, still-running instance
    for day in range(1, 26):
        (tmp_path / f"session-202610{day:02d}-000000.log").write_text("closed")
    mine = SessionLog(tmp_path, keep=20, clock=lambda: datetime(2026, 11, 1, 0, 0, 0))
    assert mine.open()
    assert other.path.exists(), "an active session log was pruned"
    other.write(ActivityEvent("app", "still writing"))
    other.close()
    mine.close()
    assert "still writing" in other.path.read_text(encoding="utf-8")
