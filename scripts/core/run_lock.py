"""Local single-writer ownership. Guard files persist; kernel locks never do.

Windows uses nonblocking msvcrt byte locking and GetProcessTimes creation identity.
Unknown identity/foreign metadata fail closed; age is deliberately irrelevant.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid

from core.output_plan import contained_path, validate_path
from utils.atomic_io import rename_no_clobber

LOCK_NAME = ".run-lock.json"
GUARD_NAME = ".run-writer.guard"


class LockConflict(RuntimeError):
    pass


class StaleLock(LockConflict):
    pass


def host_identity() -> str:
    return hashlib.sha256(f"{socket.gethostname()}:{uuid.getnode()}".encode()).hexdigest()


def process_identity(pid: int) -> tuple[str, str | None]:
    """Return live + creation identity, proven dead, or unknown (including denied)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        api.GetProcessTimes.restype = wintypes.BOOL
        api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        api.GetExitCodeProcess.restype = wintypes.BOOL
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        handle = api.OpenProcess(0x1000, False, pid)
        if not handle:
            return ("dead", None) if ctypes.get_last_error() == 87 else ("unknown", None)
        try:
            code = wintypes.DWORD()
            if not api.GetExitCodeProcess(handle, ctypes.byref(code)):
                return "unknown", None
            if code.value != 259:
                return "dead", None
            times = [wintypes.FILETIME() for _ in range(4)]
            if not api.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                return "unknown", None
            return "live", str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
        finally:
            api.CloseHandle(handle)
    if sys.platform.startswith("linux"):
        try:
            value = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            return "live", boot + ":" + value[19]
        except FileNotFoundError:
            return "dead", None
        except (OSError, IndexError):
            return "unknown", None
    if sys.platform == "darwin":
        try:
            result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "lstart="],
                                    capture_output=True, text=True, timeout=2,
                                    env=dict(os.environ, LC_ALL="C"))
            creation = result.stdout.strip()
            if result.returncode == 0 and creation:
                return "live", creation
            if result.returncode == 1 and not creation:
                return "dead", None
        except (OSError, subprocess.TimeoutExpired):
            pass
    return "unknown", None


class RunLock:
    def __init__(self, directory: str | Path, run_id: str):
        self.directory = Path(directory).absolute()
        self.run_id = run_id
        self.metadata = None
        self._fd = None

    def acquire(self, *, recover: bool = False):
        if self._fd is not None:
            raise LockConflict("This ownership handle is already acquired")
        validate_path(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        guard = contained_path(self.directory, GUARD_NAME)
        fd = os.open(guard, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise LockConflict("Another writer owns this run") from exc
        self._fd = fd
        try:
            path = contained_path(self.directory, LOCK_NAME)
            if path.exists():
                try:
                    old = json.loads(path.read_text(encoding="utf-8"))
                    valid = (isinstance(old, dict) and type(old.get("schema")) is int and old["schema"] == 1
                             and set(old) == {"schema", "run_id", "host", "pid", "process_creation", "owner_token", "acquired_utc"}
                             and old.get("run_id") == self.run_id
                             and old.get("host") == host_identity()
                             and type(old.get("pid")) is int and old["pid"] > 0
                             and isinstance(old.get("process_creation"), str) and bool(old["process_creation"])
                             and isinstance(old.get("owner_token"), str)
                             and len(old["owner_token"]) == 32
                             and all(c in "0123456789abcdef" for c in old["owner_token"]))
                    if valid:
                        acquired = datetime.fromisoformat(old["acquired_utc"])
                        valid = acquired.tzinfo is not None and acquired.utcoffset().total_seconds() == 0
                except (OSError, ValueError, TypeError):
                    valid = False
                if not valid:
                    raise LockConflict("Uncertain or foreign ownership record preserved; recovery refused")
                state, creation = process_identity(old["pid"])
                stale = state == "dead" or (state == "live" and bool(creation) and creation != old["process_creation"])
                if not stale:
                    raise LockConflict("Owner is live or cannot be verified; record preserved")
                if not recover:
                    raise StaleLock("The former owner has exited. Confirm stale-lock recovery explicitly")
                archive = contained_path(self.directory, f".run-lock.stale-{old['owner_token']}.json")
                if archive.exists():
                    raise LockConflict("Stale ownership archive already exists; record preserved")
                # Recheck while the lifetime guard is held, before moving the old record.
                if json.loads(path.read_text(encoding="utf-8")) != old:
                    raise LockConflict("Ownership changed during recovery")
                rename_no_clobber(path, archive)
            state, creation = process_identity(os.getpid())
            if state != "live" or not creation:
                raise LockConflict("Cannot establish this process's creation identity")
            self.metadata = {"schema": 1, "run_id": self.run_id, "owner_token": uuid.uuid4().hex,
                             "pid": os.getpid(), "host": host_identity(), "process_creation": creation,
                             "acquired_utc": datetime.now(timezone.utc).isoformat()}
            with open(path, "x", encoding="utf-8", newline="\n") as handle:
                json.dump(self.metadata, handle)
                handle.flush()
                os.fsync(handle.fileno())
            return self
        except BaseException:
            os.close(self._fd)
            self._fd = None
            raise

    def assert_owned(self):
        if self._fd is None or self.metadata is None:
            raise LockConflict("Run writer lock is not held")
        path = contained_path(self.directory, LOCK_NAME)
        try:
            same = json.loads(path.read_text(encoding="utf-8")) == self.metadata
        except (OSError, ValueError):
            same = False
        if not same:
            raise LockConflict("Ownership record changed; refusing mutation")

    def release(self):
        if self._fd is None:
            return
        try:
            self.assert_owned()
            contained_path(self.directory, LOCK_NAME).unlink()
        finally:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self if self._fd is not None else self.acquire()

    def __exit__(self, *_exc):
        self.release()
