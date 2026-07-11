"""Pytest bootstrap: put `scripts/` on sys.path so tests import packages
(`rules`, `core`, `pipelines`, ...) the same way `main.py` does at runtime.

Also registers the optional local-corpus test layer (Phase 2):
  * the `local_corpus` marker for tests that need the gitignored PDF corpora
    under files/pdf-example-chapters/ (they skip with an explicit reason when
    a corpus is absent — never a silent pass), and
  * the `--require-local-corpora` strict-mode flag, which turns those skips
    into loud failures so a real local QA run can't report green just because
    a corpus wasn't there.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


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
