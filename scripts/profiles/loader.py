"""Load a profile's approved literal corrections from its TOML file.

The data lives in ``profiles/corrections/<slug>.toml`` under a single ``[corrections]``
table (``"wrong" = "right"``). Keeping it as plain data means onboarding a correction is a
data edit, not a code edit, and there is exactly one authoritative definition per rule.

The loader validates what it reads, because a bad map would silently corrupt prose:

* the file must hold only the ``[corrections]`` table, with non-empty string keys and values;
* a key may not map to itself;
* **no key may occur inside any value** - that would let one correction feed another
  (a cascade) or loop. ``Ligo`` -> ``Liguo`` is fine (``Liguo`` does not contain ``Ligo``).

It does not change how corrections are applied: that stays in ``pipelines/universal.py``
(longest key first, plain substring replacement while protected terms are masked).
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by the supported Python 3.10 runtime
    import tomli as tomllib

CORRECTIONS_DIR = Path(__file__).resolve().parent / "corrections"


class CorrectionsError(ValueError):
    """A corrections file is missing or malformed."""


def parse_corrections(text: str, source: str = "<string>") -> dict[str, str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise CorrectionsError(f"{source}: not valid TOML ({exc})") from exc
    if set(data) != {"corrections"} or not isinstance(data["corrections"], dict):
        raise CorrectionsError(f"{source}: expected exactly one [corrections] table")
    table = data["corrections"]
    for key, value in table.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value:
            raise CorrectionsError(f"{source}: {key!r} must map a non-empty string to a non-empty string")
        if key == value:
            raise CorrectionsError(f"{source}: {key!r} maps to itself")
    for key in table:
        for value in table.values():
            if key in value:
                raise CorrectionsError(
                    f"{source}: key {key!r} occurs inside replacement {value!r} (cascade)"
                )
    return dict(table)


def load_corrections(slug: str) -> dict[str, str]:
    """The ordered ``{wrong: right}`` map for a profile, from ``corrections/<slug>.toml``."""
    path = CORRECTIONS_DIR / f"{slug}.toml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CorrectionsError(f"cannot read corrections for {slug!r}: {exc}") from exc
    return parse_corrections(text, source=path.name)
