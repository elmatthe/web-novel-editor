"""Per-novel edit-details loader (universal base + optional novel-specific layer).

The Webnovel Editor keeps its human-readable editing rules as markdown in
`files/Novel-Edits-Details/`:

  * `UNIVERSAL.md`        — the baseline editor rules, always loaded and applied as the
                            base for every novel.
  * `<Novel-Name>.md`     — edits unique to one novel (e.g. `Shadow-Slave.md`), layered on
                            top of the universal rules when that novel is selected.

`load_edit_details(novel_name)` always loads the universal base, then maps the selected
novel name to its `<Novel-Name>.md` file and layers it on top. The lookup is
case- and separator-insensitive ("Shadow Slave", "shadow-slave", "Shadow_Slave" all
resolve to `Shadow-Slave.md`). If no matching novel file exists, it falls back to
universal-only editing — it never raises for a missing novel file.

The markdown is the documentation/specification layer for the deterministic Python rules
in `scripts/rules/` and `scripts/pipelines/`; this module is what loads and surfaces it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# files/Novel-Edits-Details/ lives three levels up from scripts/Universal/core/.
EDIT_DETAILS_DIR = (
    Path(__file__).resolve().parents[3] / "files" / "Novel-Edits-Details"
)
UNIVERSAL_FILENAME = "UNIVERSAL.md"

_SEP_RE = re.compile(r"[\s_\-]+")


@dataclass(frozen=True)
class EditDetails:
    """The resolved edit-details for one run.

    Attributes:
        novel_name: the novel name requested (None for universal-only).
        universal: the UNIVERSAL.md text (empty string if that file is absent).
        novel: the novel-specific markdown text, or None when none was applied.
        novel_path: the resolved `<Novel-Name>.md` path, or None.
        combined: universal text followed by the novel text (universal alone on fallback).
        used_universal_only: True when no novel-specific file was applied.
    """

    novel_name: Optional[str] = None
    universal: str = ""
    novel: Optional[str] = None
    novel_path: Optional[Path] = None
    combined: str = ""
    used_universal_only: bool = True
    source_files: tuple[Path, ...] = field(default_factory=tuple)


def _norm_key(name: str) -> str:
    """Normalize a novel name/filename stem to a comparison key.

    Lowercases and collapses any run of spaces, underscores, or hyphens to a single
    space, so "Shadow Slave", "shadow-slave", and "Shadow_Slave" all map to the same key.
    """
    return _SEP_RE.sub(" ", name).strip().lower()


def novel_md_filename(novel_name: str) -> str:
    """Return the conventional `<Novel-Name>.md` filename for a novel name.

    Words are split on whitespace/underscores/hyphens, Title-Cased, and joined with
    hyphens: "shadow slave" -> "Shadow-Slave.md". Used for documentation and when
    scaffolding a new novel's file; resolution itself is case/separator-insensitive.
    """
    parts = [p for p in _SEP_RE.split(novel_name.strip()) if p]
    if not parts:
        return ".md"
    return "-".join(word[:1].upper() + word[1:] for word in parts) + ".md"


def resolve_novel_md_path(
    novel_name: Optional[str],
    base_dir: Path | str = EDIT_DETAILS_DIR,
) -> Optional[Path]:
    """Map a selected novel name to its existing `<Novel-Name>.md` path, or None.

    Returns None when `novel_name` is empty, the folder is missing, or no markdown file
    matches (case/separator-insensitive). `UNIVERSAL.md` is never returned here — it is
    the base, not a novel-specific match. Never raises.
    """
    if not novel_name or not novel_name.strip():
        return None

    folder = Path(base_dir)
    if not folder.is_dir():
        return None

    want = _norm_key(novel_name)
    if not want or want == _norm_key(Path(UNIVERSAL_FILENAME).stem):
        return None

    try:
        candidates = sorted(folder.glob("*.md"))
    except OSError:
        return None

    for path in candidates:
        if path.name == UNIVERSAL_FILENAME:
            continue
        if _norm_key(path.stem) == want:
            return path
    return None


def _read_text(path: Path) -> str:
    """Read a markdown file as UTF-8, returning '' on any read error (never raises)."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def load_edit_details(
    novel_name: Optional[str] = None,
    base_dir: Path | str = EDIT_DETAILS_DIR,
) -> EditDetails:
    """Load the universal base and, if a matching novel file exists, layer it on top.

    The universal rules (`UNIVERSAL.md`) are always loaded as the base. When `novel_name`
    resolves to a `<Novel-Name>.md` file, its text is appended after the universal text and
    `used_universal_only` is False. When no novel file matches (missing folder, no match,
    or `novel_name` is None), the result is universal-only and never raises.
    """
    folder = Path(base_dir)
    universal_path = folder / UNIVERSAL_FILENAME
    universal_text = _read_text(universal_path) if universal_path.is_file() else ""

    sources: list[Path] = []
    if universal_path.is_file():
        sources.append(universal_path)

    novel_path = resolve_novel_md_path(novel_name, base_dir)
    if novel_path is not None:
        novel_text = _read_text(novel_path)
        sources.append(novel_path)
        combined = (
            f"{universal_text}\n\n{novel_text}".strip()
            if universal_text
            else novel_text.strip()
        )
        return EditDetails(
            novel_name=novel_name,
            universal=universal_text,
            novel=novel_text,
            novel_path=novel_path,
            combined=combined,
            used_universal_only=False,
            source_files=tuple(sources),
        )

    # Fallback: universal-only editing (no matching novel file).
    return EditDetails(
        novel_name=novel_name,
        universal=universal_text,
        novel=None,
        novel_path=None,
        combined=universal_text.strip(),
        used_universal_only=True,
        source_files=tuple(sources),
    )
