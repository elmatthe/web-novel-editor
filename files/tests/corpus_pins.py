"""Hash-pinned fixtures for the optional ``local_corpus`` test layer.

The corpus-backed tests were written against corpora named ``The_Noble_Queen-v2``,
``Supreme_Magus-v2`` and ``webscraped_shadow_slave``. Those directories are gone from
the development machine; the current local corpora are *re-scrapes* named
``the-noble-queen-1``, ``supreme-magus-1`` and ``shadow-slave-1``. Phase 00 checked
the old SHA-256 baseline against them: **not one PDF is byte-identical**, so the old
recorded file lists cannot be reused and a bare directory alias would silently change
what the tests cover.

This module is the replacement contract:

* a logical corpus name resolves to the legacy directory first (so a machine that
  still has the ``-v2`` corpora keeps its original coverage), then to the current one;
* for a current directory, ``corpus_pins.json`` lists the exact files each test uses,
  with the SHA-256 of every one. The pins were derived with the same detectors the
  tests assert on (``junk_strip``), over the corpus as it was on 2026-10-28;
* before a pinned file is used its hash is verified. A re-scrape therefore **fails
  loudly** ("regenerate the pins") instead of quietly testing different chapters.

Nothing here reads or writes a corpus; it only opens pinned files for reading.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = REPO_ROOT / "files" / "pdf-example-chapters"
_PINS_FILE = Path(__file__).with_name("corpus_pins.json")

#: logical corpus -> candidate directory names, legacy first.
CANDIDATES: dict[str, tuple[str, ...]] = {
    "The_Noble_Queen-v2": ("The_Noble_Queen-v2", "the-noble-queen-1"),
    "Supreme_Magus-v2": ("Supreme_Magus-v2", "supreme-magus-1"),
    "webscraped_shadow_slave": ("webscraped_shadow_slave", "shadow-slave-1"),
}

_cache: dict | None = None


def _pins() -> dict:
    global _cache
    if _cache is None:
        _cache = json.loads(_PINS_FILE.read_text(encoding="utf-8"))["corpora"]
    return _cache


def _has_pdfs(path: Path) -> bool:
    return path.is_dir() and any(f.lower().endswith(".pdf") for f in os.listdir(path))


def resolve(logical: str) -> Path | None:
    """The local directory for a logical corpus, or None when no candidate exists."""
    for name in CANDIDATES.get(logical, (logical,)):
        path = CORPUS_ROOT / name
        if _has_pdfs(path):
            return path
    return None


def is_pinned(path: Path | str) -> bool:
    """True when ``path`` is a current (re-scrape) directory that has pinned fixtures."""
    return Path(path).name in _pins()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pinned_entries(path: Path | str, *roles: str) -> dict[str, dict]:
    """Pinned files carrying any of ``roles``, each verified against its recorded hash.

    Fails the test (never skips) if a pinned file is missing or its bytes changed: the
    corpus was re-scraped and the pins must be regenerated deliberately.
    """
    path = Path(path)
    entries = _pins()[path.name]["files"]
    chosen = {n: e for n, e in entries.items() if set(roles) & set(e["roles"])}
    for name, entry in chosen.items():
        target = path / name
        if not target.is_file():
            pytest.fail(
                f"pinned fixture missing from {path.name}: {name} - the corpus changed; "
                "regenerate files/tests/corpus_pins.json",
                pytrace=False,
            )
        if _sha256(target) != entry["sha256"]:
            pytest.fail(
                f"pinned fixture bytes changed in {path.name}: {name} - the corpus was "
                "re-scraped; regenerate files/tests/corpus_pins.json",
                pytrace=False,
            )
    return chosen
