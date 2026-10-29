"""Shared offline runner for runtime Python smoke tests (never provisioning).

The guard is prepended to each child's supplied PYTHONPATH without changing the parent
environment. Descendant interpreters inherit it. A successful exit cannot hide an
attempt: both the runner and its fixture teardown inspect the append-only attempt log.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


_SITECUSTOMIZE = textwrap.dedent(
    """
    import os, socket

    def _deny(kind):
        def blocked(*args, **kwargs):
            with open(os.environ["WNE_GUARD_LOG"], "a", encoding="utf-8") as fh:
                fh.write(kind + "\\n")
            raise OSError("network disabled by the test suite (" + kind + ")")
        return blocked

    socket.socket.connect = _deny("socket.connect")
    socket.socket.connect_ex = _deny("socket.connect_ex")
    socket.create_connection = _deny("socket.create_connection")
    socket.socket.sendto = _deny("socket.sendto")
    with open(os.environ["WNE_GUARD_READY"], "a", encoding="utf-8") as fh:
        fh.write("ready\\n")
    """
)


class OfflinePython:
    def __init__(self, directory: Path):
        self.guard_dir = directory / "guard"
        self.guard_dir.mkdir()
        (self.guard_dir / "sitecustomize.py").write_text(_SITECUSTOMIZE, encoding="utf-8")
        self.attempt_log = directory / "attempts.log"
        self._runs = 0

    def assert_no_attempts(self):
        attempts = self.attempt_log.read_text(encoding="utf-8") if self.attempt_log.exists() else ""
        assert not attempts, "child attempted network access (even if swallowed): " + attempts

    def run(self, args, *, env=None, **kwargs):
        child_env = dict(os.environ if env is None else env)
        child_env["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(self.guard_dir), child_env.get("PYTHONPATH", "")) if p
        )
        child_env["PYTHONDONTWRITEBYTECODE"] = "1"
        child_env["WNE_GUARD_LOG"] = str(self.attempt_log)
        self._runs += 1
        ready = self.guard_dir.parent / f"ready-{self._runs}.log"
        child_env["WNE_GUARD_READY"] = str(ready)
        try:
            completed = subprocess.run([sys.executable, *args], env=child_env, **kwargs)
        finally:
            self.assert_no_attempts()
        assert ready.is_file(), "child offline guard did not initialize"
        return completed
