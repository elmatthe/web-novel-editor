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
    ProviderCapabilities,
    ProviderStatus,
)
from .provider import AIProvider

__all__ = [
    "AIProvider",
    "AuthenticationError",
    "CompletionRequest",
    "CompletionResult",
    "ContextTooLong",
    "DailyQuotaExhausted",
    "InvalidResponse",
    "ModelUnavailable",
    "ProviderCapabilities",
    "ProviderStatus",
    "ProviderUnavailable",
    "RateLimited",
    "RequestCancelled",
    "TransientNetworkError",
]
