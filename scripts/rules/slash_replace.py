"""Conservative slash replacement for TTS.

Only numeric ratios are converted: ``6/7`` -> ``6 out of 7``. Every other slash
(word/word, ``and/or``, ``his/her``, anything non-numeric) is preserved exactly as
written, because its intended meaning cannot be inferred safely.
"""

from __future__ import annotations

import re

_X_OF_Y_RE = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")


def replace_slashes(text: str) -> str:
    """Convert numeric ratios to ``out of``; leave all other slashes untouched."""
    return _X_OF_Y_RE.sub(lambda m: f"{m.group(1)} out of {m.group(2)}", text)
