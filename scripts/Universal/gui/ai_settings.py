"""AI preference resolution, provider probing, and run-rate maths for the GUI.

This module is deliberately tkinter-free, so every rule below is unit-testable
headlessly. It also keeps the optional parts of the AI stack out of import time:
only ``ai.models`` and ``ai.settings`` (pure stdlib) are imported at module load,
while ``ai.config`` (needs ``tomli`` on Python 3.10), ``ai.factory`` and
``ai.editor`` are imported inside the function that needs them. Importing this
module — and therefore starting the app — must work on a machine with no local
AI service and no optional AI packages installed.

**The status the panel shows is the provider's own.** ``probe_provider`` calls the
adapter's real ``health_check()`` and ``list_models()`` and passes the resulting
``ProviderStatus`` straight through; none of that detection is re-implemented
here. Two GUI-level states sit *alongside* those values without replacing any of
them:

``unchecked``
    Nothing has been asked of any provider yet. This is the script-only startup
    state, and it is why turning the AI pass off never touches a provider.
``no_model_selected``
    The service answered, but no model tag has been chosen yet. The probe had to
    use a placeholder tag to enumerate what is installed, so the provider's
    literal ``model_missing`` would blame the service for a choice the user has
    not made. (DECISIONS #054.)

The opt-in switch itself is session-only: ``load_ai_preferences`` always resolves
``enabled`` to False, so the AI pass can never come up already on. Only the
choices in ``PERSISTED_KEYS`` are written to the per-user settings file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from ai.models import ProviderStatus, RunPolicy
from ai.settings import settings_path, write_settings_atomic

# Only the *values* of the AI enums are captured at module load. The enum classes
# themselves are re-imported inside the functions that build objects with them, so
# a reloaded `ai.models` can never leave this module comparing against a stale
# class identity.
POLICY_PREFER_AI = RunPolicy.PREFER_AI.value
POLICY_AI_REQUIRED = RunPolicy.AI_REQUIRED.value
STATUS_OK = ProviderStatus.OK.value
STATUS_MODEL_MISSING = ProviderStatus.MODEL_MISSING.value
STATUS_PACKAGE_UNAVAILABLE = ProviderStatus.PACKAGE_UNAVAILABLE.value
STATUS_PROVIDER_ERROR = ProviderStatus.PROVIDER_ERROR.value

# The committed application defaults live in the repo-root config.toml:
#   scripts/Universal/gui/ai_settings.py -> gui -> Universal -> scripts -> root
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.toml"

# Only these two GUI choices are remembered between sessions. `enabled` is
# deliberately absent — see the module docstring.
PERSISTED_KEYS = ("model", "policy")
DEFAULT_POLICY = POLICY_PREFER_AI

# GUI-level states, additive to ProviderStatus (never substitutes for one).
STATUS_UNCHECKED = "unchecked"
STATUS_NO_MODEL = "no_model_selected"

# A complete, deliberately unreal tag used only to enumerate installed models
# before the user has chosen one. The adapter requires a complete `name:tag`
# before it will talk to the service at all, and this can never collide with a
# real installed tag.
LISTING_PLACEHOLDER_TAG = "__no_model_selected__:list"

# Every state the panel can report, in the provider's own vocabulary plus the two
# GUI states. Each message is distinct: a failure is never flattened into a
# generic "unavailable".
_STATUS_MESSAGES: dict[str, tuple[str, str]] = {
    ProviderStatus.OK.value: (
        "Ready — {model} is installed and the local AI service answered.", "success"),
    ProviderStatus.PACKAGE_UNAVAILABLE.value: (
        "The provider package is not installed in this build, so the AI pass "
        "cannot run.", "warn"),
    ProviderStatus.SERVICE_DOWN.value: (
        "The local AI service is not running, or is not reachable at the "
        "configured endpoint.", "warn"),
    ProviderStatus.MODEL_MISSING.value: (
        "The service answered, but the model {model} is not installed on this "
        "machine.", "warn"),
    ProviderStatus.INVALID_CONFIGURATION.value: (
        "The AI configuration is not usable — check the endpoint and model tag "
        "in config.toml.", "error"),
    ProviderStatus.TIMEOUT.value: (
        "The local AI service did not answer before the configured timeout.",
        "warn"),
    ProviderStatus.PROVIDER_ERROR.value: (
        "The AI provider returned an unexpected error.", "error"),
    ProviderStatus.AUTH_MISSING.value: (
        "This provider needs credentials that are not configured.", "error"),
    ProviderStatus.QUOTA_EXHAUSTED.value: (
        "This provider's quota is exhausted.", "error"),
    STATUS_UNCHECKED: (
        "Not checked — the AI pass is off, so no service has been contacted.",
        "muted"),
    STATUS_NO_MODEL: (
        "The service answered. Choose one of the installed models to use the "
        "AI pass.", "warn"),
}


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------
def default_settings_file() -> Path | None:
    """The per-user settings file, or None on a platform without one."""
    try:
        return settings_path()
    except OSError:
        return None


def load_ai_preferences(
    *,
    config_path: Path | None = None,
    settings_file: Path | None = None,
) -> dict[str, Any]:
    """Resolve in-code defaults < config.toml < per-user settings.

    ``enabled`` is always forced back to False: the AI pass is opt-in per
    session, so a persisted choice can never switch it on at launch.
    """
    from ai.config import load_config, load_settings, resolve_ai_config

    config_path = DEFAULT_CONFIG_PATH if config_path is None else config_path
    if settings_file is None:
        settings_file = default_settings_file()

    try:
        defaults = load_config(config_path)
    except (OSError, ValueError):
        defaults = {}
    user_settings: dict[str, Any] = {}
    if settings_file is not None:
        try:
            user_settings = load_settings(settings_file)
        except (OSError, ValueError):
            user_settings = {}

    resolved = resolve_ai_config(config_defaults=defaults, user_settings=user_settings)
    resolved["enabled"] = False
    resolved.setdefault("policy", DEFAULT_POLICY)
    resolved["model"] = str(resolved.get("model") or "").strip()
    return resolved


def save_ai_preferences(
    prefs: Mapping[str, Any], *, settings_file: Path | None = None
) -> bool:
    """Persist only ``PERSISTED_KEYS``, merging into any existing settings file.

    Returns False rather than raising when the location is not writable — a
    non-writable profile directory must never break the app.
    """
    import json

    if settings_file is None:
        settings_file = default_settings_file()
    if settings_file is None:
        return False

    document: dict[str, Any] = {}
    try:
        if settings_file.exists():
            loaded = json.loads(settings_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                document = loaded
    except (OSError, ValueError):
        document = {}

    section = document.get("ai")
    section = dict(section) if isinstance(section, dict) else {}
    section.pop("enabled", None)
    for key in PERSISTED_KEYS:
        section[key] = prefs.get(key, "")
    document["ai"] = section

    try:
        write_settings_atomic(settings_file, document)
    except (OSError, ValueError):
        return False
    return True


# ---------------------------------------------------------------------------
# Status reporting
# ---------------------------------------------------------------------------
def describe_status(status: str, *, model: str = "") -> tuple[str, str]:
    """Return (plain-language message, log level) for a status value."""
    template, level = _STATUS_MESSAGES.get(
        str(status), ("The AI provider reported an unrecognised state.", "error")
    )
    return template.format(model=model or "the selected model"), level


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ProviderProbe:
    """One honest snapshot of the provider: its own status plus installed tags."""

    status: str
    models: tuple[str, ...] = ()


def _create_provider(prefs: Mapping[str, Any], model_id: str):
    """Construct whatever provider the configuration names.

    The GUI never names a provider itself — that boundary belongs to the factory
    and the configuration layer, so 2b's cloud adapters need no change here.
    """
    from ai.config import IN_CODE_DEFAULTS
    from ai.factory import create_provider

    return create_provider(
        str(prefs.get("provider") or IN_CODE_DEFAULTS["provider"]),
        model_id=model_id,
        endpoint=prefs.get("endpoint", ""),
        timeout_seconds=float(prefs.get("timeout_seconds", 120)),
        keep_alive=prefs.get("keep_alive", "30m"),
        context_limit=int(prefs.get("context_limit", 32768)),
        max_output_tokens=int(prefs.get("max_output_tokens", 4096)),
        request_overhead_tokens=int(prefs.get("request_overhead_tokens", 128)),
        context_safety_margin_tokens=int(
            prefs.get("context_safety_margin_tokens", 256)),
        output_margin_tokens=int(prefs.get("output_margin_tokens", 64)),
    )


def probe_provider(
    prefs: Mapping[str, Any],
    *,
    create: Callable[[Mapping[str, Any], str], Any] | None = None,
) -> ProviderProbe:
    """Ask the real provider how it is, and what it has installed.

    Blocking (it talks to the local service), so callers run it off the UI
    thread. It never raises: an unreachable, misconfigured, or absent provider
    is a status, not an exception.
    """
    create = create or _create_provider
    model = str(prefs.get("model") or "").strip()
    probe_model = model or LISTING_PLACEHOLDER_TAG

    try:
        provider = create(prefs, probe_model)
    except Exception:
        # No adapter in this build — the same situation the provider itself
        # reports when its SDK is missing.
        return ProviderProbe(STATUS_PACKAGE_UNAVAILABLE)

    try:
        status = provider.health_check()
    except Exception:
        return ProviderProbe(STATUS_PROVIDER_ERROR)
    value = getattr(status, "value", str(status))

    # A model list is only meaningful when the service actually answered.
    models: tuple[str, ...] = ()
    if value in (STATUS_OK, STATUS_MODEL_MISSING):
        try:
            models = tuple(str(name) for name in provider.list_models())
        except Exception:
            models = ()

    if not model and value == STATUS_MODEL_MISSING:
        # The placeholder tag was never real; do not blame the service for it.
        value = STATUS_NO_MODEL
    return ProviderProbe(value, models)


# ---------------------------------------------------------------------------
# Editor construction
# ---------------------------------------------------------------------------
def _enum_or_default(enum_cls, raw: Any, default):
    try:
        return enum_cls(str(raw))
    except ValueError:
        return default


def build_ai_editor(
    prefs: Mapping[str, Any],
    *,
    create: Callable[[Mapping[str, Any], str], Any] | None = None,
):
    """Build the run-scoped editor for one batch.

    The provider factory stays unevaluated: nothing is constructed, health
    checked, or contacted until ``run_batch`` actually needs the provider.
    """
    from ai.editor import AIEditor, EditorOptions
    from ai.models import ProtectionStrategy, RunPolicy as Policy

    create = create or _create_provider
    model = str(prefs.get("model") or "").strip()
    options = EditorOptions(
        model_id=model,
        policy=_enum_or_default(Policy, prefs.get("policy"), Policy.PREFER_AI),
        protection_strategy=_enum_or_default(
            ProtectionStrategy, prefs.get("protection_strategy"),
            ProtectionStrategy.MASK),
        seed=prefs.get("seed", 0),
        timeout_seconds=float(prefs.get("timeout_seconds", 120)),
        request_overhead_tokens=int(prefs.get("request_overhead_tokens", 128)),
        safety_margin_tokens=int(prefs.get("context_safety_margin_tokens", 256)),
    )
    return AIEditor(lambda: create(prefs, model), options)


# ---------------------------------------------------------------------------
# Running average and ETA
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RunRate:
    """Observed pace of the current batch. ``None`` means 'not yet knowable'."""

    completed: int
    total: int
    seconds_per_file: float | None
    eta_seconds: float | None


def compute_rate(completed: int, total: int, elapsed_seconds: float) -> RunRate:
    """A plain running average over the chapters finished so far."""
    if completed <= 0 or elapsed_seconds <= 0:
        return RunRate(completed, total, None, None)
    per_file = elapsed_seconds / completed
    remaining = total - completed
    eta = per_file * remaining if remaining > 0 else None
    return RunRate(completed, total, per_file, eta)


def format_duration(seconds: float) -> str:
    """Compact human duration: ``9s`` / ``1m 36s`` / ``1h 02m``."""
    total = int(round(max(0.0, seconds)))
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m {total % 60:02d}s"
    return f"{total // 3600}h {(total % 3600) // 60:02d}m"


def format_rate(rate: RunRate) -> str:
    """One short readout, or '' while the pace is still unknown."""
    if rate.seconds_per_file is None:
        return ""
    text = f"average {rate.seconds_per_file:.1f} s/chapter"
    if rate.eta_seconds is not None:
        text += f" — about {format_duration(rate.eta_seconds)} left"
    return text
