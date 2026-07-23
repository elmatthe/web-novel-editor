"""Provider protocol. Transport implementations belong in ``ai.providers``."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import CompletionRequest, CompletionResult, ProviderCapabilities, ProviderStatus


@runtime_checkable
class AIProvider(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...

    def health_check(self) -> ProviderStatus: ...

    def list_models(self) -> list[str]: ...

    def complete(self, request: CompletionRequest) -> CompletionResult: ...
