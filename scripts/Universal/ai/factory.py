"""Lazy provider construction without importing optional SDKs."""

from __future__ import annotations

from importlib import import_module
from typing import Callable

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


def create_provider(name: str, **kwargs) -> AIProvider:
    key = name.strip().lower()
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
