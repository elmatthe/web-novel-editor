"""Every decision the cloud GUI makes, with no tkinter in sight.

Plan 2b Phase 6 adds a provider dropdown, a consent dialog, a status line, an ETA and
a resume offer. The widgets for those live in ``gui.app``; every *rule* lives here, so
each one is unit-testable headlessly — the same separation Plan 2a used for
``gui.ai_settings`` and for exactly the same reason.

Four things this module deliberately does **not** do:

* It never contacts a provider. Building the dropdown is pure policy over
  configuration; the only network call in the AI panel is still the explicit
  "Check service" probe in ``gui.ai_settings``.
* It never invents a status vocabulary. ``ai.cloud.check_readiness`` already
  distinguishes six states with a plain sentence each, and those are passed straight
  through. Flattening them into "available / unavailable" would destroy the very
  reason the drop asks for.
* It never populates the model picker from a live model list. A list endpoint reports
  technical availability, not free-tier eligibility for this account — the picker is
  built from the reviewed ``[[ai.approved_models]]`` records and nothing else. A test
  asserts that this module never names the provider-listing call at all.
* It never invents a limit figure. Every number in the ETA comes from a measurement,
  from a live response header, or from this app's own configured pacing floor — and
  where a figure is genuinely unknown, the estimate says so by name rather than
  guessing. See :func:`estimate_run`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ai.approved_models import (
    ensure_model_available,
    find_approved,
    load_approved_models,
    selectable_models,
)
from ai.cloud import (
    CLOUD_PROVIDERS,
    STATUS_CONSENT_REQUIRED,
    STATUS_NO_MODEL,
    STATUS_PROVIDER_DISABLED,
    check_readiness,
    is_cloud_provider,
    provider_settings,
)
from ai.disclosure import (
    DISCLOSURE_VERSION,
    PROVIDER_LABELS as DISCLOSURE_LABELS,
    PROVIDER_LINKS,
    disclosure_text,
    read_acknowledgements,
    record_acknowledgement,
)
from ai.models import ProviderStatus
from core.run_manifest import ResumeOffer, load_manifest, plan_resume

# The local provider's product name is deliberately NOT written here. It is confined
# to the provider factory and the configuration layer by a pre-existing invariant (with
# its own test), and the GUI has no business hardcoding it: this module asks the
# configuration boundary what the non-cloud provider is called.
_LOCAL_PROVIDER: str | None = None

LOCAL_LABEL = "On this computer (local)"


def local_provider() -> str:
    """The non-cloud provider's name, read once from the configuration defaults."""
    global _LOCAL_PROVIDER
    if _LOCAL_PROVIDER is None:
        from ai.config import IN_CODE_DEFAULTS

        _LOCAL_PROVIDER = str(IN_CODE_DEFAULTS.get("provider") or "")
    return _LOCAL_PROVIDER


def provider_label(provider: str) -> str:
    """The dropdown's display name for one provider."""
    name = str(provider or "").strip().lower()
    if not is_cloud_provider(name):
        return LOCAL_LABEL
    return f"{DISCLOSURE_LABELS.get(name, name)} — cloud"

# The level names are the GUI log's existing semantic levels, so one provider state
# reads the same whether it lands in the status line or the log.
_STATUS_LEVELS: dict[str, str] = {
    ProviderStatus.OK.value: "success",
    ProviderStatus.AUTH_MISSING.value: "warn",
    ProviderStatus.MODEL_MISSING.value: "warn",
    ProviderStatus.QUOTA_EXHAUSTED.value: "warn",
    ProviderStatus.INVALID_CONFIGURATION.value: "error",
    STATUS_CONSENT_REQUIRED: "warn",
    STATUS_NO_MODEL: "warn",
    STATUS_PROVIDER_DISABLED: "muted",
}

# Continuation lines in the condensed log (v0.11.0) are indented under the file line
# they belong to. Reused verbatim so a cloud event reads exactly like the existing
# "AI rejected" and "heading-only page" warnings rather than introducing a second shape.
LOG_INDENT = "        ⚠ "


# ===========================================================================
# Provider selection
# ===========================================================================
@dataclass(frozen=True)
class ProviderOption:
    """One row of the provider dropdown.

    ``ready`` and ``status`` are the provider's own answer, straight from
    ``check_readiness``. ``selectable`` is the *dropdown's* separate question and is
    deliberately not the same thing: a provider with no key is not ready, but it is
    absolutely still selectable, because selecting it is how the user gets told to add
    one. Only a provider with nowhere to go at all is greyed out — see
    :func:`provider_option`.
    """

    provider: str
    label: str
    selectable: bool
    ready: bool
    status: str
    reason: str
    level: str
    models: tuple[str, ...] = ()

    @property
    def is_cloud(self) -> bool:
        return self.provider in CLOUD_PROVIDERS


def selected_ai_table(
    ai_table: Mapping[str, Any] | None, provider: str, model_id: str = ""
) -> dict[str, Any]:
    """The ``[ai]`` table as it stands once the user has picked ``provider``.

    ``config.toml`` ships ``enabled = false`` for both cloud providers so that nothing
    is pre-selected before the Phase 7 comparison run. **Choosing the provider in the
    dropdown is what turns it on** — that is the "turn it on in the AI settings" the
    Phase 1 message refers to, and it is why the dropdown evaluates each provider as if
    it had been selected rather than showing every cloud provider as "turned off".

    This overlay is not a loosened safety rail. It moves one rail (an explicit user act
    before any cloud call) from a config flag onto the dropdown plus the disclosure
    dialog; every other rail — key present, model approved and free-confirmed, consent
    recorded for this disclosure version — is untouched and is still enforced by
    ``ensure_cloud_request_allowed`` before a single chapter leaves the machine.
    """
    table = dict(ai_table or {})
    name = str(provider or "").strip().lower()
    if not is_cloud_provider(name):
        return table
    section = dict(table.get(name) or {})
    section["enabled"] = True
    wanted = str(model_id or "").strip()
    if wanted:
        section["model"] = wanted
    table[name] = section
    return table


def approved_model_choices(
    provider: str,
    *,
    ai_table: Mapping[str, Any] | None = None,
    strict_free_only: bool | None = None,
) -> tuple[str, ...]:
    """The exact model IDs the picker may offer, from the reviewed records only."""
    name = str(provider or "").strip().lower()
    if not is_cloud_provider(name):
        return ()
    if strict_free_only is None:
        try:
            strict_free_only = bool(
                provider_settings(ai_table, name).get("strict_free_tier_only", True)
            )
        except Exception:
            strict_free_only = True
    models = load_approved_models(ai_table)
    return tuple(
        m.id for m in selectable_models(models, name, strict_free_only=strict_free_only)
    )


def _retirement_reason(
    provider: str,
    model_id: str,
    ai_table: Mapping[str, Any] | None,
    discovered_ids: Sequence[str] | None,
) -> str:
    """The provider's own retirement message, or '' when nothing says otherwise.

    An **empty** ``discovered_ids`` means the list could not be read — "unverifiable",
    not "retired". That rule is **not** re-implemented here: ``ensure_model_available``
    owns it and has its own Phase 1 test, and a second copy of the same condition in
    this module was found by mutation testing to be dead weight that no test could
    distinguish. Retirement is only ever reported from a real answer.
    """
    if not model_id:
        return ""
    model = find_approved(load_approved_models(ai_table), provider, model_id)
    if model is None:
        return ""
    try:
        ensure_model_available(model, discovered_ids)
    except Exception as exc:
        return str(exc)
    return ""


def provider_option(
    provider: str,
    *,
    ai_table: Mapping[str, Any] | None = None,
    model_id: str = "",
    environ: Mapping[str, str] | None = None,
    secrets_file: Path | None = None,
    dotenv_path: Path | None = None,
    settings_file: Path | None = None,
    version: str = DISCLOSURE_VERSION,
    discovered_ids: Sequence[str] | None = None,
) -> ProviderOption:
    """One dropdown row. Never raises and never contacts anything."""
    name = str(provider or "").strip().lower()

    if not is_cloud_provider(name):
        # The local provider is the path that always exists; its live health is the
        # existing "Check service" probe's job, not this function's.
        return ProviderOption(
            provider=name,
            label=provider_label(name),
            selectable=True,
            ready=True,
            status=ProviderStatus.OK.value,
            reason="",
            level="muted",
        )

    table = selected_ai_table(ai_table, name, model_id)
    choices = approved_model_choices(name, ai_table=table)
    readiness = check_readiness(
        name,
        ai_table=table,
        environ=environ,
        secrets_file=secrets_file,
        dotenv_path=dotenv_path,
        settings_file=settings_file,
        version=version,
    )

    status = readiness.status
    reason = "" if readiness.ready else readiness.message
    ready = readiness.ready

    retired = _retirement_reason(name, readiness.model_id, table, discovered_ids)
    if retired:
        ready = False
        status = ProviderStatus.MODEL_MISSING.value
        reason = retired

    # The one condition that greys a provider out entirely: there is no approved,
    # stable, free-confirmed model to pick, so nothing the user does inside this app
    # leads anywhere. That is the drop's rule — a provider is never selectable if its
    # only path forward is an unapproved or unknown-free-tier-confidence model.
    selectable = bool(choices)
    if not selectable:
        ready = False
        status = ProviderStatus.MODEL_MISSING.value
        reason = (
            f"No approved model is available for "
            f"{DISCLOSURE_LABELS.get(name, name)}. Every reviewed record for it is "
            f"preview, not free of charge, or of unknown free-tier confidence, so "
            f"there is nothing this app is allowed to call. Add a reviewed record "
            f"under [[ai.approved_models]] in config.toml."
        )

    return ProviderOption(
        provider=name,
        label=provider_label(name),
        selectable=selectable,
        ready=ready,
        status=status,
        reason=reason,
        level=_STATUS_LEVELS.get(status, "warn"),
        models=choices,
    )


def provider_options(**kwargs: Any) -> tuple[ProviderOption, ...]:
    """Every row of the dropdown, local first — the path that always works.

    ``model_id`` is the model chosen in the panel, and it applies **only** to
    ``selected``. A model belongs to one provider; letting the box's current value leak
    into every row would evaluate Gemini's readiness against a Groq model ID and report
    a refusal that has nothing to do with Gemini.
    """
    model_id = kwargs.pop("model_id", "")
    selected = str(kwargs.pop("selected", "") or "").strip().lower()
    rows = [provider_option(local_provider(), **kwargs)]
    for name in CLOUD_PROVIDERS:
        rows.append(
            provider_option(
                name, model_id=(model_id if name == selected else ""), **kwargs
            )
        )
    return tuple(rows)


def measured_fallback_rate(payload: Mapping[str, Any] | None) -> float | None:
    """The observed fallback rate from a run manifest, or None when nothing is recorded.

    This is the drop's "measured accepted/fallback rate" and it is the one ETA input a
    previous run really does leave behind. Chapters with no AI status at all are not
    counted — an unmeasured chapter must not be silently scored as a success.
    """
    entries = (payload or {}).get("entries") or []
    accepted = fallback = 0
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        status = str(entry.get("ai_status") or "")
        if status == "accepted":
            accepted += 1
        elif status == "fallback":
            fallback += 1
    total = accepted + fallback
    return (fallback / total) if total else None


# ===========================================================================
# The privacy + billing disclosure
# ===========================================================================
DISCLOSURE_NEW = "new"
DISCLOSURE_CHANGED = "changed"
DISCLOSURE_ACKNOWLEDGED = "acknowledged"


@dataclass(frozen=True)
class DisclosureNeed:
    """Whether the disclosure must be shown, and what the dialog should say."""

    provider: str
    required: bool
    state: str
    version: str
    acknowledged_version: str
    title: str
    body: str
    accept_label: str
    cancel_label: str
    billing_url: str


def disclosure_requirement(
    provider: str,
    *,
    settings_file: Path | None = None,
    version: str = DISCLOSURE_VERSION,
) -> DisclosureNeed:
    """Decide whether to ask, and distinguish "never asked" from "the notice changed".

    Both currently produce the same ``False`` from ``is_acknowledged``, but they are not
    the same thing to a user: someone who accepted version 1 and now meets version 2 is
    not being told they never consented — they are being told the notice has changed.
    Computed from Phase 1's existing acknowledgement record; nothing here writes.
    """
    name = str(provider or "").strip().lower()
    label = DISCLOSURE_LABELS.get(name, name or "this provider")
    stored = read_acknowledgements(settings_file=settings_file).get(name, "")
    current = str(version)

    if stored == current:
        state, required = DISCLOSURE_ACKNOWLEDGED, False
    elif stored:
        state, required = DISCLOSURE_CHANGED, True
    else:
        state, required = DISCLOSURE_NEW, True

    body = disclosure_text(name)
    if state == DISCLOSURE_CHANGED:
        body = (
            f"This notice has changed since you last accepted it, so it is being "
            f"shown again. Please read it before continuing.\n\n" + body
        )

    return DisclosureNeed(
        provider=name,
        required=required,
        state=state,
        version=current,
        acknowledged_version=stored,
        title=f"Send chapter text to {label}?",
        body=body,
        accept_label=f"I understand — send chapters to {label}",
        cancel_label="Cancel — keep local or script-only editing",
        billing_url=PROVIDER_LINKS.get(name, {}).get("billing", ""),
    )


# ===========================================================================
# In-app key entry — a GUI door onto Phase 1's storage, and nothing more
# ===========================================================================
# Phase 1 built key precedence, the atomic per-user `secrets.json` write, the
# permission tightening and presence-only reporting, and deferred only the entry
# dialog. Everything below **calls** those functions; none of it reimplements any part
# of them, and no key value is ever held, returned, logged or formatted into a message
# here. `ai.secrets` is imported inside each function so it resolves in the same
# generation as its caller (`test_ai_foundation` reloads the package mid-suite).
@dataclass(frozen=True)
class KeyOutcome:
    """What happened to a stored key. Carries no key value, by construction."""

    provider: str
    saved: bool
    removed: bool
    message: str
    level: str


@dataclass(frozen=True)
class KeyPrompt:
    """What the key dialog should say. Carries no key value, by construction."""

    provider: str
    title: str
    body: str
    current: str
    can_forget: bool
    env_var: str


def save_key(
    provider: str, key: str, *, secrets_file: Path | None = None
) -> KeyOutcome:
    """Save one provider's key through Phase 1's ``store_api_key``.

    That function owns the atomic write, the permission tightening and registering the
    value with the redactor. This adds only the wording.
    """
    from ai import secrets

    name = str(provider or "").strip().lower()
    label = DISCLOSURE_LABELS.get(name, name or "this provider")
    if not is_cloud_provider(name):
        return KeyOutcome(name, False, False,
                          f"{label} does not use an API key.", "muted")

    if secrets.store_api_key(name, key, path=secrets_file):
        return KeyOutcome(
            name, True, False,
            f"{label} key saved on this computer. It is stored outside the project "
            f"folder, readable only by your account, and never written to a log.",
            "success",
        )
    return KeyOutcome(
        name, False, False,
        f"That does not look like a usable {label} key, so nothing was saved. Paste "
        f"the whole key from the provider's console.",
        "warn",
    )


def forget_key(provider: str, *, secrets_file: Path | None = None) -> KeyOutcome:
    """Delete one provider's saved key through Phase 1's ``delete_api_key``.

    Only the saved copy is removed. An environment variable or a developer ``.env``
    is not this app's to delete, and the wording says so rather than implying the
    provider is now certainly keyless.
    """
    from ai import secrets

    name = str(provider or "").strip().lower()
    label = DISCLOSURE_LABELS.get(name, name or "this provider")
    if not is_cloud_provider(name):
        return KeyOutcome(name, False, False,
                          f"{label} does not use an API key.", "muted")

    if secrets.delete_api_key(name, path=secrets_file):
        return KeyOutcome(
            name, False, True,
            f"The saved {label} key was removed from this computer. If a key is still "
            f"found, it is coming from an environment variable or the developer .env.",
            "success",
        )
    return KeyOutcome(
        name, False, False,
        f"There was no saved {label} key on this computer to remove.", "muted",
    )


def key_prompt(
    provider: str,
    *,
    environ: Mapping[str, str] | None = None,
    secrets_file: Path | None = None,
    dotenv_path: Path | None = None,
) -> KeyPrompt | None:
    """What the key dialog should show, or None for a provider that takes no key.

    ``current`` is Phase 1's **presence-only** sentence — which source a key was found
    in, never the key. That matters here beyond privacy: the environment variable
    outranks the saved file, so a correctly saved key can still not be the one in use,
    and saying which source is winning stops that looking like a failed save.
    """
    from ai import secrets

    name = str(provider or "").strip().lower()
    if not is_cloud_provider(name):
        return None
    label = DISCLOSURE_LABELS.get(name, name)
    presence = secrets.describe_key(
        name, environ=environ, secrets_file=secrets_file, dotenv_path=dotenv_path
    )
    saved = secrets.describe_key(
        name, environ={}, secrets_file=secrets_file, dotenv_path=Path(_NOWHERE)
    )
    return KeyPrompt(
        provider=name,
        title=f"{label} API key",
        body=(
            f"Paste your {label} API key below. It is saved on this computer only, "
            f"outside the project folder, and is never written to a log, a manifest or "
            f"the project's configuration.\n\n"
            f"An API key is a credential — treat it like a password. Use a key from a "
            f"project or organization with billing disabled."
        ),
        current=presence.message,
        can_forget=saved.source == "secrets_file",
        env_var=secrets.ENV_VARS.get(name, ""),
    )


# A path that cannot exist, used to ask "is there a key in the *saved file*" without
# letting a developer .env answer for it.
_NOWHERE = "\0no-such-dotenv"


def accept_disclosure(
    provider: str,
    *,
    settings_file: Path | None = None,
    version: str = DISCLOSURE_VERSION,
) -> bool:
    """Record the acceptance. Stores the version string and nothing else."""
    return record_acknowledgement(
        provider, settings_file=settings_file, version=version
    )


# ===========================================================================
# The ETA
# ===========================================================================
ETA_RANGE = "range"
ETA_LOWER_BOUND = "lower_bound"
ETA_NONE = "none"

SECONDS_PER_MINUTE = 60.0

# Above this many remaining chapters, say plainly that a free tier is for subsets.
# Phase 0 correction #5: on Groq free, TPD binds at roughly ten chapters a day, so a
# whole-novel cloud run is not viable and the user is entitled to know before starting.
SUBSET_ADVICE_THRESHOLD = 200


@dataclass(frozen=True)
class RunEstimate:
    """A labelled estimate, or an honest refusal to give one.

    Three kinds, and the difference between them is the whole point:

    ``range``
        Every binding input is known. ``low_seconds``/``high_seconds`` bracket the run.
    ``lower_bound``
        The per-chapter cost is known and this app's own pacing gives a real floor, but
        a *daily* limit is unknown — and an unknown daily quota is unbounded in the bad
        direction, so no upper end can honestly be stated. ``high_seconds`` is None.
    ``none``
        The per-chapter cost itself is unmeasured, so there are no hours to give at all.
        This is the normal state before the first cloud run has ever been made.
    """

    provider: str
    model_id: str
    remaining_files: int
    kind: str
    low_seconds: float | None
    high_seconds: float | None
    binding: str
    unknowns: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default=())

    @property
    def headline(self) -> str:
        if self.kind == ETA_RANGE:
            if self.high_seconds is not None and self.low_seconds is not None and (
                format_span(self.low_seconds) == format_span(self.high_seconds)
            ):
                # A true single value. Printing "3 hours – 3 hours" would look broken;
                # "approximately" plus the Estimate label is what makes it an estimate,
                # not the presence of a dash. Do not "fix" this into a fake band.
                return (
                    f"Estimate: approximately {format_span(self.low_seconds)} for "
                    f"{self.remaining_files} chapter(s)."
                )
            return (
                f"Estimate: approximately {format_span(self.low_seconds or 0)}–"
                f"{format_span(self.high_seconds or 0)} for "
                f"{self.remaining_files} chapter(s)."
            )
        if self.kind == ETA_LOWER_BOUND:
            return (
                f"Estimate: at least {format_span(self.low_seconds or 0)} of "
                f"processing for {self.remaining_files} chapter(s) — the total cannot "
                f"be estimated, see below."
            )
        if self.remaining_files <= 0:
            return "Estimate: there are no chapters queued."
        return (
            f"Estimate: how long {self.remaining_files} chapter(s) will take cannot "
            f"be estimated yet."
        )

    def as_text(self) -> str:
        lines = [self.headline]
        if self.unknowns:
            lines.append("Not known: " + "; ".join(self.unknowns) + ".")
        lines.extend(self.notes)
        return "\n".join(lines)


def format_span(seconds: float) -> str:
    """Minutes, hours or days — whichever reads honestly at that magnitude.

    The drop asks for hours, and hours is the base unit. Minutes and days are used at
    the extremes because "approximately 0.08 hours" and "approximately 312 hours" are
    worse for the reader than "5 minutes" and "13 days" without being any more precise.
    """
    total = max(0.0, float(seconds))
    if total < 3600:
        value = max(1, int(round(total / 60.0)))
        return f"{value} minute" + ("" if value == 1 else "s")
    if total < 48 * 3600:
        value = max(1, int(round(total / 3600.0)))
        return f"{value} hour" + ("" if value == 1 else "s")
    value = max(1, int(round(total / 86400.0)))
    return f"{value} day" + ("" if value == 1 else "s")


def _number(value: Any) -> float | None:
    """A float, or None when the value is absent or unparsable. Zero is kept."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive(value: Any) -> float | None:
    """A float above zero, or None. For *observed* figures, where a reported zero is
    indistinguishable from a missing one and must not be paced on."""
    number = _number(value)
    return number if number is not None and number > 0 else None


def estimate_run(
    *,
    provider: str,
    model_id: str,
    remaining_files: int,
    settings: Mapping[str, Any] | None = None,
    requests_per_chapter: float | None = None,
    tokens_per_chapter: float | None = None,
    fallback_rate: float | None = None,
    observed: Mapping[str, Any] | None = None,
) -> RunEstimate:
    """The honest ETA, shown before a cloud run starts.

    Inputs, and what happens when each is unknown:

    ``remaining_files``
        Always known.
    ``requests_per_chapter`` / ``tokens_per_chapter``
        Measured. Unknown ⇒ there is nothing to multiply, so the answer is ``none``.
    ``fallback_rate``
        Measured. Unknown ⇒ the range widens to its *true* worst case rather than
        collapsing: 2a retries a rejected chunk at most once before chapter-atomic
        fallback, so a chapter costs between 1× and 2×. That is a derived bound, not a
        guess.
    ``observed``
        Live figures scraped from response headers — ``rpm``, ``tpm``, ``rpd``, ``tpd``,
        ``reset_seconds``. Absent per-minute figures fall back to this app's own
        configured pacing floor, which is a real known number *about this app* and is
        always worded that way, never as a claim about the provider's limit. Absent
        daily figures cannot fall back to anything: Groq never reports tokens-per-day
        and Google publishes no free-tier table at all, so the daily term is genuinely
        unknown and the result degrades to ``lower_bound``.
    ``reset_seconds``
        Folds the reset-time uncertainty in: a run spanning *d* quota-days crosses
        *d − 1* resets, and each one costs somewhere between nothing and a whole reset
        period, because how far into the current window the run starts is not knowable.
        Unknown reset ⇒ the daily term is unusable ⇒ ``lower_bound``, by the same rule.
    """
    name = str(provider or "").strip().lower()
    label = DISCLOSURE_LABELS.get(name, name or "this provider")
    live: Mapping[str, Any] = observed or {}
    floors = settings or {}
    files = max(0, int(remaining_files))

    unknowns: list[str] = []
    notes: list[str] = []

    if files > SUBSET_ADVICE_THRESHOLD:
        notes.append(
            "Free cloud tiers are sized for subsets and comparison runs, not for a "
            "whole novel — the local on-this-computer pass remains the bulk path."
        )

    # -- per-chapter cost ---------------------------------------------------
    requests = _positive(requests_per_chapter)
    tokens = _positive(tokens_per_chapter)
    if requests is None:
        unknowns.append("how many requests a chapter costs (nothing measured yet)")
    if tokens is None:
        unknowns.append("how many tokens a chapter costs (nothing measured yet)")

    if fallback_rate is None:
        unknowns.append(
            "how often the AI's edit is rejected, which decides whether a chapter "
            "costs one pass or two"
        )
        low_multiplier, high_multiplier = 1.0, 2.0
    else:
        rate = min(1.0, max(0.0, float(fallback_rate)))
        low_multiplier, high_multiplier = 1.0, 1.0 + rate

    if files <= 0 or requests is None or tokens is None:
        return RunEstimate(
            provider=name,
            model_id=model_id,
            remaining_files=files,
            kind=ETA_NONE,
            low_seconds=None,
            high_seconds=None,
            binding="unknown",
            unknowns=tuple(unknowns),
            notes=tuple(notes + _limit_notes(name, live)),
        )

    total_requests_low = files * requests * low_multiplier
    total_requests_high = files * requests * high_multiplier
    total_tokens_low = files * tokens * low_multiplier
    total_tokens_high = files * tokens * high_multiplier

    # -- per-minute pacing ---------------------------------------------------
    # Configured floors are read *without* a positivity filter, on purpose: a floor of
    # zero is a meaningful configured value ("do not pace on this axis"), not a parse
    # failure, and hiding it behind `_positive` would leave two places deciding what
    # zero means. `is_rate` below is the single place that decides.
    rpm = _positive(live.get("rpm"))
    rpm_from_provider = rpm is not None
    if rpm is None:
        rpm = _number(floors.get("rpm_floor"))
    tpm = _positive(live.get("tpm"))
    tpm_from_provider = tpm is not None
    if tpm is None:
        tpm = _number(floors.get("tpm_floor"))

    # One guard, stated once: a rate of zero or less is **not a constraint**, and it is
    # certainly not "infinitely slow". Gemini ships `tpm_floor = 0` deliberately — no
    # Gemini token figure exists to base one on, and Phase 4 refused to invent one — so
    # this branch is the normal Gemini path, not an edge case. Written as an explicit
    # `is_rate` test rather than leaning on `_positive` returning None, so that removing
    # it is a real change a test can catch rather than a redundancy nothing notices.
    def is_rate(value: float | None) -> bool:
        return value is not None and value > 0

    minute_terms: list[tuple[str, float, float]] = []
    if is_rate(rpm):
        minute_terms.append(
            ("requests_per_minute",
             total_requests_low / rpm * SECONDS_PER_MINUTE,
             total_requests_high / rpm * SECONDS_PER_MINUTE)
        )
    if is_rate(tpm):
        minute_terms.append(
            ("tokens_per_minute",
             total_tokens_low / tpm * SECONDS_PER_MINUTE,
             total_tokens_high / tpm * SECONDS_PER_MINUTE)
        )

    if not rpm_from_provider or not tpm_from_provider:
        notes.append(
            "The per-minute figures below are this app's own pacing, not a limit "
            f"{label} has told us about."
        )

    if not minute_terms:
        unknowns.append("any per-minute pace to work from")
        return RunEstimate(
            provider=name,
            model_id=model_id,
            remaining_files=files,
            kind=ETA_NONE,
            low_seconds=None,
            high_seconds=None,
            binding="unknown",
            unknowns=tuple(unknowns),
            notes=tuple(notes + _limit_notes(name, live)),
        )

    binding, processing_low, processing_high = max(
        minute_terms, key=lambda term: term[2]
    )

    # -- daily quota ---------------------------------------------------------
    rpd = _positive(live.get("rpd"))
    tpd = _positive(live.get("tpd"))
    reset_seconds = _positive(live.get("reset_seconds"))

    if rpd is None:
        unknowns.append(f"{label}'s requests-per-day quota")
    if tpd is None:
        unknowns.append(f"{label}'s tokens-per-day quota")
    if (rpd is not None or tpd is not None) and reset_seconds is None:
        unknowns.append("when the daily quota resets")

    notes.extend(_limit_notes(name, live))

    if rpd is None or tpd is None or reset_seconds is None:
        # An unknown *daily* quota is unbounded in the bad direction — the run might
        # finish today or stop every day for a fortnight — so no upper end can be
        # honestly stated. An unknown *per-minute* figure is different: this app's own
        # floor still gives a real lower bound, which is why one is reported.
        return RunEstimate(
            provider=name,
            model_id=model_id,
            remaining_files=files,
            kind=ETA_LOWER_BOUND,
            low_seconds=processing_low,
            high_seconds=None,
            binding="unknown",
            unknowns=tuple(unknowns),
            notes=tuple(notes),
        )

    quota_days_low = max(total_requests_low / rpd, total_tokens_low / tpd)
    quota_days_high = max(total_requests_high / rpd, total_tokens_high / tpd)
    if quota_days_high > (processing_high / reset_seconds):
        binding = (
            "tokens_per_day"
            if total_tokens_high / tpd >= total_requests_high / rpd
            else "requests_per_day"
        )

    # A run spanning d quota-days crosses d-1 resets. Each crossing costs somewhere
    # between nothing (the window was about to roll over anyway) and a whole reset
    # period (it had only just started), because how far into the current window this
    # run begins is not knowable. That is the entire width of the range's daily term —
    # the low end therefore adds nothing, deliberately, and must not grow a fudge factor.
    crossed_high = max(0, math.ceil(quota_days_high) - 1)
    return RunEstimate(
        provider=name,
        model_id=model_id,
        remaining_files=files,
        kind=ETA_RANGE,
        low_seconds=processing_low,
        high_seconds=processing_high + crossed_high * reset_seconds,
        binding=binding,
        unknowns=tuple(unknowns),
        notes=tuple(notes),
    )


def _limit_notes(provider: str, observed: Mapping[str, Any]) -> list[str]:
    """The provider-specific honesty each ETA owes the user.

    These are statements about what each provider does and does not report — recorded
    research findings, not limit figures — and they are the whole reason the drop
    singles Gemini out.
    """
    name = str(provider or "").strip().lower()
    notes: list[str] = []
    if name == "gemini":
        notes.append(
            "Google publishes no free-tier rate-limit table for the Gemini API and "
            "returns no rate-limit headers, so the limit that will actually stop this "
            "run is unknown. The live figures for your project are in AI Studio."
        )
    elif name == "groq":
        if not observed.get("rpm") and not observed.get("tpm"):
            notes.append(
                "Groq reports its per-minute and per-day request figures in response "
                "headers, but only once a request has been made."
            )
        notes.append(
            "Groq never reports tokens per day, and on the free plan that is the "
            "limit that binds first — check your own limits page before a long run."
        )
    return notes


# ===========================================================================
# The resume offer
# ===========================================================================
@dataclass(frozen=True)
class ResumePlan:
    """What the Yes/No answer to the resume dialog actually means.

    ``resumed = False`` is not a failure — it is the ordinary fresh-run path, which
    allocates the next ``<novel>-N`` folder exactly as it always has. Declining is not
    a call into the manifest layer at all, so nothing on disk is touched.
    """

    resumed: bool
    run_kwargs: dict[str, Any]
    checkpoint_kwargs: dict[str, Any]
    message: str
    fallback_rate: float | None = None


def resume_prompt(offer: ResumeOffer) -> str:
    """The dialog's question. Counts come from the queue, never from ``completed_count``
    (a resumed run's entries start empty — see the HANDOFF note)."""
    novel = offer.novel or "a previous run"
    lines = [
        f"An unfinished run for {novel} was found.",
        f"{offer.reason}",
        f"Output folder: {offer.output_dir}",
    ]
    if offer.missing_inputs:
        lines.append(
            f"{len(offer.missing_inputs)} of the remaining chapter file(s) can no "
            f"longer be found where that run left them; they will be reported as "
            f"skipped."
        )
    if offer.stopped_reason:
        lines.append(f"It stopped because: {offer.stopped_reason.replace('_', ' ')}.")
    lines.append("Resume it? Choosing No starts a fresh run in a new folder.")
    return "\n\n".join(lines)


def resume_decision(offer: ResumeOffer, *, accepted: bool) -> ResumePlan:
    """Turn the dialog's answer into run arguments. Never raises."""
    if offer is None or not offer.available or not accepted:
        return ResumePlan(False, {}, {}, "Starting a fresh run.")

    payload = load_manifest(offer.manifest_path) if offer.manifest_path else None
    if payload is None:
        # It was readable when the offer was made and is not now. Guessing the queue
        # would be inventing the very state the manifest exists to record.
        return ResumePlan(
            False, {}, {},
            "That run's manifest could no longer be read, so a fresh run was started "
            "instead.",
        )

    try:
        run_kwargs = plan_resume(offer)
    except ValueError:
        return ResumePlan(False, {}, {}, "That run cannot be resumed; starting a "
                                         "fresh run.")

    run = payload.get("run") or {}
    # The checkpoint continues the ORIGINAL queue from the original index, so the
    # manifest keeps describing the run it claims to continue. Rebuilding it from just
    # the remainder would work, but a second resume would then be continuing a run
    # whose recorded shape had silently changed underneath it.
    checkpoint_kwargs = {
        "output_dir": offer.output_dir,
        "queue": [str(item) for item in payload["queue"]],
        "start_index": int(payload["next_index"]),
        "novel": offer.novel,
        "mirror_root": offer.mirror_root,
        "provider": str(run.get("provider") or ""),
        "model_id": str(run.get("model_id") or ""),
        "prompt_version": str(run.get("prompt_version") or ""),
        "gate_version": str(run.get("gate_version") or ""),
        "ai_policy": str(run.get("ai_policy") or ""),
    }
    return ResumePlan(
        True,
        run_kwargs,
        checkpoint_kwargs,
        f"Resuming into {offer.output_dir}.",
        fallback_rate=measured_fallback_rate(payload),
    )


# ===========================================================================
# Condensed-log additions
# ===========================================================================
def cloud_run_header(provider: str, model_id: str) -> tuple[str, str] | None:
    """One run-scoped line naming the provider and model, or None for the local path.

    Run-scoped facts belong on a run-scoped line. The provider and model cannot change
    mid-run — they are fixed when the editor is constructed — so repeating them on
    every per-file line would add N lines of noise and break the condensed log's whole
    point. The per-file ``[i/total] name — outcome`` line is not touched.
    """
    name = str(provider or "").strip().lower()
    if not is_cloud_provider(name):
        return None
    label = DISCLOSURE_LABELS.get(name, name)
    return (
        f"Cloud provider: {label} — model {model_id}. Chapter text leaves this "
        f"computer for this run.",
        "accent",
    )


def quota_stop_message(record: Mapping[str, Any] | None) -> tuple[str, str]:
    """The one line a quota stop adds, in the existing indented continuation shape."""
    data: Mapping[str, Any] = record or {}
    name = str(data.get("provider") or "").strip().lower()
    label = DISCLOSURE_LABELS.get(name, name or "the provider")
    limits = PROVIDER_LINKS.get(name, {}).get("limits", "")

    if data.get("is_daily"):
        text = (
            f"Daily free quota reached for {label}. The run has stopped cleanly and "
            f"everything finished so far is saved — you can close the app and resume "
            f"tomorrow."
        )
        if data.get("reset_known"):
            reset = _positive(data.get("reset_seconds"))
            if reset:
                text += f" The quota resets in about {format_span(reset)}."
        else:
            text += (
                f" The reset time is unknown — this app does not guess it. See "
                f"{limits or 'the provider’s limits page'}."
            )
    else:
        text = (
            f"{label} asked for a wait longer than this session will hold. The run has "
            f"stopped cleanly and everything finished so far is saved."
        )
        reset = _positive(data.get("reset_seconds"))
        if data.get("reset_known") and reset:
            text += f" It asked for about {format_span(reset)}."
        elif limits:
            text += f" See {limits}."
    return LOG_INDENT + text, "warn"


__all__ = [
    "DISCLOSURE_ACKNOWLEDGED",
    "DISCLOSURE_CHANGED",
    "DISCLOSURE_NEW",
    "ETA_LOWER_BOUND",
    "ETA_NONE",
    "ETA_RANGE",
    "LOG_INDENT",
    "LOCAL_LABEL",
    "STATUS_CONSENT_REQUIRED",
    "STATUS_NO_MODEL",
    "STATUS_PROVIDER_DISABLED",
    "DisclosureNeed",
    "KeyOutcome",
    "KeyPrompt",
    "ProviderOption",
    "ResumePlan",
    "RunEstimate",
    "accept_disclosure",
    "approved_model_choices",
    "cloud_run_header",
    "disclosure_requirement",
    "estimate_run",
    "forget_key",
    "format_span",
    "is_cloud_provider",
    "key_prompt",
    "local_provider",
    "measured_fallback_rate",
    "provider_label",
    "provider_option",
    "provider_options",
    "provider_settings",
    "quota_stop_message",
    "resume_decision",
    "resume_prompt",
    "save_key",
    "selected_ai_table",
]
