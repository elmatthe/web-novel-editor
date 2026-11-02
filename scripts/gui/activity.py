"""Activity: structured events, a bounded thread-safe channel, the display model and session logs.

Adapted (Phase 02B) from the author's PDF-Splitter ``scripts/pdf_splitter/activity.py`` at
``edcbd4fe6db96bb7515e719172fbd4172fe3ef19``, itself derived from Audiobook Creation Tool's
job UI. Kept: the event record, the coalescing/bounded channel, the capped Summary/Detailed
model, the fail-once session log and the Tk-free pump. Changed for this editor: a display
``tone`` (success/accent/muted) carried beside the severity, a bridge from the batch runner's
historical ``gui_log(message, level)`` seam, editor-specific session-log names, and
application-owned session-log retention. Removed: developer-preview events.

Rules
-----
* Workers only call :meth:`Activity.emit` (lock-protected, bounded). They never touch a
  widget or call Tk, not even ``after``. The Tk thread owns :class:`ActivityPump`.
* ``summary=True`` events appear in Summary and Detailed; the rest only in Detailed. Message
  events also go to the session log, which carries file names, counts, hashes, durations and
  bounded errors, never chapter bodies.
* Progress events coalesce by key. Routine detail may be dropped when the channel is full and
  is counted; warnings, errors, summary lines and job events are never dropped.
* Display history is capped per view. Clear Log empties the views only.
* A failing session log produces one visible warning and stops writing.

This module imports no Tk.
"""

from __future__ import annotations

import os
import re
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

INFO, WARNING, ERROR = "info", "warning", "error"
DEFAULT_LINE_CAP = 5000
DEFAULT_DRAIN_LIMIT = 64
DEFAULT_MAX_PENDING = 500
DEFAULT_POLL_MS = 80
#: Closed application session logs kept by retention (Master Plan §6.4).
DEFAULT_LOG_RETENTION = 20
SESSION_LOG_PATTERN = re.compile(r"session-\d{8}-\d{6}(?:-\d+)?\.log")

_REPO_ROOT = Path(__file__).resolve().parents[2]
#: Development/test override so automated runs never write or prune the user's real logs.
LOG_DIR_ENV = "WNE_LOG_DIR"


def default_log_dir() -> Path:
    """Session logs live in the repository's ignored writable runtime area."""
    override = os.environ.get(LOG_DIR_ENV)
    return Path(override) if override else _REPO_ROOT / "files" / "runtime-data" / "logs"


@dataclass(frozen=True)
class ActivityEvent:
    """One immutable thing worth telling the user or the log; safe across threads.

    ``kind`` is ``"message"`` (displayed and logged), ``"separator"`` (a run divider shown in
    both views) or ``"job"`` (``payload`` is routed to the controller; not displayed).
    ``tone`` only selects a display color (``success``, ``accent``, ``muted``).
    """

    origin: str
    message: str = ""
    severity: str = INFO
    summary: bool = False
    tone: str | None = None
    payload: object | None = None
    kind: str = "message"
    coalesce_key: str | None = None

    @property
    def important(self) -> bool:
        """Events that must never be dropped or coalesced away silently."""
        return (self.severity != INFO or self.summary or self.kind != "message"
                ) and self.coalesce_key is None


@dataclass(frozen=True)
class ActivityLine:
    text: str
    severity: str = INFO
    tone: str | None = None


@dataclass(frozen=True)
class RenderUpdate:
    """What the views must do: append these lines, and/or empty themselves first."""

    summary: tuple[ActivityLine, ...] = ()
    detailed: tuple[ActivityLine, ...] = ()
    cleared: bool = False

    @property
    def empty(self) -> bool:
        return not (self.summary or self.detailed or self.cleared)


def format_event(event: ActivityEvent) -> ActivityLine:
    prefix = {WARNING: "Warning: ", ERROR: "Error: "}.get(event.severity, "")
    message = event.message
    # Batch-runner lines already say FAILED/skipped; avoid "Error: ... FAILED" noise for them.
    if prefix and (message.lstrip().startswith("[") or message.lstrip().startswith("-")):
        prefix = ""
    return ActivityLine(prefix + message, event.severity, event.tone)


# Legacy batch-runner levels -> (severity, Summary?, tone). "muted" diagnostics (output
# mappings, loaded rule sources, category counts) stay in Detailed only.
_LEGACY_LEVELS = {
    "success": (INFO, True, "success"),
    "accent": (INFO, True, "accent"),
    "info": (INFO, True, None),
    "muted": (INFO, False, "muted"),
    "warn": (WARNING, True, None),
    "error": (ERROR, True, None),
}


#: Diagnostics are bounded so no log line can carry more than a short fragment of text.
MAX_MESSAGE_CHARS = 300


def bridge_event(message: str, level: str = "info", origin: str = "batch") -> ActivityEvent:
    """Translate one historical ``gui_log(message, level)`` call into a structured event."""
    severity, summary, tone = _LEGACY_LEVELS.get(level, (INFO, False, "muted"))
    text = str(message)
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[:MAX_MESSAGE_CHARS - 1] + "…"
    return ActivityEvent(origin, text, severity, summary=summary, tone=tone)


# --------------------------------------------------------------------------- channel

class ActivityChannel:
    """A bounded, lock-protected hand-off from worker threads to the Tk thread."""

    def __init__(self, max_pending: int = DEFAULT_MAX_PENDING) -> None:
        if max_pending < 1:
            raise ValueError("max_pending must be at least 1")
        self._max = max_pending
        self._lock = threading.Lock()
        self._entries: deque[list] = deque()
        self._by_key: dict[str, list] = {}
        self._closed = False
        self.dropped = 0
        self.coalesced = 0

    def emit(self, event: ActivityEvent) -> bool:
        """Queue *event* (any thread). Returns False if it was refused or dropped."""
        with self._lock:
            if self._closed:
                return False
            key = event.coalesce_key
            if key is not None and key in self._by_key:
                self._by_key[key][0] = event  # newest wins, in the original position
                self.coalesced += 1
                return True
            if not event.important and key is None and len(self._entries) >= self._max:
                self.dropped += 1  # routine detail only; counted, never silent
                return False
            entry = [event]
            self._entries.append(entry)
            if key is not None:
                self._by_key[key] = entry
            return True

    def drain(self, limit: int) -> list[ActivityEvent]:
        """Remove and return up to *limit* events, oldest first."""
        out: list[ActivityEvent] = []
        with self._lock:
            while self._entries and len(out) < limit:
                entry = self._entries.popleft()
                event = entry[0]
                if event.coalesce_key is not None and self._by_key.get(event.coalesce_key) is entry:
                    del self._by_key[event.coalesce_key]
                out.append(event)
        return out

    def pending(self) -> int:
        with self._lock:
            return len(self._entries)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._entries.clear()
            self._by_key.clear()


# ------------------------------------------------------------------------ display model

class ActivityModel:
    """The in-memory Summary/Detailed history, capped per view. Pure data."""

    def __init__(self, line_cap: int = DEFAULT_LINE_CAP) -> None:
        self.line_cap = line_cap
        self.summary: deque[ActivityLine] = deque(maxlen=line_cap)
        self.detailed: deque[ActivityLine] = deque(maxlen=line_cap)

    def add(self, event: ActivityEvent) -> tuple[ActivityLine | None, ActivityLine]:
        line = format_event(event)
        self.detailed.append(line)
        if event.summary or event.kind == "separator":
            self.summary.append(line)
            return line, line
        return None, line

    def clear(self) -> None:
        self.summary.clear()
        self.detailed.clear()


# -------------------------------------------------------------------------- session log

def prune_session_logs(directory: str | Path, *, keep: int = DEFAULT_LOG_RETENTION,
                       active: Path | None = None) -> list[Path]:
    """Delete closed application session logs beyond the newest *keep*.

    Only regular files whose whole name matches ``session-YYYYMMDD-HHMMSS[-N].log`` are
    candidates; the active log, other logs, run folders, audits and any other file are never
    touched. Failures are ignored (retention must never stop the application).
    """
    directory = Path(directory)
    active_name = Path(active).name if active is not None else None
    try:
        logs = sorted((p for p in directory.iterdir()
                       if SESSION_LOG_PATTERN.fullmatch(p.name) and p.name != active_name
                       and p.is_file() and not p.is_symlink()),
                      key=lambda p: p.name, reverse=True)
    except OSError:
        return []
    removed = []
    for old in logs[max(0, keep):]:
        if _held_by_live_session(old):
            continue  # another running instance is still writing it
        try:
            old.unlink()  # on Windows an open log cannot be deleted; that error is ignored
            removed.append(old)
        except OSError:
            pass
    return removed


def _hold_session_lock(handle) -> None:
    """POSIX: keep an advisory lock on this session's own log for its lifetime."""
    if os.name != "nt":
        import fcntl
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            pass


def _held_by_live_session(path: Path) -> bool:
    if os.name == "nt":
        return False  # the open-file deletion refusal protects active logs on Windows
    import fcntl
    try:
        with path.open("a") as probe:
            try:
                fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            fcntl.flock(probe.fileno(), fcntl.LOCK_UN)
    except OSError:
        return True
    return False


class SessionLog:
    """One diagnostic log file per application session (default: ``files/runtime-data/logs``).

    Takes only event message text (never payloads), reports a failure once through
    :attr:`failed` / :attr:`last_error` instead of raising, and prunes old closed logs.
    """

    def __init__(self, directory: str | Path, *, keep: int = DEFAULT_LOG_RETENTION,
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self.directory = Path(directory)
        self.keep = keep
        self._clock = clock
        self._lock = threading.Lock()
        self._handle = None
        self.path: Path | None = None
        self.failed = False
        self.last_error = ""
        self.pruned: list[Path] = []

    @property
    def is_open(self) -> bool:
        return self._handle is not None

    def open(self) -> bool:
        with self._lock:
            if self._handle is not None:
                return True
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                stamp = self._clock().strftime("%Y%m%d-%H%M%S")
                path = self.directory / f"session-{stamp}.log"
                counter = 1
                while path.exists():
                    counter += 1
                    path = self.directory / f"session-{stamp}-{counter}.log"
                self._handle = path.open("x", encoding="utf-8", newline="\n", buffering=1)
                _hold_session_lock(self._handle)
                self.path = path
                self._handle.write(f"{self._clock():%Y-%m-%d %H:%M:%S} [info] Web Novel Editor session started\n")
            except OSError as exc:
                self._fail(exc)
                return False
        self.pruned = prune_session_logs(self.directory, keep=self.keep, active=self.path)
        return True

    def write(self, event: ActivityEvent) -> bool:
        with self._lock:
            if self.failed or self._handle is None:
                return False
            try:
                self._handle.write(f"{self._clock():%Y-%m-%d %H:%M:%S} [{event.severity}] "
                                   f"{event.origin}: {event.message}\n")
                return True
            except (OSError, ValueError) as exc:
                self._fail(exc)
                return False

    def _fail(self, exc: Exception) -> None:
        self.failed = True
        self.last_error = f"{type(exc).__name__}: {exc}"
        handle, self._handle = self._handle, None
        if handle is not None:
            try:
                handle.close()
            except (OSError, ValueError):
                pass

    def close(self) -> None:
        with self._lock:
            handle, self._handle = self._handle, None
            if handle is None:
                return
            try:
                handle.write(f"{self._clock():%Y-%m-%d %H:%M:%S} [info] Web Novel Editor session closed\n")
                handle.close()
            except (OSError, ValueError):
                pass


# --------------------------------------------------------------------------- the facade

class Activity:
    """Routes events to the display model, the session log and the job sink.

    ``report`` is for the Tk thread (immediate); ``emit`` is for any thread (queued). Both end
    in the same routing, so a producer's thread never affects how an event is shown.
    """

    def __init__(self, *, session_log: SessionLog | None = None,
                 on_render: Callable[[RenderUpdate], None] | None = None,
                 job_sink: Callable[[ActivityEvent], None] | None = None,
                 line_cap: int = DEFAULT_LINE_CAP, drain_limit: int = DEFAULT_DRAIN_LIMIT,
                 max_pending: int = DEFAULT_MAX_PENDING) -> None:
        self.channel = ActivityChannel(max_pending)
        self.model = ActivityModel(line_cap)
        self.session_log = session_log
        self.on_render = on_render or (lambda update: None)
        self.job_sink = job_sink or (lambda event: None)
        self.drain_limit = drain_limit
        self._owner = threading.get_ident()
        self._closed = False
        self._log_failure_reported = False
        self._reported_drops = 0

    @property
    def closed(self) -> bool:
        return self._closed

    def emit(self, event: ActivityEvent) -> bool:
        """Thread-safe. Queues the event for the Tk thread's next pump."""
        if self._closed:
            return False
        return self.channel.emit(event)

    def report(self, event: ActivityEvent) -> bool:
        """Tk thread only: route *event* now."""
        if self._closed:
            return False
        if threading.get_ident() != self._owner:
            raise RuntimeError("Activity.report must be called from the Tk thread; use emit() elsewhere")
        self._flush([event])
        return True

    def pump(self, limit: int | None = None) -> int:
        """Tk thread: route at most *limit* queued events (bounded work per tick)."""
        if self._closed:
            return 0
        events = self.channel.drain(self.drain_limit if limit is None else limit)
        if events:
            self._flush(events)
        dropped = self.channel.dropped
        if dropped != self._reported_drops and not self._closed:
            self._reported_drops = dropped
            self._flush([ActivityEvent("activity", f"{dropped} routine detail line(s) were not displayed "
                                       "to keep the window responsive.", INFO, tone="muted")])
        return len(events)

    def _flush(self, events: list[ActivityEvent]) -> None:
        summary: list[ActivityLine] = []
        detailed: list[ActivityLine] = []

        def render() -> None:
            update = RenderUpdate(tuple(summary), tuple(detailed))
            summary.clear()
            detailed.clear()
            if not update.empty and not self._closed:
                self.on_render(update)

        for event in events:
            if self._closed:
                break
            if event.kind == "job":
                # Show everything emitted before this job event first, so a completion
                # handler (which may report more lines or open a dialog) never reorders output.
                render()
                self.job_sink(event)
                continue
            self._to_disk(event)
            s_line, d_line = self.model.add(event)
            if s_line is not None:
                summary.append(s_line)
            detailed.append(d_line)
        render()

    def _to_disk(self, event: ActivityEvent) -> None:
        log = self.session_log
        if log is None or log.failed:
            return
        if not log.write(event) and log.failed and not self._log_failure_reported:
            self._log_failure_reported = True
            warning = ActivityEvent(
                "activity", f"The session log could not be written ({log.last_error}); technical details "
                            "are not being saved for this session.", WARNING, summary=True)
            s_line, d_line = self.model.add(warning)  # shown, never re-sent to the failing log
            self.on_render(RenderUpdate((s_line,) if s_line else (), (d_line,)))

    def note_log_open_failure(self) -> None:
        """Make an unavailable session log visible once (call after ``SessionLog.open`` fails)."""
        log = self.session_log
        if log is not None and log.failed and not self._log_failure_reported:
            self._log_failure_reported = True
            self.report(ActivityEvent(
                "activity", f"The session log could not be created ({log.last_error}); technical details "
                            "are not being saved for this session.", WARNING, summary=True))

    def clear_display(self) -> None:
        """Clear Log: empty the displayed views. Session log files and run state are untouched."""
        self.model.clear()
        self.on_render(RenderUpdate(cleared=True))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.channel.close()
        if self.session_log is not None:
            self.session_log.close()


# ---------------------------------------------------------------------------- the pump

class ActivityPump:
    """Drains the channel from a scheduler while something can still produce events.

    *schedule*/*cancel* have the shape of ``widget.after`` / ``widget.after_cancel`` but are
    plain callables, so this module needs no widget. At most one callback is outstanding; the
    pump stops when nothing is active and nothing is pending.
    """

    def __init__(self, activity: Activity, schedule: Callable[[int, Callable[[], None]], object],
                 cancel: Callable[[object], None], is_active: Callable[[], bool], *,
                 interval_ms: int = DEFAULT_POLL_MS) -> None:
        self._activity = activity
        self._schedule = schedule
        self._cancel = cancel
        self._is_active = is_active
        self._interval = max(1, int(interval_ms))
        self._handle: object | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running or self._activity.closed:
            return
        self._running = True
        self._handle = self._schedule(self._interval, self.tick)

    def tick(self) -> None:
        self._handle = None
        if not self._running:
            return
        try:
            self._activity.pump()
        finally:
            more = self._activity.channel.pending() > 0
            if self._running and not self._activity.closed and (more or self._is_active()):
                self._handle = self._schedule(1 if more else self._interval, self.tick)
            else:
                self._running = False

    def stop(self) -> None:
        self._running = False
        handle, self._handle = self._handle, None
        if handle is not None:
            try:
                self._cancel(handle)
            except Exception:  # noqa: BLE001 - a dead Tk interpreter has nothing left to cancel
                pass
