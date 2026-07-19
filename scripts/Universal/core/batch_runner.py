"""Batch runner — orchestrates the full per-file processing loop.

Sequence per file: extract text -> editorial rule pipeline -> build <name>.pdf (the
original filename, kept as-is since v0.11.0) into the output folder. Each file is
wrapped in its own try/except so one failure (corrupt PDF, locked file, image-only
scan) never stops the batch. Low-confidence extractions (< MIN_CHARS) are skipped +
logged rather than written as garbage.

Folder-input mode passes `mirror_root` (the selected input folder): each output then
lands in a subfolder of `output_dir` mirroring the input tree, with the selected
folder's own name as the root inside it. Without `mirror_root` (upload mode) all
outputs land flat in `output_dir`.

Output never overwrites: `unique_output_path` appends a numeric suffix on collision.
The `dry_run` option runs extraction but skips PDF output (useful for the Phase-4 text
pipeline). `write_debug_text` saves the extracted text alongside the PDF for inspection.

Pause/continue (v0.11.0): an optional `pause_gate` Event is consulted BETWEEN files
(set = run, cleared = pause). The file being processed always finishes — the gate can
never interrupt mid-write, which is exactly the safe seam the deferred *cancellation*
discussion (DECISIONS #020) said run_batch lacked.

The GUI log is condensed (v0.11.0): one line per file plus an end-of-batch summary
block. Verbose per-stage/per-replacement detail lives only in the JSONL replacement
log; pipeline "⚠" integrity warnings still surface in the GUI.

Originals are only ever opened for reading; this module never writes to an input path.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable, Optional, Sequence

from core.edit_details import load_edit_details
from core.novel_registry import NOVEL_INDEX_DIR, resolve_dispatch
from core.protected_lexicon import load_protected_lexicon
from core.replacement_log import ReplacementLog
from pdf.builder import build_pdf, detect_heading_only_pages
from pdf.extractor import extract_text_from_pdf, is_low_confidence
from utils.file_utils import debug_text_path, unique_output_path


def _noop(*_args, **_kwargs) -> None:
    pass


def run_batch(
    pdf_paths: Sequence[str],
    output_dir: str,
    *,
    write_replacement_log: bool = False,
    write_debug_text: bool = False,
    dry_run: bool = False,
    novel_name: Optional[str] = None,
    mirror_root: Optional[str] = None,
    pause_gate: Optional[threading.Event] = None,
    gui_log: Callable[..., None] | None = None,
    progress: Callable[[int], None] | None = None,
) -> dict:
    """Process each PDF sequentially and return a run summary dict.

    `mirror_root` (folder-input mode) is the selected input folder: each file's output
    is written under `output_dir/<mirror_root's own name>/<relative subpath>`, so the
    input tree is mirrored inside the output folder. None (upload mode) = flat output.

    `novel_name` selects the editorial pipeline via `core.novel_registry.resolve_dispatch`.
    A registered novel (e.g. "Shadow Slave") runs its real profile pipeline; any other
    value — including None (the default) — falls back to **universal-only** editing (the
    universal rules with no novel-specific substitutions). The GUI always passes the
    selected novel explicitly; the bare default is universal-only by design.

    `pause_gate` (optional) is the cooperative pause seam: an Event that is SET while
    the batch should run. It is consulted only BETWEEN files — if cleared, the loop
    logs "Paused after chapter N of M" and blocks on `pause_gate.wait()` until set
    again (Continue). The current file always completes first, so pausing can never
    corrupt an output mid-write. Session-only: the gate lives with the caller.

    Callbacks (both optional):
        gui_log(message, level="info") — progress/diagnostic lines for the UI/log.
        progress(value:int)           — number of files completed so far (1..N).

    Returns: {total, succeeded, failed, skipped, output_dir, outputs:[paths],
    novel, profile_applied} — the last two are the run's dispatch provenance (the
    resolved display name and whether a real per-novel profile ran vs. universal-only).
    """
    log = gui_log or _noop
    tick = progress or _noop

    total = len(pdf_paths)
    succeeded = 0
    failed = 0
    skipped = 0
    outputs: list[str] = []

    if not dry_run:
        os.makedirs(output_dir, exist_ok=True)

    log(f"Starting batch: {total} file(s).", "accent")
    log(f"Output folder: {output_dir}", "muted")

    # Resolve the selected novel to its pipeline + profile (universal-only fallback when
    # the novel has no real editorial profile). This is the single dispatch seam.
    dispatch = resolve_dispatch(novel_name)
    selected_label = novel_name if novel_name else "(none — universal-only)"
    log(f"Selected novel: {selected_label}", "accent")

    # Load the per-novel edit details markdown: UNIVERSAL.md is always the base; the
    # selected novel's <Novel-Name>.md is layered on top when it exists, else universal.
    details = load_edit_details(novel_name)
    log("Loaded universal editor rules (UNIVERSAL.md).", "muted")
    if dispatch.has_profile:
        layer = details.novel_path.name if details.novel_path else "built-in profile"
        log(f"Applied novel-specific editing layer for "
            f"{dispatch.display_name} ({layer}).", "muted")
    elif (novel_name or "").strip().lower() == "universal":
        # "Universal" is an explicit, intentional roster choice (the default since
        # Plan 1 Phase 3) — not a novel that happens to lack a profile.
        log("Universal editing selected — applying the standard universal-only "
            "editing (no novel-specific layer).", "muted")
    else:
        log(f"No novel-specific profile for '{selected_label}' — "
            f"universal-only editing.", "muted")

    # Load the protected lexicon once for the whole run (built-in names + user index).
    index_path = (
        str(NOVEL_INDEX_DIR / dispatch.index_filename) if dispatch.index_filename else ""
    )
    lexicon = load_protected_lexicon(index_path, dispatch.canonical_names)
    log(f"Loaded {len(lexicon.terms)} protected term(s) for "
        f"{dispatch.display_name}.", "muted")
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

    failed_files: list[tuple[str, str]] = []
    skipped_files: list[tuple[str, str]] = []

    for i, src in enumerate(pdf_paths, start=1):
        # Cooperative pause seam (v0.11.0): consulted only BETWEEN files, so the file
        # that was in flight when Pause was clicked has already fully completed (its
        # one-line result is logged) and nothing holds before the first file or after
        # the last. Cleared gate = hold here until Continue sets it again.
        if pause_gate is not None and i > 1 and not pause_gate.is_set():
            log(f"Paused after chapter {i - 1} of {total}.", "warn")
            pause_gate.wait()
            log(f"Continuing with chapter {i} of {total}.", "accent")

        name = os.path.basename(src)
        try:
            if not os.path.isfile(src):
                skipped += 1
                skipped_files.append((name, "not found"))
                log(f"[{i}/{total}] {name} — skipped (not found)", "warn")
                continue

            text = extract_text_from_pdf(src)

            if is_low_confidence(text):
                skipped += 1
                skipped_files.append((name, "image-only/empty"))
                log(f"[{i}/{total}] {name} — skipped (image-only/empty)", "warn")
                continue

            # Run the selected novel's editorial pipeline. The ReplacementLog is now
            # always built (it feeds the condensed line's edit count); the JSONL file
            # itself is still written only when the option is enabled.
            repl_log = ReplacementLog(metadata=run_metadata)
            text = dispatch.run_pipeline(
                text, lexicon, repl_log=repl_log, gui_log=pipe_log, dry_run=dry_run
            )
            edits = len(repl_log)
            edits_label = f"{edits} edit" + ("" if edits == 1 else "s")

            if dry_run:
                log(f"[{i}/{total}] {name} — done (dry run, {edits_label})", "info")
                succeeded += 1
                continue

            # Folder mode: mirror the input tree (rooted at the selected folder's own
            # name) inside output_dir; a file somehow outside mirror_root falls back
            # to the flat output root rather than failing the batch.
            file_out_dir = output_dir
            if mirror_root:
                try:
                    rel = Path(src).parent.relative_to(Path(mirror_root).parent)
                    file_out_dir = os.path.join(output_dir, *rel.parts)
                except ValueError:
                    pass
                os.makedirs(file_out_dir, exist_ok=True)

            out_path = unique_output_path(file_out_dir, name)
            build_pdf(text, out_path)
            outputs.append(out_path)
            log(f"[{i}/{total}] {name} — done ({edits_label})", "success")

            # Phase 6 (detection-only, never deletes): a heading-only page can
            # only arise from multi-chapter input (the pipeline puts \f before
            # each later heading), so single-chapter builds — today's normal
            # case — skip the post-build scan entirely.
            if len([p for p in text.split("\f") if p.strip()]) >= 2:
                flagged_pages = detect_heading_only_pages(out_path)
                if flagged_pages:
                    pages_str = ", ".join(str(p) for p in flagged_pages)
                    log(f"        ⚠ heading-only page(s) {pages_str} in "
                        f"{os.path.basename(out_path)} — preserved (review: "
                        f"title-only chapter or upstream data loss)", "warn")
                    repl_log.record(
                        f"heading-only page(s): {pages_str}",
                        "[FLAGGED: heading-only page(s) preserved - review]",
                        "pdf.heading_only_page_flag",
                        "integrity_flag",
                        os.path.basename(out_path),
                    )

            # Sidecars are written silently (condensed log: one line per file); the
            # end-of-batch summary already points the user at the output folder.
            if write_replacement_log:
                jsonl = os.path.splitext(out_path)[0] + "_replacements.jsonl"
                repl_log.write_jsonl(jsonl)

            if write_debug_text:
                dbg = debug_text_path(out_path)
                with open(dbg, "w", encoding="utf-8") as fh:
                    fh.write(text)

            succeeded += 1

        except Exception as exc:  # continue-on-failure: never abort the batch
            failed += 1
            reason = f"{type(exc).__name__}: {exc}"
            failed_files.append((name, reason))
            log(f"[{i}/{total}] {name} — FAILED ({reason})", "error")
        finally:
            tick(i)

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
    # End-of-batch summary block: totals, then the failed/skipped files by name so
    # problem files are findable without scrolling (sections omitted when empty).
    log(f"Batch complete: {succeeded} done, {failed} failed, {skipped} skipped "
        f"of {total}.", "success" if failed == 0 else "warn")
    if failed_files:
        log("Failed:", "error")
        for name, reason in failed_files:
            log(f"  - {name} ({reason})", "error")
    if skipped_files:
        log("Skipped:", "warn")
        for name, reason in skipped_files:
            log(f"  - {name} ({reason})", "warn")
    return summary
