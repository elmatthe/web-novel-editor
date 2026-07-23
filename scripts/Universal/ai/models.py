"""Stable provider-neutral request, response, and capability models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProviderStatus(str, Enum):
    OK = "ok"
    SERVICE_DOWN = "service_down"
    MODEL_MISSING = "model_missing"
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
