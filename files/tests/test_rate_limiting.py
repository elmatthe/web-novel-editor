"""Plan 2b Phase 4 — rate limiting and quota classification.

Everything here is offline and hermetic. No cloud SDK is imported, no key is read,
no network call is made, and — the load-bearing property of this suite — **nothing
ever really sleeps**: every limiter under test is built with an injected monotonic
clock and an injected sleeper that only records what it was asked to wait for.

**Every ``ai.*`` import in this file is at module level, deliberately.**
``test_ai_foundation.py::test_import_has_no_filesystem_or_sdk_side_effects`` pops every
``ai.*`` module out of ``sys.modules`` and re-imports the package, so a module that binds
some names before that happens and imports others afterwards ends up holding two
generations of the same classes. The limiter's ``except (RateLimited, ...)`` would then
fail to catch an exception this file built — in the full-suite run only, never in
isolation. One consistent generation per test module is the fix; Phases 2 and 3 hit the
same hazard and solved their version of it the same way, by adapting the test rather than
the product.
"""

from __future__ import annotations

import random
import sys
import threading
from pathlib import Path

import pytest

from ai.cloud import CLOUD_DEFAULTS, provider_settings
from ai.config import load_config
from ai.errors import (
    AIProviderError,
    AuthenticationError,
    ContextTooLong,
    DailyQuotaExhausted,
    InvalidResponse,
    ProviderUnavailable,
    RateLimited,
    RequestCancelled,
    TransientNetworkError,
)
from ai.chunking import estimate_tokens
from ai.editor import AIEditor, EditorOptions
from ai.models import (
    CompletionRequest,
    CompletionResult,
    ProviderCapabilities,
    ProviderStatus,
    RunPolicy,
)
from ai.provider import AIProvider
from ai.providers.groq import RateLimitSnapshot, read_rate_limits
from ai.rate_limits import (
    DAILY_KINDS,
    FlooredRateLimiter,
    HeaderDrivenRateLimiter,
    LimiterSettings,
    LimitKind,
    RateLimitedProvider,
    classify_limit,
    limiter_for,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config.toml"


# --------------------------------------------------------------------------
# Test doubles — an injected clock and an injected sleeper, nothing real
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def nothing_in_this_suite_may_actually_sleep(monkeypatch):
    """A real ``time.sleep`` anywhere in this file is a test bug, not a slow test."""

    def forbidden(_seconds):  # pragma: no cover - only runs if a test regresses
        raise AssertionError("a test tried to really sleep")

    monkeypatch.setattr("time.sleep", forbidden)


class FakeClock:
    """Monotonic and wall clocks that move independently, so a wall-clock jump can be
    simulated without touching any duration the limiter measures."""

    def __init__(self, monotonic: float = 1_000.0, wall: float = 1_800_000_000.0):
        self._monotonic = monotonic
        self._wall = wall

    def monotonic(self) -> float:
        return self._monotonic

    def wall(self) -> float:
        return self._wall

    def advance(self, seconds: float) -> None:
        self._monotonic += seconds
        self._wall += seconds

    def jump_wall_only(self, seconds: float) -> None:
        """A daylight-saving change, an NTP correction, or a user editing the clock."""
        self._wall += seconds

    def jump_monotonic_only(self, seconds: float) -> None:
        """A resume from system suspend on a platform whose monotonic includes it."""
        self._monotonic += seconds


class RecordingSleeper:
    """Records every requested wait and advances the fake clock instead of sleeping."""

    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.calls: list[float] = []
        self.interrupt_after: int | None = None

    @property
    def total(self) -> float:
        return sum(self.calls)

    def __call__(self, seconds: float) -> bool:
        self.calls.append(seconds)
        if self.interrupt_after is not None and len(self.calls) >= self.interrupt_after:
            return True  # woken by Stop
        self.clock.advance(seconds)
        return False


def build_limiter(cls=FlooredRateLimiter, *, clock=None, sleeper=None, **overrides):
    clock = clock or FakeClock()
    sleeper = sleeper if sleeper is not None else RecordingSleeper(clock)
    settings = LimiterSettings.from_settings(overrides, provider="groq")
    limiter = cls(
        settings=settings,
        provider_name=overrides.get("provider_name", "groq"),
        model_id="llama-3.3-70b-versatile",
        monotonic=clock.monotonic,
        wall=clock.wall,
        sleeper=sleeper,
    )
    return limiter, clock, sleeper


# --------------------------------------------------------------------------
# Configured floors — the limiter owns no numbers of its own
# --------------------------------------------------------------------------
def test_committed_config_carries_limiter_floors_for_both_cloud_providers():
    ai_table = load_config(CONFIG_PATH)
    for provider in ("gemini", "groq"):
        section = ai_table.get(provider)
        assert isinstance(section, dict), f"[ai.{provider}] is missing"
        for key in (
            "rpm_floor",
            "tpm_floor",
            "rate_limit_floor_seconds",
            "backoff_base_seconds",
            "backoff_max_seconds",
            "backoff_jitter_ratio",
            "max_attempts",
            "max_wait_seconds",
        ):
            assert key in section, f"[ai.{provider}] is missing {key}"


def test_limiter_settings_are_read_from_the_provider_subtable():
    ai_table = load_config(CONFIG_PATH)
    settings = LimiterSettings.from_settings(
        provider_settings(ai_table, "groq"), provider="groq"
    )
    assert settings.rpm_floor == ai_table["groq"]["rpm_floor"]
    assert settings.max_wait_seconds == ai_table["groq"]["max_wait_seconds"]


def test_the_limiter_module_contains_no_hardcoded_provider_limit():
    """Floors are configuration, not constants buried in the limiter."""
    source = (
        REPO_ROOT / "scripts" / "Universal" / "ai" / "rate_limits.py"
    ).read_text(encoding="utf-8")
    for figure in ("30", "6000", "12000", "100000", "14400", "500000", "200000"):
        assert f"= {figure}" not in source, f"limit {figure} is hardcoded"


def test_a_junk_configured_floor_falls_back_to_the_shipped_default():
    settings = LimiterSettings.from_settings(
        {"rpm_floor": "not a number", "backoff_max_seconds": -5}, provider="gemini"
    )
    assert settings.rpm_floor == CLOUD_DEFAULTS["gemini"]["rpm_floor"]
    assert settings.backoff_max_seconds == CLOUD_DEFAULTS["gemini"]["backoff_max_seconds"]


def test_the_minimum_interval_comes_from_the_configured_requests_per_minute_floor():
    settings = LimiterSettings.from_settings({"rpm_floor": 30}, provider="groq")
    assert settings.min_interval_seconds == pytest.approx(2.0)


def test_a_zero_requests_per_minute_floor_means_no_minimum_interval():
    settings = LimiterSettings.from_settings({"rpm_floor": 0}, provider="gemini")
    assert settings.min_interval_seconds == 0.0


# --------------------------------------------------------------------------
# Classification — RPM / TPM / RPD / TPD / capacity / transient
# --------------------------------------------------------------------------
def test_a_per_minute_rate_limit_is_classified_as_requests_per_minute_by_default():
    assert classify_limit(RateLimited("slow down")) is LimitKind.REQUESTS_PER_MINUTE


def test_a_rate_limit_naming_tokens_per_minute_is_classified_as_tokens_per_minute():
    exc = RateLimited("Rate limit reached on tokens per minute (TPM)")
    assert classify_limit(exc) is LimitKind.TOKENS_PER_MINUTE


def test_a_daily_quota_error_naming_tokens_per_day_is_classified_as_tokens_per_day():
    exc = DailyQuotaExhausted("Rate limit reached on tokens per day (TPD)")
    assert classify_limit(exc) is LimitKind.TOKENS_PER_DAY


def test_a_daily_quota_error_naming_requests_per_day_is_classified_as_requests_per_day():
    exc = DailyQuotaExhausted("Limit reached on requests per day (RPD)")
    assert classify_limit(exc) is LimitKind.REQUESTS_PER_DAY


def test_an_unspecific_daily_quota_error_is_still_daily():
    kind = classify_limit(DailyQuotaExhausted("free daily quota is used up"))
    assert kind is LimitKind.DAILY_UNSPECIFIED
    assert kind in DAILY_KINDS


def test_every_daily_kind_is_marked_daily_and_no_per_minute_kind_is():
    assert LimitKind.REQUESTS_PER_DAY in DAILY_KINDS
    assert LimitKind.TOKENS_PER_DAY in DAILY_KINDS
    assert LimitKind.REQUESTS_PER_MINUTE not in DAILY_KINDS
    assert LimitKind.TOKENS_PER_MINUTE not in DAILY_KINDS


def test_a_retryable_provider_error_is_classified_as_provider_capacity_not_quota():
    kind = classify_limit(ProviderUnavailable("service overloaded", retryable=True))
    assert kind is LimitKind.PROVIDER_CAPACITY
    assert kind not in DAILY_KINDS


def test_a_network_fault_is_classified_as_transient():
    assert classify_limit(TransientNetworkError("connection reset")) is LimitKind.TRANSIENT


@pytest.mark.parametrize(
    "exc",
    [
        ContextTooLong("too long"),
        AuthenticationError("bad key"),
        InvalidResponse("unknown finish reason", retryable=False),
        RequestCancelled("stopped"),
        ProviderUnavailable("rejected", retryable=False),
    ],
)
def test_errors_that_are_not_the_limiters_business_classify_as_none(exc):
    assert classify_limit(exc) is LimitKind.NONE


# --------------------------------------------------------------------------
# THE ASYMMETRY: Groq requests = per DAY, tokens = per MINUTE
# --------------------------------------------------------------------------
def test_zero_remaining_requests_means_daily_because_groqs_request_counter_is_per_day():
    """Reading this the other way round would wait a minute for tomorrow's quota."""

    snapshot = RateLimitSnapshot(
        remaining_requests=0, reset_requests_seconds=86400.0
    )
    kind = classify_limit(DailyQuotaExhausted("Too Many Requests"), snapshot)
    assert kind is LimitKind.REQUESTS_PER_DAY
    assert kind in DAILY_KINDS


def test_zero_remaining_tokens_means_per_minute_because_groqs_token_counter_is_per_minute():

    snapshot = RateLimitSnapshot(remaining_tokens=0, reset_tokens_seconds=7.66)
    kind = classify_limit(RateLimited("Too Many Requests"), snapshot)
    assert kind is LimitKind.TOKENS_PER_MINUTE
    assert kind not in DAILY_KINDS


def test_the_two_header_pairs_are_not_interchangeable():
    """Swap the pairs and the classification must swap with them."""

    tokens_gone = RateLimitSnapshot(remaining_tokens=0, remaining_requests=900)
    requests_gone = RateLimitSnapshot(remaining_tokens=9000, remaining_requests=0)
    assert classify_limit(RateLimited("429"), tokens_gone) is LimitKind.TOKENS_PER_MINUTE
    assert (
        classify_limit(DailyQuotaExhausted("429"), requests_gone)
        is LimitKind.REQUESTS_PER_DAY
    )


# --------------------------------------------------------------------------
# Conservative floors — the first request of a run cannot outrun a limit
# --------------------------------------------------------------------------
def test_the_first_request_of_a_run_never_waits():
    limiter, _clock, sleeper = build_limiter(rpm_floor=15)
    assert limiter.wait_before_request(estimated_tokens=100) == 0.0
    assert sleeper.calls == []


def test_a_second_immediate_request_is_paced_by_the_configured_floor():
    limiter, _clock, sleeper = build_limiter(rpm_floor=15, tpm_floor=0)
    limiter.wait_before_request(estimated_tokens=100)
    limiter.record_success(estimated_tokens=100)
    waited = limiter.wait_before_request(estimated_tokens=100)
    assert waited == pytest.approx(4.0)  # 60 / 15
    assert sleeper.calls and sum(sleeper.calls) == pytest.approx(4.0)


def test_a_request_that_arrives_after_the_interval_has_passed_does_not_wait():
    limiter, clock, sleeper = build_limiter(rpm_floor=15, tpm_floor=0)
    limiter.wait_before_request(estimated_tokens=100)
    limiter.record_success(estimated_tokens=100)
    clock.advance(10.0)
    assert limiter.wait_before_request(estimated_tokens=100) == 0.0
    assert sleeper.calls == []


def test_the_token_floor_holds_a_request_until_the_minute_window_has_room():
    limiter, _clock, sleeper = build_limiter(rpm_floor=0, tpm_floor=5000)
    limiter.wait_before_request(estimated_tokens=4000)
    limiter.record_success(estimated_tokens=4000)
    waited = limiter.wait_before_request(estimated_tokens=4000)
    assert waited == pytest.approx(60.0)
    assert sleeper.total == pytest.approx(60.0)


def test_a_single_request_larger_than_the_token_floor_proceeds_rather_than_hanging():
    """Waiting cannot make room that a single request alone exceeds; the provider's
    own limit is the authority for that case, not our floor."""
    limiter, _clock, sleeper = build_limiter(rpm_floor=0, tpm_floor=5000)
    assert limiter.wait_before_request(estimated_tokens=9000) == 0.0
    assert sleeper.calls == []


def test_a_token_floor_of_zero_models_no_token_window_at_all():
    limiter, _clock, _sleeper = build_limiter(rpm_floor=0, tpm_floor=0)
    limiter.wait_before_request(estimated_tokens=10**6)
    limiter.record_success(estimated_tokens=10**6)
    assert limiter.wait_before_request(estimated_tokens=10**6) == 0.0


def test_real_token_usage_replaces_the_estimate_when_the_provider_reports_it():
    limiter, _clock, _sleeper = build_limiter(rpm_floor=0, tpm_floor=5000)
    limiter.wait_before_request(estimated_tokens=4000)
    limiter.record_success(estimated_tokens=4000, input_tokens=100, output_tokens=50)
    # 150 real tokens, not the 4000 reserved, so there is room for another request.
    assert limiter.wait_before_request(estimated_tokens=4000) == 0.0


def test_a_missing_usage_report_keeps_the_conservative_estimate():
    limiter, _clock, _sleeper = build_limiter(rpm_floor=0, tpm_floor=5000)
    limiter.wait_before_request(estimated_tokens=4000)
    limiter.record_success(estimated_tokens=4000, input_tokens=None, output_tokens=None)
    assert limiter.wait_before_request(estimated_tokens=4000) > 0.0


# --------------------------------------------------------------------------
# The wait decision table
# --------------------------------------------------------------------------
def test_an_authoritative_retry_after_is_honoured_exactly():
    limiter, _clock, _sleeper = build_limiter(rate_limit_floor_seconds=30)
    exc = RateLimited("Too Many Requests")
    exc.retry_after_seconds = 7.5
    decision = limiter.decide_for_error(exc, attempt=0)
    assert decision.seconds == 7.5
    assert decision.authoritative is True
    assert decision.source == "retry_after"


def test_retry_after_overrides_every_computed_wait_including_the_headers():

    limiter, _clock, _sleeper = build_limiter(rate_limit_floor_seconds=30)
    snapshot = RateLimitSnapshot(
        remaining_tokens=0, reset_tokens_seconds=59.0, retry_after_seconds=3.0
    )
    exc = RateLimited("Too Many Requests")
    exc.rate_limits = snapshot
    exc.retry_after_seconds = 3.0
    decision = limiter.decide_for_error(exc, snapshot=snapshot, attempt=0)
    assert decision.seconds == 3.0
    assert decision.source == "retry_after"


def test_an_honoured_retry_after_is_never_jittered():
    """Jitter on a number the provider gave us either undershoots into overage or
    adds noise to an authoritative instruction."""
    limiter, _clock, _sleeper = build_limiter(backoff_jitter_ratio=0.9)
    seen = set()
    for _ in range(25):
        exc = RateLimited("Too Many Requests")
        exc.retry_after_seconds = 11.0
        seen.add(limiter.decide_for_error(exc, attempt=0).seconds)
    assert seen == {11.0}


def test_a_tokens_per_minute_limit_without_retry_after_uses_the_token_reset_header():

    limiter, _clock, _sleeper = build_limiter(rate_limit_floor_seconds=30)
    snapshot = RateLimitSnapshot(remaining_tokens=0, reset_tokens_seconds=7.66)
    decision = limiter.decide_for_error(
        RateLimited("Too Many Requests"), snapshot=snapshot, attempt=0
    )
    assert decision.kind is LimitKind.TOKENS_PER_MINUTE
    assert decision.seconds == pytest.approx(7.66)
    assert decision.source == "header_reset_tokens"


def test_a_per_minute_wait_never_uses_the_request_reset_header():
    """`x-ratelimit-reset-requests` is the DAY counter's reset. Using it for a
    per-minute wait would sleep for hours."""

    limiter, _clock, _sleeper = build_limiter(rate_limit_floor_seconds=30)
    snapshot = RateLimitSnapshot(remaining_requests=400, reset_requests_seconds=71_000.0)
    decision = limiter.decide_for_error(
        RateLimited("Too Many Requests"), snapshot=snapshot, attempt=0
    )
    assert decision.kind is LimitKind.REQUESTS_PER_MINUTE
    assert decision.seconds == 30.0
    assert decision.source == "floor"


def test_a_rate_limit_with_no_usable_number_falls_back_to_the_configured_floor():
    limiter, _clock, _sleeper = build_limiter(rate_limit_floor_seconds=25)
    decision = limiter.decide_for_error(RateLimited("Too Many Requests"), attempt=0)
    assert decision.seconds == 25.0
    assert decision.source == "floor"
    assert decision.authoritative is False


def test_malformed_headers_fall_back_to_the_floor_rather_than_to_a_guess():

    limiter, _clock, _sleeper = build_limiter(rate_limit_floor_seconds=25)
    snapshot = read_rate_limits(
        {
            "x-ratelimit-remaining-tokens": "not-a-number",
            "x-ratelimit-reset-tokens": "soon-ish",
            "retry-after": "whenever",
        }
    )
    decision = limiter.decide_for_error(
        RateLimited("Too Many Requests"), snapshot=snapshot, attempt=0
    )
    assert decision.seconds == 25.0
    assert decision.source == "floor"


def test_absent_headers_fall_back_to_the_floor():

    limiter, _clock, _sleeper = build_limiter(rate_limit_floor_seconds=25)
    decision = limiter.decide_for_error(
        RateLimited("Too Many Requests"), snapshot=read_rate_limits({}), attempt=0
    )
    assert decision.seconds == 25.0


# --------------------------------------------------------------------------
# Daily exhaustion is never a wait
# --------------------------------------------------------------------------
def test_daily_exhaustion_produces_no_wait_at_all():
    limiter, _clock, sleeper = build_limiter()
    decision = limiter.decide_for_error(
        DailyQuotaExhausted("free daily quota is used up (TPD)"), attempt=0
    )
    assert decision.daily is True
    assert decision.seconds == 0.0
    assert decision.retry is False
    assert sleeper.calls == []


def test_a_day_long_request_reset_header_is_recorded_but_never_slept_on():

    limiter, _clock, sleeper = build_limiter()
    snapshot = RateLimitSnapshot(remaining_requests=0, reset_requests_seconds=86_400.0)
    decision = limiter.decide_for_error(
        DailyQuotaExhausted("Too Many Requests"), snapshot=snapshot, attempt=0
    )
    assert decision.kind is LimitKind.REQUESTS_PER_DAY
    assert decision.seconds == 0.0
    assert decision.reset_seconds == pytest.approx(86_400.0)
    assert decision.reset_known is True
    limiter.wait_for(decision)
    assert sleeper.calls == []


def test_an_unknown_reset_time_is_reported_as_unknown_and_never_guessed():
    limiter, _clock, _sleeper = build_limiter()
    decision = limiter.decide_for_error(
        DailyQuotaExhausted("free daily quota is used up"), attempt=0
    )
    assert decision.reset_known is False
    assert decision.reset_seconds is None


def test_daily_exhaustion_is_recorded_on_the_quota_stop_seam_for_phase_five():
    limiter, clock, _sleeper = build_limiter()
    exc = DailyQuotaExhausted("Groq's free daily quota is used up (TPD)")
    limiter.note_quota_stop(limiter.decide_for_error(exc, attempt=0), exc)
    stop = limiter.quota_stop
    assert stop is not None
    assert stop.is_daily is True
    assert stop.kind is LimitKind.TOKENS_PER_DAY
    assert stop.provider == "groq"
    assert stop.model_id == "llama-3.3-70b-versatile"
    assert stop.reset_known is False
    assert stop.observed_wall == clock.wall()


def test_the_quota_stop_record_carries_no_key_and_no_chapter_text():
    limiter, _clock, _sleeper = build_limiter()
    exc = DailyQuotaExhausted("quota used up for gsk_LIVEKEYSHAPED0000000000000000")
    limiter.note_quota_stop(limiter.decide_for_error(exc, attempt=0), exc)
    serialized = repr(limiter.quota_stop.as_dict())
    assert "gsk_LIVEKEYSHAPED0000000000000000" not in serialized


# --------------------------------------------------------------------------
# Backoff — transients only, jittered, bounded
# --------------------------------------------------------------------------
def test_a_transient_error_is_backed_off_with_jitter_inside_its_bounds():

    clock = FakeClock()
    sleeper = RecordingSleeper(clock)
    settings = LimiterSettings.from_settings(
        {
            "backoff_base_seconds": 2,
            "backoff_max_seconds": 60,
            "backoff_jitter_ratio": 0.5,
        },
        provider="groq",
    )
    limiter = FlooredRateLimiter(
        settings=settings,
        provider_name="groq",
        model_id="m",
        monotonic=clock.monotonic,
        wall=clock.wall,
        sleeper=sleeper,
        random_source=random.Random(1234),
    )
    for attempt, ceiling in ((0, 2.0), (1, 4.0), (2, 8.0)):
        samples = [
            limiter.decide_for_error(
                TransientNetworkError("connection reset"), attempt=attempt
            ).seconds
            for _ in range(40)
        ]
        assert all(ceiling * 0.5 <= s <= ceiling for s in samples)
        assert len(set(samples)) > 1, "backoff is not actually jittered"


def test_backoff_growth_is_bounded_by_the_configured_maximum():
    limiter, _clock, _sleeper = build_limiter(
        backoff_base_seconds=2, backoff_max_seconds=60, backoff_jitter_ratio=0.0
    )
    for attempt in range(0, 20):
        decision = limiter.decide_for_error(
            TransientNetworkError("connection reset"), attempt=attempt
        )
        assert decision.seconds <= 60.0


def test_provider_capacity_errors_are_backed_off_but_are_not_quota():
    limiter, _clock, _sleeper = build_limiter(backoff_jitter_ratio=0.0)
    decision = limiter.decide_for_error(
        ProviderUnavailable("service overloaded", retryable=True), attempt=0
    )
    assert decision.kind is LimitKind.PROVIDER_CAPACITY
    assert decision.source == "backoff"
    assert decision.daily is False
    assert limiter.quota_stop is None


def test_quota_errors_are_never_backed_off():
    limiter, _clock, _sleeper = build_limiter(backoff_jitter_ratio=0.9)
    for exc in (
        RateLimited("Too Many Requests"),
        DailyQuotaExhausted("daily quota used up"),
    ):
        assert limiter.decide_for_error(exc, attempt=0).source != "backoff"


# --------------------------------------------------------------------------
# A wait longer than the session allows becomes a clean stop, not a long sleep
# --------------------------------------------------------------------------
def test_a_wait_longer_than_the_session_maximum_is_not_slept():
    limiter, _clock, sleeper = build_limiter(max_wait_seconds=900)
    exc = RateLimited("Too Many Requests")
    exc.retry_after_seconds = 4_000.0
    decision = limiter.decide_for_error(exc, attempt=0)
    assert decision.retry is False
    assert decision.too_long is True
    assert decision.seconds == 4_000.0  # reported honestly, just not slept
    limiter.wait_for(decision)
    assert sleeper.calls == []


def test_an_over_long_wait_surfaces_on_the_same_seam_but_is_not_marked_daily():
    limiter, _clock, _sleeper = build_limiter(max_wait_seconds=900)
    exc = RateLimited("Too Many Requests")
    exc.retry_after_seconds = 4_000.0
    limiter.note_quota_stop(limiter.decide_for_error(exc, attempt=0), exc)
    assert limiter.quota_stop is not None
    assert limiter.quota_stop.is_daily is False
    assert limiter.quota_stop.reset_seconds == pytest.approx(4_000.0)


# --------------------------------------------------------------------------
# Monotonic time, clock jumps, and system sleep
# --------------------------------------------------------------------------
def test_a_wall_clock_jump_during_a_countdown_changes_nothing():
    clock = FakeClock()
    sliced: list[float] = []

    def sleeper(seconds: float) -> bool:
        sliced.append(seconds)
        clock.jump_wall_only(-7_200.0 if len(sliced) == 1 else 3_600.0)
        clock.advance(seconds)
        return False

    limiter, _clock, _s = build_limiter(clock=clock, sleeper=sleeper)
    decision = limiter.decide_for_error(RateLimited("x"), attempt=0)
    slept = limiter.wait_for(decision)
    assert slept == pytest.approx(decision.seconds)
    assert sum(sliced) == pytest.approx(decision.seconds)


def test_a_monotonic_jump_forward_ends_the_countdown_instead_of_corrupting_it():
    """Resuming from system suspend must not leave a negative or extended countdown."""
    clock = FakeClock()
    sliced: list[float] = []

    def sleeper(seconds: float) -> bool:
        sliced.append(seconds)
        clock.jump_monotonic_only(10_000.0)  # woke up from suspend
        return False

    limiter, _clock, _s = build_limiter(clock=clock, sleeper=sleeper)
    decision = limiter.decide_for_error(RateLimited("x"), attempt=0)
    slept = limiter.wait_for(decision)
    assert slept >= 0.0
    assert len(sliced) == 1, "the countdown should end, not keep waiting"


def test_durations_are_measured_on_the_monotonic_clock_not_the_wall_clock():
    clock = FakeClock()
    limiter, _clock, _sleeper = build_limiter(clock=clock, rpm_floor=15, tpm_floor=0)
    limiter.wait_before_request(estimated_tokens=10)
    limiter.record_success(estimated_tokens=10)
    clock.jump_wall_only(86_400.0)  # a day passes on the wall clock only
    assert limiter.wait_before_request(estimated_tokens=10) == pytest.approx(4.0)


# --------------------------------------------------------------------------
# Interruptible waits — Stop and window close
# --------------------------------------------------------------------------
def test_stop_during_a_wait_breaks_it_immediately_and_raises_request_cancelled():
    clock = FakeClock()
    stop = threading.Event()
    sliced: list[float] = []

    def sleeper(seconds: float) -> bool:
        sliced.append(seconds)
        stop.set()  # the user pressed Stop mid-countdown
        return True

    settings = LimiterSettings.from_settings(
        {"rate_limit_floor_seconds": 300}, provider="groq"
    )
    limiter = FlooredRateLimiter(
        settings=settings,
        provider_name="groq",
        model_id="m",
        monotonic=clock.monotonic,
        wall=clock.wall,
        sleeper=sleeper,
        stop_event=stop,
    )
    decision = limiter.decide_for_error(RateLimited("x"), attempt=0)
    with pytest.raises(RequestCancelled):
        limiter.wait_for(decision)
    assert sum(sliced) < decision.seconds, "the full wait was served before stopping"


def test_a_stop_already_requested_cancels_the_wait_before_it_starts():
    clock = FakeClock()
    stop = threading.Event()
    stop.set()
    sleeper = RecordingSleeper(clock)
    settings = LimiterSettings.from_settings({}, provider="groq")
    limiter = FlooredRateLimiter(
        settings=settings,
        provider_name="groq",
        model_id="m",
        monotonic=clock.monotonic,
        wall=clock.wall,
        sleeper=sleeper,
        stop_event=stop,
    )
    with pytest.raises(RequestCancelled):
        limiter.wait_for(limiter.decide_for_error(RateLimited("x"), attempt=0))
    assert sleeper.calls == []


def test_a_long_wait_is_served_in_bounded_slices_so_stop_is_never_blocked():
    limiter, _clock, sleeper = build_limiter(rate_limit_floor_seconds=300)
    limiter.wait_for(limiter.decide_for_error(RateLimited("x"), attempt=0))
    assert sleeper.calls, "no wait was served"
    assert max(sleeper.calls) <= limiter.slice_seconds
    assert sum(sleeper.calls) == pytest.approx(300.0)


def test_a_mid_file_wait_does_not_hold_for_pause():
    """BRIEFING/DECISIONS #033: the in-flight file always finishes; a mid-file pause
    hold would need a superseding decision entry, so Phase 4 does not add one."""
    clock = FakeClock()
    pause = threading.Event()  # cleared == paused
    sleeper = RecordingSleeper(clock)
    settings = LimiterSettings.from_settings(
        {"rate_limit_floor_seconds": 5}, provider="groq"
    )
    limiter = FlooredRateLimiter(
        settings=settings,
        provider_name="groq",
        model_id="m",
        monotonic=clock.monotonic,
        wall=clock.wall,
        sleeper=sleeper,
        pause_gate=pause,
    )
    slept = limiter.wait_for(limiter.decide_for_error(RateLimited("x"), attempt=0))
    assert slept == pytest.approx(5.0)


# --------------------------------------------------------------------------
# Header-driven vs floored — selected by the capability flag, not by name
# --------------------------------------------------------------------------
class FakeProvider:
    def __init__(self, *, exposes_rate_limits: bool, name: str = "groq"):
        self._exposes = exposes_rate_limits
        self._name = name
        self.last_rate_limits = None
        self.calls: list = []
        self.responses: list = []

    def capabilities(self):

        return ProviderCapabilities(
            self._name,
            False,
            ("m",),
            131_072,
            4096,
            exposes_rate_limits=self._exposes,
        )

    def health_check(self):

        return ProviderStatus.OK

    def list_models(self):
        return ["m"]

    def complete(self, request):

        self.calls.append(request)
        if self.responses:
            outcome = self.responses.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        return CompletionResult("edited", "m", 0.1, "stop", False)


def test_a_provider_that_exposes_rate_limits_gets_the_header_driven_limiter():
    limiter = limiter_for(FakeProvider(exposes_rate_limits=True), {}, provider="groq")
    assert isinstance(limiter, HeaderDrivenRateLimiter)


def test_a_provider_that_exposes_no_rate_limits_gets_the_floored_limiter():
    limiter = limiter_for(FakeProvider(exposes_rate_limits=False), {}, provider="gemini")
    assert isinstance(limiter, FlooredRateLimiter)
    assert not isinstance(limiter, HeaderDrivenRateLimiter)


def test_the_floored_limiter_refuses_to_read_a_snapshot_at_all():
    """Gemini exposes no headers, so a floored limiter reading one would be reading a
    number that cannot exist. No figure may be invented for this provider."""

    limiter, _clock, _sleeper = build_limiter(FlooredRateLimiter)
    provider = FakeProvider(exposes_rate_limits=False)
    provider.last_rate_limits = RateLimitSnapshot(
        remaining_tokens=0, reset_tokens_seconds=42.0
    )
    assert limiter.snapshot_from(provider, None) is None


def test_the_header_driven_limiter_reads_the_snapshot_off_the_provider():

    limiter, _clock, _sleeper = build_limiter(HeaderDrivenRateLimiter)
    provider = FakeProvider(exposes_rate_limits=True)
    snapshot = RateLimitSnapshot(remaining_tokens=10, reset_tokens_seconds=42.0)
    provider.last_rate_limits = snapshot
    assert limiter.snapshot_from(provider, None) is snapshot


def test_the_header_driven_limiter_prefers_the_snapshot_carried_by_the_error():

    limiter, _clock, _sleeper = build_limiter(HeaderDrivenRateLimiter)
    provider = FakeProvider(exposes_rate_limits=True)
    provider.last_rate_limits = RateLimitSnapshot(remaining_tokens=9999)
    exc = RateLimited("429")
    exc.rate_limits = RateLimitSnapshot(remaining_tokens=0, reset_tokens_seconds=5.0)
    assert limiter.snapshot_from(provider, exc).remaining_tokens == 0


def test_a_provider_claiming_headers_but_returning_none_degrades_to_the_floor():
    limiter, _clock, _sleeper = build_limiter(
        HeaderDrivenRateLimiter, rate_limit_floor_seconds=25
    )
    provider = FakeProvider(exposes_rate_limits=True)
    assert limiter.snapshot_from(provider, None) is None
    decision = limiter.decide_for_error(RateLimited("429"), attempt=0)
    assert decision.source == "floor"
    assert decision.seconds == 25.0


# --------------------------------------------------------------------------
# The wrapper — a limiter around any provider, without touching the provider
# --------------------------------------------------------------------------
def make_request(text: str = "A paragraph of edited prose.", tokens: int = 256):

    return CompletionRequest(
        text=text,
        system_prompt="system",
        prompt_version="1.0",
        model_id="m",
        temperature=0.0,
        seed=0,
        timeout_seconds=120.0,
        max_output_tokens=tokens,
        request_id="req-1",
    )


def wrap(provider, **overrides):

    clock = FakeClock()
    sleeper = RecordingSleeper(clock)
    limiter = limiter_for(
        provider,
        overrides,
        provider="groq",
        model_id="m",
        monotonic=clock.monotonic,
        wall=clock.wall,
        sleeper=sleeper,
        random_source=random.Random(7),
    )
    return RateLimitedProvider(provider, limiter), limiter, clock, sleeper


def test_the_wrapper_satisfies_the_2a_provider_protocol():

    wrapped, _limiter, _clock, _sleeper = wrap(FakeProvider(exposes_rate_limits=True))
    assert isinstance(wrapped, AIProvider)


def test_the_wrapper_delegates_capabilities_health_and_model_list_unchanged():

    provider = FakeProvider(exposes_rate_limits=True)
    wrapped, _limiter, _clock, _sleeper = wrap(provider)
    assert wrapped.capabilities() == provider.capabilities()
    assert wrapped.health_check() is ProviderStatus.OK
    assert wrapped.list_models() == ["m"]


def test_a_successful_request_passes_straight_through_without_waiting():
    provider = FakeProvider(exposes_rate_limits=True)
    wrapped, _limiter, _clock, sleeper = wrap(provider)
    result = wrapped.complete(make_request())
    assert result.text == "edited"
    assert len(provider.calls) == 1
    assert sleeper.calls == []


def test_a_rate_limit_waits_the_retry_after_exactly_then_resumes():

    provider = FakeProvider(exposes_rate_limits=True)
    limited = RateLimited("Too Many Requests")
    limited.retry_after_seconds = 12.0
    provider.responses = [limited, CompletionResult("edited later", "m", 0.2, "stop", False)]
    wrapped, _limiter, _clock, sleeper = wrap(provider, rate_limit_floor_seconds=999)
    result = wrapped.complete(make_request())
    assert result.text == "edited later"
    assert sleeper.total == pytest.approx(12.0)
    assert len(provider.calls) == 2


def test_a_transient_error_is_retried_after_a_bounded_jittered_backoff():

    provider = FakeProvider(exposes_rate_limits=True)
    provider.responses = [
        TransientNetworkError("connection reset"),
        CompletionResult("edited later", "m", 0.2, "stop", False),
    ]
    # rpm_floor is off so the only wait measured here is the backoff itself.
    wrapped, _limiter, _clock, sleeper = wrap(
        provider,
        rpm_floor=0,
        tpm_floor=0,
        backoff_base_seconds=2,
        backoff_max_seconds=60,
        backoff_jitter_ratio=0.5,
    )
    assert wrapped.complete(make_request()).text == "edited later"
    assert 1.0 <= sleeper.total <= 2.0


def test_daily_exhaustion_raises_immediately_and_never_sleeps():
    provider = FakeProvider(exposes_rate_limits=True)
    provider.responses = [DailyQuotaExhausted("free daily quota is used up (TPD)")]
    wrapped, limiter, _clock, sleeper = wrap(provider)
    with pytest.raises(DailyQuotaExhausted):
        wrapped.complete(make_request())
    assert sleeper.calls == []
    assert len(provider.calls) == 1
    assert limiter.quota_stop is not None
    assert limiter.quota_stop.is_daily is True


def test_after_daily_exhaustion_no_further_request_is_ever_sent():
    """Never retry into overage — including on the next chapter of the run."""
    provider = FakeProvider(exposes_rate_limits=True)
    provider.responses = [DailyQuotaExhausted("daily quota used up (RPD)")]
    wrapped, _limiter, _clock, _sleeper = wrap(provider)
    with pytest.raises(DailyQuotaExhausted):
        wrapped.complete(make_request())
    with pytest.raises(DailyQuotaExhausted):
        wrapped.complete(make_request())
    assert len(provider.calls) == 1, "a second paid call was made after the day was gone"


def test_a_zero_remaining_daily_request_header_stops_the_next_call_before_it_is_sent():

    provider = FakeProvider(exposes_rate_limits=True)
    provider.responses = [CompletionResult("edited", "m", 0.1, "stop", False)]
    wrapped, limiter, _clock, sleeper = wrap(provider)
    wrapped.complete(make_request())
    # The successful response's own headers said this was the last request of the day.
    provider.last_rate_limits = RateLimitSnapshot(
        remaining_requests=0, remaining_tokens=9000
    )
    with pytest.raises(DailyQuotaExhausted):
        wrapped.complete(make_request())
    assert len(provider.calls) == 1
    assert sleeper.calls == []
    assert limiter.quota_stop.kind is LimitKind.REQUESTS_PER_DAY


def test_the_quota_stop_callback_fires_once_for_phase_five():
    provider = FakeProvider(exposes_rate_limits=True)
    provider.responses = [
        DailyQuotaExhausted("daily quota used up (TPD)"),
        DailyQuotaExhausted("daily quota used up (TPD)"),
    ]
    seen: list = []

    clock = FakeClock()
    limiter = limiter_for(
        provider,
        {},
        provider="groq",
        model_id="m",
        monotonic=clock.monotonic,
        wall=clock.wall,
        sleeper=RecordingSleeper(clock),
        on_quota_stop=seen.append,
    )
    wrapped = RateLimitedProvider(provider, limiter)
    for _ in range(2):
        with pytest.raises(DailyQuotaExhausted):
            wrapped.complete(make_request())
    assert len(seen) == 1
    assert seen[0].as_dict()["is_daily"] is True


def test_a_persistent_rate_limit_gives_up_after_the_configured_attempts():
    provider = FakeProvider(exposes_rate_limits=True)
    provider.responses = [RateLimited("Too Many Requests") for _ in range(10)]
    wrapped, _limiter, _clock, sleeper = wrap(
        provider, max_attempts=3, rate_limit_floor_seconds=10
    )
    with pytest.raises(RateLimited):
        wrapped.complete(make_request())
    assert len(provider.calls) == 3
    assert sleeper.total == pytest.approx(20.0)  # two waits between three attempts


@pytest.mark.parametrize(
    "exc",
    [
        ContextTooLong("too long"),
        AuthenticationError("bad key"),
        InvalidResponse("unknown finish reason", retryable=False),
    ],
)
def test_errors_the_limiter_does_not_own_pass_through_untouched(exc):
    provider = FakeProvider(exposes_rate_limits=True)
    provider.responses = [exc]
    wrapped, limiter, _clock, sleeper = wrap(provider)
    with pytest.raises(type(exc)):
        wrapped.complete(make_request())
    assert len(provider.calls) == 1
    assert sleeper.calls == []
    assert limiter.quota_stop is None


def test_an_over_long_wait_stops_the_run_instead_of_sleeping_through_it():
    provider = FakeProvider(exposes_rate_limits=True)
    limited = RateLimited("Too Many Requests")
    limited.retry_after_seconds = 5_000.0
    provider.responses = [limited]
    wrapped, limiter, _clock, sleeper = wrap(provider, max_wait_seconds=900)
    with pytest.raises(RateLimited):
        wrapped.complete(make_request())
    assert sleeper.calls == []
    assert limiter.quota_stop is not None
    assert limiter.quota_stop.is_daily is False
    assert limiter.quota_stop.reset_seconds == pytest.approx(5_000.0)


def test_the_wrapper_paces_successive_requests_from_the_configured_floor():
    provider = FakeProvider(exposes_rate_limits=True)
    wrapped, _limiter, _clock, sleeper = wrap(provider, rpm_floor=15, tpm_floor=0)
    wrapped.complete(make_request())
    wrapped.complete(make_request())
    assert sleeper.total == pytest.approx(4.0)


def test_the_wrapper_reserves_tokens_using_2as_own_estimator():

    provider = FakeProvider(exposes_rate_limits=True)
    wrapped, limiter, _clock, _sleeper = wrap(provider, rpm_floor=0, tpm_floor=5000)
    request = make_request("word " * 2000, tokens=1024)
    expected = (
        estimate_tokens(request.system_prompt)
        + estimate_tokens(request.text)
        + request.max_output_tokens
    )
    assert wrapped.estimated_tokens(request) == expected


# --------------------------------------------------------------------------
# Stop during a wait, end to end through 2a's real AIEditor
# --------------------------------------------------------------------------
def build_editor(wrapped, policy):

    return AIEditor(lambda: wrapped, EditorOptions(model_id="m", policy=policy))


def stop_during_wait_provider():
    """A provider that rate-limits once; Stop is pressed during the countdown."""
    provider = FakeProvider(exposes_rate_limits=True)
    provider.responses = [RateLimited("Too Many Requests")]
    stop = threading.Event()
    clock = FakeClock()
    sliced: list[float] = []

    def sleeper(seconds: float) -> bool:
        sliced.append(seconds)
        stop.set()
        return True


    limiter = limiter_for(
        provider,
        {"rate_limit_floor_seconds": 600},
        provider="groq",
        model_id="m",
        monotonic=clock.monotonic,
        wall=clock.wall,
        sleeper=sleeper,
        stop_event=stop,
    )
    return RateLimitedProvider(provider, limiter), provider, sliced


def test_stop_during_a_mid_file_wait_raises_request_cancelled_from_complete():
    wrapped, provider, sliced = stop_during_wait_provider()
    with pytest.raises(RequestCancelled):
        wrapped.complete(make_request())
    assert len(provider.calls) == 1
    assert sum(sliced) < 600.0


def test_stop_during_a_wait_routes_a_prefer_ai_chapter_to_script_only_fallback():
    """DECISIONS #037: RequestCancelled is non-retryable, so 2a's chapter-atomic
    fallback returns the deterministic text — no half-written output, and the run
    then halts at the normal between-files seam."""

    wrapped, _provider, _sliced = stop_during_wait_provider()
    baseline = "Chapter One\n\nThe deterministic pipeline already edited this."
    outcome = build_editor(wrapped, RunPolicy.PREFER_AI).edit(baseline)
    assert outcome.text == baseline  # byte-for-byte the script-only result
    assert outcome.fallback_used is True
    assert outcome.used_ai is False
    assert "RequestCancelled" in outcome.rejection_reasons


def test_stop_during_a_wait_under_ai_required_raises_rather_than_degrading():
    """AI-required's existing 2a contract is to fail honestly rather than silently
    fall back; the run still halts at the same between-files seam."""

    wrapped, _provider, _sliced = stop_during_wait_provider()
    with pytest.raises(AIProviderError):
        build_editor(wrapped, RunPolicy.AI_REQUIRED).edit("Chapter One\n\nText.")


def test_a_normal_rate_limit_wait_still_lets_the_chapter_be_edited():
    """The counterpart: without Stop, an RPM wait resumes and the chapter is edited."""

    provider = FakeProvider(exposes_rate_limits=True)
    limited = RateLimited("Too Many Requests")
    limited.retry_after_seconds = 9.0
    provider.responses = [
        limited,
        CompletionResult("Chapter One\n\nThe deterministic pipeline already edited this.",
                         "m", 0.2, "stop", False),
    ]
    wrapped, _limiter, _clock, sleeper = wrap(provider)
    baseline = "Chapter One\n\nThe deterministic pipeline already edited this."
    outcome = build_editor(wrapped, RunPolicy.PREFER_AI).edit(baseline)
    assert outcome.fallback_used is False
    assert sleeper.total == pytest.approx(9.0)


# --------------------------------------------------------------------------
# Offline, no keys, no SDKs
# --------------------------------------------------------------------------
def test_the_limiter_imports_no_provider_sdk():

    assert "groq" not in sys.modules
    assert "google.genai" not in sys.modules


def test_the_limiter_module_imports_no_provider_adapter():
    """Snapshots are read duck-typed, so the limiter needs no provider import at all."""
    source = (
        REPO_ROOT / "scripts" / "Universal" / "ai" / "rate_limits.py"
    ).read_text(encoding="utf-8")
    imports = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from ")) and "providers" in line
    ]
    assert imports == []


def test_the_whole_limiter_works_with_no_api_key_in_the_environment(monkeypatch):
    for name in ("GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    provider = FakeProvider(exposes_rate_limits=True)
    wrapped, _limiter, _clock, _sleeper = wrap(provider)
    assert wrapped.complete(make_request()).text == "edited"
