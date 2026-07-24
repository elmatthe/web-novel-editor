"""Local-only Ollama adapter.

The official SDK is imported only when this provider is constructed for use.  No
module import, health check, or completion ever pulls or installs a model.
"""

from __future__ import annotations

import importlib
import json
import threading
import time
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable
from urllib.parse import urlsplit

from ..chunking import estimate_tokens
from ..errors import (
    ContextTooLong,
    InvalidResponse,
    ModelUnavailable,
    ProviderUnavailable,
    TransientNetworkError,
)
from ..models import (
    CompletionRequest,
    CompletionResult,
    ProviderCapabilities,
    ProviderStatus,
)

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
DEFAULT_KEEP_ALIVE = "30m"
DEFAULT_CONTEXT_LIMIT = 32768
DEFAULT_MAX_OUTPUT_TOKENS = 4096
_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class RequestBudget:
    """Inspectable conservative sizing for one serialized chat request."""

    input_tokens: int
    output_tokens: int
    num_ctx: int


def _load_sdk() -> ModuleType:
    return importlib.import_module("ollama")


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _safe_error_kind(exc: BaseException) -> str:
    """Return bounded diagnostic type only; provider payload text is never exposed."""

    return type(exc).__name__[:80]


class OllamaProvider:
    """Production adapter for one exact local model tag and one request at a time."""

    def __init__(
        self,
        *,
        model_id: str,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout_seconds: float = 120.0,
        keep_alive: str = DEFAULT_KEEP_ALIVE,
        context_limit: int = DEFAULT_CONTEXT_LIMIT,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        request_overhead_tokens: int = 128,
        context_safety_margin_tokens: int = 256,
        output_margin_tokens: int = 64,
        client: Any | None = None,
        sdk_loader: Callable[[], ModuleType] = _load_sdk,
    ):
        self.model_id = model_id
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.keep_alive = keep_alive
        self.context_limit = context_limit
        self.max_output_tokens = max_output_tokens
        self.request_overhead_tokens = request_overhead_tokens
        self.context_safety_margin_tokens = context_safety_margin_tokens
        self.output_margin_tokens = output_margin_tokens
        self._client = client
        self._sdk_loader = sdk_loader
        self._sdk: ModuleType | None = None
        self._lock = threading.Lock()
        self._configuration_error = self._validate_configuration()

    def _validate_configuration(self) -> str | None:
        try:
            parsed = urlsplit(self.endpoint)
            port = parsed.port
        except (TypeError, ValueError):
            return "endpoint"
        if (
            parsed.scheme != "http"
            or (parsed.hostname or "").lower() not in _LOCAL_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
            or port is None
        ):
            return "endpoint"
        if not self.model_id or ":" not in self.model_id:
            return "model_tag"
        if (
            self.timeout_seconds <= 0
            or self.context_limit <= 0
            or self.max_output_tokens <= 0
            or self.request_overhead_tokens < 0
            or self.context_safety_margin_tokens < 0
            or self.output_margin_tokens < 0
            or not isinstance(self.keep_alive, str)
            or not self.keep_alive.strip()
        ):
            return "budget"
        return None

    def _require_configuration(self) -> None:
        if self._configuration_error is not None:
            raise ProviderUnavailable(
                f"Invalid Ollama configuration ({self._configuration_error}).",
                retryable=False,
            )

    def _get_client(self) -> Any:
        self._require_configuration()
        if self._client is not None:
            return self._client
        try:
            self._sdk = self._sdk_loader()
            self._client = self._sdk.Client(
                host=self.endpoint,
                timeout=self.timeout_seconds,
            )
        except ImportError as exc:
            raise ProviderUnavailable(
                "Ollama Python package is unavailable.", retryable=False
            ) from exc
        except Exception as exc:
            raise ProviderUnavailable(
                f"Ollama client initialization failed ({_safe_error_kind(exc)}).",
                retryable=False,
            ) from exc
        return self._client

    def capabilities(self) -> ProviderCapabilities:
        models = () if self._configuration_error else (self.model_id,)
        return ProviderCapabilities(
            "ollama",
            True,
            models,
            self.context_limit,
            self.max_output_tokens,
            supports_streaming=False,
            exposes_rate_limits=False,
            privacy_disclosure_id="local_ollama",
        )

    def health_check(self) -> ProviderStatus:
        if self._configuration_error is not None:
            return ProviderStatus.INVALID_CONFIGURATION
        try:
            models = self.list_models()
        except ProviderUnavailable as exc:
            if "package" in str(exc).lower():
                return ProviderStatus.PACKAGE_UNAVAILABLE
            return ProviderStatus.SERVICE_DOWN
        except TransientNetworkError:
            return ProviderStatus.TIMEOUT
        except Exception:
            return ProviderStatus.PROVIDER_ERROR
        return (
            ProviderStatus.OK
            if self.model_id in models
            else ProviderStatus.MODEL_MISSING
        )

    def list_models(self) -> list[str]:
        try:
            response = self._get_client().list()
            models = _field(response, "models", ()) or ()
            result: list[str] = []
            for model in models:
                name = _field(model, "model") or _field(model, "name")
                if isinstance(name, str) and name:
                    result.append(name)
            return result
        except ProviderUnavailable:
            raise
        except Exception as exc:
            self._raise_transport_error(exc)
        raise AssertionError("unreachable")

    def request_budget(self, request: CompletionRequest) -> RequestBudget:
        """Compute context/output options from all serialized request content."""

        serialized_input = json.dumps(
            {
                "messages": [
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.text},
                ]
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        input_tokens = estimate_tokens(serialized_input) + self.request_overhead_tokens
        expected_output = estimate_tokens(request.text) + self.output_margin_tokens
        output_tokens = min(
            request.max_output_tokens,
            self.max_output_tokens,
            max(1, expected_output),
        )
        num_ctx = input_tokens + output_tokens + self.context_safety_margin_tokens
        if num_ctx > self.context_limit:
            raise ContextTooLong(
                "Serialized Ollama request exceeds the configured context limit.",
                retryable=False,
            )
        return RequestBudget(input_tokens, output_tokens, num_ctx)

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self._require_configuration()
        if request.model_id != self.model_id:
            raise ModelUnavailable(
                "Requested model does not match the configured exact Ollama model tag.",
                retryable=False,
            )
        budget = self.request_budget(request)
        started = time.monotonic()
        try:
            with self._lock:
                response = self._get_client().chat(
                    model=self.model_id,
                    messages=[
                        {"role": "system", "content": request.system_prompt},
                        {"role": "user", "content": request.text},
                    ],
                    stream=False,
                    think=False,
                    keep_alive=self.keep_alive,
                    options={
                        "temperature": request.temperature,
                        "seed": request.seed,
                        "num_ctx": budget.num_ctx,
                        "num_predict": budget.output_tokens,
                    },
                )
        except (ContextTooLong, ModelUnavailable, ProviderUnavailable):
            raise
        except Exception as exc:
            self._raise_transport_error(exc)

        message = _field(response, "message", {}) or {}
        content = _field(message, "content", "")
        thinking = _field(message, "thinking", "")
        done = _field(response, "done", False)
        finish_reason = str(_field(response, "done_reason", "") or "")
        if thinking or (isinstance(content, str) and "<think" in content.lower()):
            raise InvalidResponse(
                "Ollama returned reasoning output despite thinking being disabled.",
                retryable=True,
            )
        if not isinstance(content, str) or not content:
            raise InvalidResponse("Ollama returned no candidate text.", retryable=True)
        truncated = done is not True or finish_reason.lower() != "stop"
        if truncated:
            raise InvalidResponse(
                "Ollama returned an incomplete or truncated response.", retryable=True
            )
        duration_ns = _field(response, "total_duration")
        duration = (
            float(duration_ns) / 1_000_000_000
            if isinstance(duration_ns, (int, float)) and duration_ns >= 0
            else time.monotonic() - started
        )
        return CompletionResult(
            content,
            str(_field(response, "model", self.model_id) or self.model_id),
            duration,
            finish_reason,
            False,
            input_tokens=_field(response, "prompt_eval_count"),
            output_tokens=_field(response, "eval_count"),
            execution_backend=None,
        )

    def _raise_transport_error(self, exc: BaseException) -> None:
        status_code = getattr(exc, "status_code", None)
        if status_code == 404:
            raise ModelUnavailable(
                "Configured Ollama model is unavailable.", retryable=False
            ) from exc
        kind = _safe_error_kind(exc)
        if isinstance(exc, TimeoutError) or "timeout" in kind.lower():
            raise TransientNetworkError(
                f"Ollama request timed out ({kind}).", retryable=True
            ) from exc
        raise ProviderUnavailable(
            f"Ollama service request failed ({kind}).", retryable=True
        ) from exc
