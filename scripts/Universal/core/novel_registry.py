"""Novel -> pipeline dispatch registry (single source of truth).

This module maps a selected novel name to everything needed to edit it:

  * its editorial **pipeline** (`run_pipeline`),
  * its built-in **canonical-name floor** (the protected-term set), and
  * its **novel-index filename** under `scripts/Universal/resources/novel-index/`.

It also derives the **roster** of novels shown in the GUI dropdown straight from the index
files in `scripts/Universal/resources/novel-index/` (one entry per `*.txt`), so adding a novel is a data
exercise (drop an index file + an optional profile) — never a GUI/code edit. Since
v0.11.0 the roster leads with an injected **"Universal"** entry (the default selection —
universal-only editing as an explicit, named choice), and profile-less novels carry a
display marker saying what protection they do have ("names protected" when their index
holds terms, "universal rules only" when it does not). Markers are display-only: the GUI
strips them via `clean_novel_name` before any name reaches dispatch or output-folder
naming.

Default-to-universal path
-------------------------
Dispatch is case/separator-insensitive (it reuses `edit_details._norm_key`). A novel that
is **not** in the registry falls back cleanly to **universal-only** editing:

  * the novel-agnostic universal pipeline (`pipelines.lord_of_mysteries.run_pipeline`,
    which runs the shared universal rules in order with **no** forced novel-specific
    substitutions), driven by
  * an **empty** canonical floor plus whatever the user has added to
    `scripts/Universal/resources/novel-index/<novel>.txt`.

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
from core.protected_lexicon import load_protected_lexicon
from pipelines import (
    lord_of_mysteries,
    renegade_immortal,
    shadow_slave,
    supreme_magus,
    the_noble_queen,
)
from profiles.renegade_immortal.canonical_names import RI_CANONICAL_NAMES
from profiles.shadow_slave.canonical_names import SS_CANONICAL_NAMES
from profiles.supreme_magus.canonical_names import SM_CANONICAL_NAMES
from profiles.the_noble_queen.canonical_names import NQ_CANONICAL_NAMES

# Shipped runtime data: scripts/Universal/resources/novel-index/ (one dir up from
# scripts/Universal/core/). Lives under the shipped scripts/ tree, not dev-only files/.
NOVEL_INDEX_DIR = Path(__file__).resolve().parents[1] / "resources" / "novel-index"

# The entry selected by default in the GUI dropdown. "Universal" is not an index-derived
# novel: it is injected first by `available_novels` and dispatches through the existing
# unregistered-name fallback in `resolve_dispatch` (universal-only editing). Shadow Slave
# remains in the roster, just no longer pre-selected (Plan 1 Phase 3, DECISIONS log).
DEFAULT_NOVEL = "Universal"

# Display-only suffixes for roster novels that have no real per-novel profile.
#
# THESE ARE TWO DIFFERENT STATES AND USED TO SHARE ONE LABEL. "No profile" means only
# that the novel has no special-fixes profile — its own hand-written substitution rules.
# It says nothing about whether its names are protected, which comes from its index file
# and is by far the thing a reader cares about. Reverend Insanity has no profile and
# 1,429 protected terms, and reading " — no profile yet" beside it invited exactly the
# wrong conclusion: that the novel was unprotected, when the opposite was true.
#
# So the marker now reports the protection, which is the useful fact:
#   registered profile        -> no marker at all (the fullest treatment)
#   no profile, terms indexed -> NAMES_PROTECTED_MARKER
#   no profile, no terms      -> UNIVERSAL_ONLY_MARKER
#
# `_norm_key` does NOT strip these, so they must never reach `resolve_dispatch` or the
# output-folder kebab-casing — the GUI strips them with `clean_novel_name` first.
NAMES_PROTECTED_MARKER = " — names protected"
UNIVERSAL_ONLY_MARKER = " — universal rules only"

# Kept as the historical name for the profile-less state so existing callers and tests
# keep a single symbol to reach for. It is the marker used when there is nothing to
# protect either.
NO_PROFILE_MARKER = UNIVERSAL_ONLY_MARKER

# Every display-only suffix `clean_novel_name` must be able to remove. Longest first, so
# a marker that is a suffix of another can never leave a fragment behind.
DISPLAY_MARKERS = tuple(
    sorted({NAMES_PROTECTED_MARKER, UNIVERSAL_ONLY_MARKER}, key=len, reverse=True)
)

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
        index_filename: the `scripts/Universal/resources/novel-index/<file>.txt` basename whose user terms are
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


def protected_term_count(
    index_filename: str,
    canonical_names: frozenset[str] = frozenset(),
    index_dir: Path | str = NOVEL_INDEX_DIR,
) -> int:
    """How many protected terms a novel actually has, counted the way the run counts them.

    Deliberately routed through `load_protected_lexicon` rather than counting lines: the
    roster marker and the run's own "Loaded N protected term(s)" line must never be able
    to disagree, and the loader owns comment stripping, blank lines and de-duplication.
    Never raises — a missing or unreadable file is simply zero terms.
    """
    if not index_filename:
        return len(load_protected_lexicon("", canonical_names).terms)
    path = Path(index_dir) / index_filename
    return len(load_protected_lexicon(str(path), canonical_names).terms)


def available_novels(index_dir: Path | str = NOVEL_INDEX_DIR) -> list[str]:
    """Return the dropdown roster: "Universal" first, then one display name per `*.txt`
    in the index folder, alphabetically.

    Placeholder (empty/comment-only) index files are intentionally **included** so the
    full novel roster is visible in the GUI. A novel with a registered profile carries no
    marker. A profile-less novel carries a display-only suffix saying what protection it
    *does* have — ``NAMES_PROTECTED_MARKER`` when its index holds terms,
    ``UNIVERSAL_ONLY_MARKER`` when it does not. Either way it is still selectable and
    dispatches to universal-only editing exactly as before once the GUI strips the marker
    (`clean_novel_name`). If the folder is missing or empty the roster is just
    ``["Universal"]`` (the dropdown is never empty).
    """
    roster = [DEFAULT_NOVEL]
    folder = Path(index_dir)
    if not folder.is_dir():
        return roster

    files = sorted(folder.glob("*.txt"), key=lambda p: display_name_from_index_filename(p.name))
    for path in files:
        name = display_name_from_index_filename(path.name)
        if _norm_key(name) in _REGISTRY:
            roster.append(name)
            continue
        terms = protected_term_count(path.name, frozenset(), folder)
        roster.append(name + (NAMES_PROTECTED_MARKER if terms else UNIVERSAL_ONLY_MARKER))
    return roster


def clean_novel_name(display_name: str) -> str:
    """Map a dropdown display string back to the clean novel name.

    Strips any display-only marker in ``DISPLAY_MARKERS``; anything else (including
    "Universal" and real-profile names) passes through unchanged. The GUI must call this
    before a selection reaches `run_batch`/`resolve_dispatch` or output-folder naming —
    `_norm_key` would not remove a marker.
    """
    for marker in DISPLAY_MARKERS:
        if display_name.endswith(marker):
            return display_name[: -len(marker)]
    return display_name


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
    # Registered 2026-07-26 solely to give this novel its own forced-substitution map
    # (Ligou/Ligo -> Liguo, the author's canonical ruling). Forced substitutions are
    # per-profile data and the universal fallback's map is shared by every profile-less
    # novel, so a registration was the only way to scope the fix to this novel.
    # Its floor is empty and its pipeline mirrors the universal one stage-for-stage, so
    # protection and output are otherwise unchanged from the pre-promotion behaviour.
    _norm_key("Renegade Immortal"): NovelDispatch(
        display_name="Renegade Immortal",
        run_pipeline=renegade_immortal.run_pipeline,
        canonical_names=RI_CANONICAL_NAMES,
        index_filename="renegade-immortal.txt",
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
