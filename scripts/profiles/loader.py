"""Load a profile's approved literal corrections from its TOML file.

The data lives in ``profiles/corrections/<slug>.toml`` under a single ``[corrections]``
table (``"wrong" = "right"``). Keeping it as plain data means onboarding a correction is a
data edit, not a code edit, and there is exactly one authoritative definition per rule.

The loader validates what it reads, because a bad map would silently corrupt prose:

* the file must hold only the ``[corrections]`` table, with non-empty string keys and values;
* a key may not map to itself;
* **no key may occur inside any value** - that would let one correction feed another
  (a cascade) or loop. ``Ligo`` -> ``Liguo`` is fine (``Liguo`` does not contain ``Ligo``);
* keys that are the same after NFC normalization conflict (Phase 03);
* a correction may not merely delete words (shortening): ``Clan Valor`` -> ``Valor`` is
  refused, while joining split words (``F riya`` -> ``Friya``) is still allowed (Phase 03);
* :func:`validate_against_protection` refuses keys that overlap a protected term; the batch
  runner calls it before any file is processed.

Corrections are applied in ``pipelines/universal.py`` longest key first, on token boundaries
(a key never matches inside a longer word), while protected terms are masked.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by the supported Python 3.10 runtime
    import tomli as tomllib

CORRECTIONS_DIR = Path(__file__).resolve().parent / "corrections"
_WORD_RE = re.compile(r"\w+")


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
    seen: dict[str, str] = {}
    for key, value in table.items():
        normalized = unicodedata.normalize("NFC", key)
        if normalized in seen:
            raise CorrectionsError(f"{source}: {key!r} and {seen[normalized]!r} are the same key (conflict)")
        seen[normalized] = key
        if _deletes_words(key, value):
            raise CorrectionsError(
                f"{source}: {key!r} -> {value!r} only deletes words (shortening is never a correction; "
                "e.g. 'Clan Valor' must never become 'Valor')")
    return dict(table)


def _deletes_words(key: str, value: str) -> bool:
    """True when the value's words are a strict, in-order subset of the key's words."""
    key_words, value_words = _WORD_RE.findall(key), _WORD_RE.findall(value)
    if not value_words or len(value_words) >= len(key_words):
        return False
    remaining = iter(key_words)
    return all(word in remaining for word in value_words)


def validate_against_protection(corrections, protected_terms, *, source: str = "corrections") -> None:
    """Refuse a correction that a protected term would mask or contradict.

    A key equal to (or sharing a whole-token span with) a protected term could never be applied
    consistently — the term is masked before corrections run — or it would rewrite a protected
    spelling. Both are data errors, reported before any file is processed.
    """
    for key in corrections:
        for term in protected_terms:
            if key.casefold() == term.casefold() or _token_contains(term, key) or _token_contains(key, term):
                raise CorrectionsError(f"{source}: correction {key!r} overlaps protected term {term!r}")


def _token_contains(outer: str, inner: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(inner) + r"(?!\w)", outer) is not None


def load_corrections(slug: str) -> dict[str, str]:
    """The ordered ``{wrong: right}`` map for a profile, from ``corrections/<slug>.toml``."""
    path = CORRECTIONS_DIR / f"{slug}.toml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CorrectionsError(f"cannot read corrections for {slug!r}: {exc}") from exc
    return parse_corrections(text, source=path.name)
