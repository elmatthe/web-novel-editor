"""Plan 2b Phase 2 — GeminiProvider, mocked at the transport.

Every test here runs **offline**. No `google.genai` package is imported, no network
call is made, no real API key is read, and no per-user file is touched: each test
either injects a fake client or passes explicit non-existent `secrets_file` /
`dotenv_path` locations, so a developer who happens to have a real GEMINI_API_KEY on
this machine cannot make the suite pass or fail for the wrong reason.

The fake key is deliberately shaped like a real Google key (``AIza…``) so the shape
half of the Phase 1 redactor is exercised as well as the registered-literal half.
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
from ai.disclosure import DISCLOSURE_VERSION
from ai.factory import create_provider
from ai.models import CompletionRequest, ProviderStatus
from ai.providers.gemini import (
    GeminiProvider,
    _safe_message,
    quota_period,
    retry_delay_seconds,
)

FAKE_KEY = "AIzaSyFAKEgeminikeyfortestsonly0000000001"
MODEL = "gemini-3.5-flash"
NOWHERE = Path("this-file-does-not-exist-anywhere.json")


# ---------------------------------------------------------------------------
# Reviewed records — the same nine-field shape config.toml ships.
# ---------------------------------------------------------------------------
def record(
    model_id: str = MODEL,
    *,
    provider: str = "gemini",
    status: str = "stable",
    context_limit: int = 1_048_576,
    output_limit: int = 65_536,
    confidence: str = "confirmed",
) -> ApprovedModel:
    return ApprovedModel(
        id=model_id,
        provider=provider,
        status=status,
        context_limit=context_limit,
        output_limit=output_limit,
        reviewed_on="2026-07-24",
        source_url="https://ai.google.dev/gemini-api/docs/models",
        free_tier_confidence=confidence,
        pilot_status="not-piloted",
    )


APPROVED = (
    record(),
    record("gemini-3.6-flash"),
    record("gemini-3.1-pro-preview", status="preview", confidence="not-free"),
    record("gemini-mystery-flash", confidence="unknown"),
    record("llama-3.3-70b-versatile", provider="groq", context_limit=131072,
           output_limit=32768),
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
# Transport fakes, shaped like google-genai's response objects.
# ---------------------------------------------------------------------------
class FakeAPIError(Exception):
    """Duck-typed stand-in for ``google.genai.errors.APIError`` (has ``.code``)."""

    def __init__(self, code: int, message: str):
        super().__init__(f"{code} {message}")
        self.code = code
        self.message = message


def obj(**fields):
    return pytypes.SimpleNamespace(**fields)


def response(
    text: str = "He walks home.",
    *,
    finish_reason: str | None = "STOP",
    block_reason: str | None = None,
    prompt_tokens: int | None = 23,
    output_tokens: int | None = 7,
    response_id: str | None = "resp-abc123",
    model_version: str | None = MODEL,
):
    parts = [obj(text=text, thought=None)] if text else []
    candidates = [obj(finish_reason=finish_reason, content=obj(parts=parts))]
    return obj(
        text=text or None,
        candidates=candidates,
        prompt_feedback=obj(block_reason=block_reason) if block_reason else None,
        usage_metadata=obj(
            prompt_token_count=prompt_tokens,
            candidates_token_count=output_tokens,
            thoughts_token_count=None,
            total_token_count=None,
        ),
        response_id=response_id,
        model_version=model_version,
    )


class FakeModelsService:
    """Stands in for ``client.models`` — the SDK's models service."""

    def __init__(self, outer: "_Client"):
        self._outer = outer

    def list(self, **kwargs):
        self._outer.list_calls += 1
        if self._outer.list_error:
            raise self._outer.list_error
        return [obj(name=f"models/{name}") for name in self._outer.model_ids]

    def generate_content(self, **kwargs):
        self._outer.calls.append(kwargs)
        if self._outer.generate_error:
            raise self._outer.generate_error
        return self._outer.response


class _Client:
    """In-process stand-in for ``genai.Client``. Nothing here touches a network."""

    def __init__(
        self,
        *,
        models=(MODEL, "gemini-3.6-flash"),
        response=None,
        list_error=None,
        generate_error=None,
    ):
        self.model_ids = models
        self.response = response if response is not None else globals()["response"]()
        self.list_error = list_error
        self.generate_error = generate_error
        self.calls: list[dict] = []
        self.list_calls = 0
        self.models = FakeModelsService(self)


def provider(client=None, **kwargs):
    kwargs.setdefault("model_id", MODEL)
    kwargs.setdefault("approved_models", APPROVED)
    kwargs.setdefault("api_key", FAKE_KEY)
    return GeminiProvider(client=client if client is not None else _Client(), **kwargs)


# ---------------------------------------------------------------------------
# SDK isolation
# ---------------------------------------------------------------------------
def test_importing_the_adapter_does_not_import_the_google_sdk():
    assert "google.genai" not in sys.modules


def cleared_guard_context(tmp_path, model_id: str = MODEL) -> dict:
    """A run context the Plan 2b Phase 7a spend guard clears.

    Since 7a the factory refuses to build any cloud adapter that the guard has not
    cleared, so an adapter test that goes through the factory has to supply one. Every
    location is hermetic: a fake key in an injected environment, a settings file written
    here, and secrets/dotenv paths that do not exist.
    """
    import json

    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"ai": {"cloud_disclosure": {"gemini": DISCLOSURE_VERSION}}}),
        encoding="utf-8",
    )
    return {
        "ai_table": {
            "gemini": {
                "enabled": True,
                "model": model_id,
                "strict_free_tier_only": True,
            },
            "approved_models": [m.as_dict() for m in APPROVED],
        },
        "model_id": model_id,
        "environ": {"GEMINI_API_KEY": FAKE_KEY},
        "secrets_file": tmp_path / "no-secrets.json",
        "dotenv_path": tmp_path / "no.env",
        "settings_file": settings,
    }


def test_factory_constructs_adapter_without_loading_sdk(tmp_path):
    loaded = []
    built = create_provider(
        "gemini",
        guard_context=cleared_guard_context(tmp_path),
        model_id=MODEL,
        approved_models=APPROVED,
        api_key=FAKE_KEY,
        sdk_loader=lambda: loaded.append(True),
    )
    # Foundation import-isolation tests deliberately reload the ``ai`` package, so the
    # lazily imported class is not always the same object this module imported.
    # Assert the factory's result without depending on stale class identity.
    assert type(built).__name__ == "GeminiProvider"
    assert built.capabilities().provider_name == "gemini"
    assert loaded == []


def test_missing_sdk_reports_package_unavailable_rather_than_crashing():
    def boom():
        raise ImportError("No module named 'google.genai'")

    guard = GeminiProvider(
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
    assert caps.provider_name == "gemini"
    assert caps.is_local is False
    assert caps.model_ids == (MODEL,)
    assert caps.context_limit == 1_048_576
    assert caps.max_output_tokens == 65_536
    assert caps.supports_streaming is False
    # Google documents no rate-limit response headers (Phase 0 correction #4,
    # re-verified 2026-07-24), so Phase 4 must run this provider off a floor.
    assert caps.exposes_rate_limits is False
    assert caps.privacy_disclosure_id


def test_explicit_max_output_override_caps_but_never_raises_the_record():
    assert provider(max_output_tokens=4096).capabilities().max_output_tokens == 4096
    assert provider(max_output_tokens=999_999).capabilities().max_output_tokens == 65_536


def test_capabilities_offer_no_model_when_the_configured_one_is_refused():
    caps = provider(model_id="gemini-not-approved").capabilities()
    assert caps.model_ids == ()
    assert caps.max_output_tokens == 0


# ---------------------------------------------------------------------------
# Model listing and approved-record filtering
# ---------------------------------------------------------------------------
def test_list_models_strips_the_models_prefix():
    assert provider().list_models() == [MODEL, "gemini-3.6-flash"]


def test_approved_choices_are_the_intersection_of_live_and_reviewed_models():
    client = _Client(models=(MODEL, "gemini-3.6-flash", "gemini-9.9-unreviewed"))
    # gemini-9.9-unreviewed is live but not reviewed; the preview/not-free and
    # unknown-confidence records are reviewed but refused in strict mode.
    assert provider(client).approved_model_choices() == (MODEL, "gemini-3.6-flash")


def test_approved_choices_exclude_another_providers_approved_model():
    client = _Client(models=(MODEL, "llama-3.3-70b-versatile"))
    assert "llama-3.3-70b-versatile" not in provider(client).approved_model_choices()


# ---------------------------------------------------------------------------
# Refusals — nothing is ever substituted
# ---------------------------------------------------------------------------
def test_non_approved_model_is_refused_and_never_calls_the_provider():
    client = _Client()
    guard = provider(client, model_id="gemini-3.9-imaginary")
    with pytest.raises(ModelUnavailable):
        guard.complete(request(model="gemini-3.9-imaginary"))
    assert client.calls == []


def test_unknown_free_tier_confidence_is_refused_in_strict_mode():
    with pytest.raises(ModelUnavailable) as caught:
        provider(model_id="gemini-mystery-flash").complete(
            request(model="gemini-mystery-flash")
        )
    assert caught.value.retryable is False
    assert "free_tier_confidence" in str(caught.value)


def test_preview_and_not_free_model_is_refused_in_strict_mode():
    with pytest.raises(ModelUnavailable):
        provider(model_id="gemini-3.1-pro-preview").complete(
            request(model="gemini-3.1-pro-preview")
        )


def test_moving_alias_is_refused_even_if_hand_edited_into_the_config():
    approved = APPROVED + (record("gemini-flash-latest"),)
    with pytest.raises(ModelUnavailable) as caught:
        provider(model_id="gemini-flash-latest", approved_models=approved).complete(
            request(model="gemini-flash-latest")
        )
    assert "alias" in str(caught.value).lower()


def test_a_groq_approved_model_is_not_callable_through_gemini():
    with pytest.raises(ModelUnavailable):
        provider(model_id="llama-3.3-70b-versatile").complete(
            request(model="llama-3.3-70b-versatile")
        )


def test_request_for_a_different_model_than_the_configured_one_is_refused():
    client = _Client()
    with pytest.raises(ModelUnavailable):
        provider(client).complete(request(model="gemini-3.6-flash"))
    assert client.calls == []


def test_retired_model_makes_the_provider_unavailable_with_no_substitution():
    client = _Client(models=("gemini-3.6-flash",))  # the configured one is gone
    guard = provider(client)
    assert guard.health_check() is ProviderStatus.MODEL_MISSING
    with pytest.raises(ModelUnavailable) as caught:
        guard.complete(request())
    message = str(caught.value)
    assert "retired" in message
    assert "gemini-3.6-flash" not in message  # names no replacement
    assert client.calls == []


def test_an_empty_live_list_is_unverifiable_not_retired():
    client = _Client(models=())
    guard = provider(client)
    assert guard.health_check() is not ProviderStatus.MODEL_MISSING
    assert guard.complete(request()).text == "He walks home."


def test_no_substitution_helper_exists_on_the_adapter():
    import ai.providers.gemini as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    for banned in ("def _pick_", "def pick_", "fallback_model", "def newest"):
        assert banned not in source


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------
def test_successful_completion_maps_into_the_2a_result():
    client = _Client()
    result = provider(client).complete(request())
    assert result.text == "He walks home."
    assert result.model_id == MODEL
    assert result.finish_reason == "STOP"
    assert result.truncated is False
    assert result.provider_request_id == "resp-abc123"
    assert result.input_tokens == 23
    assert result.output_tokens == 7
    assert result.duration_seconds >= 0


def test_the_model_actually_used_is_reported_not_the_one_requested():
    client = _Client(response=response(model_version="gemini-3.5-flash-002"))
    assert provider(client).complete(request()).model_id == "gemini-3.5-flash-002"


def test_missing_usage_metadata_reports_none_rather_than_inventing_counts():
    client = _Client(response=response(prompt_tokens=None, output_tokens=None))
    result = provider(client).complete(request())
    assert result.input_tokens is None
    assert result.output_tokens is None


def test_request_sends_the_explicit_bounded_output_and_deterministic_settings():
    client = _Client()
    provider(client).complete(request(maximum=500))
    sent = client.calls[0]
    assert sent["model"] == MODEL
    assert sent["contents"] == "He walk home."
    config = sent["config"]
    assert config["system_instruction"] == "Correct only certain grammar errors."
    assert config["max_output_tokens"] == 500  # the request's cap, bounded
    assert 0 < config["max_output_tokens"] <= 65_536
    assert config["temperature"] == 0.0
    assert config["seed"] == 17
    assert config["candidate_count"] == 1


def test_thinking_is_disabled_so_it_cannot_eat_the_output_budget():
    client = _Client()
    provider(client).complete(request())
    thinking = client.calls[0]["config"]["thinking_config"]
    assert thinking.get("include_thoughts") is False
    assert thinking.get("thinking_budget") == 0 or thinking.get("thinking_level")


def test_gemini_three_models_use_thinking_level_not_the_zero_budget():
    client = _Client()
    provider(client, model_id="gemini-3.6-flash").complete(
        request(model="gemini-3.6-flash")
    )
    thinking = client.calls[0]["config"]["thinking_config"]
    assert thinking.get("thinking_level") == "MINIMAL"
    assert "thinking_budget" not in thinking


# ---------------------------------------------------------------------------
# Finish-reason mapping — the fail-closed rules
# ---------------------------------------------------------------------------
def test_max_tokens_is_truncation_and_is_eligible_for_one_retry():
    client = _Client(response=response("He walks ho", finish_reason="MAX_TOKENS"))
    with pytest.raises(InvalidResponse) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is True
    assert "truncat" in str(caught.value).lower()


@pytest.mark.parametrize(
    "reason",
    ["SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "LANGUAGE"],
)
def test_content_blocks_fail_permanently_rather_than_retrying(reason):
    client = _Client(response=response("partial", finish_reason=reason))
    with pytest.raises(InvalidResponse) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is False


def test_a_blocked_prompt_is_reported_before_any_candidate_is_read():
    client = _Client(
        response=response("", finish_reason=None, block_reason="SAFETY")
    )
    with pytest.raises(InvalidResponse) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is False
    assert "block" in str(caught.value).lower()


def test_an_unknown_finish_reason_fails_closed_and_never_returns_the_text():
    client = _Client(
        response=response("He walks home.", finish_reason="SOME_FUTURE_REASON")
    )
    with pytest.raises(InvalidResponse) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is False
    assert "SOME_FUTURE_REASON" in str(caught.value)
    assert "He walks home." not in str(caught.value)


@pytest.mark.parametrize("reason", [None, "", "FINISH_REASON_UNSPECIFIED"])
def test_an_absent_or_unspecified_finish_reason_also_fails_closed(reason):
    client = _Client(response=response("He walks home.", finish_reason=reason))
    with pytest.raises(InvalidResponse) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is False


def test_a_stop_with_no_text_is_not_a_success():
    client = _Client(response=response("", finish_reason="STOP"))
    with pytest.raises(InvalidResponse):
        provider(client).complete(request())


# ---------------------------------------------------------------------------
# Context limits
# ---------------------------------------------------------------------------
def test_input_beyond_the_reviewed_context_limit_is_refused_before_the_call():
    client = _Client()
    small = (record(context_limit=800, output_limit=256),) + APPROVED[1:]
    with pytest.raises(ContextTooLong):
        provider(client, approved_models=small).complete(request("word " * 4000))
    assert client.calls == []


def test_a_provider_side_token_limit_error_maps_to_context_too_long():
    client = _Client(
        generate_error=FakeAPIError(
            400, "INVALID_ARGUMENT: The input token count exceeds the maximum."
        )
    )
    with pytest.raises(ContextTooLong) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is False


# ---------------------------------------------------------------------------
# Error mapping — retryable vs permanent
# ---------------------------------------------------------------------------
def test_no_key_anywhere_is_an_authentication_error_not_a_crash():
    guard = GeminiProvider(
        model_id=MODEL,
        approved_models=APPROVED,
        client=_Client(),
        environ={},
        secrets_file=NOWHERE,
        dotenv_path=NOWHERE,
    )
    assert guard.health_check() is ProviderStatus.AUTH_MISSING
    with pytest.raises(AuthenticationError) as caught:
        guard.complete(request())
    assert caught.value.retryable is False


def test_a_key_in_the_environment_is_found_without_touching_the_user_profile():
    guard = GeminiProvider(
        model_id=MODEL,
        approved_models=APPROVED,
        client=_Client(),
        environ={"GEMINI_API_KEY": FAKE_KEY},
        secrets_file=NOWHERE,
        dotenv_path=NOWHERE,
    )
    assert guard.health_check() is ProviderStatus.OK


@pytest.mark.parametrize("code", [401, 403])
def test_rejected_credentials_map_to_a_permanent_authentication_error(code):
    client = _Client(generate_error=FakeAPIError(code, "API key not valid"))
    with pytest.raises(AuthenticationError) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is False


def test_a_404_means_the_model_is_gone_not_that_the_service_is_down():
    client = _Client(generate_error=FakeAPIError(404, "models/x is not found"))
    with pytest.raises(ModelUnavailable):
        provider(client).complete(request())


def test_a_plain_429_is_a_retryable_rate_limit():
    client = _Client(
        generate_error=FakeAPIError(429, "RESOURCE_EXHAUSTED: too many requests")
    )
    with pytest.raises(RateLimited) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is True


def test_a_per_day_429_is_daily_quota_exhaustion_and_is_not_retried():
    client = _Client(
        generate_error=FakeAPIError(
            429,
            "RESOURCE_EXHAUSTED: quota metric generate_content_free_tier_requests, "
            "limit GenerateRequestsPerDayPerProjectPerModel",
        )
    )
    with pytest.raises(DailyQuotaExhausted) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is False


@pytest.mark.parametrize("code", [500, 502, 503, 504])
def test_server_side_faults_are_retryable_outages(code):
    client = _Client(generate_error=FakeAPIError(code, "backend unavailable"))
    with pytest.raises(ProviderUnavailable) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is True


def test_a_network_failure_is_a_transient_network_error():
    class ConnectError(Exception):
        pass

    client = _Client(generate_error=ConnectError("connection refused"))
    with pytest.raises(TransientNetworkError) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is True


def test_a_timeout_is_a_transient_network_error():
    client = _Client(generate_error=TimeoutError("read timed out"))
    with pytest.raises(TransientNetworkError):
        provider(client).complete(request())


# ---------------------------------------------------------------------------
# health_check never raises and distinguishes its states
# ---------------------------------------------------------------------------
def test_health_check_reports_ok_when_everything_lines_up():
    assert provider().health_check() is ProviderStatus.OK


@pytest.mark.parametrize(
    "error,expected",
    [
        (FakeAPIError(403, "API key not valid"), ProviderStatus.AUTH_MISSING),
        (FakeAPIError(429, "too many requests"), ProviderStatus.QUOTA_EXHAUSTED),
        (FakeAPIError(503, "backend unavailable"), ProviderStatus.SERVICE_DOWN),
        (TimeoutError("read timed out"), ProviderStatus.TIMEOUT),
    ],
)
def test_health_check_distinguishes_transport_failures(error, expected):
    assert provider(_Client(list_error=error)).health_check() is expected


def test_health_check_never_raises_even_on_an_unexpected_fault():
    class Weird(Exception):
        pass

    assert provider(_Client(list_error=Weird("?"))).health_check() in tuple(
        ProviderStatus
    )


# ---------------------------------------------------------------------------
# Redaction — the injected key must never surface
# ---------------------------------------------------------------------------
def test_a_key_echoed_in_provider_error_text_is_redacted():
    leak = f"400 INVALID_ARGUMENT https://generativelanguage.googleapis.com/v1?key={FAKE_KEY}"
    client = _Client(generate_error=FakeAPIError(400, leak))
    with pytest.raises(Exception) as caught:
        provider(client).complete(request())
    assert FAKE_KEY not in str(caught.value)
    assert FAKE_KEY not in repr(caught.value)


def test_a_key_echoed_in_a_list_failure_is_redacted():
    client = _Client(list_error=FakeAPIError(400, f"bad key={FAKE_KEY}"))
    with pytest.raises(Exception) as caught:
        provider(client).list_models()
    assert FAKE_KEY not in str(caught.value)


def test_the_adapter_log_sink_masks_the_key(caplog):
    guard = provider()
    with caplog.at_level(logging.DEBUG, logger="ai.providers.gemini"):
        guard.complete(request())
        logging.getLogger("ai.providers.gemini").debug("probe key=%s", FAKE_KEY)
    rendered = "\n".join(r.getMessage() for r in caplog.records)
    assert FAKE_KEY not in rendered
    assert "[REDACTED]" in rendered


def test_no_key_reaches_the_transport_call_record():
    client = _Client()
    provider(client).complete(request())
    assert FAKE_KEY not in repr(client.calls)


def test_the_adapter_never_stores_the_key_in_its_repr():
    assert FAKE_KEY not in repr(provider())


# ---------------------------------------------------------------------------
# Phase 8 bug fix — read the quota period off the STRUCTURED QuotaFailure body
#
# Phase 7b: Gemini's daily exhaustion classified as a per-minute limit, so prefer-AI
# retried chapter after chapter for ~35 minutes instead of checkpointing. The evidence
# was always in the response — `error.details[]` carries a `google.rpc.QuotaFailure`
# whose `quotaId` names the exact period — but `str(APIError)` puts the human message and
# its documentation URL first, and `_safe_message` truncates at 300 characters to bound
# what reaches a log. `quotaId` sits past character 400. These tests build the error the
# way the SDK really does, long message included, so the truncation is reproduced rather
# than assumed.
# ---------------------------------------------------------------------------
_GOOGLE_429_MESSAGE = (
    "You exceeded your current quota, please check your plan and billing details. "
    "For more information on this error, head to: "
    "https://ai.google.dev/gemini-api/docs/rate-limits."
)


class RealisticAPIError(Exception):
    """Mimics ``google.genai.errors.APIError``: ``.details`` is the whole response JSON
    and ``__str__`` is ``f"{code} {status}. {details}"`` (verified via Context7 against
    the SDK's own ``errors.py``)."""

    def __init__(self, code: int, violations, *, retry_delay: str | None = None):
        details = []
        if violations is not None:
            details.append(
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": violations,
                }
            )
        if retry_delay is not None:
            details.append(
                {"@type": "type.googleapis.com/google.rpc.RetryInfo",
                 "retryDelay": retry_delay}
            )
        self.details = {
            "error": {
                "code": code,
                "message": _GOOGLE_429_MESSAGE,
                "status": "RESOURCE_EXHAUSTED",
                "details": details,
            }
        }
        self.code = code
        self.message = _GOOGLE_429_MESSAGE
        super().__init__(f"{code} RESOURCE_EXHAUSTED. {self.details}")


def _violation(quota_id: str) -> dict:
    return {
        "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
        "quotaId": quota_id,
        "quotaDimensions": {"model": "gemini-3.6-flash", "location": "global"},
        "quotaValue": "50",
    }


def test_the_truncated_message_really_does_hide_the_quota_id():
    """The premise of this whole fix, asserted rather than believed."""
    error = RealisticAPIError(429, [_violation("GenerateRequestsPerDayPerProjectPerModel-FreeTier")])
    assert "PerDay" in str(error)
    assert "PerDay" not in _safe_message(error), (
        "if this ever passes the classifier the string check would have sufficed"
    )


def test_a_daily_quota_id_is_read_from_the_structured_body():
    client = _Client(
        generate_error=RealisticAPIError(
            429, [_violation("GenerateRequestsPerDayPerProjectPerModel-FreeTier")]
        )
    )
    with pytest.raises(DailyQuotaExhausted) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is False


@pytest.mark.parametrize(
    "quota_id",
    [
        "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
        "GenerateContentInputTokensPerModelPerMinute-FreeTier",
    ],
)
def test_a_per_minute_quota_id_stays_a_retryable_rate_limit(quota_id):
    client = _Client(generate_error=RealisticAPIError(429, [_violation(quota_id)]))
    with pytest.raises(RateLimited) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is True


def test_a_body_naming_both_periods_fails_closed_to_daily():
    """Waiting a minute for a quota that resets tomorrow is the failure being fixed."""
    client = _Client(
        generate_error=RealisticAPIError(
            429,
            [
                _violation("GenerateRequestsPerMinutePerProjectPerModel-FreeTier"),
                _violation("GenerateRequestsPerDayPerProjectPerModel-FreeTier"),
            ],
        )
    )
    with pytest.raises(DailyQuotaExhausted):
        provider(client).complete(request())


def test_retry_info_becomes_the_authoritative_wait():
    client = _Client(
        generate_error=RealisticAPIError(
            429,
            [_violation("GenerateRequestsPerMinutePerProjectPerModel-FreeTier")],
            retry_delay="36s",
        )
    )
    with pytest.raises(RateLimited) as caught:
        provider(client).complete(request())
    # Phase 4's limiter prefers this over its configured floor.
    assert caught.value.retry_after_seconds == 36.0


def test_a_429_with_no_quota_details_is_still_a_plain_rate_limit():
    """Fail-safe: no structured evidence means no claim. The limiter's own escalation
    window is what stops such a run, not a guess made here."""
    client = _Client(generate_error=RealisticAPIError(429, None))
    with pytest.raises(RateLimited) as caught:
        provider(client).complete(request())
    assert caught.value.retryable is True
    assert caught.value.retry_after_seconds is None


@pytest.mark.parametrize(
    "body",
    [None, "not a mapping", {"error": "not a mapping"}, {"error": {"details": "nope"}},
     {"error": {"details": [None, 7, {"@type": "other"}]}}],
)
def test_malformed_error_bodies_never_raise_out_of_the_classifier(body):
    error = FakeAPIError(429, "too many requests")
    error.details = body
    assert quota_period(error) is None
    assert retry_delay_seconds(error) is None


# ---------------------------------------------------------------------------
# The per-day quota that REFILLS (DECISIONS #072) -- captured live 2026-07-27
# ---------------------------------------------------------------------------
# The 429 that stopped the frozen re-run, verbatim from `error.details`:
#
#   quotaId:     GenerateRequestsPerDayPerProjectPerModel-FreeTier
#   quotaMetric: generativelanguage.googleapis.com/generate_content_free_tier_requests
#   quotaValue:  20
#   RetryInfo.retryDelay: "53s"
#
# Both halves are true at once: it IS the per-day quota, and the wait IS 53 seconds.
# The classifier was never wrong. What was wrong was throwing the 53 away.

def test_the_real_captured_429_reads_as_per_day_AND_carries_a_short_delay():
    """The evidence for #072, pinned so the premise cannot rot."""
    error = RealisticAPIError(
        429, [_violation("GenerateRequestsPerDayPerProjectPerModel-FreeTier")],
        retry_delay="53s",
    )
    assert quota_period(error) == "day"
    assert retry_delay_seconds(error) == 53.0


def test_a_daily_quota_error_carries_the_retry_delay_to_the_limiter():
    """The adapter must SURFACE the delay; the limiter decides what to do with it.

    Before #072 `retry_after_seconds` was attached only to `RateLimited`, so a per-day
    429 reached the limiter with the one number that could have kept the run going
    already discarded.
    """
    guard = provider(_Client(), model_id=MODEL)
    error = RealisticAPIError(
        429, [_violation("GenerateRequestsPerDayPerProjectPerModel-FreeTier")],
        retry_delay="53s",
    )
    with pytest.raises(DailyQuotaExhausted) as caught:
        guard._raise_transport_error(error)

    assert caught.value.retry_after_seconds == 53.0
    # Still non-retryable at the adapter level: the LIMITER owns the wait decision,
    # not the adapter, and not the editor own retry loop.
    assert caught.value.retryable is False


def test_a_daily_quota_error_with_no_retry_info_surfaces_none_not_a_guess():
    guard = provider(_Client(), model_id=MODEL)
    error = RealisticAPIError(
        429, [_violation("GenerateRequestsPerDayPerProjectPerModel-FreeTier")],
        retry_delay=None,
    )
    with pytest.raises(DailyQuotaExhausted) as caught:
        guard._raise_transport_error(error)
    assert caught.value.retry_after_seconds is None
