"""Replacement audit log — JSONL output of every substitution the pipeline makes.

Phase 4 deliverable (ported/adapted from `ss_pdf_editor-v1.py`). Phase 1 defines
the dataclass shapes so other modules can type against them; serialization and the
recording API are fleshed out in Phase 4.

One JSONL record per replacement, written alongside each output PDF as
`EDITED_<name>_replacements.jsonl` when the option is enabled. Every junk_strip
removal (Stage 1.5) is logged here too.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class ReplacementEntry:
    """A single substitution made by a rule.

    Attributes:
        original: the text that was replaced.
        replacement: what it became (empty string for a pure removal).
        rule: the rule function/category that made the change (e.g. "junk_strip").
        category: coarse grouping (e.g. "fingerprint", "punctuation", "name").
        context: a short surrounding snippet for human audit.
    """

    original: str
    replacement: str
    rule: str
    category: str = ""
    context: str = ""


@dataclass
class ReplacementLog:
    """Collects ReplacementEntry records for one file and writes them as JSONL.

    `metadata`, when set, is run-level dispatch provenance (which novel/pipeline/mode
    produced this log). It is written as a single `{"record": "run_metadata", ...}`
    header line ahead of the entries — a run header, not a per-event field, so
    individual replacement records keep their existing schema. It never counts toward
    `len(log)`.
    """

    entries: list[ReplacementEntry] = field(default_factory=list)
    metadata: dict | None = None

    def record(
        self,
        original: str,
        replacement: str,
        rule: str,
        category: str = "",
        context: str = "",
    ) -> None:
        """Append a replacement record.

        No-op changes (original == replacement) are dropped so the log stays a
        faithful record of what actually changed. The context snippet is
        flattened to a single line and clipped for readable audit output.
        """
        if original == replacement:
            return
        ctx = " ".join(context.split())[:160]
        self.entries.append(
            ReplacementEntry(
                original=original,
                replacement=replacement,
                rule=rule,
                category=category,
                context=ctx,
            )
        )

    def write_jsonl(self, path: str) -> None:
        """Serialize entries to a UTF-8 JSONL file (one record per line).

        When `metadata` is set, a `run_metadata` header record is written first so the
        log carries its own dispatch provenance on disk.
        """
        with open(path, "w", encoding="utf-8") as fh:
            if self.metadata is not None:
                fh.write(
                    json.dumps({"record": "run_metadata", **self.metadata},
                               ensure_ascii=False)
                    + "\n"
                )
            for e in self.entries:
                fh.write(
                    json.dumps(
                        {
                            "original": e.original,
                            "replacement": e.replacement,
                            "rule": e.rule,
                            "category": e.category,
                            "context": e.context,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def __len__(self) -> int:
        return len(self.entries)
