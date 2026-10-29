"""Stage 2 — Ligature normalization (ﬁ->fi, ﬂ->fl, ﬀ->ff, ﬃ->ffi, ﬄ->ffl, ﬅ/ﬆ->st).

Phase 4 deliverable. Runs globally before any other text processing. Stub is a no-op.
"""

from __future__ import annotations

_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}


def normalize_ligatures(text: str) -> str:
    """Replace PDF ligature characters with their ASCII equivalents."""
    for src, dst in _LIGATURES.items():
        if src in text:
            text = text.replace(src, dst)
    return text
