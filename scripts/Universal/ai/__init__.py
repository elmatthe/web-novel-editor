"""Provider-neutral AI editing contracts.

Importing this package is deliberately side-effect free and never imports an SDK.
"""

from .errors import (
    AuthenticationError,
    ContextTooLong,
    DailyQuotaExhausted,
    InvalidResponse,
    ModelUnavailable,
    ProviderUnavailable,
    RateLimited,
    RequestCancelled,
    TransientNetworkError,
)
from .models import (
    CompletionRequest,
    CompletionResult,
    AIOutcome,
    ProviderCapabilities,
    ProtectionStrategy,
    ProviderRunState,
    ProviderStatus,
    RunPolicy,
)
from .provider import AIProvider

__all__ = [
    "AIProvider",
    "AIOutcome",
    "AuthenticationError",
    "CompletionRequest",
    "CompletionResult",
    "ContextTooLong",
    "DailyQuotaExhausted",
    "InvalidResponse",
    "ModelUnavailable",
    "ProviderCapabilities",
    "ProtectionStrategy",
    "ProviderRunState",
    "ProviderStatus",
    "ProviderUnavailable",
    "RateLimited",
    "RequestCancelled",
    "RunPolicy",
    "TransientNetworkError",
]
