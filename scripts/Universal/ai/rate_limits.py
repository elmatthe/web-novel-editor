"""Rate limiting and quota classification (Plan 2b Phase 4).

Provider-neutral by construction: this module imports no provider SDK, no adapter, and
no GUI. It reads a rate-limit snapshot **duck-typed** off whatever the adapter hands it,
so the header-driven path works for Groq without this file knowing Groq exists.

**No number in this module is a limit.** Every figure comes from the ``[ai.gemini]`` /
``[ai.groq]`` subtables in ``config.toml`` (with the same values mirrored into
``cloud.CLOUD_DEFAULTS`` purely so a missing section still yields a conservative limiter
rather than an unlimited one).

The asymmetry this file exists to respect
-----------------------------------------
Groq returns ``x-ratelimit-*-requests`` as a **per-day** counter and
``x-ratelimit-*-tokens`` as a **per-minute** counter; Gemini returns nothing at all.
Reading those two the other way round would make the limiter wait a minute for a quota
that resets tomorrow — or, far worse, sleep until tomorrow for a quota that resets in
seven seconds. :func:`classify_limit` encodes the correct direction and
``test_rate_limiting.py`` asserts it in both directions.
"""

from __future__ import annotations

import random
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping

from . import redaction
from .cloud import CLOUD_DEFAULTS
from .errors import (
    DailyQuotaExhausted,
    ProviderUnavailable,
    RateLimited,
    RequestCancelled,
    TransientNetworkError,
)

SECONDS_PER_MINUTE = 60.0

#: How long a single uninterruptible sleep may last. Nothing to do with any provider
#: limit — it is the responsiveness bound that keeps Stop from ever waiting on a
#: countdown, and the reason a long wait is served as many short ones.
WAIT_SLICE_SECONDS = 5.0

#: Bound on the text copied out of a provider error into the quota-stop record.
QUOTA_STOP_REASON_LIMIT = 240


class LimitKind(str, Enum):
    """What kind of limit was hit — never a guess, and never "429 means daily"."""

    NONE = "none"
    REQUESTS_PER_MINUTE = "requests_per_minute"
    TOKENS_PER_MINUTE = "tokens_per_minute"
    REQUESTS_PER_DAY = "requests_per_day"
    TOKENS_PER_DAY = "tokens_per_day"
    DAILY_UNSPECIFIED = "daily_unspecified"
    PROVIDER_CAPACITY = "provider_capacity"
    TRANSIENT = "transient"


#: Kinds that must never become a wait. A daily quota is a clean stop, not a sleep.
DAILY_KINDS = frozenset(
    {
        LimitKind.REQUESTS_PER_DAY,
        LimitKind.TOKENS_PER_DAY,
        LimitKind.DAILY_UNSPECIFIED,
    }
)

#: Kinds a jittered backoff may be applied to. Deliberately excludes every quota kind:
#: backing off a quota error is either pointless (per-minute has an authoritative reset)
#: or dangerous (per-day would retry into overage).
BACKOFF_KINDS = frozenset({LimitKind.PROVIDER_CAPACITY, LimitKind.TRANSIENT})


def _squash(text: str) -> str:
    return text.lower().replace(" ", "").replace("_", "").replace("-", "")


def _names_tokens_per_day(squashed: str) -> bool:
    return "tpd" in squashed or "tokensperday" in squashed


def _names_requests_per_day(squashed: str) -> bool:
    return "rpd" in squashed or "requestsperday" in squashed


def _names_tokens_per_minute(squashed: str) -> bool:
    return "tpm" in squashed or "tokensperminute" in squashed


def _names_requests_per_minute(squashed: str) -> bool:
    return "rpm" in squashed or "requestsperminute" in squashed


def classify_limit(exc: BaseException, snapshot: Any | None = None) -> LimitKind:
    """Classify a provider error into the limit it actually represents.

    Evidence is used in the order it is trustworthy: the provider's own wording first
    (it names the exact limit), then the rate-limit headers, then the error type's own
    meaning. Anything the limiter has no business acting on — auth, context, a refused
    response, a cancelled request — is :attr:`LimitKind.NONE` and passes straight
    through untouched.

    ``snapshot`` is any object exposing the Groq-shaped ``remaining_requests`` /
    ``remaining_tokens`` fields; it is read with ``getattr`` so this module needs no
    import from ``ai.providers``.
    """
    squashed = _squash(str(exc))
    remaining_requests = getattr(snapshot, "remaining_requests", None)
    remaining_tokens = getattr(snapshot, "remaining_tokens", None)

    if isinstance(exc, DailyQuotaExhausted):
        if _names_tokens_per_day(squashed):
            return LimitKind.TOKENS_PER_DAY
        if _names_requests_per_day(squashed):
            return LimitKind.REQUESTS_PER_DAY
        # The request counter is the per-DAY one. Zero remaining is positive evidence
        # of daily request exhaustion even when the body says only "Too Many Requests".
        if remaining_requests == 0:
            return LimitKind.REQUESTS_PER_DAY
        return LimitKind.DAILY_UNSPECIFIED

    if isinstance(exc, RateLimited):
        if _names_tokens_per_minute(squashed):
            return LimitKind.TOKENS_PER_MINUTE
        if _names_requests_per_minute(squashed):
            return LimitKind.REQUESTS_PER_MINUTE
        # The token counter is the per-MINUTE one, so an empty token budget is a
        # seconds-long wait — not a day.
        if remaining_tokens == 0:
            return LimitKind.TOKENS_PER_MINUTE
        return LimitKind.REQUESTS_PER_MINUTE

    if isinstance(exc, TransientNetworkError):
        return LimitKind.TRANSIENT
    if isinstance(exc, ProviderUnavailable) and getattr(exc, "retryable", False):
        # Capacity, not quota. Retryable with a backoff, but it must never be counted
        # as quota exhaustion or it would checkpoint a run that only needed a pause.
        return LimitKind.PROVIDER_CAPACITY
    return LimitKind.NONE


def limit_period_is_named(exc: BaseException, snapshot: Any | None = None) -> bool:
    """Whether the provider gave POSITIVE evidence of which limit was hit.

    :func:`classify_limit` must always return something, so when a 429 says nothing but
    "Too Many Requests" it falls through to ``REQUESTS_PER_MINUTE`` — the safe guess, and
    a guess. This function is what distinguishes the guess from the evidence, so
    :meth:`RateLimiter.decide_for_error` can stop guessing forever.
    """
    squashed = _squash(str(exc))
    if (
        _names_tokens_per_day(squashed)
        or _names_requests_per_day(squashed)
        or _names_tokens_per_minute(squashed)
        or _names_requests_per_minute(squashed)
    ):
        return True
    return (
        getattr(snapshot, "remaining_requests", None) == 0
        or getattr(snapshot, "remaining_tokens", None) == 0
    )


def _positive_float(value: Any, fallback: float) -> float:
    """A usable non-negative number, or the shipped fallback. Never a partial guess."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    if number != number or number in (float("inf"), float("-inf")) or number < 0:
        return float(fallback)
    return number


def _positive_int(value: Any, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return int(fallback)
    return number if number > 0 else int(fallback)


@dataclass(frozen=True)
class LimiterSettings:
    """The configured floors, coerced once so the limiter never re-parses TOML."""

    rpm_floor: float
    tpm_floor: int
    rate_limit_floor_seconds: float
    backoff_base_seconds: float
    backoff_max_seconds: float
    backoff_jitter_ratio: float
    max_attempts: int
    max_wait_seconds: float
    unnamed_limit_escalation_seconds: float = 0.0
    #: Seconds. A per-DAY quota whose own ``RetryInfo.retryDelay`` is at or under this
    #: is waited rather than checkpointed. 0 disables it, which is the pre-#072
    #: behaviour and what Groq ships. Never a guess: it gates an authoritative number
    #: the provider supplied, and gates nothing when the provider supplied none.
    daily_quota_retry_delay_max_seconds: float = 0.0

    @property
    def min_interval_seconds(self) -> float:
        """Seconds the client holds between requests before any header is seen."""
        if self.rpm_floor <= 0:
            return 0.0
        return SECONDS_PER_MINUTE / self.rpm_floor

    @classmethod
    def from_settings(
        cls, settings: Mapping[str, Any] | None, *, provider: str
    ) -> "LimiterSettings":
        """Build from a merged ``[ai.<provider>]`` mapping.

        A missing or unreadable value falls back to the shipped default for that
        provider rather than to "no limit" — a limiter that silently loses its floor is
        worse than one that paces too slowly.
        """
        defaults = CLOUD_DEFAULTS.get(str(provider or "").strip().lower(), {})
        source: Mapping[str, Any] = settings if isinstance(settings, Mapping) else {}

        def number(key: str) -> float:
            return _positive_float(source.get(key), defaults.get(key, 0))

        return cls(
            rpm_floor=number("rpm_floor"),
            tpm_floor=int(number("tpm_floor")),
            rate_limit_floor_seconds=number("rate_limit_floor_seconds"),
            backoff_base_seconds=number("backoff_base_seconds"),
            backoff_max_seconds=number("backoff_max_seconds"),
            backoff_jitter_ratio=min(1.0, number("backoff_jitter_ratio")),
            max_attempts=_positive_int(
                source.get("max_attempts"), defaults.get("max_attempts", 1)
            ),
            max_wait_seconds=number("max_wait_seconds"),
            unnamed_limit_escalation_seconds=number("unnamed_limit_escalation_seconds"),
            daily_quota_retry_delay_max_seconds=number(
                "daily_quota_retry_delay_max_seconds"
            ),
        )


@dataclass(frozen=True)
class WaitDecision:
    """What the limiter decided to do about one error, and why.

    ``seconds`` is always reported honestly even when it will not be slept — a caller
    (and Phase 6's status line) is entitled to know that the provider asked for an hour;
    ``retry`` is what says whether this process will actually serve that wait.
    """

    kind: LimitKind
    seconds: float = 0.0
    source: str = "none"
    authoritative: bool = False
    daily: bool = False
    retry: bool = False
    too_long: bool = False
    reset_seconds: float | None = None
    reset_known: bool = False


@dataclass(frozen=True)
class QuotaStop:
    """The Phase 4 → Phase 5 seam.

    Phase 4's job ends here: it stops cleanly and records *why*, in a small, serializable
    record that carries **no API key, no chapter text, and no file path**. Phase 5 hooks
    this to write its run manifest and offer "resume tomorrow"; Phase 6 renders
    ``reset_known == False`` as an honest "reset time unknown — see the provider's limits
    page" rather than guessing midnight or a provider timezone.

    ``is_daily`` distinguishes the two ways a run can stop on a limit: a genuine daily
    quota (resume tomorrow), or a per-minute wait longer than this session is willing to
    sleep through (resume when the wait has passed).
    """

    provider: str
    model_id: str
    kind: LimitKind
    reason: str
    reset_seconds: float | None
    reset_known: bool
    is_daily: bool
    observed_monotonic: float
    observed_wall: float

    def as_dict(self) -> dict[str, Any]:
        """A manifest-safe mapping. ``observed_monotonic`` is deliberately absent: it is
        meaningless once written to disk and read back in another process."""
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "kind": self.kind.value,
            "reason": self.reason,
            "reset_seconds": self.reset_seconds,
            "reset_known": self.reset_known,
            "is_daily": self.is_daily,
            "observed_wall": self.observed_wall,
        }


def _default_sleeper_for(stop_event: threading.Event | None) -> Callable[[float], bool]:
    """A sleeper that a Stop can wake immediately.

    ``Event.wait`` returns as soon as the event is set, so a pending Stop breaks the
    countdown at once rather than up to one slice late. Without an event there is
    nothing to wake for and a plain sleep is correct.
    """
    if stop_event is None:
        def sleeper(seconds: float) -> bool:
            time.sleep(seconds)
            return False
    else:
        def sleeper(seconds: float) -> bool:
            return bool(stop_event.wait(seconds))
    return sleeper


class RateLimiter:
    """The shared limiter: floors, the wait decision table, and interruptible waiting.

    Subclasses differ in exactly one thing — where limit information comes from. That is
    :meth:`snapshot_from`, and nothing else. Selection between them is by
    ``capabilities().exposes_rate_limits``, never by provider name.
    """

    def __init__(
        self,
        *,
        settings: LimiterSettings,
        provider_name: str,
        model_id: str = "",
        monotonic: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        sleeper: Callable[[float], bool] | None = None,
        stop_event: threading.Event | None = None,
        pause_gate: threading.Event | None = None,
        random_source: random.Random | None = None,
        on_quota_stop: Callable[[QuotaStop], None] | None = None,
        slice_seconds: float = WAIT_SLICE_SECONDS,
    ):
        self.settings = settings
        self.provider_name = provider_name
        self.model_id = model_id
        self.slice_seconds = max(0.01, float(slice_seconds))
        self._monotonic = monotonic
        self._wall = wall
        self._sleeper = sleeper if sleeper is not None else _default_sleeper_for(stop_event)
        self._stop_event = stop_event
        # Held only so a caller may hand one over without special-casing. A rate-limit
        # wait deliberately does NOT hold for pause: 2a's contract is that the in-flight
        # file always finishes, and BRIEFING states a mid-file hold needs a superseding
        # DECISIONS entry. Pausing here would lengthen the very window Pause exists to
        # bound.
        self._pause_gate = pause_gate
        self._random = random_source if random_source is not None else random.Random()
        self._on_quota_stop = on_quota_stop

        self._last_request_monotonic: float | None = None
        self._token_events: deque[tuple[float, int]] = deque()
        self._quota_stop: QuotaStop | None = None
        # When an unexplained limit error was first seen with no success since. Monotonic,
        # so a clock jump cannot shorten or extend the escalation window.
        self._unnamed_limit_since: float | None = None

    # -- provider-specific ------------------------------------------------
    def snapshot_from(self, provider: Any, exc: BaseException | None) -> Any | None:
        """Where limit information comes from. The base limiter has none."""
        return None

    def is_daily_exhausted(self, snapshot: Any | None) -> bool:
        """Whether a snapshot alone proves the day's quota is gone."""
        return False

    # -- state ------------------------------------------------------------
    @property
    def quota_stop(self) -> QuotaStop | None:
        return self._quota_stop

    def _stopped(self) -> bool:
        return self._stop_event is not None and self._stop_event.is_set()

    def _raise_cancelled(self) -> None:
        raise RequestCancelled(
            "Stop was requested while waiting for the provider's rate limit, so this "
            "request was cancelled. The chapter falls back to script-only editing and "
            "the run stops after it.",
            retryable=False,
        )

    # -- proactive pacing --------------------------------------------------
    def pre_request_wait_seconds(
        self, estimated_tokens: int = 0, snapshot: Any | None = None
    ) -> float:
        """How long to hold before issuing a request, from the floors and any headers."""
        now = self._monotonic()
        waits = [self._interval_wait(now), self._token_window_wait(now, estimated_tokens)]
        header_wait = self._header_wait(snapshot, estimated_tokens)
        if header_wait is not None:
            waits.append(header_wait)
        return max([0.0, *waits])

    def _interval_wait(self, now: float) -> float:
        interval = self.settings.min_interval_seconds
        if interval <= 0 or self._last_request_monotonic is None:
            return 0.0
        return max(0.0, self._last_request_monotonic + interval - now)

    def _token_window_wait(self, now: float, estimated_tokens: int) -> float:
        """Hold until the rolling minute has room for ``estimated_tokens``.

        A request larger than the whole floor is *not* held: no amount of waiting makes
        room for it, and the floor is our own self-restraint rather than the provider's
        actual limit, so refusing it here would break a run over a number we invented.
        The provider's own limit remains the authority for that case.
        """
        floor = self.settings.tpm_floor
        if floor <= 0 or estimated_tokens <= 0:
            return 0.0
        self._expire_token_events(now)
        used = sum(tokens for _ts, tokens in self._token_events)
        if used + estimated_tokens <= floor:
            return 0.0
        freed = 0
        for timestamp, tokens in self._token_events:
            freed += tokens
            if used - freed + estimated_tokens <= floor:
                return max(0.0, timestamp + SECONDS_PER_MINUTE - now)
        return 0.0

    def _expire_token_events(self, now: float) -> None:
        cutoff = now - SECONDS_PER_MINUTE
        while self._token_events and self._token_events[0][0] <= cutoff:
            self._token_events.popleft()

    def _header_wait(self, snapshot: Any | None, estimated_tokens: int) -> float | None:
        return None

    def wait_before_request(
        self, estimated_tokens: int = 0, *, snapshot: Any | None = None
    ) -> float:
        """Serve the proactive wait, then mark the request as issued."""
        seconds = self.pre_request_wait_seconds(estimated_tokens, snapshot)
        slept = self._serve(seconds) if seconds > 0 else 0.0
        self._last_request_monotonic = self._monotonic()
        return slept

    def record_success(
        self,
        *,
        estimated_tokens: int = 0,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        snapshot: Any | None = None,
    ) -> None:
        """Charge a completed request against the rolling window.

        Real usage replaces the reservation when the provider reported it; when it did
        not — both cloud adapters return ``None`` rather than inventing a figure — the
        conservative estimate stands.
        """
        if input_tokens is None and output_tokens is None:
            spent = int(estimated_tokens)
        else:
            spent = int(input_tokens or 0) + int(output_tokens or 0)
        if spent > 0 and self.settings.tpm_floor > 0:
            self._token_events.append((self._monotonic(), spent))
        # A request got through, so whatever the unexplained 429s were, they have cleared.
        self._unnamed_limit_since = None

    # -- the decision table -----------------------------------------------
    def decide_for_error(
        self, exc: BaseException, *, snapshot: Any | None = None, attempt: int = 0
    ) -> WaitDecision:
        kind = classify_limit(exc, snapshot)
        if kind is LimitKind.NONE:
            self._unnamed_limit_since = None
            return WaitDecision(LimitKind.NONE)

        kind = self._escalate_if_unexplained(kind, exc, snapshot)

        if kind in DAILY_KINDS:
            # DECISIONS #069 splits waits "by duration, not by error code", and until
            # #072 this branch split them by code: every per-day quota checkpointed the
            # run, however short the wait actually was. Google's free tier turns out to
            # enforce requests-per-day as a REFILLING window — the 429 names
            # `GenerateRequestsPerDayPerProjectPerModel-FreeTier` and, in the same body,
            # says "Please retry in 53s", and retrying then really does succeed. So an
            # authoritative short delay is served here rather than thrown away.
            #
            # The three ways this stays conservative: the number must come from the
            # provider (`retry_after_seconds` on the error, never a floor and never a
            # guess), it must be at or under a configured cap, and the cap ships at 0 —
            # off — for any provider not proven to behave this way. Groq's tokens-per-day
            # keeps latching in 0.0 s with no network call, which is what Phase 7b
            # measured and what it should keep doing.
            authoritative_delay = _float_or_none(
                getattr(exc, "retry_after_seconds", None)
            )
            cap = self.settings.daily_quota_retry_delay_max_seconds
            if (
                authoritative_delay is not None
                and cap > 0
                and 0 < authoritative_delay <= cap
            ):
                return WaitDecision(
                    kind,
                    authoritative_delay,
                    "retry_after_daily_refill",
                    authoritative=True,
                    daily=False,   # not a stop: the provider said to come back shortly
                    retry=True,
                    reset_seconds=authoritative_delay,
                    reset_known=True,
                )
            # Otherwise: never a wait. Not once, not briefly, not "just until the reset".
            reset = _float_or_none(getattr(snapshot, "reset_requests_seconds", None))
            return WaitDecision(
                kind,
                0.0,
                "daily",
                daily=True,
                retry=False,
                reset_seconds=reset,
                reset_known=reset is not None,
            )

        if kind in BACKOFF_KINDS:
            seconds = self._backoff_seconds(attempt)
            too_long = seconds > self.settings.max_wait_seconds
            return WaitDecision(
                kind,
                seconds,
                "backoff",
                retry=not too_long,
                too_long=too_long,
                reset_seconds=seconds if too_long else None,
                reset_known=too_long,
            )

        # Per-minute quota. Authority order: the provider's own instruction, then the
        # matching reset header, then our configured floor. Note which header is NOT
        # consulted here: `reset_requests_seconds` is the per-DAY counter's reset.
        seconds = _float_or_none(getattr(exc, "retry_after_seconds", None))
        source, authoritative = "retry_after", True
        if seconds is None:
            seconds = _float_or_none(getattr(snapshot, "retry_after_seconds", None))
        if seconds is None:
            authoritative = False
            if kind is LimitKind.TOKENS_PER_MINUTE:
                seconds = _float_or_none(getattr(snapshot, "reset_tokens_seconds", None))
                source = "header_reset_tokens"
            if seconds is None:
                seconds = self.settings.rate_limit_floor_seconds
                source = "floor"

        too_long = seconds > self.settings.max_wait_seconds
        known = authoritative or source == "header_reset_tokens"
        return WaitDecision(
            kind,
            seconds,
            source,
            authoritative=authoritative,
            retry=not too_long,
            too_long=too_long,
            reset_seconds=seconds if known else None,
            reset_known=known,
        )

    def _escalate_if_unexplained(
        self, kind: LimitKind, exc: BaseException, snapshot: Any | None
    ) -> LimitKind:
        """Stop guessing "per minute" forever when the provider never says which limit.

        Phase 7b's real cost. Gemini's 429 named no period the classifier could reach, so
        every one of them classified as a per-minute limit, the limiter waited and
        retried, and prefer-AI degraded chapter after chapter — **~35 minutes of futile
        calls** where Groq, whose message *does* name `tokens per day`, latched
        immediately and refused the rest of the run in 0.0 s with no network traffic. The
        structured fix lives in the Gemini adapter; this is the provider-neutral floor
        under it, for any provider that goes quiet about the period, including a future
        one and including Gemini when a body arrives without `QuotaFailure`.

        Escalating to ``DAILY_UNSPECIFIED`` is not a claim that the daily quota is gone.
        It routes to the same clean stop: write the checkpoint, tell the user the reset
        time is unknown, offer the provider's limits page and a Retry. Resuming is one
        click whenever the limit clears, so being wrong costs a stop the user can undo —
        while being wrong the other way costs the run.

        Only unexplained limits count. A named per-minute limit with an authoritative
        `Retry-After` is left exactly as it is, however long it goes on.
        """
        window = self.settings.unnamed_limit_escalation_seconds
        if window <= 0 or kind in DAILY_KINDS or kind in BACKOFF_KINDS:
            return kind
        if limit_period_is_named(exc, snapshot):
            self._unnamed_limit_since = None
            return kind
        now = self._monotonic()
        if self._unnamed_limit_since is None:
            self._unnamed_limit_since = now
            return kind
        if now - self._unnamed_limit_since < window:
            return kind
        return LimitKind.DAILY_UNSPECIFIED

    def _backoff_seconds(self, attempt: int) -> float:
        """Jittered, bounded, and only ever reached from a transient or capacity error."""
        step = self.settings.backoff_base_seconds * (2 ** max(0, int(attempt)))
        ceiling = min(step, self.settings.backoff_max_seconds)
        low = ceiling * (1.0 - self.settings.backoff_jitter_ratio)
        return self._random.uniform(low, ceiling)

    # -- serving a wait ----------------------------------------------------
    def wait_for(self, decision: WaitDecision) -> float:
        """Serve a decision's wait. A decision that is not retryable waits zero."""
        if not decision.retry or decision.seconds <= 0:
            return 0.0
        return self._serve(decision.seconds)

    def _serve(self, seconds: float) -> float:
        """Wait ``seconds`` in bounded slices against the MONOTONIC clock.

        The deadline is a monotonic instant, so a wall-clock jump — daylight saving, an
        NTP correction, a user editing the clock — cannot change the countdown by
        construction. The remaining time is recomputed from the clock on every pass, so
        a suspend/resume that moves monotonic forward simply ends the wait rather than
        leaving a negative or extended one.
        """
        if self._stopped():
            self._raise_cancelled()
        started = self._monotonic()
        deadline = started + seconds
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                break
            interrupted = self._sleeper(min(self.slice_seconds, remaining))
            if interrupted or self._stopped():
                self._raise_cancelled()
        return max(0.0, self._monotonic() - started)

    # -- the Phase 5 seam --------------------------------------------------
    def note_quota_stop(
        self, decision: WaitDecision, exc: BaseException | None = None
    ) -> QuotaStop | None:
        """Record a clean stop. Only the first one is kept — a run stops once."""
        if decision.retry or not (decision.daily or decision.too_long):
            return self._quota_stop
        if self._quota_stop is None:
            reason = redaction.redact(str(exc) if exc is not None else "")
            self._quota_stop = QuotaStop(
                provider=self.provider_name,
                model_id=self.model_id,
                kind=decision.kind,
                reason=reason[:QUOTA_STOP_REASON_LIMIT],
                reset_seconds=decision.reset_seconds,
                reset_known=decision.reset_known,
                is_daily=decision.daily,
                observed_monotonic=self._monotonic(),
                observed_wall=self._wall(),
            )
            if self._on_quota_stop is not None:
                self._on_quota_stop(self._quota_stop)
        return self._quota_stop


class FlooredRateLimiter(RateLimiter):
    """For providers that expose no rate-limit information at all (Gemini).

    Every decision comes from the configured floor. :meth:`snapshot_from` returns
    ``None`` unconditionally and deliberately: this provider publishes no limits and
    returns no headers, so there is no number to read — and inventing one is exactly
    what this plan forbids.
    """


class HeaderDrivenRateLimiter(RateLimiter):
    """For providers that return real rate-limit headers (Groq).

    The snapshot the adapter scraped wins over the floor, on success responses and on
    429s alike. Where the snapshot says nothing usable, the floor is still there.
    """

    def snapshot_from(self, provider: Any, exc: BaseException | None) -> Any | None:
        # The error's own snapshot first: on a 429 it is the fresher reading, and it is
        # the one case where there is no successful response to have updated the
        # provider's copy.
        snapshot = getattr(exc, "rate_limits", None) if exc is not None else None
        if snapshot is None:
            snapshot = getattr(provider, "last_rate_limits", None)
        return snapshot

    def is_daily_exhausted(self, snapshot: Any | None) -> bool:
        # `x-ratelimit-remaining-requests` is the per-DAY counter. Zero means tomorrow,
        # so the next request must not be sent at all.
        return getattr(snapshot, "remaining_requests", None) == 0

    def _header_wait(self, snapshot: Any | None, estimated_tokens: int) -> float | None:
        """Hold when the live per-MINUTE token budget cannot cover this request."""
        remaining = getattr(snapshot, "remaining_tokens", None)
        if remaining is None or estimated_tokens <= 0 or remaining >= estimated_tokens:
            return None
        return _float_or_none(getattr(snapshot, "reset_tokens_seconds", None))


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


class RateLimitedProvider:
    """One provider, paced. Satisfies 2a's four-method protocol and nothing more.

    This is the whole reason Phase 4 needed no change to ``AIEditor``, to the adapters,
    or to the base contract: the editor asks for an ``AIProvider`` and gets one. The
    limiter lives here, between the editor and the transport, where it can see the
    provider's errors and its headers without either side knowing it exists.

    What ``complete()`` does, in order:

    1. **Refuse outright** if the day's quota is already gone. Not a wait, not a retry —
       a run that has hit the daily wall must not spend one more request on the next
       chapter.
    2. **Pace** the request from the floors, and from live headers where the provider
       returns them.
    3. **Send** it.
    4. On a per-minute limit or a transient fault, **wait and retry**, bounded by the
       configured attempts. On a daily quota, **stop cleanly** and record why. On
       anything else — auth, context, a refused response — get out of the way.
    """

    def __init__(self, provider: Any, limiter: RateLimiter):
        self._provider = provider
        self._limiter = limiter

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"RateLimitedProvider({self._provider!r})"

    @property
    def inner(self) -> Any:
        return self._provider

    @property
    def limiter(self) -> RateLimiter:
        return self._limiter

    # -- delegated, unchanged ---------------------------------------------
    def capabilities(self):
        return self._provider.capabilities()

    def health_check(self):
        return self._provider.health_check()

    def list_models(self) -> list[str]:
        return self._provider.list_models()

    # -- pacing ------------------------------------------------------------
    def estimated_tokens(self, request: Any) -> int:
        """A deliberately conservative reservation, using 2a's own estimator.

        Reserving the full output budget over-reserves — which is the fail-safe
        direction and the same trade-off DECISIONS #053 kept for the local provider.
        The reservation is replaced by the real usage as soon as the provider reports it.
        """
        from .chunking import estimate_tokens

        return (
            estimate_tokens(getattr(request, "system_prompt", "") or "")
            + estimate_tokens(getattr(request, "text", "") or "")
            + int(getattr(request, "max_output_tokens", 0) or 0)
        )

    def _daily_block(self) -> DailyQuotaExhausted:
        stop = self._limiter.quota_stop
        reason = stop.reason if stop is not None else ""
        return DailyQuotaExhausted(
            f"The provider's free daily quota is already used up for this run"
            f"{': ' + reason if reason else '.'}",
            retryable=False,
        )

    def _daily_from_headers(self) -> DailyQuotaExhausted:
        return DailyQuotaExhausted(
            f"The provider reports no requests remaining for today for "
            f"{self._limiter.model_id or 'this model'} (requests per day), so this "
            f"request was not sent.",
            retryable=False,
        )

    def complete(self, request: Any):
        limiter = self._limiter
        stop = limiter.quota_stop
        if stop is not None and stop.is_daily:
            raise self._daily_block()

        reserve = self.estimated_tokens(request)
        attempts = max(1, limiter.settings.max_attempts)
        last_error: BaseException | None = None

        for attempt in range(attempts):
            snapshot = limiter.snapshot_from(self._provider, None)
            if limiter.is_daily_exhausted(snapshot):
                exhausted = self._daily_from_headers()
                limiter.note_quota_stop(
                    limiter.decide_for_error(exhausted, snapshot=snapshot), exhausted
                )
                raise exhausted

            limiter.wait_before_request(reserve, snapshot=snapshot)
            try:
                result = self._provider.complete(request)
            except (RateLimited, DailyQuotaExhausted, TransientNetworkError,
                    ProviderUnavailable) as exc:
                snapshot = limiter.snapshot_from(self._provider, exc)
                decision = limiter.decide_for_error(
                    exc, snapshot=snapshot, attempt=attempt
                )
                if decision.kind is LimitKind.NONE:
                    raise
                limiter.note_quota_stop(decision, exc)
                if not decision.retry:
                    raise
                last_error = exc
                if attempt + 1 >= attempts:
                    # Out of attempts. Serving the wait now would only delay the
                    # honest failure the editor is already going to fall back from.
                    break
                # May raise RequestCancelled if Stop is pressed mid-countdown.
                limiter.wait_for(decision)
                continue

            limiter.record_success(
                estimated_tokens=reserve,
                input_tokens=getattr(result, "input_tokens", None),
                output_tokens=getattr(result, "output_tokens", None),
                snapshot=limiter.snapshot_from(self._provider, None),
            )
            return result

        assert last_error is not None  # the loop only exits here after a failure
        raise last_error


def limiter_for(
    adapter: Any,
    settings: Mapping[str, Any] | None,
    *,
    provider: str,
    model_id: str = "",
    **kwargs: Any,
) -> RateLimiter:
    """Pick the limiter from the adapter's declared capability, never from its name.

    ``exposes_rate_limits`` is the switch the whole phase turns on: True means the
    adapter really does return headers and the limiter may be driven by them; False
    means it does not, and the configured floor is all there is. A provider added later
    gets the right limiter without this function learning its name.
    """
    exposes = False
    try:
        exposes = bool(adapter.capabilities().exposes_rate_limits)
    except Exception:  # pragma: no cover - a broken adapter must still be paced
        exposes = False
    cls = HeaderDrivenRateLimiter if exposes else FlooredRateLimiter
    return cls(
        settings=LimiterSettings.from_settings(settings, provider=provider),
        provider_name=provider,
        model_id=model_id,
        **kwargs,
    )


__all__ = [
    "BACKOFF_KINDS",
    "DAILY_KINDS",
    "FlooredRateLimiter",
    "HeaderDrivenRateLimiter",
    "LimitKind",
    "LimiterSettings",
    "QuotaStop",
    "RateLimitedProvider",
    "RateLimiter",
    "WaitDecision",
    "classify_limit",
    "limiter_for",
]
