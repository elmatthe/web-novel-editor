"""Plan 2b Phase 3 — GroqProvider, mocked at the transport.

Every test here runs **offline**. No ``groq`` package is imported, no network call is
made, no real API key is read, and no per-user file is touched: each test either
injects a fake client or passes explicit non-existent ``secrets_file`` / ``dotenv_path``
locations, so a developer who happens to have a real GROQ_API_KEY on this machine
cannot make the suite pass or fail for the wrong reason.

The fake key is deliberately shaped like a real Groq key (``gsk_…``) so the shape half
of the Phase 1 redactor is exercised as well as the registered-literal half.

**What is different here from the Gemini suite, and why it matters.** Groq publishes
exact per-model free-tier limits *and* returns ``retry-after`` plus
``x-ratelimit-{limit,remaining,reset}-{requests,tokens}``. That asymmetry is the point
of this phase, so a large block below is about capturing those headers — from both a
successful response and a 429 — and parsing Groq's duration strings ("2m59.56s")
without ever crashing on a malformed or absent one.
"""

from __future__ import annotations

import logging
import sys
import types as pytypes
from pathlib import Path

import pytest

from ai.approved_models import ApprovedModel
from ai.errors import (
    AuthenticationError,
    ContextTooLong,
    DailyQuotaExhausted,
    InvalidResponse,
    ModelUnavailable,
    ProviderUnavailable,
    RateLimited,
    TransientNetworkError,
)
from ai.factory import create_provider
from ai.models import CompletionRequest, ProviderStatus
from ai.providers.groq import GroqProvider, parse_reset_duration

FAKE_KEY = "gsk_FAKEgroqkeyfortestsonly000000000001"
MODEL = "llama-3.3-70b-versatile"
NAMESPACED_MODEL = "openai/gpt-oss-120b"
NOWHERE = Path("this-file-does-not-exist-anywhere.json")


# ---------------------------------------------------------------------------
# Reviewed records — the same nine-field shape config.toml ships.
# ---------------------------------------------------------------------------
def record(
    model_id: str = MODEL,
    *,
    provider: str = "groq",
    status: str = "stable",
    context_limit: int = 131_072,
    output_limit: int = 32_768,
    confidence: str = "confirmed",
) -> ApprovedModel:
    return ApprovedModel(
        id=model_id,
        provider=provider,
        status=status,
        context_limit=context_limit,
        output_limit=output_limit,
        reviewed_on="2026-07-25",
        source_url="https://console.groq.com/docs/models",
        free_tier_confidence=confidence,
        pilot_status="not-piloted",
    )


APPROVED = (
    record(),
    record(NAMESPACED_MODEL, output_limit=65_536),
    record("llama-3.1-8b-instant", output_limit=131_072),
    # Groq's Qwen tag is *preview*, not production (re-verified 2026-07-25), so it is
    # exactly the kind of record strict free-only mode must refuse.
    record("qwen/qwen3.6-27b", status="preview", output_limit=16_384,
           confidence="unknown"),
    record("gemini-3.5-flash", provider="gemini", context_limit=1_048_576,
           output_limit=65_536),
)


def request(
    text: str = "He walk home.",
    *,
    system: str = "Correct only certain grammar errors.",
    model: str = MODEL,
    maximum: int = 500,
) -> CompletionRequest:
    return CompletionRequest(
        text, system, "1.0", model, 0.0, 17, 12.5, maximum, "request-test"
    )


# ---------------------------------------------------------------------------
# Transport fakes, shaped like the groq SDK's objects.
# ---------------------------------------------------------------------------
def obj(**fields):
    return pytypes.SimpleNamespace(**fields)


class FakeAPIStatusError(Exception):
    """Duck-typed stand-in for ``groq.APIStatusError``.

    The real class carries ``.status_code``, ``.message`` and ``.response`` (an httpx
    response whose ``.headers`` is a case-insensitive mapping).
    """

    def __init__(self, status_code: int, message: str, headers: dict | None = None):
        super().__init__(f"{status_code} {message}")
        self.status_code = status_code
        self.message = message
        self.response = obj(headers=dict(headers or {}), status_code=status_code)


HEADERS = {
    # Groq's own documentation: limit/remaining-requests are RPD, limit/remaining-
    # tokens are TPM, and the reset headers are duration strings.
    "x-ratelimit-limit-requests": "1000",
    "x-ratelimit-remaining-requests": "999",
    "x-ratelimit-reset-requests": "2m59.56s",
    "x-ratelimit-limit-tokens": "12000",
    "x-ratelimit-remaining-tokens": "11500",
    "x-ratelimit-reset-tokens": "7.66s",
    "x-groq-request-id": "req-header-001",
}


def completion(
    text: str = "He walks home.",
    *,
    finish_reason: str | None = "stop",
    prompt_tokens: int | None = 23,
    output_tokens: int | None = 7,
    completion_id: str = "chatcmpl-abc123",
    model: str = MODEL,
    usage: bool = True,
    choices: bool = True,
):
    message = obj(content=text, role="assistant", tool_calls=None)
    picks = [obj(finish_reason=finish_reason, index=0, message=message)] if choices else []
    return obj(
        id=completion_id,
        choices=picks,
        created=1_800_000_000,
        model=model,
        object="chat.completion",
        usage=(
            obj(
                prompt_tokens=prompt_tokens,
                completion_tokens=output_tokens,
                total_tokens=None,
            )
            if usage
            else None
        ),
        x_groq=obj(id="req-xgroq-002"),
    )


class _RawResponse:
    """Stands in for the SDK's ``APIResponse`` from ``with_raw_response``."""

    def __init__(self, parsed, headers):
        self.headers = dict(headers)
        self._parsed = parsed

    def parse(self):
        return self._parsed


class _RawCompletions:
    def __init__(self, outer):
        self._outer = outer

    def create(self, **kwargs):
        self._outer.calls.append(kwargs)
        self._outer.raw_calls += 1
        if self._outer.error:
            raise self._outer.error
        return _RawResponse(self._outer.completion, self._outer.headers)


class _Completions:
    def __init__(self, outer):
        self._outer = outer
        self.with_raw_response = _RawCompletions(outer)

    def create(self, **kwargs):
        self._outer.calls.append(kwargs)
        self._outer.plain_calls += 1
        if self._outer.error:
            raise self._outer.error
        return self._outer.completion


class _Models:
    def __init__(self, outer):
        self._outer = outer

    def list(self, **kwargs):
        self._outer.list_calls += 1
        if self._outer.list_error:
            raise self._outer.list_error
        return obj(
            object="list",
            data=[obj(id=name, owned_by="groq") for name in self._outer.model_ids],
        )


class _Client:
    """In-process stand-in for ``groq.Groq``. Nothing here touches a network."""

    def __init__(
        self,
        *,
        models=(MODEL, NAMESPACED_MODEL, "llama-3.1-8b-instant"),
        result=None,
        headers=None,
        list_error=None,
        error=None,
        raw_support=True,
    ):
        self.model_ids = models
        self.completion = result if result is not None else completion()
        self.headers = HEADERS if headers is None else headers
        self.list_error = list_error
        self.error = error
        self.calls: list[dict] = []
        self.list_calls = 0
        self.raw_calls = 0
        self.plain_calls = 0
        self.chat = obj(completions=_Completions(self))
        if not raw_support:
            del self.chat.completions.with_raw_response
        self.models = _Models(self)


def provider(client=None, **kwargs):
    kwargs.setdefault("model_id", MODEL)
    kwargs.setdefault("approved_models", APPROVED)
    kwargs.setdefault("api_key", FAKE_KEY)
    return GroqProvider(client=client if client is not None else _Client(), **kwargs)


# ---------------------------------------------------------------------------
# SDK isolation
# ---------------------------------------------------------------------------
def test_importing_the_adapter_does_not_import_the_groq_sdk():
    assert "groq" not in sys.modules


def test_factory_constructs_adapter_without_loading_sdk():
    loaded = []
    built = create_provider(
        "groq",
        model_id=MODEL,
        approved_models=APPROVED,
        api_key=FAKE_KEY,
        sdk_loader=lambda: loaded.append(True),
    )
    # The foundation import-isolation tests reload the ``ai`` package, so the lazily
    # imported class is not always the same object this module imported. Assert the
    # factory's result without depending on stale class identity.
    assert type(built).__name__ == "GroqProvider"
    assert built.capabilities().provider_name == "groq"
    assert loaded == []


def test_missing_sdk_reports_package_unavailable_rather_than_crashing():
    def boom():
        raise ImportError("No module named 'groq'")

    guard = GroqProvider(
        model_id=MODEL, approved_models=APPROVED, api_key=FAKE_KEY, sdk_loader=boom
    )
    assert guard.health_check() is ProviderStatus.PACKAGE_UNAVAILABLE
    with pytest.raises(ProviderUnavailable):
        guard.complete(request())


# ---------------------------------------------------------------------------
# Capabilities, driven by the reviewed record
# ---------------------------------------------------------------------------
def test_capabilities_report_the_reviewed_record_not_a_default():
    caps = provider().capabilities()
    assert caps.provider_name == "groq"
    assert caps.is_local is False
    assert caps.model_ids == (MODEL,)
    assert caps.context_limit == 131_072
    assert caps.max_output_tokens == 32_768
    assert caps.supports_streaming is False
    assert caps.privacy_disclosure_id


def test_capabilities_report_that_groq_exposes_rate_limits():
    """The Phase 0 correction #4 asymmetry, stated through the 2a contract field.

    Gemini reports False because Google documents no such headers; Groq reports True
    because it documents and returns them. Phase 4 reads exactly this flag to decide
    whether to run header-driven or from a conservative floor.
    """
    assert provider().capabilities().exposes_rate_limits is True


def test_explicit_max_output_override_caps_but_never_raises_the_record():
    assert provider(max_output_tokens=1024).capabilities().max_output_tokens == 1024
    assert provider(max_output_tokens=999_999).capabilities().max_output_tokens == 32_768


def test_capabilities_offer_no_model_when_the_configured_one_is_refused():
    guard = GroqProvider(
        model_id="not-an-approved-model", approved_models=APPROVED, api_key=FAKE_KEY
    )
    assert guard.capabilities().model_ids == ()
    assert guard.health_check() is ProviderStatus.MODEL_MISSING


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------
def test_list_models_preserves_namespaced_ids_untouched():
    """``openai/gpt-oss-120b`` is one model ID, not a prefix plus a name.

    Gemini's adapter strips a ``models/`` resource prefix. Doing anything of the sort
    here would silently rewrite a real Groq model ID into one that does not exist, so
    this adapter must pass IDs through byte-for-byte.
    """
    assert provider().list_models() == [
        MODEL,
        NAMESPACED_MODEL,
        "llama-3.1-8b-instant",
    ]


def test_approved_choices_are_the_intersection_of_live_and_reviewed_models():
    client = _Client(models=(MODEL, "some-unreviewed-model", NAMESPACED_MODEL))
    assert provider(client).approved_model_choices() == (MODEL, NAMESPACED_MODEL)


def test_approved_choices_exclude_a_preview_model_even_when_it_is_live():
    client = _Client(models=(MODEL, "qwen/qwen3.6-27b"))
    assert provider(client).approved_model_choices() == (MODEL,)


def test_approved_choices_exclude_another_providers_approved_model():
    client = _Client(models=(MODEL, "gemini-3.5-flash"))
    assert provider(client).approved_model_choices() == (MODEL,)


# ---------------------------------------------------------------------------
# Refusals — nothing is ever substituted
# ---------------------------------------------------------------------------
def test_non_approved_model_is_refused_and_never_calls_the_provider():
    client = _Client()
    guard = GroqProvider(
        model_id="llama-guess-70b", approved_models=APPROVED, api_key=FAKE_KEY,
        client=client,
    )
    with pytest.raises(ModelUnavailable):
        guard.complete(request(model="llama-guess-70b"))
    assert client.calls == []


def test_unknown_free_tier_confidence_is_refused_in_strict_mode():
    guard = GroqProvider(
        model_id="qwen/qwen3.6-27b", approved_models=APPROVED, api_key=FAKE_KEY,
        client=_Client(),
    )
    with pytest.raises(ModelUnavailable):
        guard.complete(request(model="qwen/qwen3.6-27b"))


def test_a_preview_model_is_refused_in_strict_mode():
    approved = (record("qwen/qwen3.6-27b", status="preview", confidence="confirmed"),)
    guard = GroqProvider(
        model_id="qwen/qwen3.6-27b", approved_models=approved, api_key=FAKE_KEY,
        client=_Client(),
    )
    with pytest.raises(ModelUnavailable) as caught:
        guard.complete(request(model="qwen/qwen3.6-27b"))
    assert "stable" in str(caught.value).lower()


def test_moving_alias_is_refused_even_if_hand_edited_into_the_config():
    approved = (record("llama-3.3-70b-latest"),)
    guard = GroqProvider(
        model_id="llama-3.3-70b-latest", approved_models=approved, api_key=FAKE_KEY,
        client=_Client(),
    )
    with pytest.raises(ModelUnavailable) as caught:
        guard.complete(request(model="llama-3.3-70b-latest"))
    assert "alias" in str(caught.value).lower()


def test_a_gemini_approved_model_is_not_callable_through_groq():
    guard = GroqProvider(
        model_id="gemini-3.5-flash", approved_models=APPROVED, api_key=FAKE_KEY,
        client=_Client(),
    )
    with pytest.raises(ModelUnavailable):
        guard.complete(request(model="gemini-3.5-flash"))


def test_request_for_a_different_model_than_the_configured_one_is_refused():
    with pytest.raises(ModelUnavailable):
        provider().complete(request(model=NAMESPACED_MODEL))


def test_retired_model_makes_the_provider_unavailable_with_no_substitution():
    """Groq's lineup moves — a model that vanished must stop the run, not reroute it."""
    client = _Client(models=("llama-3.1-8b-instant", NAMESPACED_MODEL))
    guard = provider(client)
    with pytest.raises(ModelUnavailable) as caught:
        guard.complete(request())
    message = str(caught.value)
    assert "retired" in message.lower()
    for other in ("llama-3.1-8b-instant", NAMESPACED_MODEL):
        assert other not in message
    assert client.calls == []


def test_an_empty_live_list_is_unverifiable_not_retired():
    """An unreadable list endpoint must not be able to fake a retirement."""
    result = provider(_Client(models=())).complete(request())
    assert result.text == "He walks home."


def test_availability_is_checked_once_not_per_chapter():
    client = _Client()
    guard = provider(client)
    for _ in range(4):
        guard.complete(request())
    assert client.list_calls == 1


def test_no_substitution_helper_exists_on_the_adapter():
    import ai.providers.groq as module

    text = Path(module.__file__).read_text(encoding="utf-8").lower()
    for banned in ("def _fallback_model", "def _pick_model", "def _newest",
                   "def _substitute"):
        assert banned not in text


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------
def test_successful_completion_maps_into_the_2a_result():
    result = provider().complete(request())
    assert result.text == "He walks home."
    assert result.model_id == MODEL
    assert result.finish_reason == "stop"
    assert result.truncated is False
    assert result.input_tokens == 23
    assert result.output_tokens == 7
    assert result.duration_seconds >= 0.0
    assert result.provider_request_id == "req-header-001"


def test_the_model_actually_used_is_reported_not_the_one_requested():
    client = _Client(result=completion(model="llama-3.3-70b-versatile-0125"))
    assert provider(client).complete(request()).model_id == "llama-3.3-70b-versatile-0125"


def test_missing_usage_reports_none_rather_than_inventing_counts():
    client = _Client(result=completion(usage=False))
    result = provider(client).complete(request())
    assert result.input_tokens is None
    assert result.output_tokens is None


def test_request_sends_the_explicit_bounded_output_and_deterministic_settings():
    client = _Client()
    provider(client).complete(request(maximum=321))
    sent = client.calls[0]
    assert sent["model"] == MODEL
    assert sent["max_completion_tokens"] == 321
    assert sent["temperature"] == 0.0
    assert sent["seed"] == 17
    assert sent["n"] == 1
    assert sent["stream"] is False


def test_the_output_budget_can_never_exceed_the_reviewed_record():
    client = _Client()
    provider(client).complete(request(maximum=999_999))
    assert client.calls[0]["max_completion_tokens"] == 32_768


def test_the_system_prompt_and_the_chapter_are_separate_messages():
    client = _Client()
    provider(client).complete(request("He walk home.", system="Fix grammar."))
    messages = client.calls[0]["messages"]
    assert messages == [
        {"role": "system", "content": "Fix grammar."},
        {"role": "user", "content": "He walk home."},
    ]


def test_reasoning_is_disabled_on_gpt_oss_so_it_cannot_eat_the_output_budget():
    """gpt-oss are reasoning models; reasoning tokens are billed against the output
    budget, so leaving it on risks paying for a ``length`` finish with no visible text.
    This is the direct analogue of the Gemini adapter turning thinking off."""
    client = _Client()
    guard = provider(client, model_id=NAMESPACED_MODEL)
    guard.complete(request(model=NAMESPACED_MODEL))
    assert client.calls[0]["reasoning_effort"] == "none"


def test_llama_models_are_not_sent_a_reasoning_effort_parameter():
    """Sending a reasoning parameter to a non-reasoning model is a 400."""
    client = _Client()
    provider(client).complete(request())
    assert "reasoning_effort" not in client.calls[0]


def test_the_sdk_client_is_built_with_its_own_retries_disabled():
    """2a's editor and Phase 4's limiter own retry policy.

    The SDK retries twice by default. Silent retries would double-spend the free
    tier's tokens-per-day and hide 429s from the limiter that exists to see them.
    """
    captured = {}

    class Recorder:
        def Groq(self, **kwargs):  # noqa: N802 - mirrors the SDK's class name
            captured.update(kwargs)
            return _Client()

    guard = GroqProvider(
        model_id=MODEL, approved_models=APPROVED, api_key=FAKE_KEY,
        sdk_loader=Recorder,
    )
    guard.complete(request())
    assert captured["max_retries"] == 0
    assert captured["api_key"] == FAKE_KEY


# ---------------------------------------------------------------------------
# Finish reasons — the fail-closed rule
# ---------------------------------------------------------------------------
def test_length_is_truncation_and_is_eligible_for_one_retry():
    client = _Client(result=completion(finish_reason="length"))
    with pytest.raises(InvalidResponse) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is True


@pytest.mark.parametrize("reason", ["tool_calls", "function_call"])
def test_tool_call_finishes_fail_permanently_rather_than_retrying(reason):
    client = _Client(result=completion(finish_reason=reason))
    with pytest.raises(InvalidResponse) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is False


def test_an_unknown_finish_reason_fails_closed_and_never_returns_the_text():
    """The load-bearing guard: a value this build has never seen is refused, and the
    candidate text is discarded rather than returned as a successful edit."""
    client = _Client(
        result=completion("Completely rewritten prose.", finish_reason="content_filter")
    )
    with pytest.raises(InvalidResponse) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is False
    assert "Completely rewritten prose." not in str(caught.value)


@pytest.mark.parametrize("reason", [None, "", "unspecified"])
def test_an_absent_or_unspecified_finish_reason_also_fails_closed(reason):
    client = _Client(result=completion(finish_reason=reason))
    with pytest.raises(InvalidResponse) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is False


def test_a_stop_with_no_text_is_not_a_success():
    client = _Client(result=completion(""))
    with pytest.raises(InvalidResponse):
        provider(client).complete(request())


def test_no_choices_at_all_is_an_invalid_response():
    client = _Client(result=completion(choices=False))
    with pytest.raises(InvalidResponse):
        provider(client).complete(request())


# ---------------------------------------------------------------------------
# Context limits
# ---------------------------------------------------------------------------
def test_input_beyond_the_reviewed_context_limit_is_refused_before_the_call():
    client = _Client()
    with pytest.raises(ContextTooLong):
        provider(client).complete(request("word " * 120_000))
    assert client.calls == []


def test_a_provider_side_token_limit_error_maps_to_context_too_long():
    error = FakeAPIStatusError(
        400,
        "Please reduce the length of the messages: request exceeds the maximum "
        "context length of 131072 tokens",
    )
    client = _Client(error=error)
    with pytest.raises(ContextTooLong):
        provider(client).complete(request())


def test_a_413_payload_too_large_is_context_too_long():
    client = _Client(error=FakeAPIStatusError(413, "Request Entity Too Large"))
    with pytest.raises(ContextTooLong):
        provider(client).complete(request())


def test_an_ordinary_400_is_not_mistaken_for_a_context_problem():
    client = _Client(error=FakeAPIStatusError(400, "unsupported parameter 'foo'"))
    with pytest.raises(ProviderUnavailable) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is False


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def test_no_key_anywhere_is_an_authentication_error_not_a_crash():
    guard = GroqProvider(
        model_id=MODEL,
        approved_models=APPROVED,
        environ={},
        secrets_file=NOWHERE,
        dotenv_path=NOWHERE,
    )
    assert guard.health_check() is ProviderStatus.AUTH_MISSING
    with pytest.raises(AuthenticationError):
        guard.complete(request())


def test_a_key_in_the_environment_is_found_without_touching_the_user_profile():
    guard = GroqProvider(
        model_id=MODEL,
        approved_models=APPROVED,
        client=_Client(),
        environ={"GROQ_API_KEY": FAKE_KEY},
        secrets_file=NOWHERE,
        dotenv_path=NOWHERE,
    )
    assert guard.health_check() is ProviderStatus.OK


@pytest.mark.parametrize("code", [401, 403])
def test_rejected_credentials_map_to_a_permanent_authentication_error(code):
    client = _Client(error=FakeAPIStatusError(code, "Invalid API Key"))
    with pytest.raises(AuthenticationError) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is False


def test_a_404_means_the_model_is_gone_not_that_the_service_is_down():
    client = _Client(error=FakeAPIStatusError(404, "model not found"))
    with pytest.raises(ModelUnavailable) as caught:
        provider(client).complete(request())
    assert "llama-3.1-8b-instant" not in str(caught.value)


# ---------------------------------------------------------------------------
# Rate limits — the Groq asymmetry, and the point of this phase
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("7.66s", 7.66),
        ("2m59.56s", 179.56),
        ("1h2m3s", 3723.0),
        ("500ms", 0.5),
        ("30", 30.0),
        ("0s", 0.0),
    ],
)
def test_reset_durations_are_parsed_into_seconds(raw, expected):
    assert parse_reset_duration(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", [None, "", "soon", "abc", "--", "m", "1x2y"])
def test_a_malformed_reset_duration_is_none_rather_than_a_guess(raw):
    assert parse_reset_duration(raw) is None


def test_rate_limit_headers_are_captured_from_a_successful_response():
    guard = provider()
    guard.complete(request())
    limits = guard.last_rate_limits
    assert limits.limit_requests == 1000
    assert limits.remaining_requests == 999
    assert limits.reset_requests_seconds == pytest.approx(179.56)
    assert limits.limit_tokens == 12000
    assert limits.remaining_tokens == 11500
    assert limits.reset_tokens_seconds == pytest.approx(7.66)
    assert limits.retry_after_seconds is None


def test_rate_limit_headers_are_read_case_insensitively():
    client = _Client(headers={"X-RateLimit-Remaining-Tokens": "42"})
    guard = provider(client)
    guard.complete(request())
    assert guard.last_rate_limits.remaining_tokens == 42


def test_absent_rate_limit_headers_leave_an_empty_snapshot_not_a_crash():
    guard = provider(_Client(headers={}))
    guard.complete(request())
    limits = guard.last_rate_limits
    assert limits.remaining_requests is None
    assert limits.remaining_tokens is None
    assert limits.is_empty is True


def test_malformed_rate_limit_headers_are_ignored_rather_than_crashing():
    client = _Client(
        headers={
            "x-ratelimit-limit-requests": "not-a-number",
            "x-ratelimit-remaining-tokens": "",
            "x-ratelimit-reset-tokens": "whenever",
            "retry-after": "later",
        }
    )
    guard = provider(client)
    assert guard.complete(request()).text == "He walks home."
    limits = guard.last_rate_limits
    assert limits.limit_requests is None
    assert limits.remaining_tokens is None
    assert limits.reset_tokens_seconds is None
    assert limits.retry_after_seconds is None


def test_a_per_minute_429_is_a_retryable_rate_limit():
    error = FakeAPIStatusError(
        429,
        "Rate limit reached for model `llama-3.3-70b-versatile` in organization "
        "`org_x` on tokens per minute (TPM): Limit 12000, Used 11800, Requested 900.",
        headers={"retry-after": "9", "x-ratelimit-remaining-tokens": "0"},
    )
    with pytest.raises(RateLimited) as caught:
        provider(_Client(error=error)).complete(request())
    assert caught.value.retryable is True


def test_a_tokens_per_day_429_is_daily_quota_exhaustion_and_is_not_retried():
    error = FakeAPIStatusError(
        429,
        "Rate limit reached for model `llama-3.3-70b-versatile` in organization "
        "`org_x` on tokens per day (TPD): Limit 100000, Used 100000, Requested 2000.",
        headers={"retry-after": "43200"},
    )
    with pytest.raises(DailyQuotaExhausted) as caught:
        provider(_Client(error=error)).complete(request())
    assert caught.value.retryable is False


def test_a_requests_per_day_429_is_daily_quota_exhaustion():
    error = FakeAPIStatusError(
        429,
        "Rate limit reached on requests per day (RPD): Limit 1000, Used 1000.",
    )
    with pytest.raises(DailyQuotaExhausted):
        provider(_Client(error=error)).complete(request())


def test_exhausted_daily_request_headers_classify_as_daily_without_any_wording():
    """``x-ratelimit-remaining-requests`` is a *per-day* counter on Groq, so zero
    remaining is daily exhaustion even when the message text says nothing useful."""
    error = FakeAPIStatusError(
        429,
        "Too Many Requests",
        headers={"x-ratelimit-limit-requests": "1000",
                 "x-ratelimit-remaining-requests": "0"},
    )
    with pytest.raises(DailyQuotaExhausted):
        provider(_Client(error=error)).complete(request())


def test_a_bare_429_stays_a_retryable_rate_limit_rather_than_guessing_daily():
    """Never infer daily exhaustion from every 429 — the drop forbids it."""
    with pytest.raises(RateLimited):
        provider(_Client(error=FakeAPIStatusError(429, "Too Many Requests"))).complete(
            request()
        )


def test_retry_after_from_a_429_is_captured_for_the_limiter():
    error = FakeAPIStatusError(
        429, "on tokens per minute (TPM)", headers={"retry-after": "12.5"}
    )
    guard = provider(_Client(error=error))
    with pytest.raises(RateLimited) as caught:
        guard.complete(request())
    assert caught.value.retry_after_seconds == pytest.approx(12.5)
    assert guard.last_rate_limits.retry_after_seconds == pytest.approx(12.5)


def test_the_raised_error_carries_the_whole_snapshot_for_phase_four():
    error = FakeAPIStatusError(
        429,
        "on tokens per day (TPD)",
        headers={"retry-after": "600", "x-ratelimit-reset-requests": "1m0s"},
    )
    with pytest.raises(DailyQuotaExhausted) as caught:
        provider(_Client(error=error)).complete(request())
    limits = caught.value.rate_limits
    assert limits.retry_after_seconds == pytest.approx(600.0)
    assert limits.reset_requests_seconds == pytest.approx(60.0)


def test_a_client_without_raw_response_support_still_completes():
    """Older SDK builds lack ``with_raw_response``; losing the headers must degrade
    the limiter to a floor, not break the run."""
    client = _Client(raw_support=False)
    guard = provider(client)
    assert guard.complete(request()).text == "He walks home."
    assert client.plain_calls == 1
    assert guard.last_rate_limits is None or guard.last_rate_limits.is_empty


def test_the_request_id_falls_back_to_the_body_when_no_header_is_present():
    client = _Client(headers={})
    assert provider(client).complete(request()).provider_request_id == "req-xgroq-002"


# ---------------------------------------------------------------------------
# Server and network faults
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("code", [500, 502, 503, 504])
def test_server_side_faults_are_retryable_outages(code):
    client = _Client(error=FakeAPIStatusError(code, "upstream error"))
    with pytest.raises(ProviderUnavailable) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is True


def test_a_network_failure_is_a_transient_network_error():
    class APIConnectionError(Exception):
        pass

    client = _Client(error=APIConnectionError("Connection error."))
    with pytest.raises(TransientNetworkError):
        provider(client).complete(request())


def test_a_timeout_is_a_transient_network_error():
    class APITimeoutError(Exception):
        pass

    client = _Client(error=APITimeoutError("Request timed out."))
    with pytest.raises(TransientNetworkError):
        provider(client).complete(request())


# ---------------------------------------------------------------------------
# Health reporting — never raises
# ---------------------------------------------------------------------------
def test_health_check_reports_ok_when_everything_lines_up():
    assert provider().health_check() is ProviderStatus.OK


@pytest.mark.parametrize(
    "error,expected",
    [
        (FakeAPIStatusError(401, "bad key"), ProviderStatus.AUTH_MISSING),
        (FakeAPIStatusError(429, "on tokens per day (TPD)"),
         ProviderStatus.QUOTA_EXHAUSTED),
        (FakeAPIStatusError(503, "down"), ProviderStatus.SERVICE_DOWN),
    ],
)
def test_health_check_distinguishes_transport_failures(error, expected):
    assert provider(_Client(list_error=error)).health_check() is expected


def test_health_check_never_raises_even_on_an_unexpected_fault():
    class Exploding:
        def __getattr__(self, name):
            raise RuntimeError("nothing about this is normal")

    guard = GroqProvider(
        model_id=MODEL, approved_models=APPROVED, api_key=FAKE_KEY, client=Exploding()
    )
    assert isinstance(guard.health_check(), ProviderStatus)


def test_health_check_reports_a_retired_model_as_missing():
    guard = provider(_Client(models=("llama-3.1-8b-instant",)))
    assert guard.health_check() is ProviderStatus.MODEL_MISSING


# ---------------------------------------------------------------------------
# Redaction — the Phase 1 boundary
# ---------------------------------------------------------------------------
def test_a_key_echoed_in_provider_error_text_is_redacted():
    error = FakeAPIStatusError(
        401, f"Invalid API Key provided: {FAKE_KEY} for organization org_x"
    )
    with pytest.raises(AuthenticationError) as caught:
        provider(_Client(error=error)).complete(request())
    assert FAKE_KEY not in str(caught.value)


def test_a_key_echoed_in_a_list_failure_is_redacted():
    error = FakeAPIStatusError(403, f"Forbidden (Authorization: Bearer {FAKE_KEY})")
    with pytest.raises(AuthenticationError) as caught:
        provider(_Client(list_error=error)).list_models()
    assert FAKE_KEY not in str(caught.value)


def test_the_adapter_log_sink_masks_the_key(caplog):
    import ai.providers.groq as module

    guard = provider()
    with caplog.at_level(logging.DEBUG, logger=module.__name__):
        module.logger.debug("outbound key=%s", FAKE_KEY)
    guard.complete(request())
    assert FAKE_KEY not in caplog.text


def test_no_key_reaches_the_transport_call_record():
    client = _Client()
    provider(client).complete(request())
    assert FAKE_KEY not in repr(client.calls)


def test_the_adapter_never_stores_the_key_in_its_repr():
    assert FAKE_KEY not in repr(provider())
