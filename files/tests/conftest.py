"""Pytest bootstrap for the webnovel-editor suite.

The tests live in ``files/tests/`` (dev-only, not shipped) while the packages
they exercise ship from ``scripts/Universal/`` (``core``, ``rules``,
``pipelines``, ``gui``, ...). Insert that ``Universal`` directory onto
``sys.path`` so ``import core`` / ``import rules`` / ... resolve the same way
``scripts/Universal/main.py`` does at runtime, no matter where pytest is invoked
from.

Layout (relative to this file):
    <repo>/files/tests/conftest.py   <- this file  (parents[2] == <repo>)
    <repo>/scripts/Universal/        <- package root added below

Also registers the optional local-corpus test layer (Phase 2):
  * the ``local_corpus`` marker for tests that need the gitignored PDF corpora
    under files/pdf-example-chapters/ (they skip with an explicit reason when
    a corpus is absent — never a silent pass), and
  * the ``--require-local-corpora`` strict-mode flag, which turns those skips
    into loud failures so a real local QA run can't report green just because
    a corpus wasn't there.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_UNIVERSAL = _REPO_ROOT / "scripts" / "Universal"

if str(_UNIVERSAL) not in sys.path:
    sys.path.insert(0, str(_UNIVERSAL))


def pytest_addoption(parser):
    parser.addoption(
        "--require-local-corpora",
        action="store_true",
        default=False,
        help=(
            "Fail (instead of skip) corpus-backed tests when a required local "
            "corpus is missing from files/pdf-example-chapters/."
        ),
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "local_corpus: needs the gitignored local PDF corpora under "
        "files/pdf-example-chapters/ (skipped with a reason when absent; "
        "made mandatory by --require-local-corpora)",
    )
