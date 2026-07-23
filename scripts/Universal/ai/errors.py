"""Typed provider error taxonomy shared by local and future cloud adapters."""

from __future__ import annotations


class AIProviderError(Exception):
    retryable = False

    def __init__(self, message: str = "", *, retryable: bool | None = None):
        super().__init__(message)
        if retryable is not None:
            self.retryable = retryable


class ProviderUnavailable(AIProviderError):
    retryable = True


class AuthenticationError(AIProviderError):
    retryable = False


class ModelUnavailable(AIProviderError):
    retryable = False


class ContextTooLong(AIProviderError):
    retryable = False


class RateLimited(AIProviderError):
    retryable = True


class DailyQuotaExhausted(AIProviderError):
    retryable = False


class TransientNetworkError(AIProviderError):
    retryable = True


class InvalidResponse(AIProviderError):
    retryable = True


class RequestCancelled(AIProviderError):
    retryable = False
