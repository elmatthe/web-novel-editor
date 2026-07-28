"""Cloud API key discovery, storage, and presence-only reporting (Plan 2b Phase 1).

**No key value ever leaves this module except through :func:`resolve_api_key`**, which
is what an adapter calls immediately before building its client. Everything the GUI,
the logs, and the status panel see comes from :func:`describe_key`, which returns a
:class:`KeyPresence` — a record that structurally *cannot* carry the value, because it
never stores one.

Precedence, highest first:

1. ``KeySource.ENVIRONMENT`` — the ``GEMINI_API_KEY`` / ``GROQ_API_KEY`` process
   environment variables. This is both providers' own documented guidance and the
   path an advanced user or a CI job will reach for first.
2. ``KeySource.SECRETS_FILE`` — ``secrets.json`` in the per-user application-data
   directory. This is the end-user store, and it is **outside the repo folder** on
   purpose: a downloaded-and-unzipped project directory is the wrong home for a
   credential, however well gitignored it is.
3. ``KeySource.SESSION`` — a key typed into a masked prompt, held in memory only for
   this process and never written anywhere.
4. ``KeySource.DEV_DOTENV`` — a repo-root ``.env``, **read only**, as a documented
   developer override. No code path in this project writes one, and reading it never
   mutates ``os.environ`` (which would leak the value into every child process this
   app spawns).
5. ``KeySource.NONE`` — no key. The provider is reported unavailable with a plain
   sentence saying what to do about it, and nothing is attempted.

The ``.env`` slot sits *below* the session key rather than at the top: the drop lists
only slots 1–3 and calls ``.env`` a developer override, and an override that silently
outranked the user's own saved key would be a surprising place for a wrong key to hide.

The per-user directory and the atomic write are **2a's** — ``runtime_dir()`` and
``write_settings_atomic()`` from ``ai.settings`` — reused here rather than
reimplemented, so the secrets file and the settings file can never disagree about
where the application's data lives.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from . import redaction
from .settings import runtime_dir, write_settings_atomic

# The provider's own documented variable name. Changing one of these is a
# user-visible contract change, not a refactor.
ENV_VARS: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
}

PROVIDER_LABELS: dict[str, str] = {"gemini": "Gemini", "groq": "Groq"}

SECRETS_FILENAME = "secrets.json"
SECRETS_FILE_VERSION = 1

# ai/secrets.py -> ai -> Universal -> scripts -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DOTENV_PATH = REPO_ROOT / ".env"

# Session keys: this process only, never persisted, never included in any record.
_SESSION_KEYS: dict[str, str] = {}


class KeySource(str, Enum):
    ENVIRONMENT = "environment"
    SECRETS_FILE = "secrets_file"
    SESSION = "session"
    DEV_DOTENV = "dev_dotenv"
    NONE = "none"


@dataclass(frozen=True)
class KeyPresence:
    """Presence-only key report. Holds no key value, by construction."""

    provider: str
    found: bool
    source: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "found": self.found,
            "source": self.source,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------
def secrets_path(**kwargs) -> Path:
    """The per-user secrets file, alongside 2a's ``settings.json``.

    Raises ``OSError`` on an unsupported platform, exactly as ``runtime_dir()``
    already does — callers that must not fail catch it and fall back to "no file".
    """
    return runtime_dir(**kwargs) / SECRETS_FILENAME


def default_secrets_file() -> Path | None:
    """The per-user secrets file, or None on a platform without one."""
    try:
        return secrets_path()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Session keys (memory only)
# ---------------------------------------------------------------------------
def set_session_key(provider: str, key: str) -> bool:
    """Hold a key for this process only. Never written to disk."""
    name = _normalise(provider)
    value = _clean(key)
    if not value:
        return False
    _SESSION_KEYS[name] = value
    redaction.register_secret(value)
    return True


def clear_session_keys() -> None:
    _SESSION_KEYS.clear()


def session_providers() -> tuple[str, ...]:
    """Which providers have a session key — never the keys themselves."""
    return tuple(sorted(_SESSION_KEYS))


# ---------------------------------------------------------------------------
# The per-user secrets file
# ---------------------------------------------------------------------------
def _read_secrets_document(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # An unreadable or corrupt secrets file is "no key", never a crash.
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _stored_keys(path: Path | None) -> dict[str, str]:
    keys = _read_secrets_document(path).get("keys")
    if not isinstance(keys, dict):
        return {}
    return {str(k).strip().lower(): v for k, v in keys.items() if isinstance(v, str)}


def _restrict_permissions(path: Path) -> None:
    """Tighten the file down as far as this OS allows. Never raises.

    POSIX gets an exact answer (owner read/write only). Windows has no equivalent
    mode bit, so the real mechanism is an ACL: strip inheritance and grant the
    current user alone. If that fails for any reason the key is still written — a
    weaker-than-hoped ACL must not cost the user their saved key.
    """
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    if sys.platform != "win32":
        return
    try:
        user = os.environ.get("USERNAME") or ""
        if not user:
            import getpass

            user = getpass.getuser()
        if not user:
            return
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        # Best effort only. Never surface a console window, never raise.
        pass


def store_api_key(provider: str, key: str, *, path: Path | None = None) -> bool:
    """Save a key to the per-user secrets file, atomically and restricted.

    Returns False rather than raising when there is nowhere to write or the value is
    not a usable key — a read-only profile directory must never break the app.
    """
    name = _normalise(provider)
    value = _clean(key)
    if not value:
        return False
    if path is None:
        path = default_secrets_file()
    if path is None:
        return False

    document = _read_secrets_document(path)
    keys = document.get("keys")
    keys = dict(keys) if isinstance(keys, dict) else {}
    keys[name] = value
    document["keys"] = keys
    document["version"] = SECRETS_FILE_VERSION

    try:
        write_settings_atomic(path, document)
    except (OSError, ValueError):
        return False
    _restrict_permissions(path)
    redaction.register_secret(value)
    return True


def delete_api_key(provider: str, *, path: Path | None = None) -> bool:
    """Remove one provider's stored key. Returns True if something was removed."""
    name = _normalise(provider)
    if path is None:
        path = default_secrets_file()
    if path is None or not path.exists():
        return False
    document = _read_secrets_document(path)
    keys = document.get("keys")
    keys = dict(keys) if isinstance(keys, dict) else {}
    if name not in keys:
        return False
    keys.pop(name)
    document["keys"] = keys
    document["version"] = SECRETS_FILE_VERSION
    try:
        write_settings_atomic(path, document)
    except (OSError, ValueError):
        return False
    _restrict_permissions(path)
    return True


# ---------------------------------------------------------------------------
# The developer .env override (read-only)
# ---------------------------------------------------------------------------
def _read_dotenv(path: Path | None) -> dict[str, str]:
    """Parse a simple ``KEY=VALUE`` file. Never writes, never touches os.environ."""
    if path is None or not path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[len("export "):].strip()
        name, sep, value = line.partition("=")
        if not sep:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name.strip()] = value
    return values


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def _normalise(provider: str) -> str:
    return str(provider or "").strip().lower()


def _clean(value: Any) -> str:
    """A usable key, or "" — whitespace and implausibly short values are not keys."""
    if not isinstance(value, str):
        return ""
    candidate = value.strip()
    if len(candidate) < redaction.MIN_SECRET_LENGTH:
        return ""
    return candidate


def resolve_api_key(
    provider: str,
    *,
    environ: Mapping[str, str] | None = None,
    secrets_file: Path | None = None,
    dotenv_path: Path | None = None,
) -> tuple[str | None, KeySource]:
    """Find this provider's key by precedence. **Returns the value** — handle with care.

    Any key found is registered with the redactor before it is returned, so from this
    moment on it cannot appear in a log, a traceback, or a serialized record.

    ``secrets_file`` and ``dotenv_path`` default to the real per-user and repo-root
    locations; pass them explicitly (as the tests do) to stay hermetic.
    """
    name = _normalise(provider)
    environ = os.environ if environ is None else environ
    if secrets_file is None:
        secrets_file = default_secrets_file()
    if dotenv_path is None:
        dotenv_path = DEFAULT_DOTENV_PATH

    env_var = ENV_VARS.get(name, "")
    candidates: tuple[tuple[str, KeySource], ...] = (
        (_clean(environ.get(env_var)) if env_var else "", KeySource.ENVIRONMENT),
        (_clean(_stored_keys(secrets_file).get(name)), KeySource.SECRETS_FILE),
        (_clean(_SESSION_KEYS.get(name)), KeySource.SESSION),
        (_clean(_read_dotenv(dotenv_path).get(env_var)) if env_var else "",
         KeySource.DEV_DOTENV),
    )
    for value, source in candidates:
        if value:
            redaction.register_secret(value)
            return value, source
    return None, KeySource.NONE


def describe_key(
    provider: str,
    *,
    environ: Mapping[str, str] | None = None,
    secrets_file: Path | None = None,
    dotenv_path: Path | None = None,
) -> KeyPresence:
    """Presence-only report for the GUI and the status log.

    The resolved value is discarded inside this function and never reaches the
    returned record, so there is nothing for a caller to leak by accident.
    """
    name = _normalise(provider)
    value, source = resolve_api_key(
        name, environ=environ, secrets_file=secrets_file, dotenv_path=dotenv_path
    )
    found = value is not None
    del value  # explicit: nothing below this line may see the key
    return KeyPresence(name, found, source.value, _presence_message(name, source))


def _presence_message(provider: str, source: KeySource) -> str:
    label = PROVIDER_LABELS.get(provider, provider or "This provider")
    env_var = ENV_VARS.get(provider, "the provider's API key environment variable")
    if source is KeySource.ENVIRONMENT:
        return f"Key found in the {env_var} environment variable."
    if source is KeySource.SECRETS_FILE:
        return "Key found in your saved settings on this computer."
    if source is KeySource.SESSION:
        return "Key entered for this session only — it has not been saved."
    if source is KeySource.DEV_DOTENV:
        return "Key found in the developer .env override in the project folder."
    return (
        f"No API key found, so {label} is unavailable. Set the {env_var} environment "
        f"variable, or save a key in the app's AI settings."
    )
