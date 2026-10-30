"""Sequential mixed-input worker using the existing editorial dispatch and batch loop.

Every real output uses a locked schema-3 checkpoint, staged selected formats and
required companions. Dry runs write nothing. Pause/Stop remain file-boundary only.
Source files are read-only; persistence/ownership failures stop the worker.
"""

from __future__ import annotations

import os
import threading
import re
from pathlib import Path
from typing import Callable, Optional, Sequence

from core.edit_details import load_edit_details
from core.novel_registry import NOVEL_INDEX_DIR, resolve_dispatch
from core.protected_lexicon import load_protected_lexicon
from core.replacement_log import ReplacementLog
from core.run_manifest import (RunCheckpoint, ManifestError, CheckpointError,
                               read_manifest, manifest_path, effective_rules_digest)
from core.run_lock import LockConflict
from pdf.builder import build_pdf, detect_heading_only_pages
from pdf.extractor import extract_text_from_pdf, is_low_confidence


def _noop(*_args, **_kwargs) -> None:
    pass


class TextInputError(ValueError):
    """A fixed, actionable decoding message safe for ordinary diagnostics."""


def run_batch(pdf_paths, output_dir, *, output_formats=("pdf",), resume=False,
              retry_failed=False, recover_stale=False, import_roots=None, **kwargs):
    """Own one immutable script-only run for the entire sequential worker lifetime.

    Resume loads the original full queue, formats, companions and profile; current
    GUI preferences never replace frozen settings. Explicit stale recovery is opt-in.
    """
    paths = [str(Path(p).absolute()) for p in pdf_paths]
    track = kwargs.pop("checkpoint", None)
    if resume:
        saved = read_manifest(manifest_path(output_dir))
        if paths and paths != saved["queue"]:
            raise ManifestError("Resume requires the original full ordered queue")
        paths = saved["queue"]
        options = saved["run"]["options"]
        output_formats = tuple(options["formats"])
        kwargs.update(novel_name=saved["run"]["novel"], dry_run=False,
                      write_debug_text=options["write_debug_text"],
                      write_replacement_log=options["write_replacement_log"])
    if not output_formats or set(output_formats) - {"pdf", "txt"} or len(set(output_formats)) != len(output_formats):
        raise ValueError("Select at least one output format")
    if len(set(os.path.normcase(p) for p in paths)) != len(paths):
        raise ValueError("Duplicate source path")
    if retry_failed and not resume:
        raise ValueError("Retry Failed requires the original run")
    stop = kwargs.get("stop_event")
    dry = kwargs.get("dry_run", False)
    if dry or not paths or (not resume and stop is not None and stop.is_set()):
        return _run_batch(paths, output_dir, output_formats=output_formats, **kwargs)
    novel = kwargs.get("novel_name")
    dispatch = resolve_dispatch(novel)
    index = str(NOVEL_INDEX_DIR / dispatch.index_filename) if dispatch.index_filename else ""
    lexicon = load_protected_lexicon(index, dispatch.canonical_names)
    digest = effective_rules_digest(novel, dispatch, lexicon)
    try:
        if resume:
            track = RunCheckpoint.resume(output_dir, rules_digest=digest, recover=recover_stale)
        else:
            track = track or RunCheckpoint(output_dir, paths, novel=novel,
                                           mirror_root=kwargs.get("mirror_root"), import_roots=import_roots)
            if track.queue != paths:
                raise ManifestError("Checkpoint queue differs from worker queue")
            if track.novel != (novel or ""):
                raise ManifestError("Checkpoint profile differs from worker profile")
            track.start(formats=output_formats, rules_digest=digest,
                        write_debug_text=kwargs.get("write_debug_text", False),
                        write_replacement_log=kwargs.get("write_replacement_log", False))
        for entry in track.payload()["entries"]:
            if kwargs.get("gui_log"):
                destinations = ", ".join(entry["outputs"].values())
                kwargs["gui_log"](f"Output mapping: {Path(entry['source']).name} → {destinations}", "muted")
        return _run_batch(paths, output_dir, checkpoint=track, output_formats=output_formats,
                          retry_failed=retry_failed, _dispatch=dispatch, _lexicon=lexicon, **kwargs)
    finally:
        if track is not None:
            track.close()


def serialize_txt(text: str) -> str:
    """TXT product format: LF, readable paragraph/chapter breaks, final newline."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def _run_batch(
    pdf_paths: Sequence[str],
    output_dir: str,
    *,
    write_replacement_log: bool = False,
    write_debug_text: bool = False,
    dry_run: bool = False,
    novel_name: Optional[str] = None,
    mirror_root: Optional[str] = None,
    pause_gate: Optional[threading.Event] = None,
    stop_event: Optional[threading.Event] = None,
    checkpoint: RunCheckpoint | None = None,
    output_formats=("pdf",),
    retry_failed=False,
    _dispatch=None,
    _lexicon=None,
    gui_log: Callable[..., None] | None = None,
    progress: Callable[[int], None] | None = None,
) -> dict:
    """Process eligible original-queue items; only verified publication counts as success.

    Callbacks retain the historical condensed log and progress seams. Attempt totals
    describe this invocation; durable terminal totals describe the complete run.
    """
    log = gui_log or _noop
    tick = progress or _noop

    total = len(pdf_paths)
    succeeded = 0
    failed = 0
    skipped = 0
    outputs: list[str] = []
    stopped = False
    # A dry run writes no PDF and no output folder, so it writes no manifest either.
    track = checkpoint if (checkpoint is not None and not dry_run) else None

    log(f"Starting batch: {total} file(s).", "accent")
    log(f"Output folder: {output_dir}", "muted")

    # Resolve the selected novel to its pipeline + profile (universal-only fallback when
    # the novel has no real editorial profile). This is the single dispatch seam.
    dispatch = _dispatch or resolve_dispatch(novel_name)
    selected_label = novel_name if novel_name else "(none — universal-only)"
    log(f"Selected novel: {selected_label}", "accent")

    # Load the per-novel edit details markdown: UNIVERSAL.md is always the base; the
    # selected novel's <Novel-Name>.md is layered on top when it exists, else universal.
    details = load_edit_details(novel_name)
    log("Loaded universal editor rules (UNIVERSAL.md).", "muted")

    # Load the protected lexicon once for the whole run (built-in names + user index).
    index_path = (
        str(NOVEL_INDEX_DIR / dispatch.index_filename) if dispatch.index_filename else ""
    )
    lexicon = _lexicon or load_protected_lexicon(index_path, dispatch.canonical_names)
    term_count = len(lexicon.terms)
    log(f"Loaded {term_count} protected term(s) for "
        f"{dispatch.display_name}.", "muted")

    # The profile line comes AFTER the lexicon on purpose: it must be able to say whether
    # the novel's names are protected, and "has a profile" and "has protected names" are
    # two independent facts that this line used to collapse into one. Saying "no
    # novel-specific profile — universal-only editing" for a novel carrying 1,429
    # protected terms was technically true and read as the exact opposite of the truth.
    if dispatch.has_profile:
        layer = details.novel_path.name if details.novel_path else "built-in profile"
        log(f"Applied novel-specific editing layer for "
            f"{dispatch.display_name} ({layer}).", "muted")
    elif (novel_name or "").strip().lower() == "universal":
        # "Universal" is an explicit, intentional roster choice (the default since
        # Plan 1 Phase 3) — not a novel that happens to lack a profile.
        log("Universal editing selected — applying the standard universal-only "
            "editing (no novel-specific layer).", "muted")
    elif term_count:
        log(f"No novel-specific fix-up rules for '{selected_label}' — universal "
            f"editing rules apply, and its {term_count} protected name(s) are "
            f"preserved.", "muted")
    else:
        log(f"No novel-specific fix-up rules and no protected names for "
            f"'{selected_label}' — universal editing rules only.", "muted")
    # Condensed log (v0.11.0): the pipeline's verbose per-stage chatter stays out of
    # the GUI (the JSONL carries the detail); its "⚠" integrity warnings (e.g. CDN
    # error pages, DECISIONS #005) must still surface loudly.
    pipe_log = (
        (lambda m: log(m, "warn") if "⚠" in m else None) if gui_log else None
    )

    # Run-level dispatch provenance (Phase 5): recorded once per run and stamped onto
    # every JSONL replacement log as a run_metadata header, so which novel/pipeline/mode
    # produced an output is provable from the log itself, in both modes.
    run_metadata = {
        "selected": novel_name or "",
        "novel": dispatch.display_name,
        "mode": "novel-profile" if dispatch.has_profile else "universal-only",
        "pipeline": dispatch.run_pipeline.__module__,
        "protected_terms": len(lexicon.terms),
    }

    if total and not dry_run and not (stop_event is not None and stop_event.is_set()):
        os.makedirs(output_dir, exist_ok=True)

    failed_files: list[tuple[str, str]] = []
    skipped_files: list[tuple[str, str]] = []

    for i, src in enumerate(pdf_paths, start=1):
        if track is not None:
            entry = track.entry(src)
            if entry["status"] == "completed" or (retry_failed and entry["status"] not in {"failed", "prepared"}):
                continue
            if not retry_failed and entry["status"] in {"failed", "skipped"}:
                continue
        if stop_event is not None and stop_event.is_set():
            stopped = True
            log(f"Stop requested — batch ended before chapter {i} of {total}.", "warn")
            break
        # Cooperative pause seam (v0.11.0): consulted only BETWEEN files, so the file
        # that was in flight when Pause was clicked has already fully completed (its
        # one-line result is logged) and nothing holds before the first file or after
        # the last. Cleared gate = hold here until Continue sets it again.
        if pause_gate is not None and i > 1 and not pause_gate.is_set():
            log(f"Paused after chapter {i - 1} of {total}.", "warn")
            if isinstance(pause_gate, threading.Event):
                while not pause_gate.wait(0.1):
                    if stop_event is not None and stop_event.is_set():
                        break
            else:
                pause_gate.wait()
            # Stop may be what released a paused worker. Re-check before logging
            # Continue or beginning any extraction/PDF work for this file.
            if stop_event is not None and stop_event.is_set():
                stopped = True
                log(
                    f"Stop requested — batch ended before chapter {i} of {total}.",
                    "warn",
                )
                break
            log(f"Continuing with chapter {i} of {total}.", "accent")

        name = os.path.basename(src)
        try:
            if track is not None and track.entry(src)["status"] == "prepared":
                track.publish(src)
                outputs.extend(str(Path(output_dir) / p) for kind, p in track.entry(src)["outputs"].items()
                               if kind in {"pdf", "txt"})
                succeeded += 1
                log(f"[{i}/{total}] {name} — done (recovered publication)", "success")
                continue
            if not os.path.isfile(src):
                skipped += 1
                skipped_files.append((name, "not found"))
                log(f"[{i}/{total}] {name} — skipped (not found)", "warn")
                if track is not None:
                    track.record_skipped(src, "not found")
                continue

            if track is not None:
                track.verify_source(src)
            is_txt = Path(src).suffix.lower() == ".txt"
            if is_txt:
                try:
                    text = Path(src).read_text(encoding="utf-8-sig")
                except UnicodeDecodeError as exc:
                    raise TextInputError("TXT must be UTF-8 or UTF-8 BOM; convert the source encoding and start a new run") from exc
                text = text.replace("\r\n", "\n").replace("\r", "\n")
                if "\x00" in text:
                    raise TextInputError("TXT contains NUL characters; convert the source encoding and start a new run")
            else:
                text = extract_text_from_pdf(src)

            empty = not text.strip() if is_txt else is_low_confidence(text)
            if empty:
                skipped += 1
                skipped_files.append((name, "image-only/empty"))
                log(f"[{i}/{total}] {name} — skipped (image-only/empty)", "warn")
                if track is not None:
                    track.record_skipped(src, "image-only/empty")
                continue

            # Run the selected novel's editorial pipeline. The ReplacementLog is now
            # always built (it feeds the condensed line's edit count); the JSONL file
            # itself is still written only when the option is enabled.
            repl_log = ReplacementLog(metadata=run_metadata)
            pipe_options = {"repl_log": repl_log, "gui_log": pipe_log, "dry_run": dry_run}
            if is_txt:
                pipe_options["input_kind"] = "txt"
            text = dispatch.run_pipeline(text, lexicon, **pipe_options)
            # Edit count for the condensed line: real edits only. integrity_flag
            # records (error pages #005, heading-only pages #017) mark problems,
            # not edits — they stay in the JSONL but must not inflate this count.
            edits = sum(
                1 for e in repl_log.entries if e.category != "integrity_flag"
            )
            edits_label = f"{edits} edit" + ("" if edits == 1 else "s")
            if dry_run:
                log(f"[{i}/{total}] {name} — done (dry run, {edits_label})", "info")
                succeeded += 1
                continue

            if track is None:
                raise ManifestError("Real output requires durable run ownership")
            entry = track.entry(src)
            if "pdf" in output_formats:
                track.stage(src, "pdf", lambda path: build_pdf(text, str(path)))
            if "txt" in output_formats:
                track.stage(src, "txt", lambda path: path.write_text(serialize_txt(text), encoding="utf-8", newline="\n"))

            # Phase 6 (detection-only, never deletes): a heading-only page can
            # only arise from multi-chapter input (the pipeline puts \f before
            # each later heading), so single-chapter builds — today's normal
            # case — skip the post-build scan entirely.
            if "pdf" in output_formats and len([p for p in text.split("\f") if p.strip()]) >= 2:
                pdf_stage = Path(output_dir) / entry["staged"]["pdf"]
                flagged_pages = detect_heading_only_pages(str(pdf_stage))
                if flagged_pages:
                    pages_str = ", ".join(str(p) for p in flagged_pages)
                    log(f"        ⚠ heading-only page(s) {pages_str} in "
                        f"{Path(entry['outputs']['pdf']).name} — preserved (review: "
                        f"title-only chapter or upstream data loss)", "warn")
                    repl_log.record(
                        f"heading-only page(s): {pages_str}",
                        "[FLAGGED: heading-only page(s) preserved - review]",
                        "pdf.heading_only_page_flag",
                        "integrity_flag",
                        Path(entry["outputs"]["pdf"]).name,
                    )

            # Sidecars are written silently (condensed log: one line per file); the
            # end-of-batch summary already points the user at the output folder.
            if write_replacement_log:
                track.stage(src, "audit", lambda path: repl_log.write_jsonl(str(path)))

            if write_debug_text:
                track.stage(src, "debug", lambda path: path.write_text(text, encoding="utf-8", newline="\n"))

            # Checkpoint LAST, on the far side of the PDF and its sidecars: a
            # `completed` entry must always mean the output really exists, so a
            # resumed run never skips a chapter it never wrote.
            track.prepare(src)
            track.publish(src)
            outputs.extend(str(Path(output_dir) / path) for kind, path in entry["outputs"].items()
                           if kind in {"pdf", "txt"})
            succeeded += 1
            log(f"[{i}/{total}] {name} — done ({edits_label})", "success")

        except (CheckpointError, LockConflict):
            log("Run ownership/checkpoint failed — stopped safely; no further file started.", "error")
            raise
        except Exception as exc:  # continue-on-failure: never abort the batch
            failed += 1
            reason = f"{type(exc).__name__}: processing/publication failed; review source encoding, readability or destination access"
            if isinstance(exc, (TextInputError, ManifestError)):
                reason = f"{type(exc).__name__}: {exc}"
            failed_files.append((name, reason))
            log(f"[{i}/{total}] {name} — FAILED ({reason})", "error")
            # Recorded as failed, and the queue still advances — otherwise a resumed
            # run would retry the same corrupt PDF forever.
            if track is not None:
                track.record_failed(src, type(exc).__name__)
        finally:
            tick(i)

    if track is not None:
        # A run that consumed its queue is marked complete and is never offered for
        # resume; a stopped one stays resumable from exactly here.
        track.finish(stopped=stopped)

    summary = {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "output_dir": output_dir,
        "outputs": outputs,
        "novel": dispatch.display_name,
        "profile_applied": dispatch.has_profile,
    }
    if stopped:
        summary["stopped"] = True
    if track is not None:
        statuses = [e["status"] for e in track.payload()["entries"]]
        summary.update(completed_total=statuses.count("completed"),
                       failed_total=statuses.count("failed") + statuses.count("prepared"),
                       skipped_total=statuses.count("skipped"),
                       pending_total=statuses.count("pending"),
                       run_complete=track.payload()["complete"],
                       finished_with_errors=any(s in {"failed", "prepared"} for s in statuses))
    # End-of-batch summary block: totals, then the failed/skipped files by name so
    # problem files are findable without scrolling (sections omitted when empty).
    log(f"Batch complete: {succeeded} done, {failed} failed, {skipped} skipped "
        f"of {total}.", "warn" if failed or summary.get("finished_with_errors") else "success")
    if summary.get("finished_with_errors"):
        log(f"Run retains {summary['failed_total']} failed/incomplete item(s). Use Retry Failed after resolving access/readability problems.", "warn")
    if summary.get("pending_total"):
        log(f"Run incomplete: {summary['pending_total']} pending item(s). Use Resume Run to continue the original queue.", "warn")
    if failed_files:
        log("Failed:", "error")
        for name, reason in failed_files:
            log(f"  - {name} ({reason})", "error")
    if skipped_files:
        log("Skipped:", "warn")
        for name, reason in skipped_files:
            log(f"  - {name} ({reason})", "warn")
    return summary
