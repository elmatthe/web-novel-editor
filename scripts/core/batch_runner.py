"""Batch runner — orchestrates the full per-file processing loop (Phase 3).

Phase 3 sequence per file: extract text -> (rules are Phase 4, skipped here) -> build
EDITED_<name>.pdf into the chosen folder. Each file is wrapped in its own try/except so
one failure (corrupt PDF, locked file, image-only scan) never stops the batch. Low-
confidence extractions (< MIN_CHARS) are skipped + logged rather than written as garbage.

Output never overwrites: `unique_output_path` appends a numeric suffix on collision.
The `dry_run` option runs extraction but skips PDF output (useful for the Phase-4 text
pipeline). `write_debug_text` saves the extracted text alongside the PDF for inspection.

Originals are only ever opened for reading; this module never writes to an input path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Sequence

from core.protected_lexicon import load_protected_lexicon
from core.replacement_log import ReplacementLog
from pdf.builder import build_pdf
from pdf.extractor import extract_text_from_pdf, is_low_confidence
from pipelines import shadow_slave
from profiles.shadow_slave.canonical_names import SS_CANONICAL_NAMES
from utils.file_utils import debug_text_path, unique_output_path

# Active novel profile (v1 supports Shadow Slave only). The novel-index file is
# user-maintained; a missing/empty file falls back to the built-in canonical names.
_NOVEL_INDEX = (
    Path(__file__).resolve().parents[2] / "files" / "novel-index" / "shadow-slave.txt"
)


def _noop(*_args, **_kwargs) -> None:
    pass


def run_batch(
    pdf_paths: Sequence[str],
    output_dir: str,
    *,
    write_replacement_log: bool = False,
    write_debug_text: bool = False,
    dry_run: bool = False,
    gui_log: Callable[..., None] | None = None,
    progress: Callable[[int], None] | None = None,
) -> dict:
    """Process each PDF sequentially and return a run summary dict.

    Callbacks (both optional):
        gui_log(message, level="info") — progress/diagnostic lines for the UI/log.
        progress(value:int)           — number of files completed so far (1..N).

    Returns: {total, succeeded, failed, skipped, output_dir, outputs:[paths]}.
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

    # Load the protected lexicon once for the whole run (built-in names + user terms).
    lexicon = load_protected_lexicon(str(_NOVEL_INDEX), SS_CANONICAL_NAMES)
    log(f"Loaded {len(lexicon.terms)} protected term(s) for Shadow Slave.", "muted")
    pipe_log = (lambda m: log(m, "muted")) if gui_log else None

    for i, src in enumerate(pdf_paths, start=1):
        name = os.path.basename(src)
        try:
            if not os.path.isfile(src):
                log(f"  [{i}/{total}] SKIP (not found): {name}", "warn")
                skipped += 1
                continue

            log(f"  [{i}/{total}] Extracting: {name}", "info")
            text = extract_text_from_pdf(src)

            if is_low_confidence(text):
                log(f"  [{i}/{total}] SKIP (low-confidence/empty extraction, "
                    f"{len(text.strip())} chars): {name}", "warn")
                skipped += 1
                continue

            # Run the deterministic editorial pipeline (extract -> clean -> build).
            repl_log = ReplacementLog() if write_replacement_log else None
            text = shadow_slave.run_pipeline(
                text, lexicon, repl_log=repl_log, gui_log=pipe_log, dry_run=dry_run
            )

            if dry_run:
                log(f"  [{i}/{total}] Dry run, no PDF written ({len(text)} chars): "
                    f"{name}", "info")
                succeeded += 1
                continue

            out_path = unique_output_path(output_dir, name)
            build_pdf(text, out_path)
            outputs.append(out_path)
            log(f"  [{i}/{total}] Wrote: {os.path.basename(out_path)}", "success")

            if repl_log is not None:
                jsonl = os.path.splitext(out_path)[0] + "_replacements.jsonl"
                repl_log.write_jsonl(jsonl)
                log(f"        replacement log ({len(repl_log)}) -> "
                    f"{os.path.basename(jsonl)}", "muted")

            if write_debug_text:
                dbg = debug_text_path(out_path)
                with open(dbg, "w", encoding="utf-8") as fh:
                    fh.write(text)
                log(f"        debug text -> {os.path.basename(dbg)}", "muted")

            succeeded += 1

        except Exception as exc:  # continue-on-failure: never abort the batch
            failed += 1
            log(f"  [{i}/{total}] FAILED: {name} -> {type(exc).__name__}: {exc}",
                "error")
        finally:
            tick(i)

    summary = {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "output_dir": output_dir,
        "outputs": outputs,
    }
    log(f"Batch complete: {succeeded} ok, {failed} failed, {skipped} skipped "
        f"of {total}.", "success" if failed == 0 else "warn")
    return summary
