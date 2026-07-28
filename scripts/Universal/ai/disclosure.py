"""The cloud privacy + billing disclosure and its acknowledgement record.

Sending a chapter to a cloud provider takes the user's text off their machine. Plan 2b
treats that as a consent decision, made once, explicitly, **before the first cloud
request** — not as a side effect of ticking a checkbox labelled "AI".

What is stored: **only the acknowledged disclosure version, per provider.** No name, no
date, no account identifier, no chapter text, no key — nothing that could identify the
user or their work. Acknowledging Gemini does not acknowledge Groq, because the text
names which company receives the chapters.

Bumping :data:`DISCLOSURE_VERSION` invalidates every existing acknowledgement and the
user is asked again. Do that whenever the disclosure's *meaning* changes; a typo fix is
not a version bump.

The wording of :func:`disclosure_text` follows the drop's honest safety contract. In
particular it does **not** promise the app cannot incur charges: a desktop application
holding a user-supplied key cannot authoritatively determine whether the project or
organization behind that key is billed, so the app says what it actually does — never
enables billing, never upgrades an account, never intentionally selects a paid or
preview model — and asks the user to confirm the rest in the provider's own console.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .errors import AIProviderError
from .settings import settings_path, write_settings_atomic

DISCLOSURE_VERSION = "1"

# Where the acknowledgement lives inside the existing per-user settings.json.
SETTINGS_SECTION = "ai"
ACK_KEY = "cloud_disclosure"

PROVIDER_LABELS: dict[str, str] = {"gemini": "Google (Gemini)", "groq": "Groq"}

PROVIDER_LINKS: dict[str, dict[str, str]] = {
    "gemini": {
        "billing": "https://aistudio.google.com/app/plan_information",
        "limits": "https://ai.google.dev/gemini-api/docs/rate-limits",
        "terms": "https://ai.google.dev/gemini-api/terms",
    },
    "groq": {
        "billing": "https://console.groq.com/settings/billing",
        "limits": "https://console.groq.com/settings/limits",
        "terms": "https://groq.com/terms-of-use/",
    },
}


class DisclosureNotAcknowledged(AIProviderError):
    """Raised when a cloud request is attempted before consent is recorded.

    Defined here rather than in ``errors.py`` on purpose: 2a's error taxonomy is the
    shared provider contract and Plan 2b is not permitted to change it.
    """

    retryable = False


def disclosure_text(provider: str) -> str:
    """The full disclosure shown before the first cloud request to this provider."""
    name = str(provider or "").strip().lower()
    label = PROVIDER_LABELS.get(name, name or "this provider")
    links = PROVIDER_LINKS.get(name, {})
    billing = links.get("billing", "the provider's console")
    return (
        f"Your chapter text will leave this computer.\n\n"
        f"If you continue, the text of each chapter this app edits is sent over the "
        f"internet to {label}, which processes it on its own servers under its own "
        f"terms and data-use policies. Free-tier data handling can differ from paid-tier "
        f"handling — read the provider's terms if that matters to you.\n\n"
        f"About cost. This app never enables billing, never upgrades an account, and "
        f"never intentionally selects a paid-only or preview model. It can only call the "
        f"exact models on its reviewed approved list. But a desktop app holding a key "
        f"you supplied cannot tell for certain whether the project or organization behind "
        f"that key is billed, so it cannot promise you will never be charged. Use a key "
        f"from a project with billing disabled, and confirm that yourself here:\n"
        f"{billing}\n\n"
        f"You do not have to do this. Choosing Cancel keeps the app in local or "
        f"script-only editing, which never sends your text anywhere."
    )


def acknowledgement_record(version: str = DISCLOSURE_VERSION) -> str:
    """The entire stored value: a version string, and nothing else."""
    return str(version)


# ---------------------------------------------------------------------------
# Persistence — merged into 2a's per-user settings.json
# ---------------------------------------------------------------------------
def _default_settings_file() -> Path | None:
    try:
        return settings_path()
    except OSError:
        return None


def _read_document(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def read_acknowledgements(*, settings_file: Path | None = None) -> dict[str, str]:
    """``{provider: acknowledged_version}``. Empty when nothing is recorded."""
    if settings_file is None:
        settings_file = _default_settings_file()
    section = _read_document(settings_file).get(SETTINGS_SECTION)
    if not isinstance(section, Mapping):
        return {}
    record = section.get(ACK_KEY)
    if not isinstance(record, Mapping):
        return {}
    return {
        str(k).strip().lower(): str(v)
        for k, v in record.items()
        if isinstance(v, (str, int))
    }


def is_acknowledged(
    provider: str,
    *,
    settings_file: Path | None = None,
    version: str = DISCLOSURE_VERSION,
) -> bool:
    """True only when *this* provider acknowledged *this* version of the text."""
    name = str(provider or "").strip().lower()
    return read_acknowledgements(settings_file=settings_file).get(name) == str(version)


def record_acknowledgement(
    provider: str,
    *,
    settings_file: Path | None = None,
    version: str = DISCLOSURE_VERSION,
) -> bool:
    """Record that the user accepted the disclosure. Stores only the version.

    Merges into the existing settings document — the user's model and policy choices
    must survive. Returns False rather than raising when the location is not writable.
    """
    name = str(provider or "").strip().lower()
    if not name:
        return False
    if settings_file is None:
        settings_file = _default_settings_file()
    if settings_file is None:
        return False

    document = _read_document(settings_file)
    section = document.get(SETTINGS_SECTION)
    section = dict(section) if isinstance(section, Mapping) else {}
    record = section.get(ACK_KEY)
    record = dict(record) if isinstance(record, Mapping) else {}
    record[name] = acknowledgement_record(version)
    section[ACK_KEY] = record
    document[SETTINGS_SECTION] = section

    try:
        write_settings_atomic(settings_file, document)
    except (OSError, ValueError):
        return False
    return True


def require_acknowledged(
    provider: str,
    *,
    settings_file: Path | None = None,
    version: str = DISCLOSURE_VERSION,
) -> None:
    """The gate. Raises :class:`DisclosureNotAcknowledged` if consent is not recorded."""
    if is_acknowledged(provider, settings_file=settings_file, version=version):
        return
    label = PROVIDER_LABELS.get(str(provider or "").strip().lower(), provider)
    raise DisclosureNotAcknowledged(
        f"The cloud privacy and billing disclosure for {label} has not been "
        f"acknowledged, so no chapter text may be sent. Review and accept it before "
        f"running a cloud pass.",
        retryable=False,
    )
