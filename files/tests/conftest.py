"""Pytest bootstrap for the webnovel-editor suite.

The tests live in ``files/tests/`` (dev-only, not shipped) while the packages
they exercise ship from ``scripts/`` (``core``, ``rules``,
``pipelines``, ``gui``, ...). Insert that ``scripts`` directory onto
``sys.path`` so ``import core`` / ``import rules`` / ... resolve the same way
``scripts/main.py`` does at runtime, no matter where pytest is invoked
from.

Layout (relative to this file):
    <repo>/files/tests/conftest.py   <- this file  (parents[2] == <repo>)
    <repo>/scripts/                  <- package root added below

Also registers the optional local-corpus test layer (Phase 2):
  * the ``local_corpus`` marker for tests that need the gitignored PDF corpora
    under files/pdf-example-chapters/ (they skip with an explicit reason when
    a corpus is absent — never a silent pass), and
  * the ``--require-local-corpora`` strict-mode flag, which turns those skips
    into loud failures so a real local QA run can't report green just because
    a corpus wasn't there.
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


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
        "allow_tk_failure: this test deliberately provokes a Tk initialization error "
        "(the strict-Tk fixture steps aside for it)",
    )
    config.addinivalue_line(
        "markers",
        "local_corpus: needs the gitignored local PDF corpora under "
        "files/pdf-example-chapters/ (skipped with a reason when absent; "
        "made mandatory by --require-local-corpora)",
    )


# ---------------------------------------------------------------------------
# Offline contract (Phase 01A)
# ---------------------------------------------------------------------------
# Normal editing and a healthy launch need no network. Every test therefore runs with
# outbound socket use refused and recorded, and a recorded attempt FAILS THE TEST AT
# TEARDOWN even if the code under test caught the exception - swallowing the error must
# not hide the attempt. This is Python-level evidence, not an OS firewall; the
# `test_offline_guard` module also proves the guard reaches child interpreters.
#
# Provisioning/download tests have a separate scope and mocked installers; runtime tests
# may not opt out just to pass.
@pytest.fixture
def network_attempts(request):
    """The list of refused outbound attempts for this test (clear it to acknowledge)."""
    return request.node._wne_network_attempts


@pytest.fixture(autouse=True)
def _deny_network(request, monkeypatch):
    attempts: list[str] = []
    request.node._wne_network_attempts = attempts

    def refuse(kind):
        def blocked(*args, **kwargs):
            target = [a for a in args if not isinstance(a, socket.socket)]
            attempts.append(f"{kind}{tuple(target)!r}")
            raise OSError(f"network disabled by the test suite ({kind})")

        return blocked

    monkeypatch.setattr(socket.socket, "connect", refuse("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", refuse("socket.connect_ex"))
    monkeypatch.setattr(socket, "create_connection", refuse("socket.create_connection"))
    monkeypatch.setattr(socket.socket, "sendto", refuse("socket.sendto"))
    yield
    if attempts:
        pytest.fail(
            "the code under test attempted network access (even if it handled the "
            "error): " + "; ".join(attempts),
            pytrace=False,
        )


# ---------------------------------------------------------------------------
# Strict Tk on Windows (Phase 01A)
# ---------------------------------------------------------------------------
# Every GUI test used to turn ANY TclError at window construction into
# `pytest.skip("no display available for Tk")`. On a Windows desktop a display always
# exists, so that message hid a real fault: on HOME-PC the Tcl/Tk library files
# (init.tcl, ttk/spinbox.tcl) intermittently failed to read and 1-2 Tk tests silently
# skipped while the verifier still exited 0. A Tk initialization error on Windows is
# now a test ERROR carrying the real Tcl message. Set WNE_ALLOW_TK_SKIP=1 to restore the
# old behaviour (e.g. a headless Windows CI runner); POSIX hosts are unaffected.
@pytest.fixture(autouse=True)
def _tk_init_errors_are_failures(request, monkeypatch):
    if (
        sys.platform != "win32"
        or os.environ.get("WNE_ALLOW_TK_SKIP") == "1"
        or request.node.get_closest_marker("allow_tk_failure")
    ):
        yield
        return
    try:
        import tkinter
    except Exception:  # no tkinter at all: the tests skip via importorskip, as before
        yield
        return

    errors: list[str] = []
    original = tkinter.Tk.__init__

    def recording_init(self, *args, **kwargs):
        try:
            return original(self, *args, **kwargs)
        except tkinter.TclError as exc:
            errors.append(str(exc).strip())
            raise

    monkeypatch.setattr(tkinter.Tk, "__init__", recording_init)
    yield
    if errors:
        pytest.fail(
            "Tk failed to initialise on Windows - this is an environment fault or a "
            "regression, not 'no display'. Real Tcl error: " + errors[0][:400],
            pytrace=False,
        )
