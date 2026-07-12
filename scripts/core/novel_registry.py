"""Novel -> pipeline dispatch registry (single source of truth).

This module maps a selected novel name to everything needed to edit it:

  * its editorial **pipeline** (`run_pipeline`),
  * its built-in **canonical-name floor** (the protected-term set), and
  * its **novel-index filename** under `files/novel-index/`.

It also derives the **roster** of novels shown in the GUI dropdown straight from the index
files in `files/novel-index/` (one entry per `*.txt`), so adding a novel is a data
exercise (drop an index file + an optional profile) — never a GUI/code edit.

Default-to-universal path
-------------------------
Dispatch is case/separator-insensitive (it reuses `edit_details._norm_key`). A novel that
is **not** in the registry falls back cleanly to **universal-only** editing:

  * the novel-agnostic universal pipeline (`pipelines.lord_of_mysteries.run_pipeline`,
    which runs the shared universal rules in order with **no** forced novel-specific
    substitutions), driven by
  * an **empty** canonical floor plus whatever the user has added to
    `files/novel-index/<novel>.txt`.

So a profile-less novel (e.g. Lord of the Mysteries) gets universal grammar, unicode
stripping, the mandatory em-dash sweep, etc., never crashes, and never picks up another
novel's special-fixes. Promoting such a novel to a real profile later is one line here
plus a profile package — no core refactor (Phase 5b did exactly this for The Noble
Queen and Supreme Magus).

Note on the universal pipeline seam: the universal-only fallback intentionally reuses the
Phase-7 `lord_of_mysteries` stub pipeline, which is universal-rules-only precisely because
its profile (`LOTM_SPECIAL_FIXES`) is empty. `test_novel_registry` pins that emptiness, so
if a real Lord of the Mysteries profile is ever authored the coupling is caught and the
universal fallback can be given its own dedicated seam at that point.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from core.edit_details import _norm_key
from pipelines import lord_of_mysteries, shadow_slave, supreme_magus, the_noble_queen
from profiles.shadow_slave.canonical_names import SS_CANONICAL_NAMES
from profiles.supreme_magus.canonical_names import SM_CANONICAL_NAMES
from profiles.the_noble_queen.canonical_names import NQ_CANONICAL_NAMES

# files/novel-index/ lives two levels up from scripts/core/.
NOVEL_INDEX_DIR = Path(__file__).resolve().parents[2] / "files" / "novel-index"

# The novel selected by default in the GUI dropdown.
DEFAULT_NOVEL = "Shadow Slave"

# Small words kept lowercase when Title-Casing a display name (unless they are the first
# word). This makes "lord-of-the-mysteries.txt" -> "Lord of the Mysteries", matching the
# spec's example, while "shadow-slave.txt" -> "Shadow Slave" is unaffected. Casing is
# cosmetic only; dispatch normalizes it away via `_norm_key`.
_SMALL_WORDS = frozenset(
    {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in",
     "nor", "of", "on", "or", "the", "to", "with"}
)

_SEP_RE = re.compile(r"[\s_\-]+")


@dataclass(frozen=True)
class NovelDispatch:
    """Everything `run_batch` needs to edit one novel.

    Attributes:
        display_name: human-readable novel name (for the dropdown / logs).
        run_pipeline: the pipeline callable
            ``run_pipeline(text, lexicon, *, repl_log, gui_log, dry_run) -> str``.
        canonical_names: the built-in protected-term floor for this novel
            (empty frozenset for the universal-only fallback).
        index_filename: the `files/novel-index/<file>.txt` basename whose user terms are
            loaded on top of the floor ("" when there is no associated index).
        has_profile: True for a real per-novel editorial profile; False when this is the
            universal-only fallback.
    """

    display_name: str
    run_pipeline: Callable[..., str]
    canonical_names: frozenset[str]
    index_filename: str
    has_profile: bool


# --- roster derivation (filename <-> display name) -------------------------------------

def display_name_from_index_filename(filename: str) -> str:
    """Derive a dropdown display name from an index filename.

    Reverse of the novel-name -> filename convention: split the stem on hyphens/
    underscores/spaces and Title-Case, keeping common small words lowercase unless first.
    ``"shadow-slave.txt"`` -> ``"Shadow Slave"``; ``"lord-of-the-mysteries.txt"`` ->
    ``"Lord of the Mysteries"``.
    """
    stem = Path(filename).stem
    words = [w for w in _SEP_RE.split(stem) if w]
    out: list[str] = []
    for i, word in enumerate(words):
        lower = word.lower()
        if i != 0 and lower in _SMALL_WORDS:
            out.append(lower)
        else:
            out.append(lower[:1].upper() + lower[1:])
    return " ".join(out)


def index_filename_for(novel_name: Optional[str]) -> str:
    """Map a novel name to its conventional `<novel>.txt` index filename, or "".

    ``"Lord of the Mysteries"`` -> ``"lord-of-the-mysteries.txt"``. Empty/None -> "".
    """
    key = _norm_key(novel_name) if novel_name else ""
    if not key:
        return ""
    return key.replace(" ", "-") + ".txt"


def available_novels(index_dir: Path | str = NOVEL_INDEX_DIR) -> list[str]:
    """Return the dropdown roster: one display name per `*.txt` in the index folder.

    Placeholder (empty/comment-only) index files are intentionally **included** so the
    full novel roster is visible in the GUI. The default novel is listed first; the rest
    follow alphabetically. Falls back to ``[DEFAULT_NOVEL]`` if the folder is missing or
    has no index files (the dropdown is never empty).
    """
    folder = Path(index_dir)
    if not folder.is_dir():
        return [DEFAULT_NOVEL]

    names = [display_name_from_index_filename(p.name) for p in sorted(folder.glob("*.txt"))]
    if not names:
        return [DEFAULT_NOVEL]

    default_key = _norm_key(DEFAULT_NOVEL)
    ordered = [n for n in names if _norm_key(n) == default_key]
    ordered += sorted(n for n in names if _norm_key(n) != default_key)
    return ordered


# --- registry + dispatch ---------------------------------------------------------------

# The one place a real per-novel editorial profile is registered. Keyed by normalized
# novel name. To onboard a real profile: add its pipeline + profile package, then one
# entry here. Everything not listed dispatches to the universal-only fallback below.
_REGISTRY: dict[str, NovelDispatch] = {
    _norm_key("Shadow Slave"): NovelDispatch(
        display_name="Shadow Slave",
        run_pipeline=shadow_slave.run_pipeline,
        canonical_names=SS_CANONICAL_NAMES,
        index_filename="shadow-slave.txt",
        has_profile=True,
    ),
    _norm_key("The Noble Queen"): NovelDispatch(
        display_name="The Noble Queen",
        run_pipeline=the_noble_queen.run_pipeline,
        canonical_names=NQ_CANONICAL_NAMES,
        index_filename="the-noble-queen.txt",
        has_profile=True,
    ),
    _norm_key("Supreme Magus"): NovelDispatch(
        display_name="Supreme Magus",
        run_pipeline=supreme_magus.run_pipeline,
        canonical_names=SM_CANONICAL_NAMES,
        index_filename="supreme-magus.txt",
        has_profile=True,
    ),
}


def resolve_dispatch(novel_name: Optional[str]) -> NovelDispatch:
    """Resolve a selected novel name to its `NovelDispatch`.

    A registered novel returns its real profile dispatch. Anything else (unknown novel,
    a placeholder-only novel, empty, or None) returns the **universal-only** fallback:
    the universal pipeline, an empty canonical floor, and — when a name was given — that
    novel's own `<novel>.txt` index so any user-added protected terms are still honored.
    Never raises.
    """
    key = _norm_key(novel_name) if novel_name else ""
    if key and key in _REGISTRY:
        return _REGISTRY[key]

    display = novel_name.strip() if novel_name and novel_name.strip() else "Universal"
    return NovelDispatch(
        display_name=display,
        run_pipeline=lord_of_mysteries.run_pipeline,  # universal rules only (empty profile)
        canonical_names=frozenset(),
        index_filename=index_filename_for(novel_name),
        has_profile=False,
    )
