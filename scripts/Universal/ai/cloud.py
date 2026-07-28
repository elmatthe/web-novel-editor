"""Cloud provider readiness and the single gate every cloud request passes through.

Two entry points, deliberately shaped differently:

* :func:`check_readiness` **never raises**. It answers "can this provider run, and if
  not, what do I tell the user?" and is what the GUI calls to grey a provider out with
  a plain sentence. A missing key, an unapproved model, and a corrupt config are all
  states here, not exceptions.
* :func:`ensure_cloud_request_allowed` **only raises or returns the approved record**.
  It is the enforcement point: no cloud request may be issued without passing it. Every
  rail — provider known, provider enabled, key available, model approved, disclosure
  acknowledged — is checked in that order, so the user sees the most fixable problem
  first rather than a consent prompt they cannot act on yet.

The rails are checked here, once, rather than inside each adapter, so Phases 2 and 3
cannot each grow their own slightly different version of the safety contract.

This module imports no provider SDK and makes no network call. It is pure policy over
configuration, and it is safe to import at GUI start-up.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .approved_models import (
    ApprovedModel,
    ensure_model_approved,
    load_approved_models,
    selectable_models,
)
from .disclosure import (
    DISCLOSURE_VERSION,
    DisclosureNotAcknowledged,
    is_acknowledged,
    require_acknowledged,
)
from .errors import AuthenticationError, ProviderUnavailable
from .models import ProviderStatus
from .secrets import ENV_VARS, PROVIDER_LABELS, describe_key

CLOUD_PROVIDERS: tuple[str, ...] = ("gemini", "groq")

# Cloud-level states that sit alongside ProviderStatus without replacing any of it,
# the same way gui.ai_settings adds its own two. `no_model_selected` intentionally
# repeats the GUI's existing constant value so the panel's message table already
# renders it.
STATUS_CONSENT_REQUIRED = "consent_required"
STATUS_PROVIDER_DISABLED = "provider_disabled"
STATUS_NO_MODEL = "no_model_selected"

# Secret-free per-provider defaults. `config.toml` overrides these; neither layer ever
# holds a credential. `model` ships empty on purpose — the Phase 7 comparison run picks
# the default, so nothing pre-selects one before that evidence exists.
CLOUD_DEFAULTS: dict[str, dict[str, Any]] = {
    "gemini": {
        "enabled": False,
        "model": "",
        "timeout_seconds": 120,
        "max_output_tokens": 4096,
        "strict_free_tier_only": True,
        # Google documents no response rate-limit headers, so Phase 4 must run this
        # provider off a conservative configured floor. (Phase 0 correction #4.)
        "exposes_rate_limits": False,
        "billing_url": "https://aistudio.google.com/app/plan_information",
        "limits_url": "https://ai.google.dev/gemini-api/docs/rate-limits",
        # Phase 4 limiter floors. These mirror `config.toml`, which is the file a user
        # edits; they live here only so a missing or corrupt `[ai.gemini]` section
        # yields a *conservative* limiter rather than an unlimited one. See the long
        # note in `config.toml` — they are client-side self-restraint, never a claim
        # about the provider's real limit. `tpm_floor = 0` is deliberate: Gemini
        # publishes no token figure, and inventing one is exactly what is forbidden.
        "rpm_floor": 10,
        "tpm_floor": 0,
        "rate_limit_floor_seconds": 30,
        "backoff_base_seconds": 2,
        "backoff_max_seconds": 60,
        "backoff_jitter_ratio": 0.3,
        "max_attempts": 3,
        "max_wait_seconds": 900,
        "unnamed_limit_escalation_seconds": 600,
        # Google's free-tier requests-per-day quota refills, and its 429 says how long
        # to wait. See the long note in `config.toml` and DECISIONS #072.
        "daily_quota_retry_delay_max_seconds": 120,
    },
    "groq": {
        "enabled": False,
        "model": "",
        "timeout_seconds": 120,
        "max_output_tokens": 4096,
        "strict_free_tier_only": True,
        # Groq returns retry-after and x-ratelimit-* on every response, so Phase 4 can
        # drive this provider from real headers. (Phase 0 correction #4.)
        "exposes_rate_limits": True,
        "billing_url": "https://console.groq.com/settings/billing",
        "limits_url": "https://console.groq.com/settings/limits",
        # Phase 4 limiter floors — see the `config.toml` note. Live headers override
        # every one of these as soon as a response arrives; they govern only the
        # opening request of a run and any response whose headers were unreadable.
        "rpm_floor": 15,
        "tpm_floor": 5000,
        "rate_limit_floor_seconds": 30,
        "backoff_base_seconds": 2,
        "backoff_max_seconds": 60,
        "backoff_jitter_ratio": 0.3,
        "max_attempts": 3,
        "max_wait_seconds": 900,
        "unnamed_limit_escalation_seconds": 600,
    },
}


def is_cloud_provider(name: str) -> bool:
    return str(name or "").strip().lower() in CLOUD_PROVIDERS


def provider_settings(
    ai_table: Mapping[str, Any] | None, provider: str
) -> dict[str, Any]:
    """The secret-free ``[ai.<provider>]`` settings, over this module's defaults."""
    name = str(provider or "").strip().lower()
    if name not in CLOUD_DEFAULTS:
        raise ProviderUnavailable(
            f"'{provider}' is not a cloud provider this app supports.", retryable=False
        )
    resolved = dict(CLOUD_DEFAULTS[name])
    section = ai_table.get(name) if isinstance(ai_table, Mapping) else None
    if isinstance(section, Mapping):
        resolved.update(section)
    return resolved


@dataclass(frozen=True)
class CloudReadiness:
    """One honest snapshot of a cloud provider, safe to display and to log."""

    provider: str
    ready: bool
    status: str
    message: str
    key_present: bool
    key_source: str
    model_id: str
    disclosure_acknowledged: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "ready": self.ready,
            "status": self.status,
            "message": self.message,
            "key_present": self.key_present,
            "key_source": self.key_source,
            "model_id": self.model_id,
            "disclosure_acknowledged": self.disclosure_acknowledged,
        }


def _unready(provider, status, message, *, key=None, model_id="", acknowledged=False):
    return CloudReadiness(
        provider=provider,
        ready=False,
        status=status,
        message=message,
        key_present=bool(key and key.found),
        key_source=key.source if key else "none",
        model_id=model_id,
        disclosure_acknowledged=acknowledged,
    )


def check_readiness(
    provider: str,
    *,
    ai_table: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
    secrets_file: Path | None = None,
    dotenv_path: Path | None = None,
    settings_file: Path | None = None,
    version: str = DISCLOSURE_VERSION,
) -> CloudReadiness:
    """Answer "can this provider run?" without raising and without calling out."""
    name = str(provider or "").strip().lower()
    if not is_cloud_provider(name):
        return _unready(
            name,
            ProviderStatus.INVALID_CONFIGURATION.value,
            f"'{provider}' is not a cloud provider this app supports.",
        )

    try:
        settings = provider_settings(ai_table, name)
    except ProviderUnavailable as exc:
        return _unready(name, ProviderStatus.INVALID_CONFIGURATION.value, str(exc))

    label = PROVIDER_LABELS.get(name, name)
    if not settings.get("enabled", False):
        return _unready(
            name,
            STATUS_PROVIDER_DISABLED,
            f"{label} is turned off in the AI settings. Turn it on to use it.",
        )

    key = describe_key(
        name, environ=environ, secrets_file=secrets_file, dotenv_path=dotenv_path
    )
    if not key.found:
        return _unready(name, ProviderStatus.AUTH_MISSING.value, key.message, key=key)

    model_id = str(settings.get("model") or "").strip()
    strict = bool(settings.get("strict_free_tier_only", True))
    models = load_approved_models(ai_table)
    if not model_id:
        choices = selectable_models(models, name, strict_free_only=strict)
        listed = ", ".join(m.id for m in choices) if choices else "none yet"
        return _unready(
            name,
            STATUS_NO_MODEL,
            f"No model has been chosen for {label}. Approved choices: {listed}.",
            key=key,
        )
    try:
        approved = ensure_model_approved(
            model_id, provider=name, models=models, strict_free_only=strict
        )
    except Exception as exc:
        return _unready(
            name,
            ProviderStatus.MODEL_MISSING.value,
            str(exc),
            key=key,
            model_id=model_id,
        )

    acknowledged = is_acknowledged(
        name, settings_file=settings_file, version=version
    )
    if not acknowledged:
        return _unready(
            name,
            STATUS_CONSENT_REQUIRED,
            f"Before any chapter text is sent to {label}, the cloud privacy and "
            f"billing disclosure has to be reviewed and accepted.",
            key=key,
            model_id=approved.id,
        )

    return CloudReadiness(
        provider=name,
        ready=True,
        status=ProviderStatus.OK.value,
        message=(
            f"Ready — {approved.id} is approved, a key was found, and the cloud "
            f"disclosure has been accepted."
        ),
        key_present=True,
        key_source=key.source,
        model_id=approved.id,
        disclosure_acknowledged=True,
    )


def ensure_cloud_request_allowed(
    provider: str,
    *,
    ai_table: Mapping[str, Any] | None = None,
    model_id: str | None = None,
    environ: Mapping[str, str] | None = None,
    secrets_file: Path | None = None,
    dotenv_path: Path | None = None,
    settings_file: Path | None = None,
    version: str = DISCLOSURE_VERSION,
) -> ApprovedModel:
    """Enforce every rail before a cloud request. Returns the approved record.

    Raises ``ProviderUnavailable`` (unknown or disabled provider),
    ``AuthenticationError`` (no key), ``ModelUnavailable`` (not approved, unknown
    free-tier confidence, or not stable), or ``DisclosureNotAcknowledged`` (no consent).
    Nothing is substituted and nothing is assumed at any step.
    """
    name = str(provider or "").strip().lower()
    if not is_cloud_provider(name):
        raise ProviderUnavailable(
            f"'{provider}' is not a cloud provider this app supports.", retryable=False
        )

    settings = provider_settings(ai_table, name)
    label = PROVIDER_LABELS.get(name, name)
    if not settings.get("enabled", False):
        raise ProviderUnavailable(
            f"{label} is not enabled in the AI settings.", retryable=False
        )

    key = describe_key(
        name, environ=environ, secrets_file=secrets_file, dotenv_path=dotenv_path
    )
    if not key.found:
        env_var = ENV_VARS.get(name, "the provider's API key environment variable")
        raise AuthenticationError(
            f"No API key is available for {label}. Set the {env_var} environment "
            f"variable, or save a key in the app's AI settings.",
            retryable=False,
        )

    wanted = model_id if model_id is not None else settings.get("model", "")
    approved = ensure_model_approved(
        wanted,
        provider=name,
        models=load_approved_models(ai_table),
        strict_free_only=bool(settings.get("strict_free_tier_only", True)),
    )

    require_acknowledged(name, settings_file=settings_file, version=version)
    return approved


__all__ = [
    "CLOUD_DEFAULTS",
    "CLOUD_PROVIDERS",
    "CloudReadiness",
    "DisclosureNotAcknowledged",
    "STATUS_CONSENT_REQUIRED",
    "STATUS_NO_MODEL",
    "STATUS_PROVIDER_DISABLED",
    "check_readiness",
    "ensure_cloud_request_allowed",
    "is_cloud_provider",
    "provider_settings",
]
