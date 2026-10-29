"""Lazy provider construction without importing optional SDKs.

This is also **the single call site of the Plan 2b Phase 7a spend guard**. Turning a
provider *name* into a provider *object* happens here and only here, so a cloud adapter —
the only thing that can send a chapter to a paid-capable service — cannot come into
existence without the guard clearing it first. See ``ai.spend_guard``.

Two details of the placement are load-bearing:

* The guard runs on the **name**, before ``_BUILDERS`` is consulted, so a builder
  registered under a cloud provider's name cannot slip past it either.
* It runs **before the adapter is constructed**, so a refused run never produces an
  object that could be asked to complete anything.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Mapping

from . import spend_guard
from .cloud import is_cloud_provider
from .errors import ProviderUnavailable
from .provider import AIProvider

ProviderBuilder = Callable[..., AIProvider]
_BUILDERS: dict[str, ProviderBuilder] = {}
_MODULES = {
    "ollama": ("ai.providers.ollama", "OllamaProvider"),
    "gemini": ("ai.providers.gemini", "GeminiProvider"),
    "groq": ("ai.providers.groq", "GroqProvider"),
}


def register_provider(name: str, builder: ProviderBuilder) -> None:
    _BUILDERS[name.strip().lower()] = builder


def create_provider(
    name: str, *, guard_context: Mapping[str, Any] | None = None, **kwargs
) -> AIProvider:
    """Build one provider. For a cloud provider, the spend guard must clear it first.

    ``guard_context`` carries what the guard reads (the resolved ``[ai]`` table, the
    chosen model ID, the key locations, the settings file). It is required for a cloud
    provider and ignored for a local one. Omitting it is a **refusal**, not a pass: a
    caller that has not supplied what the guard needs has not shown that the run stays
    free, and the guard fails closed on exactly that.
    """
    key = name.strip().lower()
    if is_cloud_provider(key):
        spend_guard.ensure_free_tier_run_allowed(key, guard_context)
    if key in _BUILDERS:
        return _BUILDERS[key](**kwargs)
    if key not in _MODULES:
        raise ProviderUnavailable(f"Unknown provider: {name}", retryable=False)
    module_name, class_name = _MODULES[key]
    try:
        module = import_module(module_name)
        builder = getattr(module, class_name)
    except (ImportError, AttributeError) as exc:
        raise ProviderUnavailable(
            f"Provider '{key}' is not installed in this build.", retryable=False
        ) from exc
    return builder(**kwargs)
