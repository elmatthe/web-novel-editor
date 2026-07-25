"""The single redaction boundary for credentials (Plan 2b Phase 1).

Every string that could carry an API key must leave the application through this
module. There is deliberately **one** implementation and no second path: the GUI log
sink, exception reporting, serialized manifests/JSONL, and any command line all call
into the functions below. A later phase that needs to log something new routes it
through here rather than adding a redactor of its own.

Two independent layers run on every string, so a mistake in either one is not enough
to leak a key:

1. **Registered literals.** ``ai.secrets`` calls :func:`register_secret` the moment it
   resolves a key from any source, so the exact value is masked wherever it appears —
   even embedded inside a URL, a JSON blob, or a provider's error text.
2. **Shape patterns.** Google (``AIza…``), Groq (``gsk_…``) and OpenAI-style (``sk-…``)
   key shapes, ``Authorization: Bearer …``, and ``api_key=…`` style assignments are
   masked whether or not they were ever registered. This is what protects a key that
   was pasted into a config file, echoed by a third-party library, or never passed
   through our own resolver at all.

The registry lives in memory for the process lifetime and is never serialized,
persisted, or exposed — :func:`registered_secret_count` reports only how many values
are held, never which.

This module imports nothing outside the standard library and has no side effects at
import time, so it is safe to import from the GUI at start-up.
"""

from __future__ import annotations

import logging
import re
import traceback
from typing import Any, Iterable, Mapping, Sequence

REDACTED = "[REDACTED]"

# Values shorter than this are not plausible credentials, and masking them would turn
# ordinary log text into noise. ``ai.secrets`` applies the same floor when deciding
# whether a discovered value is a usable key at all, so the two agree.
MIN_SECRET_LENGTH = 6

# Process-lifetime registry of exact secret values. Never written to disk, never
# included in any report, never returned by any public function here.
_SECRETS: set[str] = set()

_SHAPE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Google AI / Gemini API keys.
    re.compile(r"AIza[0-9A-Za-z_\-]{16,}"),
    # Groq API keys.
    re.compile(r"gsk_[0-9A-Za-z]{16,}"),
    # OpenAI-style keys, which several SDKs and proxies also emit.
    re.compile(r"sk-[0-9A-Za-z_\-]{16,}"),
)

# ``Authorization: Bearer <token>`` — the token, not the scheme, is the secret.
_BEARER_PATTERN = re.compile(r"(?i)(\bbearer\s+)([A-Za-z0-9._\-]{12,})")

# ``api_key=…`` / ``x-goog-api-key: …`` / ``x-api-key: …`` style assignments, quoted
# or bare. Only the value is replaced; the field name stays readable so the log still
# says *what* was withheld.
_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(\b(?:api[-_]?key|apikey|x-goog-api-key|x-api-key|access[-_]?token)\b\s*[:=]\s*)"
    r"([\"']?)([^\s\"',;}\]]{8,})\2"
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def register_secret(value: Any) -> bool:
    """Remember an exact secret value so it is masked everywhere from now on.

    Returns False for anything too short to be a real credential, which keeps a
    stray empty string from turning every log line into ``[REDACTED]``.
    """
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if len(candidate) < MIN_SECRET_LENGTH:
        return False
    _SECRETS.add(candidate)
    return True


def forget_secrets() -> None:
    """Drop every registered value (session teardown and test isolation)."""
    _SECRETS.clear()


def registered_secret_count() -> int:
    """How many secrets are held — never which ones."""
    return len(_SECRETS)


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------
def _mask_group(match: re.Match[str], group: int) -> str:
    text = match.group(0)
    start, end = match.span(group)
    return text[: start - match.start()] + REDACTED + text[end - match.start():]


def redact(text: Any) -> str:
    """Return ``text`` with every known or key-shaped credential masked."""
    if text is None:
        return ""
    result = text if isinstance(text, str) else str(text)
    # Longest first, so a secret that contains another secret as a substring is
    # replaced whole rather than leaving a readable tail behind.
    for secret in sorted(_SECRETS, key=len, reverse=True):
        if secret in result:
            result = result.replace(secret, REDACTED)
    for pattern in _SHAPE_PATTERNS:
        result = pattern.sub(REDACTED, result)
    result = _BEARER_PATTERN.sub(lambda m: m.group(1) + REDACTED, result)
    result = _ASSIGNMENT_PATTERN.sub(lambda m: _mask_group(m, 3), result)
    return result


def redact_obj(obj: Any) -> Any:
    """Recursively redact strings inside dicts, lists, tuples, and sets.

    Used for anything that gets serialized — JSONL rows, the Phase 5 run manifest,
    provenance records, and debug dumps. Container types are preserved so callers
    can serialize the result exactly as they would have serialized the original.
    """
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, Mapping):
        return {redact_obj(key): redact_obj(value) for key, value in obj.items()}
    if isinstance(obj, tuple):
        return tuple(redact_obj(item) for item in obj)
    if isinstance(obj, list):
        return [redact_obj(item) for item in obj]
    if isinstance(obj, (set, frozenset)):
        return type(obj)(redact_obj(item) for item in obj)
    return obj


def redact_argv(args: Sequence[Any]) -> list[str]:
    """Redact a subprocess argument list before it is logged or reported."""
    return [redact(arg) for arg in args]


def redact_exception(exc: BaseException) -> str:
    """The exception's message, safe to show or log.

    Provider SDKs routinely put the request URL — key query parameter and all —
    into the exception text, so this is never optional.
    """
    return redact(f"{type(exc).__name__}: {exc}")


def redact_traceback(exc: BaseException | None = None) -> str:
    """A full formatted traceback with every credential masked."""
    if exc is None:
        return redact("".join(traceback.format_exc()))
    return redact(
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    )


# ---------------------------------------------------------------------------
# Standard-library logging
# ---------------------------------------------------------------------------
class RedactingFilter(logging.Filter):
    """Masks credentials in the record's message and its formatting arguments."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - stdlib name
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                if isinstance(record.args, Mapping):
                    record.args = {k: redact_obj(v) for k, v in record.args.items()}
                elif isinstance(record.args, tuple):
                    record.args = tuple(redact_obj(a) for a in record.args)
        except Exception:  # pragma: no cover - a redactor must never break logging
            record.msg = REDACTED
            record.args = ()
        return True


def install_logging_redaction(loggers: Iterable[logging.Logger] | None = None) -> None:
    """Attach :class:`RedactingFilter` to the given loggers (root by default)."""
    targets = list(loggers) if loggers is not None else [logging.getLogger()]
    for logger in targets:
        if not any(isinstance(f, RedactingFilter) for f in logger.filters):
            logger.addFilter(RedactingFilter())
