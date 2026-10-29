"""Checkpointed runs — the atomic run manifest and the resume decision.

After **each completed file** the run's state can be written atomically into the output
folder, so a run can be stopped at any moment and picked up later from exactly where it
stopped. (Phase 01A retired the cloud-only wiring; script-only persistent resume is
completed in Phase 02A. The seam is kept intact and tested.)

Three rules shape everything here.

**Checkpoints are file-boundary only.** A file is either fully checkpointed as complete
or not checkpointed at all. The recording call sits on the far side of ``build_pdf`` and
its sidecars, so a manifest entry means "the output exists".

**Never guess at partial state.** :func:`load_manifest` rejects rather than repairs — a
missing, truncated, mis-shaped, or differently-versioned manifest returns ``None`` and
the caller starts a fresh run. It never raises, because the caller is a GUI. In
particular a **schema-1 manifest written by the retired cloud runs is refused**: it has
no deterministic-output guarantees and may reference AI-edited outputs, so it is never
converted into a script-only resume. It is left untouched on disk.

**Nothing sensitive is written.** There is no field that could carry chapter text.

The writer is ``utils.settings.write_settings_atomic`` — tempfile + ``fsync`` +
``os.replace``. The whole manifest is rewritten each time rather than appended to: an
append-only journal is exactly the shape a kill can leave half-written, whereas a
whole-file atomic replace means the file on disk is always a complete, valid manifest.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from utils.settings import write_settings_atomic

MANIFEST_NAME = "run-manifest.json"

#: Bumped only when the payload shape changes incompatibly. Only this exact version is
#: read: a newer one is refused rather than partially read, and schema 1 (the retired
#: cloud-run manifests) is refused rather than converted.
SCHEMA_VERSION = 2

STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

STOP_USER = "user_stop"

#: The only keys an entry may ever carry. Asserted by a test, because the natural way to
#: leak chapter text is to add a well-meaning "summary" or "preview" field later.
ENTRY_KEYS = ("source", "status", "output", "size", "mtime_ns", "recorded_at")


def manifest_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / MANIFEST_NAME


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
        clock: Callable[[], float] = time.time,
        start_index: int = 0,
    ):
        self.output_dir = str(output_dir)
        self.queue = [str(item) for item in queue]
        self._clock = clock
        self._run = {
            "novel": novel,
            "mirror_root": mirror_root,
            "started_at": clock(),
        }
        self._entries: list[dict[str, Any]] = []
        self._next_index = max(0, int(start_index))
        self._stopped_reason = ""
        self._complete = False

    # -- state -------------------------------------------------------------
    @property
    def path(self) -> Path:
        return manifest_path(self.output_dir)

    @property
    def next_index(self) -> int:
        return self._next_index

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "run": dict(self._run),
            "output_dir": self.output_dir,
            "queue": list(self.queue),
            "next_index": self._next_index,
            "entries": [dict(entry) for entry in self._entries],
            "stopped_reason": self._stopped_reason,
            "complete": self._complete,
        }

    # -- recording ---------------------------------------------------------
    def _record(self, source: str, status: str, output: str) -> None:
        size, mtime_ns = _identity(source)
        self._entries.append(
            {
                "source": str(source),
                "status": status,
                "output": str(output or ""),
                "size": size,
                "mtime_ns": mtime_ns,
                "recorded_at": self._clock(),
            }
        )
        self._next_index += 1
        self.write()

    def record_completed(self, source: str, output_path: str) -> None:
        """Record one file whose PDF and sidecars are already on disk.

        This is the only call that names an output, and it is the only one that means
        "done". It must never be reached with a partially written file.
        """
        self._record(source, STATUS_COMPLETED, output_path)

    def record_failed(self, source: str, reason: str = "") -> None:
        """Record a file that failed. The queue still advances — a resumed run must not
        retry a corrupt PDF forever. The reason is deliberately not persisted; the JSONL
        sidecar holds the detail."""
        self._record(source, STATUS_FAILED, "")

    def record_skipped(self, source: str, reason: str = "") -> None:
        self._record(source, STATUS_SKIPPED, "")

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
    if version != SCHEMA_VERSION:
        # Newer: written by a later build, half-reading it would invent state.
        # Older (schema 1): a retired cloud-run manifest - never converted to a resume.
        return None

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
    "SCHEMA_VERSION",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_SKIPPED",
    "STOP_USER",
    "ResumeOffer",
    "RunCheckpoint",
    "find_resumable_run",
    "load_manifest",
    "manifest_path",
    "plan_resume",
]
