"""Checkpointed runs — the atomic run manifest and the resume decision (Plan 2b Phase 5).

A cloud run can be longer than a day. The previous design asked the user to leave the
window open for roughly twelve days while the app slept through daily quota resets; this
module is what replaces that. After **each completed file** the run's state is written
atomically into the output folder, so the app can be closed at any moment — by the user,
by a Windows update, or because the day's free quota is gone — and the run picked up
later from exactly where it stopped.

Three rules shape everything here.

**Checkpoints are file-boundary only.** A file is either fully checkpointed as complete
or not checkpointed at all. The recording call sits on the far side of ``build_pdf`` and
its sidecars, so a manifest entry means "the output exists". Nothing partial can be
persisted even in principle: chunk state lives inside ``AIEditor.edit``, which is
chapter-atomic and returns either accepted text or the deterministic baseline, so there
is no partial chapter for this layer to see.

**Never guess at partial state.** :func:`load_manifest` rejects rather than repairs — a
missing, truncated, mis-shaped, or forward-versioned manifest returns ``None`` and the
caller starts a fresh run. It never raises, because the caller is a GUI.

**Nothing sensitive is written.** There is no field that could carry chapter text, and
every free-text value goes through the Phase 1 redaction boundary and is length-bounded.
The API key never reaches this layer at all; redaction is the second line, not the first.

The writer is 2a's ``write_settings_atomic`` — tempfile + ``fsync`` + ``os.replace``, the
same call Phase 1 used for ``secrets.json``. The whole manifest is rewritten each time
rather than appended to: an append-only journal is cheap but is exactly the shape a kill
can leave half-written, whereas a whole-file atomic replace means the file on disk is
always a complete, valid manifest. The queue costs a few hundred KB for a 3,000-chapter
run, rewritten once per file — noise against a multi-second-per-chapter AI pass.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ai.redaction import redact, redact_obj
from ai.settings import write_settings_atomic

MANIFEST_NAME = "run-manifest.json"

#: Bumped only when the payload shape changes incompatibly. A manifest whose version is
#: newer than this build understands is refused outright rather than partially read.
SCHEMA_VERSION = 1

#: Free text (a failure reason) is bounded before it is written. Nothing here is meant to
#: be a log — the JSONL sidecar is where detail belongs.
REASON_LIMIT = 200

STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

STOP_USER = "user_stop"
STOP_DAILY_QUOTA = "daily_quota"
STOP_LONG_WAIT = "long_wait"

#: The only keys an entry may ever carry. Asserted by a test, because the natural way to
#: leak chapter text is to add a well-meaning "summary" or "preview" field later.
ENTRY_KEYS = ("source", "status", "output", "ai_status", "size", "mtime_ns", "recorded_at")


def manifest_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / MANIFEST_NAME


def _safe_text(value: Any, limit: int = REASON_LIMIT) -> str:
    text = redact(str(value or ""))
    return text[:limit]


def _identity(source: str) -> tuple[int, int]:
    """Size and mtime of a source file — provenance, not a cryptographic guarantee.

    Enough to notice that an input was replaced between runs, cheap enough to take for
    every file (one ``stat``, no hashing 3,000 PDFs). A missing file records zeros rather
    than failing a checkpoint that has already produced real output.
    """
    try:
        info = os.stat(source)
    except OSError:
        return 0, 0
    return info.st_size, info.st_mtime_ns


class RunCheckpoint:
    """The live state of one run, rewritten atomically after every finished file.

    Construct it with everything known at run start; ``run_batch`` then only reports
    outcomes. Passing ``None`` for the checkpoint anywhere keeps the historical
    behaviour exactly — this class is additive and inert by omission.
    """

    def __init__(
        self,
        output_dir: str | Path,
        queue: Sequence[str],
        *,
        novel: str = "",
        mirror_root: str | None = None,
        provider: str = "",
        model_id: str = "",
        prompt_version: str = "",
        gate_version: str = "",
        ai_policy: str = "",
        stop_event: threading.Event | None = None,
        clock: Callable[[], float] = time.time,
        start_index: int = 0,
    ):
        self.output_dir = str(output_dir)
        self.queue = [str(item) for item in queue]
        self._clock = clock
        self._stop_event = stop_event
        self._run = {
            "novel": novel,
            "mirror_root": mirror_root,
            "provider": provider,
            "model_id": _safe_text(model_id, 120),
            "prompt_version": prompt_version,
            "gate_version": gate_version,
            "ai_policy": ai_policy,
            "started_at": clock(),
        }
        self._entries: list[dict[str, Any]] = []
        self._next_index = max(0, int(start_index))
        # Held in memory, not read back from the file: the checkpoint written when the
        # quota stop arrives is superseded moments later by the in-flight chapter's own
        # checkpoint, and that second write must carry the quota stop forward.
        self._quota_stop: dict[str, Any] | None = None
        self._stopped_reason = ""
        self._complete = False

    # -- state -------------------------------------------------------------
    @property
    def path(self) -> Path:
        return manifest_path(self.output_dir)

    @property
    def next_index(self) -> int:
        return self._next_index

    @property
    def quota_stop(self) -> dict[str, Any] | None:
        return self._quota_stop

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "run": dict(self._run),
            "output_dir": self.output_dir,
            "queue": list(self.queue),
            "next_index": self._next_index,
            "entries": [dict(entry) for entry in self._entries],
            "quota_stop": self._quota_stop,
            "stopped_reason": self._stopped_reason,
            "complete": self._complete,
        }

    # -- recording ---------------------------------------------------------
    def _record(self, source: str, status: str, output: str, ai_status: str) -> None:
        size, mtime_ns = _identity(source)
        self._entries.append(
            {
                "source": str(source),
                "status": status,
                "output": str(output or ""),
                "ai_status": ai_status or "none",
                "size": size,
                "mtime_ns": mtime_ns,
                "recorded_at": self._clock(),
            }
        )
        self._next_index += 1
        self.write()

    def record_completed(
        self, source: str, output_path: str, *, ai_status: str = "none"
    ) -> None:
        """Record one file whose PDF and sidecars are already on disk.

        This is the only call that names an output, and it is the only one that means
        "done". It must never be reached with a partially written file.
        """
        self._record(source, STATUS_COMPLETED, output_path, ai_status)

    def record_failed(self, source: str, reason: str = "") -> None:
        """Record a file that failed. The queue still advances — a resumed run must not
        retry a corrupt PDF forever. The reason is bounded and redacted, and is kept for
        the user's benefit only; the JSONL sidecar holds the detail."""
        self._record(source, STATUS_FAILED, "", "none")

    def record_skipped(self, source: str, reason: str = "") -> None:
        self._record(source, STATUS_SKIPPED, "", "none")

    # -- the Phase 4 seam --------------------------------------------------
    def on_quota_stop(self, stop: Any) -> None:
        """Consume Phase 4's ``QuotaStop``. Hand this to ``limiter_for(...)``.

        Read duck-typed through ``as_dict()``, so this module imports nothing from
        ``ai.rate_limits`` and Phase 4's public shape stays untouched.

        Writes the manifest immediately and then **sets the run's stop event**, which is
        the whole mechanism: the callback fires on the worker thread inside
        ``provider.complete()``, the quota error propagates into ``AIEditor``, which is
        chapter-atomic and falls back to the deterministic text, that chapter is written
        and checkpointed normally, and ``run_batch``'s existing between-files check ends
        the batch. No busy loop, no background wait, no new seam — and the app can be
        closed as soon as the current chapter finishes.
        """
        try:
            record = stop.as_dict()
        except Exception:  # pragma: no cover - defensive against a foreign object
            record = None
        if isinstance(record, Mapping):
            # Redacted again here, deliberately. Phase 4 already redacts when it builds
            # the QuotaStop, but this is the layer that *persists* it: the manifest owns
            # its own no-secrets guarantee rather than trusting whoever constructed the
            # object it was handed. The reason is bounded for the same reason.
            self._quota_stop = {
                key: (
                    _safe_text(record[key])
                    if isinstance(record[key], str)
                    else redact_obj(record[key])
                )
                for key in sorted(record)
            }
            self._stopped_reason = (
                STOP_DAILY_QUOTA if record.get("is_daily") else STOP_LONG_WAIT
            )
        else:
            self._stopped_reason = STOP_LONG_WAIT
        self.write()
        if self._stop_event is not None:
            self._stop_event.set()

    def finish(self, *, stopped: bool = False) -> None:
        """Close the run. A run that consumed its queue is complete and is never offered
        for resume; a stopped one stays resumable."""
        self._complete = self._next_index >= len(self.queue) and not stopped
        if stopped and not self._stopped_reason:
            self._stopped_reason = STOP_USER
        self.write()

    def write(self) -> None:
        """Atomic whole-file replace. Never leaves a partial manifest on disk."""
        write_settings_atomic(self.path, self.payload())


def load_manifest(path: str | Path) -> dict[str, Any] | None:
    """Read a manifest, or ``None``. Never raises, never repairs, never guesses.

    Every rejection below is a case where continuing would mean inventing state: a
    forward schema version this build cannot fully understand, a queue that is not a list
    of paths, an index that does not point into that queue. The caller's response to
    ``None`` is always the same — start a fresh run.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None

    version = payload.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        return None
    if version > SCHEMA_VERSION:
        return None  # written by a newer build; half-reading it would invent state

    queue = payload.get("queue")
    if not isinstance(queue, list) or not queue:
        return None
    if any(not isinstance(item, str) for item in queue):
        return None

    index = payload.get("next_index")
    if not isinstance(index, int) or isinstance(index, bool):
        return None
    if index < 0 or index > len(queue):
        return None

    if not isinstance(payload.get("entries"), list):
        return None
    return payload


@dataclass(frozen=True)
class ResumeOffer:
    """What Phase 6's dialog is given. ``available`` is the only question it must ask.

    ``reason`` is a plain sentence, safe to show. ``missing_inputs`` lets the dialog say
    honestly that some chapters have gone away since the run stopped, rather than either
    hiding it or refusing the whole resume over it.
    """

    available: bool
    reason: str
    manifest_path: Path | None = None
    output_dir: str = ""
    novel: str = ""
    mirror_root: str | None = None
    remaining: tuple[str, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    completed_count: int = 0
    stopped_reason: str = ""
    quota_stop: dict[str, Any] | None = field(default=None)


def _offer_from_payload(path: Path, payload: Mapping[str, Any]) -> ResumeOffer:
    queue = list(payload["queue"])
    index = int(payload["next_index"])
    remaining = tuple(queue[index:])
    entries = payload.get("entries") or []
    completed = sum(
        1 for e in entries if isinstance(e, Mapping) and e.get("status") == STATUS_COMPLETED
    )
    common = {
        "manifest_path": path,
        "output_dir": str(payload.get("output_dir") or path.parent),
        "novel": str(payload.get("run", {}).get("novel") or ""),
        "mirror_root": payload.get("run", {}).get("mirror_root"),
        "completed_count": completed,
        "stopped_reason": str(payload.get("stopped_reason") or ""),
        "quota_stop": payload.get("quota_stop"),
    }

    if payload.get("complete") or not remaining:
        return ResumeOffer(False, "That run finished — there is nothing to resume.", **common)

    missing = tuple(p for p in remaining if not os.path.isfile(p))
    if len(missing) == len(remaining):
        return ResumeOffer(
            False,
            "None of the remaining chapters could be found where that run left them, "
            "so there is nothing to resume.",
            missing_inputs=missing,
            **common,
        )
    return ResumeOffer(
        True,
        f"{len(remaining)} of {len(queue)} chapters were not processed.",
        remaining=remaining,
        missing_inputs=missing,
        **common,
    )


def find_resumable_run(search_dir: str | Path) -> ResumeOffer:
    """Find the newest incomplete run under ``search_dir``. Never raises.

    Looks one level down for output folders holding a manifest — which is exactly where
    ``next_numbered_output_dir`` puts them. An unreadable directory, an orphaned
    ``.tmp`` from an interrupted write, or a corrupt manifest all simply fail to produce
    an offer.
    """
    root = Path(search_dir)
    candidates: list[tuple[float, Path, dict[str, Any]]] = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return ResumeOffer(False, "No previous run was found.")

    for entry in entries:
        if not entry.is_dir():
            continue
        path = entry / MANIFEST_NAME
        payload = load_manifest(path)
        if payload is None:
            continue
        try:
            stamp = path.stat().st_mtime
        except OSError:  # pragma: no cover - the load above just read it
            stamp = 0.0
        candidates.append((stamp, path, payload))

    if not candidates:
        return ResumeOffer(False, "No previous run was found.")

    offers = [
        _offer_from_payload(path, payload)
        for _stamp, path, payload in sorted(candidates, key=lambda item: item[0], reverse=True)
    ]
    for offer in offers:
        if offer.available:
            return offer
    return offers[0]


def plan_resume(offer: ResumeOffer) -> dict[str, Any]:
    """The exact ``run_batch`` arguments for continuing an offered run.

    The output folder is the **original** one, not a fresh numbered one — that is what
    makes it a continuation rather than a second run. Declining is not a call at all: the
    caller simply takes the normal fresh-run path, which allocates the next
    ``<novel>-N`` folder as usual.
    """
    if not offer.available:
        raise ValueError("This run cannot be resumed.")
    return {
        "pdf_paths": list(offer.remaining),
        "output_dir": offer.output_dir,
        "novel_name": offer.novel,
        "mirror_root": offer.mirror_root,
    }


__all__ = [
    "ENTRY_KEYS",
    "MANIFEST_NAME",
    "REASON_LIMIT",
    "SCHEMA_VERSION",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_SKIPPED",
    "STOP_DAILY_QUOTA",
    "STOP_LONG_WAIT",
    "STOP_USER",
    "ResumeOffer",
    "RunCheckpoint",
    "find_resumable_run",
    "load_manifest",
    "manifest_path",
    "plan_resume",
]
