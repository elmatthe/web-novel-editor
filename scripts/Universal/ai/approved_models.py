"""Reviewed approved-model records and the rules that refuse everything else.

This replaces runtime "detect the models and pick the newest" selection, which was
cancelled in the Plan 2b drop for three reasons: a model-list endpoint reports technical
availability, not free-tier eligibility for *this* account; ``latest``-style aliases
hot-swap and can land on a preview model that requires billing; and lexical "newest"
sorting across two providers' naming schemes is not a real ordering.

Instead, ``config.toml`` carries a dated, reviewed record per approved model, and this
module is the only thing that decides whether a model may be called.

**What the approved list is — stated honestly, per the drop.** It is a conservative
guard against *accidentally* calling something expensive, retired, or preview. It is
user-editable TOML, so it is **not** a security boundary and **not** a billing boundary,
and it must never be described as one.

**What this module deliberately does not have:** any function that picks a substitute.
There is no "newest", no "fallback", no "first available". When the configured model is
not approved or has disappeared, the only outcome is a refusal with a message telling
the user what to fix. Silently editing three thousand chapters with a model the user did
not choose is the failure this design exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .errors import ModelUnavailable

STATUS_STABLE = "stable"

CONFIDENCE_CONFIRMED = "confirmed"
CONFIDENCE_UNKNOWN = "unknown"
CONFIDENCE_NOT_FREE = "not-free"
VALID_CONFIDENCE = (CONFIDENCE_CONFIRMED, CONFIDENCE_UNKNOWN, CONFIDENCE_NOT_FREE)

# Substrings that mark a moving alias rather than an exact release. An alias can be
# repointed by the provider at any time, including onto a paid preview model, which is
# precisely the surprise this plan refuses to allow.
ALIAS_MARKERS = ("latest", "*")

_REQUIRED_TEXT_FIELDS = ("id", "provider", "status", "reviewed_on", "source_url",
                         "pilot_status")


@dataclass(frozen=True)
class ApprovedModel:
    """One reviewed record. The nine fields are exactly the drop's schema."""

    id: str
    provider: str
    status: str
    context_limit: int
    output_limit: int
    reviewed_on: str
    source_url: str
    free_tier_confidence: str
    pilot_status: str

    @property
    def is_free_tier_confirmed(self) -> bool:
        return self.free_tier_confidence == CONFIDENCE_CONFIRMED

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "status": self.status,
            "context_limit": self.context_limit,
            "output_limit": self.output_limit,
            "reviewed_on": self.reviewed_on,
            "source_url": self.source_url,
            "free_tier_confidence": self.free_tier_confidence,
            "pilot_status": self.pilot_status,
        }


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def looks_like_alias(model_id: str) -> bool:
    """True for a moving alias such as ``gemini-flash-latest``."""
    lowered = str(model_id or "").lower()
    return any(marker in lowered for marker in ALIAS_MARKERS)


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def parse_approved_models(
    raw: Any,
) -> tuple[tuple[ApprovedModel, ...], tuple[str, ...]]:
    """Parse raw records into ``(models, problems)``.

    A malformed record is skipped with a readable reason rather than raising: a typo in
    hand-edited TOML must cost the user that one model, not the whole application.
    """
    if not isinstance(raw, (list, tuple)):
        if raw is None:
            return (), ()
        return (), ("ai.approved_models is not a list of records.",)

    models: list[ApprovedModel] = []
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()

    for index, entry in enumerate(raw):
        label = f"approved_models[{index}]"
        if not isinstance(entry, Mapping):
            problems.append(f"{label}: not a table.")
            continue

        missing = [f for f in _REQUIRED_TEXT_FIELDS
                   if not str(entry.get(f, "") or "").strip()]
        if missing:
            problems.append(f"{label}: missing {', '.join(missing)}.")
            continue

        model_id = str(entry["id"]).strip()
        if looks_like_alias(model_id):
            problems.append(
                f"{label}: '{model_id}' is a moving alias ('latest'-style). Only exact "
                f"model IDs are allowed."
            )
            continue

        context_limit = _positive_int(entry.get("context_limit"))
        output_limit = _positive_int(entry.get("output_limit"))
        if context_limit is None or output_limit is None:
            problems.append(
                f"{label}: context_limit and output_limit must be positive integers."
            )
            continue

        confidence = str(entry.get("free_tier_confidence", "") or "").strip().lower()
        if confidence not in VALID_CONFIDENCE:
            problems.append(
                f"{label}: free_tier_confidence must be one of "
                f"{', '.join(VALID_CONFIDENCE)}."
            )
            continue

        provider = str(entry["provider"]).strip().lower()
        key = (provider, model_id)
        if key in seen:
            problems.append(f"{label}: duplicate record for '{model_id}'.")
            continue
        seen.add(key)

        models.append(
            ApprovedModel(
                id=model_id,
                provider=provider,
                status=str(entry["status"]).strip().lower(),
                context_limit=context_limit,
                output_limit=output_limit,
                reviewed_on=str(entry["reviewed_on"]).strip(),
                source_url=str(entry["source_url"]).strip(),
                free_tier_confidence=confidence,
                pilot_status=str(entry["pilot_status"]).strip(),
            )
        )
    return tuple(models), tuple(problems)


def load_approved_models(ai_table: Mapping[str, Any] | None) -> tuple[ApprovedModel, ...]:
    """Read the reviewed records out of a resolved ``[ai]`` table."""
    if not isinstance(ai_table, Mapping):
        return ()
    models, _problems = parse_approved_models(ai_table.get("approved_models"))
    return models


def approved_problems(ai_table: Mapping[str, Any] | None) -> tuple[str, ...]:
    """The reasons any records were skipped, for the GUI to surface."""
    if not isinstance(ai_table, Mapping):
        return ()
    _models, problems = parse_approved_models(ai_table.get("approved_models"))
    return problems


# ---------------------------------------------------------------------------
# Selection rules
# ---------------------------------------------------------------------------
def approved_for_provider(
    models: Iterable[ApprovedModel], provider: str
) -> tuple[ApprovedModel, ...]:
    name = str(provider or "").strip().lower()
    return tuple(m for m in models if m.provider == name)


def selectable_models(
    models: Iterable[ApprovedModel],
    provider: str,
    *,
    strict_free_only: bool = True,
) -> tuple[ApprovedModel, ...]:
    """The models the GUI may offer. Strict mode is the default and ships on."""
    candidates = approved_for_provider(models, provider)
    if not strict_free_only:
        return candidates
    return tuple(
        m for m in candidates
        if m.status == STATUS_STABLE and m.free_tier_confidence == CONFIDENCE_CONFIRMED
    )


def find_approved(
    models: Iterable[ApprovedModel], provider: str, model_id: str
) -> ApprovedModel | None:
    wanted = str(model_id or "").strip()
    for model in approved_for_provider(models, provider):
        if model.id == wanted:
            return model
    return None


def ensure_model_approved(
    model_id: str,
    *,
    provider: str,
    models: Iterable[ApprovedModel],
    strict_free_only: bool = True,
) -> ApprovedModel:
    """Return the reviewed record for ``model_id``, or refuse with a clear reason.

    Every rejection raises ``ModelUnavailable`` (non-retryable). Nothing is ever
    substituted — that is the entire point of this function.
    """
    provider_name = str(provider or "").strip().lower()
    label = provider_name or "this provider"
    wanted = str(model_id or "").strip()

    if not wanted:
        raise ModelUnavailable(
            f"No model has been chosen for {label}. Pick one of the approved models "
            f"before running a cloud pass.",
            retryable=False,
        )
    if looks_like_alias(wanted):
        raise ModelUnavailable(
            f"'{wanted}' is a moving alias, and moving aliases are never used: the "
            f"provider can repoint one onto a preview or paid model without notice. "
            f"Choose an exact model ID from the approved list.",
            retryable=False,
        )

    model = find_approved(models, provider_name, wanted)
    if model is None:
        raise ModelUnavailable(
            f"'{wanted}' is not in the approved model list for {label}. Add a reviewed "
            f"record for it under [[ai.approved_models]] in config.toml, or choose one "
            f"of the models already approved.",
            retryable=False,
        )

    if not strict_free_only:
        return model

    if model.status != STATUS_STABLE:
        raise ModelUnavailable(
            f"'{model.id}' is marked '{model.status}', and only stable models are "
            f"allowed while free-tier-only mode is on. Preview and experimental models "
            f"commonly require billing.",
            retryable=False,
        )
    if model.free_tier_confidence == CONFIDENCE_NOT_FREE:
        raise ModelUnavailable(
            f"'{model.id}' is recorded as not free of charge, so it is refused while "
            f"free-tier-only mode is on.",
            retryable=False,
        )
    if model.free_tier_confidence != CONFIDENCE_CONFIRMED:
        raise ModelUnavailable(
            f"'{model.id}' has free_tier_confidence = '{model.free_tier_confidence}', "
            f"so it cannot be confirmed as free of charge. It is refused while "
            f"free-tier-only mode is on. Re-check the provider's own pricing page and "
            f"update the record's reviewed_on date if it is in fact free.",
            retryable=False,
        )
    return model


def ensure_model_available(
    model: ApprovedModel, discovered_ids: Sequence[str] | None
) -> None:
    """Confirm the approved model is still offered by the provider.

    An **empty** ``discovered_ids`` means the list could not be read — that is
    "unverifiable", not "retired", and must not be turned into a false alarm.

    When the list *was* read and the model is absent, the provider is unavailable. The
    message deliberately names no alternative: the user updates the approved list, and
    nothing is chosen on their behalf.
    """
    if not discovered_ids:
        return
    available = {str(name).strip() for name in discovered_ids}
    if model.id in available:
        return
    raise ModelUnavailable(
        f"The configured model '{model.id}' is no longer offered by {model.provider} — "
        f"it appears to have been retired. Update the approved model list in "
        f"config.toml and choose a currently offered model. No replacement will be "
        f"selected automatically.",
        retryable=False,
    )
