"""Plan 2b Phase 7a — the pre-flight spend guard: one choke point, fails closed.

**The product rule this file exists to enforce:** this tool must never cost the user
money. If a run could leave the free tier, or if the app cannot positively confirm that
it will not, the run is refused and the user is told why. A refusal is never traded for
a charge, and a refusal is never downgraded into a warning the user can click past.

**One function, one module, one call site.** :func:`ensure_free_tier_run_allowed` is the
enforcement point and it is called from exactly one place: ``ai.factory.create_provider``,
keyed on the provider *name*, **before** any builder is looked up and before any adapter
object exists. A cloud run needs a cloud adapter; in this codebase a cloud adapter can
only come from that factory; therefore no cloud run can start without passing through
here. That placement is deliberate — a check the GUI merely happens to call is a
convention, not a guard, and the GUI is not the only thing that can build an editor.

**It fails closed.** Every unknown, missing, malformed or unreadable input is a refusal.
Every exception raised while evaluating is a refusal. There is no branch that returns
"allowed" because something could not be determined.

**It does not duplicate Phase 1.** ``ai.cloud.ensure_cloud_request_allowed`` already
enforces provider-known, provider-configured, key-available, model-approved (exact ID,
no alias, stable, free-tier-confirmed) and disclosure-acknowledged, and it is *reused*
verbatim — this module composes it rather than re-deciding any of it. What this module
adds is the one condition Phase 1 could not enforce from inside itself:

    **strict free-only mode must be ON.**

Phase 1 reads ``strict_free_tier_only`` out of the configuration and hands it to
``ensure_model_approved`` as a parameter. Set it to ``false`` in ``config.toml`` and
three rails evaporate silently — the stable-status check, the free-tier-confidence check
and the not-free check are all skipped, and a preview or paid model becomes callable.
That switch is the hole this guard closes: the value must be exactly the boolean
``True``, and anything else at all is a refusal.

**What this guard is not.** It makes no claim about billing state. Provider APIs do not
expose enough authoritative billing information for a desktop app to prove that a
user-supplied key cannot incur charges, and nothing here queries, infers or asserts it.
The guard enforces *this app's own* free-only invariants; confirming that billing is
disabled stays the user's step, in the provider's own console. That is the honest
contract from the Plan 2b drop, and this module does not quietly exceed it.

This module imports no provider SDK and makes no network call — it is pure policy over
configuration and two small files, and it is safe to import at start-up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .approved_models import (
    CONFIDENCE_CONFIRMED,
    STATUS_STABLE,
    ApprovedModel,
    find_approved,
    load_approved_models,
)
from .cloud import (
    ensure_cloud_request_allowed,
    is_cloud_provider,
    provider_settings,
)
from .disclosure import (
    DISCLOSURE_VERSION,
    PROVIDER_LABELS,
    DisclosureNotAcknowledged,
)
from .errors import (
    AIProviderError,
    AuthenticationError,
    ModelUnavailable,
    ProviderUnavailable,
)

# The configuration flag that must be ON. Named once, here, so the guard and the
# message the user reads cannot drift apart.
STRICT_FLAG = "strict_free_tier_only"

# Condition codes. Every refusal carries exactly one, so the GUI, the log and a test
# can all name the same failed rail without parsing prose.
ALLOWED = "allowed"
NOT_A_CLOUD_PROVIDER = "not_a_cloud_provider"
CONTEXT_MISSING = "run_context_missing"
PROVIDER_NOT_CONFIGURED = "provider_not_configured"
STRICT_MODE_OFF = "strict_free_only_off"
NO_USABLE_KEY = "no_usable_key"
MODEL_NOT_APPROVED = "model_not_approved"
MODEL_NOT_STABLE = "model_not_stable"
MODEL_FREE_TIER_UNCONFIRMED = "model_free_tier_unconfirmed"
MODEL_SUBSTITUTED = "model_substituted"
DISCLOSURE_NOT_ACKNOWLEDGED = "disclosure_not_acknowledged"
UNEXPECTED_ERROR = "unexpected_error"

# The keys the guard reads out of a run context. Anything else is ignored; anything
# missing is treated as absent, which is a refusal wherever it matters.
_CONTEXT_KEYS = (
    "ai_table",
    "model_id",
    "environ",
    "secrets_file",
    "dotenv_path",
    "settings_file",
)


class SpendRefused(AIProviderError):
    """A cloud run was refused before it could spend anything.

    Defined here rather than in ``errors.py`` for the same reason
    ``DisclosureNotAcknowledged`` is defined in ``disclosure.py``: 2a's error taxonomy is
    the shared provider contract and Plan 2b is not permitted to change it.

    It subclasses ``AIProviderError`` on purpose. On the GUI path the refusal is caught
    before the batch starts and shown in a dialog; on any other path ``AIEditor`` already
    routes an ``AIProviderError`` to chapter-atomic script-only editing, which sends
    nothing and spends nothing. A refusal must never surface as a raw traceback.
    """

    retryable = False

    def __init__(self, message: str = "", *, condition: str = UNEXPECTED_ERROR):
        super().__init__(message, retryable=False)
        self.condition = condition


@dataclass(frozen=True)
class GuardVerdict:
    """One decision, safe to display and to log. Holds no key and no chapter text."""

    allowed: bool
    provider: str
    model_id: str
    condition: str
    reason: str
    model: ApprovedModel | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "provider": self.provider,
            "model_id": self.model_id,
            "condition": self.condition,
            "reason": self.reason,
        }


def _refuse(provider: str, model_id: str, condition: str, reason: str) -> GuardVerdict:
    return GuardVerdict(
        allowed=False,
        provider=provider,
        model_id=model_id,
        condition=condition,
        reason=reason,
    )


def _label_model_refusal(
    ai_table: Mapping[str, Any] | None, provider: str, model_id: str
) -> str:
    """Name *which* model rail failed, for a refusal Phase 1 has already decided.

    This labels; it never decides. It runs only after ``ensure_model_approved`` has
    already refused, and its worst possible outcome is a more generic condition code on
    a refusal that stands either way. The sentence the user reads is always Phase 1's
    own, never a re-wording produced here.
    """
    try:
        record = find_approved(load_approved_models(ai_table), provider, model_id)
    except Exception:  # pragma: no cover - defensive; labelling must never raise
        return MODEL_NOT_APPROVED
    if record is None:
        return MODEL_NOT_APPROVED
    if record.status != STATUS_STABLE:
        return MODEL_NOT_STABLE
    if record.free_tier_confidence != CONFIDENCE_CONFIRMED:
        return MODEL_FREE_TIER_UNCONFIRMED
    return MODEL_NOT_APPROVED


def evaluate(provider: str, context: Mapping[str, Any] | None = None) -> GuardVerdict:
    """Decide whether one cloud run may start. Never raises, never calls out.

    ``context`` carries where to read the run's inputs from: the resolved ``[ai]``
    table, the chosen model ID, the key lookup locations, and the per-user settings file
    holding the disclosure record. A missing or unusable context is a refusal — the
    guard never falls back to "somewhere sensible" and never assumes a default that
    would let a run proceed.

    The disclosure version is deliberately **not** a context key: consent is checked
    against the current :data:`DISCLOSURE_VERSION` and nothing else, so no caller can
    satisfy the rail by naming an older version of the text.
    """
    name = str(provider or "").strip().lower()
    model_id = ""
    ai_table: Mapping[str, Any] | None = None

    try:
        if not is_cloud_provider(name):
            return _refuse(
                name,
                model_id,
                NOT_A_CLOUD_PROVIDER,
                f"'{provider}' is not a cloud provider this app supports, so the "
                f"free-tier spend guard has nothing it can vouch for. No request was "
                f"made.",
            )

        if not isinstance(context, Mapping):
            return _refuse(
                name,
                model_id,
                CONTEXT_MISSING,
                f"The {PROVIDER_LABELS.get(name, name)} run was refused because the "
                f"app could not read the settings it must check before sending "
                f"anything. Nothing was sent. Reopen the AI settings and try again.",
            )

        values = {key: context.get(key) for key in _CONTEXT_KEYS}
        raw_table = values["ai_table"]
        if not isinstance(raw_table, Mapping):
            return _refuse(
                name,
                model_id,
                CONTEXT_MISSING,
                f"The {PROVIDER_LABELS.get(name, name)} run was refused because no "
                f"usable AI configuration was supplied to check it against. Nothing "
                f"was sent. Check config.toml is present and readable.",
            )
        ai_table = raw_table
        model_id = str(values["model_id"] or "").strip()

        # --- the one condition Phase 1 cannot enforce from inside itself ---------
        settings = provider_settings(ai_table, name)
        strict = settings.get(STRICT_FLAG, None)
        if strict is not True:
            return _refuse(
                name,
                model_id,
                STRICT_MODE_OFF,
                f"Strict free-tier-only mode is not switched on for "
                f"{PROVIDER_LABELS.get(name, name)} — config.toml has "
                f"{STRICT_FLAG} = {strict!r}, and this app only runs cloud models "
                f"with it set to true. With it off, preview and paid models could be "
                f"called and the app could not promise the run stays free. Set "
                f"{STRICT_FLAG} = true and try again. Nothing was sent.",
            )

        # --- every other rail is Phase 1's, reused verbatim ---------------------
        approved = ensure_cloud_request_allowed(
            name,
            ai_table=ai_table,
            model_id=model_id or None,
            environ=values["environ"],
            secrets_file=values["secrets_file"],
            dotenv_path=values["dotenv_path"],
            settings_file=values["settings_file"],
            version=DISCLOSURE_VERSION,
        )

    except ProviderUnavailable as exc:
        return _refuse(name, model_id, PROVIDER_NOT_CONFIGURED, str(exc))
    except AuthenticationError as exc:
        return _refuse(name, model_id, NO_USABLE_KEY, str(exc))
    except ModelUnavailable as exc:
        return _refuse(
            name, model_id, _label_model_refusal(ai_table, name, model_id), str(exc)
        )
    except DisclosureNotAcknowledged as exc:
        return _refuse(name, model_id, DISCLOSURE_NOT_ACKNOWLEDGED, str(exc))
    except Exception as exc:  # fail closed: an unreadable input is never a pass
        return _refuse(
            name,
            model_id,
            UNEXPECTED_ERROR,
            f"The {PROVIDER_LABELS.get(name, name)} run was refused because the app "
            f"could not finish checking that it would stay inside the free tier "
            f"({type(exc).__name__}). Nothing was sent.",
        )

    # --- post-conditions on the record Phase 1 returned -------------------------
    # These assert the *result*, they do not re-decide it. They exist so that if the
    # rules above are ever loosened, this guard still fails closed rather than
    # inheriting the loosening silently. If one of these ever fires, something
    # upstream changed and the refusal is the correct outcome.
    if model_id and approved.id != model_id:
        return _refuse(
            name,
            model_id,
            MODEL_SUBSTITUTED,
            f"The run was refused because the app was about to use '{approved.id}' "
            f"when '{model_id}' was chosen. No model is ever substituted. Nothing "
            f"was sent.",
        )
    if approved.status != STATUS_STABLE:
        return _refuse(
            name,
            approved.id,
            MODEL_NOT_STABLE,
            f"'{approved.id}' is marked '{approved.status}' rather than stable, so it "
            f"is refused: preview and experimental models commonly require billing. "
            f"Nothing was sent.",
        )
    if approved.free_tier_confidence != CONFIDENCE_CONFIRMED:
        return _refuse(
            name,
            approved.id,
            MODEL_FREE_TIER_UNCONFIRMED,
            f"'{approved.id}' has free_tier_confidence = "
            f"'{approved.free_tier_confidence}', so it cannot be confirmed as free of "
            f"charge and is refused. Nothing was sent.",
        )

    return GuardVerdict(
        allowed=True,
        provider=name,
        model_id=approved.id,
        condition=ALLOWED,
        reason=(
            f"Cleared — {approved.id} is on the reviewed approved list, is stable, is "
            f"recorded as free of charge, strict free-tier-only mode is on, a key was "
            f"found, and the cloud disclosure has been accepted for this version."
        ),
        model=approved,
    )


def ensure_free_tier_run_allowed(
    provider: str, context: Mapping[str, Any] | None = None
) -> ApprovedModel:
    """**The guard.** Return the approved record, or refuse the run.

    Raises :class:`SpendRefused` — carrying the failed condition and a sentence naming
    it — for every refusal. There is no return path that means "probably fine".
    """
    verdict = evaluate(provider, context)
    if not verdict.allowed or verdict.model is None:
        raise SpendRefused(verdict.reason, condition=verdict.condition)
    return verdict.model


__all__ = [
    "ALLOWED",
    "CONTEXT_MISSING",
    "DISCLOSURE_NOT_ACKNOWLEDGED",
    "GuardVerdict",
    "MODEL_FREE_TIER_UNCONFIRMED",
    "MODEL_NOT_APPROVED",
    "MODEL_NOT_STABLE",
    "MODEL_SUBSTITUTED",
    "NOT_A_CLOUD_PROVIDER",
    "NO_USABLE_KEY",
    "PROVIDER_NOT_CONFIGURED",
    "STRICT_FLAG",
    "STRICT_MODE_OFF",
    "SpendRefused",
    "UNEXPECTED_ERROR",
    "ensure_free_tier_run_allowed",
    "evaluate",
]
