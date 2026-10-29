"""The offline contract, proven (Phase 01A).

* the autouse guard in ``conftest`` refuses and records outbound socket use, and a test
  that does not acknowledge a recorded attempt fails at teardown;
* the guard's blind spot is covered: a *new Python interpreter* does not inherit an
  in-process monkeypatch, so the subprocess smoke tests below install the guard through
  a throwaway ``sitecustomize`` and an inherited ``PYTHONPATH``;
* normal editing and a healthy launch (``main.py --check``) make zero network attempts;
* importing the application loads none of the retired provider SDKs.

A socket monkeypatch is Python-level evidence, not an OS firewall. The release gate also
requires a real healthy launch and edit with network access disabled at the OS level.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIVERSAL = REPO_ROOT / "scripts" / "Universal"

# A harmless attempted connection: the discard port on loopback, nothing is listening.
_PROBE = ("127.0.0.1", 9)

_SITECUSTOMIZE = textwrap.dedent(
    """
    import os, socket

    _LOG = os.environ["WNE_GUARD_LOG"]

    def _deny(kind):
        def blocked(*args, **kwargs):
            with open(_LOG, "a", encoding="utf-8") as fh:
                fh.write(kind + "\\n")
            raise OSError("network disabled by the test suite (" + kind + ")")
        return blocked

    socket.socket.connect = _deny("socket.connect")
    socket.socket.connect_ex = _deny("socket.connect_ex")
    socket.create_connection = _deny("socket.create_connection")
    socket.socket.sendto = _deny("socket.sendto")
    """
)


def _guarded_env(tmp_path: Path) -> tuple[dict, Path]:
    guard_dir = tmp_path / "guard"
    guard_dir.mkdir(exist_ok=True)
    (guard_dir / "sitecustomize.py").write_text(_SITECUSTOMIZE, encoding="utf-8")
    log = tmp_path / "attempts.log"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(guard_dir), str(UNIVERSAL)])
    env["WNE_GUARD_LOG"] = str(log)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env, log


# -- the in-process guard -----------------------------------------------------------------


def test_connect_is_refused_and_recorded(network_attempts):
    with pytest.raises(OSError, match="network disabled"):
        socket.create_connection(_PROBE, timeout=1)
    assert any("create_connection" in a for a in network_attempts)
    network_attempts.clear()  # acknowledged: this test exists to provoke exactly this


def test_every_outbound_path_is_covered(network_attempts):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(OSError):
            sock.connect(_PROBE)
        with pytest.raises(OSError):
            sock.connect_ex(_PROBE)
        with pytest.raises(OSError):
            udp.sendto(b"x", _PROBE)
    finally:
        sock.close()
        udp.close()
    kinds = " ".join(network_attempts)
    for kind in ("socket.connect(", "socket.connect_ex", "socket.sendto"):
        assert kind in kinds, kinds
    network_attempts.clear()


def test_a_swallowed_connection_error_is_still_visible(network_attempts):
    """Code that catches the OSError must not be able to hide the attempt."""
    try:
        socket.create_connection(_PROBE, timeout=1)
    except OSError:
        pass  # the code under test "handled" it
    assert network_attempts, "the attempt was lost when the error was swallowed"
    network_attempts.clear()


# -- the guard reaches a new interpreter --------------------------------------------------


def test_the_guard_reaches_a_child_interpreter(tmp_path):
    env, log = _guarded_env(tmp_path)
    code = (
        "import socket\n"
        "try:\n"
        f"    socket.create_connection({_PROBE!r}, timeout=1)\n"
        "except OSError as exc:\n"
        "    print('refused:', exc)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], env=env, cwd=tmp_path,
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert "refused: network disabled" in completed.stdout, completed.stdout + completed.stderr
    assert log.read_text(encoding="utf-8").strip() == "socket.create_connection"


# -- the application makes no network attempt ---------------------------------------------


def test_a_healthy_launch_check_makes_no_network_attempt(tmp_path):
    env, log = _guarded_env(tmp_path)
    completed = subprocess.run(
        [sys.executable, str(UNIVERSAL / "main.py"), "--check"],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=60, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Startup check passed." in completed.stdout
    assert not log.exists() or log.read_text(encoding="utf-8") == ""


def test_the_application_imports_load_no_retired_sdk(tmp_path):
    """Importing every shipped package must not pull in a provider SDK or HTTP client."""
    env, log = _guarded_env(tmp_path)
    code = textwrap.dedent(
        """
        import sys
        import core.batch_runner, core.novel_registry, core.run_manifest
        import pipelines.shadow_slave, pipelines.lord_of_mysteries
        import pdf.builder, pdf.extractor
        import gui.app
        banned = ("ollama", "groq", "google.genai", "google.generativeai", "httpx",
                  "requests", "urllib3", "pydantic", "openai", "anthropic")
        loaded = sorted(m for m in banned if m in sys.modules)
        print("LOADED:" + ",".join(loaded))
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], env=env, cwd=tmp_path,
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "LOADED:" in completed.stdout
    assert completed.stdout.strip().endswith("LOADED:"), completed.stdout


def test_a_batch_run_makes_no_network_attempt(tmp_path, network_attempts):
    """A real run_batch over a real PDF: the autouse guard fails teardown on any attempt."""
    pytest.importorskip("pdfplumber")
    pytest.importorskip("reportlab")
    from core.batch_runner import run_batch
    from pdf.builder import build_pdf

    src = tmp_path / "chapter.pdf"
    build_pdf(
        "Chapter 1: Offline.\n\n" + "The quiet road stretched toward the distant gate. " * 6,
        str(src),
    )
    summary = run_batch([str(src)], str(tmp_path / "out"), novel_name="Shadow Slave")
    assert summary["succeeded"] == 1
    assert network_attempts == []
