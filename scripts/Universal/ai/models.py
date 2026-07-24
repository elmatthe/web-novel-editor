"""Stable provider-neutral request, response, and capability models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProviderStatus(str, Enum):
    OK = "ok"
    PACKAGE_UNAVAILABLE = "package_unavailable"
    SERVICE_DOWN = "service_down"
    MODEL_MISSING = "model_missing"
    INVALID_CONFIGURATION = "invalid_configuration"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"
    AUTH_MISSING = "auth_missing"
    QUOTA_EXHAUSTED = "quota_exhausted"


@dataclass(frozen=True)
class ProviderCapabilities:
    provider_name: str
    is_local: bool
    model_ids: tuple[str, ...]
    context_limit: int
    max_output_tokens: int
    supports_streaming: bool = False
    exposes_rate_limits: bool = False
    privacy_disclosure_id: str = ""


@dataclass(frozen=True)
class CompletionRequest:
    text: str
    system_prompt: str
    prompt_version: str
    model_id: str
    temperature: float
    seed: int | None
    timeout_seconds: float
    max_output_tokens: int
    request_id: str


@dataclass(frozen=True)
class CompletionResult:
    text: str
    model_id: str
    duration_seconds: float
    finish_reason: str
    truncated: bool
    provider_request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    execution_backend: str | None = None


class RunPolicy(str, Enum):
    SCRIPT_ONLY = "script_only"
    PREFER_AI = "prefer_ai"
    AI_REQUIRED = "ai_required"


class ProtectionStrategy(str, Enum):
    MASK = "mask"
    VERIFY = "verify"


class ProviderRunState(str, Enum):
    UNINITIALIZED = "uninitialized"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AIOutcome:
    text: str
    status: str
    used_ai: bool
    fallback_used: bool
    rejection_reasons: tuple[str, ...] = ()
    chunk_count: int = 0
    retry_count: int = 0
    provenance: tuple[dict, ...] = ()
