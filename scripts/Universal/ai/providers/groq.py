"""Groq adapter (Plan 2b Phase 3).

Implements 2a's four-method ``AIProvider`` protocol with **no change to the base
contract**: ``provider.py``, ``models.py`` and ``errors.py`` are untouched, and every
Groq-specific concept is normalised into the shared ``CompletionResult`` and the shared
error taxonomy before it leaves this module.

**The SDK is imported here and nowhere else**, and only when a client is actually built
— never at package import time, never by ``factory.py``, never by ``ai``'s
``__init__``. Importing this module on a machine with no ``groq`` installed is safe and
free; the missing package surfaces as ``PACKAGE_UNAVAILABLE``.

This adapter deliberately mirrors the Gemini adapter's shape and its decisions —
refusals stored rather than raised at construction, max-output taken from the reviewed
record, finish reasons compared as plain strings, one lazy ``_load_sdk()`` import site.
**Where it diverges, it diverges because Groq genuinely differs:**

1. **Groq publishes its limits and returns rate-limit headers; Google does not.** That
   asymmetry is the whole point of this module. ``EXPOSES_RATE_LIMITS`` is ``True``,
   and every response — success *and* 429 — is scraped for ``retry-after`` and
   ``x-ratelimit-{limit,remaining,reset}-{requests,tokens}`` into a
   :class:`RateLimitSnapshot`. Phase 4's limiter can therefore run header-driven for
   Groq while running floored-and-conservative for Gemini.
2. **Limits and available models vary per model *and* per organization.** Groq's own
   docs say limits apply at the organization level and differ per model, and warn that
   there may be exceptions. So nothing here hardcodes a limit, and no figure observed
   for one organization is assumed to hold for another: the live headers are the only
   authority, the reviewed record supplies context/output sizes, and availability is
   checked against this key's own model list.
3. **Model IDs are passed through byte-for-byte.** Gemini strips a ``models/`` resource
   prefix; doing anything of the sort here would rewrite ``openai/gpt-oss-120b`` — a
   real, whole model ID that merely contains a slash — into one that does not exist.
4. **Finish reasons are lowercase** (``stop``, ``length``, ``tool_calls``), where
   Gemini's are uppercase. They are still compared as plain strings, never against the
   SDK's type: a literal this module does not import cannot grow a member this module
   silently accepts.
5. **The SDK's own retries are switched off.** The client retries twice by default.
   Silent retries would double-spend a free tier where tokens-per-day is the binding
   constraint, and would hide from Phase 4's limiter the very 429s it exists to see.
6. **Reasoning is held to its minimum on the gpt-oss models only.** They are reasoning
   models and reasoning tokens come out of the output budget — the same trap Gemini's
   "thinking" posed — but sending a reasoning parameter to a Llama model is a 400, so it
   is sent per model family, exactly as the Gemini adapter sends its thinking setting.
   The *value* is family-specific too: gpt-oss takes ``low|medium|high`` and cannot turn
   reasoning off at all. See ``_MIN_REASONING_EFFORT``.

Every message this adapter raises or logs passes through the Phase 1 redactor first.
"""

from __future__ import annotations

import importlib
import logging
import re
import threading
import time
from dataclasses import dataclass
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

PROVIDER_NAME = "groq"
PRIVACY_DISCLOSURE_ID = "cloud_groq"

# Groq documents `retry-after` plus the full `x-ratelimit-*` set and returns them on
# ordinary responses as well as on 429s (re-verified against
# console.groq.com/docs/rate-limits on 2026-07-25). Reporting True here is what tells
# Phase 4 it may drive this provider from live headers instead of a static floor.
EXPOSES_RATE_LIMITS = True

DEFAULT_TIMEOUT_SECONDS = 120.0
REQUEST_OVERHEAD_TOKENS = 128
CONTEXT_SAFETY_MARGIN_TOKENS = 256

# 2a's editor owns per-chunk retries and Phase 4 owns rate-limit waits. The SDK must
# not run a retry loop of its own underneath either of them.
SDK_MAX_RETRIES = 0

# Model families that bill reasoning tokens against the output budget.
_REASONING_MODEL_PREFIXES = ("openai/gpt-oss",)

# The lowest reasoning setting the gpt-oss family accepts. Groq's own reference
# (console.groq.com/docs/reasoning and the chat-completions parameter table, re-checked
# 2026-07-27) allows `low | medium | high` for `openai/gpt-oss-*` and reserves
# `none | default` for the qwen3 family. Sending `"none"` here — which this adapter did
# until 2026-07-27 — is a hard 400 on EVERY request, so both gpt-oss records were
# approved, selectable and completely uncallable. `"low"` is the closest thing the family
# offers to the intent behind the original `"none"`: the fewest reasoning tokens taken
# out of the output budget. Reasoning text itself never reaches the gate — it arrives in
# `message.reasoning`, and `_map_response` reads `message.content`.
_MIN_REASONING_EFFORT = "low"

# --- finish reasons -------------------------------------------------------
# Compared as strings on purpose. See the module docstring: an unknown value must fail
# closed, and it cannot do that if it is matched against an imported literal type.
_FINISH_OK = "stop"
_FINISH_TRUNCATED = "length"
# The prompt layer sends no tools, so a tool-call finish is a malfunction rather than a
# transient fault: the same chapter would produce it again.
_FINISH_TOOL_CALL = frozenset({"tool_calls", "function_call"})
_FINISH_UNSPECIFIED = frozenset({"", "none", "null", "unspecified"})

# --- rate-limit headers ---------------------------------------------------
# Groq's own documented meanings, which are NOT symmetrical: the request counters are
# per *day* and the token counters are per *minute*. Reading them the other way round
# would make Phase 4 wait a minute for a quota that resets tomorrow.
HEADER_RETRY_AFTER = "retry-after"
HEADER_LIMIT_REQUESTS = "x-ratelimit-limit-requests"        # RPD
HEADER_REMAINING_REQUESTS = "x-ratelimit-remaining-requests"  # RPD
HEADER_RESET_REQUESTS = "x-ratelimit-reset-requests"
HEADER_LIMIT_TOKENS = "x-ratelimit-limit-tokens"            # TPM
HEADER_REMAINING_TOKENS = "x-ratelimit-remaining-tokens"    # TPM
HEADER_RESET_TOKENS = "x-ratelimit-reset-tokens"
HEADER_REQUEST_ID = "x-groq-request-id"

_MAX_ERROR_CHARS = 300

# "7.66s", "2m59.56s", "1h2m3s", "500ms", or a bare number of seconds.
_DURATION_PATTERN = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)?")
_UNIT_SECONDS = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}

logger = logging.getLogger(__name__)


def _load_sdk() -> ModuleType:
    """Import the SDK. The only ``groq`` import in the project."""
    return importlib.import_module("groq")


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


def parse_reset_duration(value: Any) -> float | None:
    """Seconds from a Groq duration header, or ``None`` if it cannot be read.

    Groq expresses resets as Go-style durations — ``"2m59.56s"``, ``"7.66s"``,
    ``"500ms"`` — and a bare number is treated as seconds. Anything that does not parse
    cleanly and completely returns ``None``: a limiter that waits on a misread header
    is worse than one that falls back to its configured floor, so this never guesses.
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    total = 0.0
    position = 0
    seen = False
    for match in _DURATION_PATTERN.finditer(text):
        if match.start() != position:
            return None  # unparsable text between the numbers
        position = match.end()
        number, unit = match.group(1), match.group(2)
        try:
            total += float(number) * _UNIT_SECONDS.get(unit or "s", 1.0)
        except ValueError:  # pragma: no cover - the pattern guarantees a float
            return None
        seen = True
    if not seen or position != len(text):
        return None
    return total


def _int_header(value: Any) -> int | None:
    """A whole-number header value, or ``None`` — never a partial guess."""
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _float_header(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class RateLimitSnapshot:
    """What Groq said about this organization's limits on one response.

    This is a **provider-specific extra** — the same shape the local adapter already
    uses for its inspectable ``RequestBudget``, which 2a's Phase 0 contract map
    confirmed sits outside the four-method protocol on purpose. It is deliberately
    *not* a change to 2a's shared contract. Two
    reasons it belongs here rather than on ``CompletionResult``: the shared result has
    no field that could carry it without abusing one, and — more importantly — the
    reading Phase 4 needs most arrives on a **429, where there is no completion at
    all**. A snapshot held on the provider and attached to the raised error covers both
    paths; a field on the success type would have covered only the easy one.

    The request counters are per day and the token counters are per minute; that
    asymmetry is Groq's, not a naming accident here.
    """

    limit_requests: int | None = None
    remaining_requests: int | None = None
    reset_requests_seconds: float | None = None
    limit_tokens: int | None = None
    remaining_tokens: int | None = None
    reset_tokens_seconds: float | None = None
    retry_after_seconds: float | None = None
    observed_at: float = 0.0

    @property
    def is_empty(self) -> bool:
        """True when nothing usable was returned, so Phase 4 must fall back."""
        return all(
            value is None
            for value in (
                self.limit_requests,
                self.remaining_requests,
                self.reset_requests_seconds,
                self.limit_tokens,
                self.remaining_tokens,
                self.reset_tokens_seconds,
                self.retry_after_seconds,
            )
        )

    @property
    def daily_requests_exhausted(self) -> bool:
        """Groq's request counters are per day, so zero remaining means tomorrow."""
        return self.remaining_requests == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "limit_requests": self.limit_requests,
            "remaining_requests": self.remaining_requests,
            "reset_requests_seconds": self.reset_requests_seconds,
            "limit_tokens": self.limit_tokens,
            "remaining_tokens": self.remaining_tokens,
            "reset_tokens_seconds": self.reset_tokens_seconds,
            "retry_after_seconds": self.retry_after_seconds,
        }


def _lowercase_headers(headers: Any) -> dict[str, str]:
    """HTTP headers are case-insensitive; normalise before reading them."""
    if not headers:
        return {}
    try:
        items = headers.items()
    except AttributeError:
        return {}
    result: dict[str, str] = {}
    for key, value in items:
        try:
            result[str(key).strip().lower()] = value
        except Exception:  # pragma: no cover - defensive
            continue
    return result


def read_rate_limits(headers: Any) -> RateLimitSnapshot:
    """Scrape a rate-limit snapshot. A malformed or absent header is simply absent."""
    lowered = _lowercase_headers(headers)
    return RateLimitSnapshot(
        limit_requests=_int_header(lowered.get(HEADER_LIMIT_REQUESTS)),
        remaining_requests=_int_header(lowered.get(HEADER_REMAINING_REQUESTS)),
        reset_requests_seconds=parse_reset_duration(lowered.get(HEADER_RESET_REQUESTS)),
        limit_tokens=_int_header(lowered.get(HEADER_LIMIT_TOKENS)),
        remaining_tokens=_int_header(lowered.get(HEADER_REMAINING_TOKENS)),
        reset_tokens_seconds=parse_reset_duration(lowered.get(HEADER_RESET_TOKENS)),
        retry_after_seconds=_float_header(lowered.get(HEADER_RETRY_AFTER)),
        observed_at=time.monotonic(),
    )


class GroqProvider:
    """Cloud adapter for one exact, reviewed Groq model."""

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

        # A key handed to us directly never passed through `ai.secrets`, so register it
        # with the redactor here rather than trusting it was done elsewhere.
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

        # The most recent thing Groq said about this organization's limits.
        self._rate_limits: RateLimitSnapshot | None = None

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"GroqProvider(model_id={self.model_id!r})"

    @property
    def approved_record(self) -> ApprovedModel | None:
        return self._record

    @property
    def last_rate_limits(self) -> RateLimitSnapshot | None:
        """The most recent header snapshot, or ``None`` if none has been seen.

        Phase 4 reads this rather than a configured floor whenever
        ``capabilities().exposes_rate_limits`` is True and the snapshot is not empty.
        """
        return self._rate_limits

    # -- guards ------------------------------------------------------------
    def _require_approved(self) -> ApprovedModel:
        if self._approval_error is not None:
            raise self._approval_error
        if self._record is None:  # pragma: no cover - defensive
            raise ModelUnavailable(
                "No approved Groq model is configured.", retryable=False
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
                "No API key is available for Groq. Set the GROQ_API_KEY environment "
                "variable, or save a key in the app's AI settings.",
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
            self._client = sdk.Groq(
                api_key=key,
                timeout=max(1.0, float(self.timeout_seconds)),
                max_retries=SDK_MAX_RETRIES,
            )
        except ImportError as exc:
            raise ProviderUnavailable(
                "The groq package is unavailable in this build.", retryable=False
            ) from exc
        except Exception as exc:
            raise ProviderUnavailable(
                f"Groq client initialization failed ({_safe_message(exc)}).",
                retryable=False,
            ) from exc
        return self._client

    def _check_retirement(self, record: ApprovedModel) -> None:
        """Confirm once that the approved model is still offered *to this key*.

        Groq's lineup and per-organization availability both move, so this is checked
        against the live list rather than assumed from the reviewed record. A transport
        failure here is *not* evidence of retirement, so it is swallowed and the check
        is left to run again later; the real request that follows will surface the
        transport problem honestly.
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
        """Every model this key can see, as exact IDs. Not a permission to call one.

        IDs are returned untouched: ``openai/gpt-oss-120b`` is one whole model ID, and
        trimming anything from it would name a model that does not exist.
        """
        try:
            listing = self._get_client().models.list()
            entries = _field(listing, "data", None)
            if entries is None:
                entries = listing if isinstance(listing, (list, tuple)) else ()
            names = []
            for entry in entries:
                name = str(_field(entry, "id") or "").strip()
                if name:
                    names.append(name)
            return names
        except (ProviderUnavailable, AuthenticationError):
            raise
        except Exception as exc:
            self._raise_transport_error(exc)
        raise AssertionError("unreachable")  # pragma: no cover

    def approved_model_choices(
        self, discovered: Sequence[str] | None = None
    ) -> tuple[str, ...]:
        """Live models that are *also* reviewed and selectable, in the live order.

        The drop's rule: other discovered models may be offered as advanced choices
        only if they are in the approved set. Nothing here selects a model — it only
        narrows what a human may pick from. Because Groq's availability is
        per-organization, the live list is this key's, not a general one.
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
                "Requested model does not match the configured exact Groq model.",
                retryable=False,
            )
        self._require_key()
        self._check_retirement(record)

        output_tokens = self._output_budget(request)
        self._check_context(request, output_tokens)
        payload = self._request_payload(request, output_tokens)

        logger.debug(
            "Groq request %s: model=%s max_output=%s",
            request.request_id,
            self.model_id,
            output_tokens,
        )
        started = time.monotonic()
        try:
            with self._lock:
                completions = self._get_client().chat.completions
                raw = getattr(completions, "with_raw_response", None)
                if raw is not None:
                    # The header path. Losing it costs Phase 4 its live figures, so it
                    # is the default and the plain call is only the fallback.
                    response = raw.create(**payload)
                    headers = _field(response, "headers", None)
                    body = response.parse()
                else:
                    body = completions.create(**payload)
                    headers = None
        except (ContextTooLong, ModelUnavailable, ProviderUnavailable,
                AuthenticationError):
            raise
        except Exception as exc:
            self._raise_transport_error(exc)

        self._remember_rate_limits(headers)
        return self._map_response(body, headers, time.monotonic() - started)

    # -- request construction ---------------------------------------------
    def _output_budget(self, request: CompletionRequest) -> int:
        budget = min(int(request.max_output_tokens), self.max_output_tokens)
        if budget <= 0:
            raise ContextTooLong(
                "No output token budget remains for this Groq request.",
                retryable=False,
            )
        return budget

    def _check_context(self, request: CompletionRequest, output_tokens: int) -> None:
        """Refuse locally rather than paying for a request that cannot fit.

        On Groq's free plan tokens-per-day is the binding constraint, so a request that
        was never going to fit is not merely a wasted round trip — it is a permanent
        bite out of the day's budget.
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

    def _is_reasoning_model(self) -> bool:
        return self.model_id.startswith(_REASONING_MODEL_PREFIXES)

    def _request_payload(
        self, request: CompletionRequest, output_tokens: int
    ) -> dict[str, Any]:
        """The outbound call's keyword arguments, built as plain data.

        Nothing here needs a type from the SDK, which is what keeps the import confined
        to client construction.
        """
        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.text},
            ],
            "max_completion_tokens": output_tokens,
            "temperature": request.temperature,
            "n": 1,
            "stream": False,
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        if self._is_reasoning_model():
            # Reasoning tokens are drawn from the output budget, so leaving them high
            # risks a paid-for `length` finish with no visible text. Only the reasoning
            # families accept this parameter at all; sending it to a Llama model is a
            # 400, and sending the wrong *value* to gpt-oss is equally a 400 — see
            # `_MIN_REASONING_EFFORT`.
            payload["reasoning_effort"] = _MIN_REASONING_EFFORT
        return payload

    # -- rate limits -------------------------------------------------------
    def _remember_rate_limits(self, headers: Any) -> RateLimitSnapshot | None:
        if headers is None:
            return None
        snapshot = read_rate_limits(headers)
        self._rate_limits = snapshot
        return snapshot

    # -- response mapping --------------------------------------------------
    def _map_response(
        self, body: Any, headers: Any, elapsed: float
    ) -> CompletionResult:
        choices = _field(body, "choices") or ()
        if not choices:
            raise InvalidResponse("Groq returned no choice at all.", retryable=True)

        finish_reason = str(_field(choices[0], "finish_reason") or "")
        # Defensive: if a future SDK returns an enum member, `str()` can render as
        # `FinishReason.STOP`. Normalise to the bare lowercase name before comparing.
        finish_reason = finish_reason.rsplit(".", 1)[-1].strip().lower()

        if finish_reason == _FINISH_TRUNCATED:
            raise InvalidResponse(
                "Groq truncated the response at the output token limit (finish "
                "reason 'length').",
                retryable=True,
            )
        if finish_reason in _FINISH_TOOL_CALL:
            raise InvalidResponse(
                f"Groq returned a tool call rather than edited text (finish reason "
                f"'{finish_reason}'), which this prompt never asks for. Retrying the "
                f"same chapter would produce the same result.",
                retryable=False,
            )
        if finish_reason in _FINISH_UNSPECIFIED:
            raise InvalidResponse(
                "Groq gave no finish reason, so the response cannot be treated as "
                "complete. The chapter falls back to script-only editing.",
                retryable=False,
            )
        if finish_reason != _FINISH_OK:
            # Fail closed. This is the important branch: a value this build has never
            # seen is refused, and the returned text is discarded rather than passed on
            # as a successful edit.
            raise InvalidResponse(
                f"Groq returned an unrecognised finish reason ('{finish_reason}'), so "
                f"the response is refused. The chapter falls back to script-only "
                f"editing.",
                retryable=False,
            )

        text = _field(_field(choices[0], "message"), "content")
        if not isinstance(text, str) or not text:
            raise InvalidResponse("Groq returned no message text.", retryable=True)

        usage = _field(body, "usage")
        model_used = str(_field(body, "model") or self.model_id)
        lowered = _lowercase_headers(headers)
        request_id = (
            lowered.get(HEADER_REQUEST_ID)
            or _field(_field(body, "x_groq"), "id")
            or _field(body, "id")
        )
        return CompletionResult(
            text,
            model_used,
            elapsed,
            finish_reason,
            False,
            provider_request_id=str(request_id) if request_id else None,
            input_tokens=_field(usage, "prompt_tokens"),
            output_tokens=_field(usage, "completion_tokens"),
            execution_backend=None,
        )

    # -- error mapping -----------------------------------------------------
    def _status_code(self, exc: BaseException) -> int | None:
        for name in ("status_code", "code", "status"):
            value = getattr(exc, name, None)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return None

    def _raise_transport_error(self, exc: BaseException) -> None:
        """Normalise an SDK/transport failure into 2a's taxonomy. Always raises.

        Classification is by HTTP status where the SDK provides one
        (``APIStatusError.status_code``) and by exception name otherwise, so no ``groq``
        import is needed to interpret a ``groq`` error.
        """
        message = _safe_message(exc)
        lowered = message.lower()
        squashed = lowered.replace(" ", "").replace("_", "").replace("-", "")
        code = self._status_code(exc)
        kind = type(exc).__name__

        # Even a failure carries limit headers, and a 429's are the ones Phase 4 needs
        # most — so read them before deciding anything.
        headers = _field(getattr(exc, "response", None), "headers", None)
        limits = self._remember_rate_limits(headers)

        if code == 413:
            raise ContextTooLong(
                f"Groq rejected the request as too large ({message}).", retryable=False
            ) from exc
        if code == 400 and any(
            marker in squashed
            for marker in ("contextlength", "tokencount", "reducethelength",
                           "exceedsthemaximum", "inputtoolong", "inputtoken",
                           "toomanytokens", "maximumcontext")
        ):
            raise ContextTooLong(
                f"Groq rejected the request as too long for the model's context "
                f"({message}).",
                retryable=False,
            ) from exc
        if code in (401, 403):
            raise AuthenticationError(
                f"Groq rejected the API key ({message}). Check the key in the "
                f"provider's console and in the app's AI settings.",
                retryable=False,
            ) from exc
        if code == 404:
            raise ModelUnavailable(
                f"Groq does not offer '{self.model_id}' to this key ({message}). No "
                f"replacement will be selected automatically.",
                retryable=False,
            ) from exc
        if code == 429:
            raise self._rate_limit_error(message, squashed, limits) from exc
        if code is not None and 500 <= code < 600:
            raise ProviderUnavailable(
                f"Groq's service returned an error ({message}).", retryable=True
            ) from exc
        if code == 400:
            raise ProviderUnavailable(
                f"Groq rejected the request ({message}).", retryable=False
            ) from exc

        if isinstance(exc, TimeoutError) or "timeout" in kind.lower() or "timed out" in lowered:
            raise TransientNetworkError(
                f"Groq request timed out ({kind}).", retryable=True
            ) from exc
        if any(
            marker in kind.lower()
            for marker in ("connect", "network", "socket", "ssl", "protocol", "read")
        ) or "connection" in lowered:
            raise TransientNetworkError(
                f"Could not reach Groq ({kind}).", retryable=True
            ) from exc
        raise ProviderUnavailable(
            f"Groq request failed ({kind}).", retryable=True
        ) from exc

    def _rate_limit_error(
        self, message: str, squashed: str, limits: RateLimitSnapshot | None
    ) -> RateLimited | DailyQuotaExhausted:
        """Split a 429 into "wait a moment" and "come back tomorrow".

        The drop forbids inferring daily exhaustion from *every* 429, so this needs
        positive evidence, and Groq gives two independent kinds. First its own wording,
        which names the exact limit ("on tokens per day (TPD)"). Failing that, the
        header rule: ``x-ratelimit-remaining-requests`` is a per-**day** counter, so
        zero remaining is daily exhaustion even when the body says only "Too Many
        Requests". Anything else stays a retryable per-minute limit.
        """
        daily_wording = any(
            marker in squashed
            for marker in ("perday", "(tpd)", "(rpd)", "tokensperday",
                           "requestsperday", "dailyquota", "daily")
        )
        if daily_wording or (limits is not None and limits.daily_requests_exhausted):
            error = DailyQuotaExhausted(
                f"Groq's free daily quota for {self.model_id} is used up ({message}). "
                f"The run can be resumed once the quota resets — Groq's limits apply "
                f"per organization and per model, so check the account's limits page.",
                retryable=False,
            )
        else:
            error = RateLimited(
                f"Groq is rate limiting this organization ({message}).", retryable=True
            )
        # Attached to the exception instance, not defined on the shared error class:
        # 2a's taxonomy is untouched, and Phase 4 still gets the numbers it needs.
        error.rate_limits = limits
        error.retry_after_seconds = limits.retry_after_seconds if limits else None
        return error
