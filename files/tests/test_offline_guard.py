"""The offline contract, proven (Phase 01A).

* the autouse guard in ``conftest`` refuses and records outbound socket use, and a test
  that does not acknowledge a recorded attempt fails at teardown;
* runtime subprocess smoke tests share the ``offline_python`` fixture, which installs
  ``sitecustomize`` even with an explicit environment/PYTHONPATH and rejects attempt logs;
* normal editing and a healthy launch (``main.py --check``) make zero network attempts;
* importing the application loads none of the retired provider SDKs.

A socket monkeypatch is Python-level evidence, not an OS firewall. The release gate also
requires a real healthy launch and edit with network access disabled at the OS level.
"""

from __future__ import annotations

import os
import socket
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"

# A harmless attempted connection: the discard port on loopback, nothing is listening.
_PROBE = ("127.0.0.1", 9)

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


def test_the_guard_reaches_a_child_interpreter(tmp_path, offline_python):
    code = (
        "import socket\n"
        "try:\n"
        f"    socket.create_connection({_PROBE!r}, timeout=1)\n"
        "except OSError as exc:\n"
        "    print('refused:', exc)\n"
    )
    with pytest.raises(AssertionError, match="child attempted network access"):
        offline_python.run(
            ["-c", code], cwd=tmp_path,
            capture_output=True, text=True, timeout=30, check=False,
        )
    assert offline_python.attempt_log.read_text(encoding="utf-8").strip() == "socket.create_connection"
    offline_python.attempt_log.write_text("", encoding="utf-8")  # deliberate guard probe acknowledged


# -- the application makes no network attempt ---------------------------------------------


def test_a_healthy_launch_check_makes_no_network_attempt(tmp_path, offline_python):
    completed = offline_python.run(
        [str(SCRIPTS / "main.py"), "--check"],
        cwd=tmp_path, capture_output=True, text=True, timeout=60, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Startup check passed." in completed.stdout


def test_the_application_imports_load_no_retired_sdk(tmp_path, offline_python):
    """Importing every shipped package must not pull in a provider SDK or HTTP client."""
    code = textwrap.dedent(
        """
        import sys
        import core.batch_runner, core.novel_registry, core.run_manifest
        import pipelines.universal
        import pdf.builder, pdf.extractor
        import gui.app
        banned = ("ollama", "groq", "google.genai", "google.generativeai", "httpx",
                  "requests", "urllib3", "pydantic", "openai", "anthropic")
        loaded = sorted(m for m in banned if m in sys.modules)
        print("LOADED:" + ",".join(loaded))
        """
    )
    env = dict(os.environ, PYTHONPATH=str(SCRIPTS))
    completed = offline_python.run(
        ["-c", code], env=env, cwd=tmp_path,
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


def test_application_imports_rejects_a_swallowed_connection(tmp_path, offline_python):
    probe = '\ntry:\n    socket.create_connection(("127.0.0.1", 9), timeout=1)\nexcept OSError:\n    pass\n'
    bootstrap = offline_python.guard_dir / "sitecustomize.py"
    bootstrap.write_text(bootstrap.read_text(encoding="utf-8") + probe, encoding="utf-8")
    with pytest.raises(AssertionError, match="child attempted network access"):
        test_the_application_imports_load_no_retired_sdk(tmp_path, offline_python)
    assert offline_python.attempt_log.read_text(encoding="utf-8").strip() == "socket.create_connection"
    offline_python.attempt_log.write_text("", encoding="utf-8")  # deliberate guard probe acknowledged


@pytest.mark.parametrize("operation", ["connect", "connect_ex", "create_connection", "sendto"])
def test_explicit_child_environment_cannot_hide_a_swallowed_attempt(tmp_path, offline_python, operation):
    (tmp_path / "custom_module.py").write_text("VALUE = 17\n", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    original = dict(env)
    code = textwrap.dedent(
        f"""
        import socket, pathlib, custom_module
        assert custom_module.VALUE == 17
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM if {operation!r} == 'sendto' else socket.SOCK_STREAM)
        try:
            if {operation!r} == 'create_connection':
                socket.create_connection(('127.0.0.1', 9), timeout=1)
            elif {operation!r} == 'sendto':
                sock.sendto(b'x', ('127.0.0.1', 9))
            else:
                getattr(sock, {operation!r})(('127.0.0.1', 9))
        except OSError:
            pass
        finally:
            sock.close()
        pathlib.Path('finished').write_text('caught and finished', encoding='utf-8')
        """
    )
    with pytest.raises(AssertionError, match="child attempted network access"):
        offline_python.run(["-c", code], env=env, cwd=tmp_path, capture_output=True, timeout=30)
    assert (tmp_path / "finished").read_text(encoding="utf-8") == "caught and finished"
    assert env == original  # the supplied environment was copied, never edited
    assert offline_python.attempt_log.read_text(encoding="utf-8").strip() == f"socket.{operation}"
    offline_python.attempt_log.write_text("", encoding="utf-8")  # deliberate guard probe acknowledged


def test_the_guard_reaches_descendant_interpreters(tmp_path, offline_python):
    code = textwrap.dedent(
        r"""
        import subprocess, sys
        probe = 'import socket\ntry:\n socket.create_connection(("127.0.0.1", 9), timeout=1)\nexcept OSError:\n pass\n'
        subprocess.run([sys.executable, '-c', probe], check=True)
        """
    )
    with pytest.raises(AssertionError, match="child attempted network access"):
        offline_python.run(["-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert offline_python.attempt_log.read_text(encoding="utf-8").strip() == "socket.create_connection"
    offline_python.attempt_log.write_text("", encoding="utf-8")  # deliberate guard probe acknowledged


def test_a_child_cannot_silently_disable_sitecustomize(offline_python):
    with pytest.raises(AssertionError, match="guard did not initialize"):
        offline_python.run(["-S", "-c", "pass"], capture_output=True, timeout=30)
