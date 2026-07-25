"""Google Gemini adapter (Plan 2b Phase 2).

Implements 2a's four-method ``AIProvider`` protocol with **no change to the base
contract**: ``provider.py``, ``models.py`` and ``errors.py`` are untouched, and every
Gemini-specific concept is normalised into the shared ``CompletionResult`` and the
shared error taxonomy before it leaves this module.

**The SDK is imported here and nowhere else**, and only when a client is actually
built — never at package import time, never by ``factory.py``, never by ``ai``'s
``__init__``. Importing this module on a machine with no ``google-genai`` installed is
safe and free; the missing package surfaces as ``PACKAGE_UNAVAILABLE``.

Three rules this adapter exists to enforce:

1. **Only an exact, reviewed, approved model may be called.** The record comes from
   ``ai.approved_models`` (which owns every refusal rule) and is resolved once, at
   construction. There is no substitution path of any kind in this file — no "newest",
   no "first available", no fallback model. A retired model makes the provider
   unavailable and names no replacement.
2. **Max output is taken from the reviewed record**, not from a constant in this file.
   A caller may pass a *lower* explicit cap; it can never raise the reviewed limit.
3. **An unrecognised finish reason fails closed.** Gemini can stop for reasons this
   code has never seen, and a future SDK will add more. Anything not on the known-good
   list is refused as a permanent failure and the candidate text is discarded — it is
   never returned as a successful edit. That is the whole reason ``_FINISH_*`` below
   are compared as plain strings rather than against the SDK's enum: an enum this
   module does not import cannot grow a member this module silently accepts.

Every message this adapter raises or logs passes through the Phase 1 redactor first.
Google routinely puts the API key into the request URL, and that URL routinely lands in
the exception text, so redaction here is not defensive decoration — it is the only
thing standing between a 403 and a key in the user's log.
"""

from __future__ import annotations

import importlib
import logging
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable, Mapping, Sequence

from .. import redaction
from ..approved_models import (
    ApprovedModel,
    ensure_model_approved,
    ensure_model_available,
    selectable_models,
)
from ..chunking import estimate_tokens
from ..errors import (
    AuthenticationError,
    ContextTooLong,
    DailyQuotaExhausted,
    InvalidResponse,
    ModelUnavailable,
    ProviderUnavailable,
    RateLimited,
    TransientNetworkError,
)
from ..models import (
    CompletionRequest,
    CompletionResult,
    ProviderCapabilities,
    ProviderStatus,
)
from ..secrets import resolve_api_key

PROVIDER_NAME = "gemini"
PRIVACY_DISCLOSURE_ID = "cloud_gemini"

# The SDK prefixes every model resource with this. `models/gemini-3.5-flash` and
# `gemini-3.5-flash` are the same model; the approved records use the bare form.
_RESOURCE_PREFIX = "models/"

# Google documents no rate-limit response headers — no `retry-after`, no
# `x-ratelimit-*` (re-verified against ai.google.dev/gemini-api/docs/rate-limits on
# 2026-07-24). Phase 4 must therefore drive this provider from a conservative
# configured floor, which is exactly what reporting False here tells it to do.
EXPOSES_RATE_LIMITS = False

DEFAULT_TIMEOUT_SECONDS = 120.0
REQUEST_OVERHEAD_TOKENS = 128
CONTEXT_SAFETY_MARGIN_TOKENS = 256

# --- finish reasons -------------------------------------------------------
# Compared as strings on purpose. See the module docstring: an unknown value must
# fail closed, and it cannot do that if it is matched against an imported enum.
_FINISH_OK = "STOP"
_FINISH_TRUNCATED = "MAX_TOKENS"
# Permanent content refusals. Retrying the same chapter text produces the same
# refusal, so these are non-retryable and go straight to script-only fallback.
_FINISH_BLOCKED = frozenset(
    {
        "SAFETY",
        "RECITATION",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
        "LANGUAGE",
        "IMAGE_SAFETY",
        "UNEXPECTED_TOOL_CALL",
        "MALFORMED_FUNCTION_CALL",
    }
)
_FINISH_UNSPECIFIED = frozenset({"", "FINISH_REASON_UNSPECIFIED"})

_MAX_ERROR_CHARS = 300

logger = logging.getLogger(__name__)


def _load_sdk() -> ModuleType:
    """Import the SDK. The only ``google.genai`` import in the project."""
    return importlib.import_module("google.genai")


def _install_log_redaction() -> None:
    if not any(isinstance(f, redaction.RedactingFilter) for f in logger.filters):
        logger.addFilter(redaction.RedactingFilter())


def _field(value: Any, name: str, default: Any = None) -> Any:
    """Read an attribute or a mapping key — the SDK returns pydantic models, and
    replay/test transports return plain dicts."""
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _safe_message(exc: BaseException) -> str:
    """Bounded, redacted error text safe to raise, log, and show the user."""
    text = redaction.redact_exception(exc)
    if len(text) > _MAX_ERROR_CHARS:
        text = text[:_MAX_ERROR_CHARS] + "…"
    return text


def _model_name(entry: Any) -> str:
    name = _field(entry, "name") or _field(entry, "id") or ""
    name = str(name).strip()
    if name.startswith(_RESOURCE_PREFIX):
        name = name[len(_RESOURCE_PREFIX):]
    return name


class GeminiProvider:
    """Cloud adapter for one exact, reviewed Gemini model."""

    def __init__(
        self,
        *,
        model_id: str,
        approved_models: Iterable[ApprovedModel] = (),
        strict_free_only: bool = True,
        api_key: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_output_tokens: int | None = None,
        request_overhead_tokens: int = REQUEST_OVERHEAD_TOKENS,
        context_safety_margin_tokens: int = CONTEXT_SAFETY_MARGIN_TOKENS,
        client: Any | None = None,
        sdk_loader: Callable[[], ModuleType] = _load_sdk,
        environ: Mapping[str, str] | None = None,
        secrets_file: Path | None = None,
        dotenv_path: Path | None = None,
    ):
        _install_log_redaction()
        self.model_id = str(model_id or "").strip()
        self.timeout_seconds = timeout_seconds
        self.request_overhead_tokens = request_overhead_tokens
        self.context_safety_margin_tokens = context_safety_margin_tokens
        self._approved_models = tuple(approved_models)
        self._strict_free_only = strict_free_only
        self._client = client
        self._sdk_loader = sdk_loader
        self._environ = environ
        self._secrets_file = secrets_file
        self._dotenv_path = dotenv_path
        self._lock = threading.Lock()

        # A key handed to us directly never passed through `ai.secrets`, so register
        # it with the redactor here rather than trusting it was done elsewhere.
        self._api_key = api_key.strip() if isinstance(api_key, str) else None
        if self._api_key:
            redaction.register_secret(self._api_key)

        # Resolve the reviewed record once. A refusal is *stored*, not raised:
        # `health_check()` must be able to report it, and the GUI must be able to
        # construct a provider in order to display why it cannot be used.
        self._record: ApprovedModel | None = None
        self._approval_error: ModelUnavailable | None = None
        try:
            self._record = ensure_model_approved(
                self.model_id,
                provider=PROVIDER_NAME,
                models=self._approved_models,
                strict_free_only=strict_free_only,
            )
        except ModelUnavailable as exc:
            self._approval_error = exc

        # Explicit max output comes from the reviewed record. An explicit argument may
        # lower it (a config cap) but must never raise it above what was reviewed.
        record_output = self._record.output_limit if self._record else 0
        if max_output_tokens is not None and record_output:
            record_output = min(int(max_output_tokens), record_output)
        self.max_output_tokens = record_output
        self.context_limit = self._record.context_limit if self._record else 0

        # Retirement is checked against the live model list once per provider, then
        # remembered — a run must not pay for a list call per chapter.
        self._availability_checked = False
        self._retirement_error: ModelUnavailable | None = None

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"GeminiProvider(model_id={self.model_id!r})"

    @property
    def approved_record(self) -> ApprovedModel | None:
        return self._record

    # -- guards ------------------------------------------------------------
    def _require_approved(self) -> ApprovedModel:
        if self._approval_error is not None:
            raise self._approval_error
        if self._record is None:  # pragma: no cover - defensive
            raise ModelUnavailable(
                "No approved Gemini model is configured.", retryable=False
            )
        return self._record

    def _require_key(self) -> str:
        if self._api_key:
            return self._api_key
        value, _source = resolve_api_key(
            PROVIDER_NAME,
            environ=self._environ,
            secrets_file=self._secrets_file,
            dotenv_path=self._dotenv_path,
        )
        if not value:
            raise AuthenticationError(
                "No API key is available for Gemini. Set the GEMINI_API_KEY "
                "environment variable, or save a key in the app's AI settings.",
                retryable=False,
            )
        self._api_key = value
        return value

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        key = self._require_key()
        try:
            sdk = self._sdk_loader()
            self._client = sdk.Client(
                api_key=key,
                http_options={"timeout": int(max(1.0, self.timeout_seconds) * 1000)},
            )
        except ImportError as exc:
            raise ProviderUnavailable(
                "The google-genai package is unavailable in this build.",
                retryable=False,
            ) from exc
        except Exception as exc:
            raise ProviderUnavailable(
                f"Gemini client initialization failed ({_safe_message(exc)}).",
                retryable=False,
            ) from exc
        return self._client

    def _check_retirement(self, record: ApprovedModel) -> None:
        """Confirm once that the approved model is still offered.

        A transport failure here is *not* evidence of retirement, so it is swallowed
        and the check is left to run again later; the real request that follows will
        surface the transport problem honestly.
        """
        if self._availability_checked:
            if self._retirement_error is not None:
                raise self._retirement_error
            return
        try:
            discovered = self.list_models()
        except (ProviderUnavailable, AuthenticationError, TransientNetworkError,
                RateLimited, DailyQuotaExhausted):
            return
        self._availability_checked = True
        try:
            ensure_model_available(record, discovered)
        except ModelUnavailable as exc:
            self._retirement_error = exc
            raise

    # -- contract ----------------------------------------------------------
    def capabilities(self) -> ProviderCapabilities:
        models = (self._record.id,) if self._record else ()
        return ProviderCapabilities(
            PROVIDER_NAME,
            False,
            models,
            self.context_limit,
            self.max_output_tokens,
            supports_streaming=False,
            exposes_rate_limits=EXPOSES_RATE_LIMITS,
            privacy_disclosure_id=PRIVACY_DISCLOSURE_ID,
        )

    def health_check(self) -> ProviderStatus:
        """Report the provider's state. Never raises — the GUI depends on that."""
        if self._approval_error is not None:
            return ProviderStatus.MODEL_MISSING
        record = self._record
        if record is None:  # pragma: no cover - defensive
            return ProviderStatus.MODEL_MISSING
        try:
            self._require_key()
        except AuthenticationError:
            return ProviderStatus.AUTH_MISSING

        try:
            discovered = self.list_models()
        except AuthenticationError:
            return ProviderStatus.AUTH_MISSING
        except (RateLimited, DailyQuotaExhausted):
            return ProviderStatus.QUOTA_EXHAUSTED
        except TransientNetworkError as exc:
            return (
                ProviderStatus.TIMEOUT
                if "timed out" in str(exc).lower()
                else ProviderStatus.SERVICE_DOWN
            )
        except ProviderUnavailable as exc:
            if "package" in str(exc).lower():
                return ProviderStatus.PACKAGE_UNAVAILABLE
            return ProviderStatus.SERVICE_DOWN
        except ModelUnavailable:
            return ProviderStatus.MODEL_MISSING
        except Exception:
            return ProviderStatus.PROVIDER_ERROR

        self._availability_checked = True
        try:
            # An *empty* list means the endpoint could not be read, which is
            # "unverifiable" and not "retired" — ensure_model_available owns that
            # distinction and returns quietly.
            ensure_model_available(record, discovered)
        except ModelUnavailable as exc:
            self._retirement_error = exc
            return ProviderStatus.MODEL_MISSING
        return ProviderStatus.OK

    def list_models(self) -> list[str]:
        """Every model the account can see, as bare IDs. Not a permission to call one."""
        try:
            listing = self._get_client().models.list()
            return [name for name in (_model_name(m) for m in listing) if name]
        except (ProviderUnavailable, AuthenticationError):
            raise
        except Exception as exc:
            self._raise_transport_error(exc)
        raise AssertionError("unreachable")  # pragma: no cover

    def approved_model_choices(self, discovered: Sequence[str] | None = None) -> tuple[str, ...]:
        """Live models that are *also* reviewed and selectable, in the live order.

        The drop's rule: other discovered models may be offered as advanced choices
        only if they are in the approved set. Nothing here selects a model — it only
        narrows what a human may pick from.
        """
        if discovered is None:
            discovered = self.list_models()
        allowed = {
            m.id
            for m in selectable_models(
                self._approved_models,
                PROVIDER_NAME,
                strict_free_only=self._strict_free_only,
            )
        }
        return tuple(name for name in discovered if name in allowed)

    def complete(self, request: CompletionRequest) -> CompletionResult:
        record = self._require_approved()
        if request.model_id != self.model_id:
            raise ModelUnavailable(
                "Requested model does not match the configured exact Gemini model.",
                retryable=False,
            )
        self._require_key()
        self._check_retirement(record)

        output_tokens = self._output_budget(request)
        self._check_context(request, output_tokens)
        config = self._request_config(request, output_tokens)

        logger.debug(
            "Gemini request %s: model=%s max_output=%s",
            request.request_id,
            self.model_id,
            output_tokens,
        )
        started = time.monotonic()
        try:
            with self._lock:
                response = self._get_client().models.generate_content(
                    model=self.model_id,
                    contents=request.text,
                    config=config,
                )
        except (ContextTooLong, ModelUnavailable, ProviderUnavailable,
                AuthenticationError):
            raise
        except Exception as exc:
            self._raise_transport_error(exc)

        return self._map_response(response, time.monotonic() - started)

    # -- request construction ---------------------------------------------
    def _output_budget(self, request: CompletionRequest) -> int:
        budget = min(int(request.max_output_tokens), self.max_output_tokens)
        if budget <= 0:
            raise ContextTooLong(
                "No output token budget remains for this Gemini request.",
                retryable=False,
            )
        return budget

    def _check_context(self, request: CompletionRequest, output_tokens: int) -> None:
        """Refuse locally rather than paying for a request that cannot fit.

        The estimate is 2a's conservative provider-neutral one; it over-reserves, and
        it over-reserves in the fail-safe direction (DECISIONS #053).
        """
        input_tokens = (
            estimate_tokens(request.system_prompt)
            + estimate_tokens(request.text)
            + self.request_overhead_tokens
        )
        needed = input_tokens + output_tokens + self.context_safety_margin_tokens
        if needed > self.context_limit:
            raise ContextTooLong(
                f"This request needs about {needed} tokens, which exceeds the "
                f"{self.context_limit}-token context limit reviewed for "
                f"{self.model_id}.",
                retryable=False,
            )

    def _thinking_config(self) -> dict[str, Any]:
        """Turn model "thinking" off, as every adapter in this project does.

        Thinking tokens are drawn from the output budget, so leaving it on risks a
        MAX_TOKENS finish with no visible text at all — a truncation the gate would
        reject anyway, paid for in full. The 3.x series takes ``thinking_level`` and
        the 2.5 series takes ``thinking_budget=0``; sending the wrong one is a 400.
        """
        if self.model_id.startswith("gemini-3"):
            return {"include_thoughts": False, "thinking_level": "MINIMAL"}
        return {"include_thoughts": False, "thinking_budget": 0}

    def _request_config(
        self, request: CompletionRequest, output_tokens: int
    ) -> dict[str, Any]:
        """A plain dict, not a ``types.GenerateContentConfig``.

        The SDK coerces it, and building it as data keeps the SDK import confined to
        client construction — nothing here needs ``google.genai.types`` to exist.
        """
        config: dict[str, Any] = {
            "system_instruction": request.system_prompt,
            "max_output_tokens": output_tokens,
            "temperature": request.temperature,
            "candidate_count": 1,
            "thinking_config": self._thinking_config(),
        }
        if request.seed is not None:
            config["seed"] = request.seed
        return config

    # -- response mapping --------------------------------------------------
    def _map_response(self, response: Any, elapsed: float) -> CompletionResult:
        blocked = _field(_field(response, "prompt_feedback"), "block_reason")
        if blocked:
            raise InvalidResponse(
                f"Gemini blocked the prompt before generating anything "
                f"(block reason: {blocked}).",
                retryable=False,
            )

        candidates = _field(response, "candidates") or ()
        if not candidates:
            raise InvalidResponse(
                "Gemini returned no candidate at all.", retryable=True
            )
        finish_reason = str(_field(candidates[0], "finish_reason") or "")
        # The SDK's enum is `CaseInSensitiveEnum`; str() of a member can render as
        # `FinishReason.STOP`. Normalise to the bare name before comparing.
        finish_reason = finish_reason.rsplit(".", 1)[-1].strip().upper()

        if finish_reason == _FINISH_TRUNCATED:
            raise InvalidResponse(
                "Gemini truncated the response at the output token limit "
                "(finish reason MAX_TOKENS).",
                retryable=True,
            )
        if finish_reason in _FINISH_BLOCKED:
            raise InvalidResponse(
                f"Gemini refused to return the edited text (finish reason "
                f"{finish_reason}). Retrying the same chapter would be refused again.",
                retryable=False,
            )
        if finish_reason in _FINISH_UNSPECIFIED:
            raise InvalidResponse(
                "Gemini gave no finish reason, so the response cannot be treated as "
                "complete. The chapter falls back to script-only editing.",
                retryable=False,
            )
        if finish_reason != _FINISH_OK:
            # Fail closed. This is the important branch: a value this build has never
            # seen is refused, and the candidate text is discarded rather than
            # returned as a successful edit.
            raise InvalidResponse(
                f"Gemini returned an unrecognised finish reason "
                f"({finish_reason}), so the response is refused. The chapter falls "
                f"back to script-only editing.",
                retryable=False,
            )

        text = _field(response, "text")
        if not isinstance(text, str) or not text:
            raise InvalidResponse("Gemini returned no candidate text.", retryable=True)

        usage = _field(response, "usage_metadata")
        model_used = str(_field(response, "model_version") or self.model_id)
        request_id = _field(response, "response_id")
        return CompletionResult(
            text,
            model_used,
            elapsed,
            finish_reason,
            False,
            provider_request_id=str(request_id) if request_id else None,
            input_tokens=_field(usage, "prompt_token_count"),
            output_tokens=_field(usage, "candidates_token_count"),
            execution_backend=None,
        )

    # -- error mapping -----------------------------------------------------
    def _raise_transport_error(self, exc: BaseException) -> None:
        """Normalise an SDK/transport failure into 2a's taxonomy. Always raises.

        Classification is by HTTP status where the SDK provides one (``APIError.code``)
        and by exception name otherwise, so no ``google.genai`` import is needed to
        interpret a ``google.genai`` error.
        """
        message = _safe_message(exc)
        lowered = message.lower()
        squashed = lowered.replace(" ", "").replace("_", "")
        code = getattr(exc, "code", None)
        code = code if isinstance(code, int) else None
        kind = type(exc).__name__

        if code == 400 and any(
            marker in squashed
            for marker in ("tokencount", "exceedsthemaximum", "contextlength",
                           "inputtoolong", "inputtoken")
        ):
            raise ContextTooLong(
                f"Gemini rejected the request as too long for the model's context "
                f"({message}).",
                retryable=False,
            ) from exc
        if code in (401, 403):
            raise AuthenticationError(
                f"Gemini rejected the API key ({message}). Check the key in the "
                f"provider's console and in the app's AI settings.",
                retryable=False,
            ) from exc
        if code == 404:
            raise ModelUnavailable(
                f"Gemini does not offer '{self.model_id}' to this key ({message}). "
                f"No replacement will be selected automatically.",
                retryable=False,
            ) from exc
        if code == 429:
            # Never infer daily exhaustion from every 429 (drop, rate-limiting
            # section). Only a quota Google itself names as per-day is treated as
            # the checkpoint-and-stop case Phase 5 handles.
            if "perday" in squashed or "daily" in squashed:
                raise DailyQuotaExhausted(
                    f"Gemini's free daily quota for {self.model_id} is used up "
                    f"({message}). Requests-per-day quotas reset at midnight "
                    f"Pacific time.",
                    retryable=False,
                ) from exc
            raise RateLimited(
                f"Gemini is rate limiting this project ({message}).", retryable=True
            ) from exc
        if code is not None and 500 <= code < 600:
            raise ProviderUnavailable(
                f"Gemini's service returned an error ({message}).", retryable=True
            ) from exc
        if code == 400:
            raise ProviderUnavailable(
                f"Gemini rejected the request ({message}).", retryable=False
            ) from exc

        if isinstance(exc, TimeoutError) or "timeout" in kind.lower() or "timed out" in lowered:
            raise TransientNetworkError(
                f"Gemini request timed out ({kind}).", retryable=True
            ) from exc
        if any(
            marker in kind.lower()
            for marker in ("connect", "network", "socket", "ssl", "protocol", "read")
        ) or "connection" in lowered:
            raise TransientNetworkError(
                f"Could not reach Gemini ({kind}).", retryable=True
            ) from exc
        raise ProviderUnavailable(
            f"Gemini request failed ({kind}).", retryable=True
        ) from exc
