"""Plan 2b Phase 7a — the pre-flight spend guard.

Three things are proved here, and the third is the one that matters:

1. **Every refusal branch refuses**, with a condition code and a sentence naming what
   failed. One test per branch, plus the happy path.
2. **It fails closed.** Missing, malformed and unreadable inputs are refusals, and so is
   an exception raised while deciding.
3. **It is genuinely on the real path.** Not "the guard works when called" — the guard is
   patched and required to be what actually ran when a cloud run starts through the
   normal entry point (``gui.ai_settings.build_ai_editor``, no injected ``create``), and
   the reverse is proved too: with the guard neutered the same refused run builds an
   adapter. That pairing is what rules out the refusal coming from somewhere else.

Hermetic by construction: every test passes explicit ``environ`` / ``secrets_file`` /
``dotenv_path`` / ``settings_file`` locations, so a developer with a real key on this
machine cannot change an outcome. Nothing here imports a provider SDK, opens a socket,
or sends anything.
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

from ai.disclosure import DISCLOSURE_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]

GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-3.6-flash"

# Recognisable fake key shapes. Never a real credential.
FAKE_GROQ_KEY = "gsk_FAKEKEYFORTESTSONLY0000000000000000000000000000000"
FAKE_GEMINI_KEY = "AIzaSyFAKEKEYFORTESTSONLY000000000000000"


def _guard():
    """The guard module, resolved at call time.

    ``test_ai_foundation`` really does pop and re-import the ``ai`` package mid-suite, so
    a module object captured at import time can be a different generation from the one
    the product raises through. Same idiom as ``test_cloud_gui``.
    """
    from ai import spend_guard

    return spend_guard


def _record(model_id, provider, **overrides):
    record = {
        "id": model_id,
        "provider": provider,
        "status": "stable",
        "context_limit": 131072,
        "output_limit": 8192,
        "reviewed_on": "2026-07-25",
        "source_url": "https://example.invalid/models",
        "free_tier_confidence": "confirmed",
        "pilot_status": "not-piloted",
    }
    record.update(overrides)
    return record


DEFAULT_RECORDS = [
    _record(GROQ_MODEL, "groq"),
    _record("llama-3.1-8b-instant", "groq"),
    _record(GEMINI_MODEL, "gemini"),
]

_UNSET = object()


def _context(
    tmp_path,
    *,
    provider="groq",
    model=GROQ_MODEL,
    records=_UNSET,
    section=None,
    environ=_UNSET,
    acknowledged=_UNSET,
    ai_table=_UNSET,
    settings_file=_UNSET,
):
    """A run context for the guard, cleared by default and broken one field at a time."""
    path = tmp_path / "settings.json"
    document = {"ai": {}}
    version = DISCLOSURE_VERSION if acknowledged is _UNSET else acknowledged
    if version is not None:
        document["ai"]["cloud_disclosure"] = {provider: str(version)}
    path.write_text(json.dumps(document), encoding="utf-8")

    raw_records = DEFAULT_RECORDS if records is _UNSET else records
    table = {
        # Deliberately not coerced: a malformed `approved_models` (None, a string, a
        # list of junk) has to reach the guard exactly as a hand-edited config would
        # present it.
        "approved_models": (
            list(raw_records) if isinstance(raw_records, list) else raw_records
        ),
        provider: {
            "enabled": True,
            "model": model,
            "strict_free_tier_only": True,
            **(section or {}),
        },
    }
    keys = {"GROQ_API_KEY": FAKE_GROQ_KEY, "GEMINI_API_KEY": FAKE_GEMINI_KEY}
    return {
        "ai_table": table if ai_table is _UNSET else ai_table,
        "model_id": model,
        "environ": keys if environ is _UNSET else environ,
        "secrets_file": tmp_path / "no-secrets.json",
        "dotenv_path": tmp_path / "no.env",
        "settings_file": path if settings_file is _UNSET else settings_file,
    }


def _refusal(tmp_path, **kwargs):
    """Evaluate one broken context and return the verdict, asserting it refused."""
    guard = _guard()
    provider = kwargs.pop("provider", "groq")
    verdict = guard.evaluate(provider, _context(tmp_path, provider=provider, **kwargs))
    assert verdict.allowed is False
    assert verdict.reason.strip(), "a refusal must always carry a readable reason"
    return verdict


# ===========================================================================
# 1. The happy path — and only the happy path
# ===========================================================================
def test_a_fully_cleared_run_is_allowed_and_returns_the_exact_record(tmp_path):
    guard = _guard()
    verdict = guard.evaluate("groq", _context(tmp_path))
    assert verdict.allowed is True
    assert verdict.condition == guard.ALLOWED
    assert verdict.model is not None
    assert verdict.model.id == GROQ_MODEL
    assert verdict.model.status == "stable"
    assert verdict.model.free_tier_confidence == "confirmed"


def test_the_enforcement_function_returns_the_record_it_cleared(tmp_path):
    approved = _guard().ensure_free_tier_run_allowed("groq", _context(tmp_path))
    assert approved.id == GROQ_MODEL


def test_the_other_provider_clears_on_its_own_terms(tmp_path):
    verdict = _guard().evaluate(
        "gemini",
        _context(tmp_path, provider="gemini", model=GEMINI_MODEL),
    )
    assert verdict.allowed is True
    assert verdict.model.id == GEMINI_MODEL


# ===========================================================================
# 2. One test per refusal branch
# ===========================================================================
def test_a_non_cloud_provider_is_refused(tmp_path):
    guard = _guard()
    for name in ("ollama", "", "not-a-provider", None):
        verdict = guard.evaluate(name, _context(tmp_path))
        assert verdict.allowed is False
        assert verdict.condition == guard.NOT_A_CLOUD_PROVIDER


def test_a_missing_run_context_is_refused(tmp_path):
    guard = _guard()
    verdict = guard.evaluate("groq", None)
    assert verdict.allowed is False
    assert verdict.condition == guard.CONTEXT_MISSING


def test_a_context_that_is_not_a_mapping_is_refused():
    guard = _guard()
    for junk in ([], "ai_table", 7, object()):
        verdict = guard.evaluate("groq", junk)
        assert verdict.allowed is False
        assert verdict.condition == guard.CONTEXT_MISSING


def test_a_missing_or_unusable_ai_table_is_refused(tmp_path):
    guard = _guard()
    for table in (None, [], "config.toml", 0):
        verdict = _refusal(tmp_path, ai_table=table)
        assert verdict.condition == guard.CONTEXT_MISSING


def test_a_provider_that_is_not_switched_on_is_refused(tmp_path):
    verdict = _refusal(tmp_path, section={"enabled": False})
    assert verdict.condition == _guard().PROVIDER_NOT_CONFIGURED


def test_strict_free_only_mode_switched_off_is_refused(tmp_path):
    """The one rail Phase 1 could not enforce from inside itself.

    With ``strict_free_tier_only = false`` Phase 1 hands ``strict_free_only=False`` to
    ``ensure_model_approved``, which then returns the record *before* checking status or
    free-tier confidence — so a preview or paid model becomes callable. The guard closes
    exactly that.
    """
    guard = _guard()
    verdict = _refusal(tmp_path, section={"strict_free_tier_only": False})
    assert verdict.condition == guard.STRICT_MODE_OFF
    assert guard.STRICT_FLAG in verdict.reason


def test_a_non_boolean_strict_flag_is_refused_rather_than_coerced(tmp_path):
    """``bool("false")`` is True and ``bool(0)`` is False, so truthiness is wrong in
    both directions. The value must be the boolean ``True`` and nothing else."""
    guard = _guard()
    for value in ("true", "false", 1, 0, None, "yes", []):
        verdict = _refusal(tmp_path, section={"strict_free_tier_only": value})
        assert verdict.condition == guard.STRICT_MODE_OFF, value


def test_strict_mode_off_is_refused_even_when_the_model_is_perfectly_free(tmp_path):
    """The refusal is about the switch, not about this particular model."""
    verdict = _refusal(
        tmp_path,
        section={"strict_free_tier_only": False},
        records=[_record(GROQ_MODEL, "groq")],
    )
    assert verdict.condition == _guard().STRICT_MODE_OFF


def test_no_key_anywhere_is_refused(tmp_path):
    verdict = _refusal(tmp_path, environ={})
    assert verdict.condition == _guard().NO_USABLE_KEY


def test_no_model_chosen_is_refused(tmp_path):
    verdict = _refusal(tmp_path, model="")
    assert verdict.condition == _guard().MODEL_NOT_APPROVED


def test_a_latest_style_alias_is_refused(tmp_path):
    guard = _guard()
    for alias in ("gemini-flash-latest", "llama-3.3-70b-latest", "groq/*"):
        verdict = _refusal(
            tmp_path,
            model=alias,
            records=DEFAULT_RECORDS + [_record(alias, "groq")],
        )
        assert verdict.condition == guard.MODEL_NOT_APPROVED
        assert verdict.allowed is False


def test_a_prefix_or_near_miss_of_an_approved_id_is_refused(tmp_path):
    """The match is exact. A prefix, a suffix and a case variant are all refusals."""
    guard = _guard()
    for near in (
        "llama-3.3-70b",
        "llama-3.3-70b-versatile-preview",
        "Llama-3.3-70B-Versatile",
        " llama-3.3-70b-versatile-x",
    ):
        verdict = _refusal(tmp_path, model=near)
        assert verdict.condition == guard.MODEL_NOT_APPROVED, near


def test_a_model_that_is_not_in_the_reviewed_list_is_refused(tmp_path):
    verdict = _refusal(tmp_path, model="some-other-model")
    assert verdict.condition == _guard().MODEL_NOT_APPROVED


def test_a_models_own_record_must_belong_to_the_selected_provider(tmp_path):
    """A Gemini record does not make a model callable on Groq."""
    verdict = _refusal(tmp_path, model=GEMINI_MODEL)
    assert verdict.condition == _guard().MODEL_NOT_APPROVED


def test_a_preview_model_is_refused(tmp_path):
    guard = _guard()
    verdict = _refusal(
        tmp_path,
        model="qwen/qwen3.6-27b",
        records=[_record("qwen/qwen3.6-27b", "groq", status="preview")],
    )
    assert verdict.condition == guard.MODEL_NOT_STABLE


def test_an_experimental_model_is_refused(tmp_path):
    verdict = _refusal(
        tmp_path,
        model="groq-experiment",
        records=[_record("groq-experiment", "groq", status="experimental")],
    )
    assert verdict.condition == _guard().MODEL_NOT_STABLE


def test_unknown_free_tier_confidence_is_refused(tmp_path):
    guard = _guard()
    verdict = _refusal(
        tmp_path,
        records=[_record(GROQ_MODEL, "groq", free_tier_confidence="unknown")],
    )
    assert verdict.condition == guard.MODEL_FREE_TIER_UNCONFIRMED


def test_a_model_recorded_as_not_free_is_refused(tmp_path):
    verdict = _refusal(
        tmp_path,
        records=[_record(GROQ_MODEL, "groq", free_tier_confidence="not-free")],
    )
    assert verdict.condition == _guard().MODEL_FREE_TIER_UNCONFIRMED


def test_an_unacknowledged_disclosure_is_refused(tmp_path):
    verdict = _refusal(tmp_path, acknowledged=None)
    assert verdict.condition == _guard().DISCLOSURE_NOT_ACKNOWLEDGED


def test_an_acknowledgement_of_an_older_disclosure_version_is_refused(tmp_path):
    """Consent is checked against the *current* version and nothing else."""
    verdict = _refusal(tmp_path, acknowledged="0")
    assert verdict.condition == _guard().DISCLOSURE_NOT_ACKNOWLEDGED


def test_the_other_providers_acknowledgement_does_not_count(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"ai": {"cloud_disclosure": {"gemini": DISCLOSURE_VERSION}}}),
        encoding="utf-8",
    )
    verdict = _refusal(tmp_path, acknowledged=None, settings_file=path)
    assert verdict.condition == _guard().DISCLOSURE_NOT_ACKNOWLEDGED


def test_an_unreadable_settings_file_is_a_refusal_not_a_pass(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("{not json at all", encoding="utf-8")
    verdict = _refusal(tmp_path, settings_file=path)
    assert verdict.condition == _guard().DISCLOSURE_NOT_ACKNOWLEDGED


def test_missing_approved_records_refuse_everything(tmp_path):
    guard = _guard()
    for records in ([], None, "not-a-list", [{"id": "x"}]):
        verdict = _refusal(tmp_path, records=records)
        assert verdict.condition == guard.MODEL_NOT_APPROVED, records


def test_an_unexpected_failure_while_deciding_is_a_refusal(tmp_path, monkeypatch):
    """Fail closed: a guard that raises is a guard someone else's `except` can swallow."""
    guard = _guard()

    def explode(*args, **kwargs):
        raise RuntimeError("config layer fell over")

    monkeypatch.setattr(guard, "ensure_cloud_request_allowed", explode)
    verdict = guard.evaluate("groq", _context(tmp_path))
    assert verdict.allowed is False
    assert verdict.condition == guard.UNEXPECTED_ERROR


def test_a_substituted_model_would_be_refused(tmp_path, monkeypatch):
    """A post-condition, not a second decision: nothing may come back but what was asked
    for. If this ever fires, a substitution path appeared upstream."""
    guard = _guard()
    from ai.approved_models import ApprovedModel

    other = ApprovedModel(
        id="llama-3.1-8b-instant", provider="groq", status="stable",
        context_limit=131072, output_limit=8192, reviewed_on="2026-07-25",
        source_url="https://example.invalid", free_tier_confidence="confirmed",
        pilot_status="not-piloted",
    )
    monkeypatch.setattr(guard, "ensure_cloud_request_allowed", lambda *a, **k: other)
    verdict = guard.evaluate("groq", _context(tmp_path))
    assert verdict.allowed is False
    assert verdict.condition == guard.MODEL_SUBSTITUTED


def test_a_loosened_upstream_rule_still_fails_closed_here(tmp_path, monkeypatch):
    """The status and confidence post-conditions, proved the same way."""
    guard = _guard()
    from ai.approved_models import ApprovedModel

    def unstable(*args, **kwargs):
        return ApprovedModel(
            id=GROQ_MODEL, provider="groq", status="preview", context_limit=131072,
            output_limit=8192, reviewed_on="2026-07-25",
            source_url="https://example.invalid", free_tier_confidence="confirmed",
            pilot_status="not-piloted",
        )

    monkeypatch.setattr(guard, "ensure_cloud_request_allowed", unstable)
    assert guard.evaluate("groq", _context(tmp_path)).condition == guard.MODEL_NOT_STABLE

    def unconfirmed(*args, **kwargs):
        return ApprovedModel(
            id=GROQ_MODEL, provider="groq", status="stable", context_limit=131072,
            output_limit=8192, reviewed_on="2026-07-25",
            source_url="https://example.invalid", free_tier_confidence="unknown",
            pilot_status="not-piloted",
        )

    monkeypatch.setattr(guard, "ensure_cloud_request_allowed", unconfirmed)
    assert (
        guard.evaluate("groq", _context(tmp_path)).condition
        == guard.MODEL_FREE_TIER_UNCONFIRMED
    )


# ===========================================================================
# 3. The refusal the user reads
# ===========================================================================
def test_every_refusal_names_the_condition_in_words(tmp_path):
    """Not a code and not a stack trace: a sentence a non-technical user can act on."""
    cases = [
        (dict(section={"strict_free_tier_only": False}), "free-tier"),
        (dict(environ={}), "key"),
        (dict(model="some-other-model"), "approved"),
        (dict(acknowledged=None), "disclosure"),
        (dict(section={"enabled": False}), "enabled"),
        (
            dict(records=[_record(GROQ_MODEL, "groq", status="preview")]),
            "preview",
        ),
        (
            dict(records=[_record(GROQ_MODEL, "groq",
                                  free_tier_confidence="unknown")]),
            "free_tier_confidence",
        ),
    ]
    for kwargs, expected in cases:
        verdict = _refusal(tmp_path, **kwargs)
        assert expected.lower() in verdict.reason.lower(), verdict.reason
        assert len(verdict.reason) > 30


def test_the_enforcement_function_raises_a_refusal_carrying_the_condition(tmp_path):
    guard = _guard()
    with pytest.raises(guard.SpendRefused) as caught:
        guard.ensure_free_tier_run_allowed("groq", _context(tmp_path, environ={}))
    assert caught.value.condition == guard.NO_USABLE_KEY
    assert str(caught.value)
    assert caught.value.retryable is False


def test_a_refusal_is_an_ai_provider_error(tmp_path):
    """So a refusal on any path degrades safely instead of surfacing as a traceback."""
    from ai.errors import AIProviderError

    guard = _guard()
    assert issubclass(guard.SpendRefused, AIProviderError)


def test_a_verdict_carries_no_key_and_no_chapter_text(tmp_path):
    verdict = _guard().evaluate("groq", _context(tmp_path))
    blob = json.dumps(verdict.as_dict())
    assert FAKE_GROQ_KEY not in blob
    assert FAKE_GEMINI_KEY not in blob
    assert "gsk_" not in blob


# ===========================================================================
# 4. The guard is on the REAL path — patched, and required to be what ran
# ===========================================================================
def _cloud_prefs(model=GROQ_MODEL, provider="groq", records=None, section=None):
    return {
        "provider": provider,
        "model": model,
        "policy": "prefer_ai",
        "protection_strategy": "mask",
        "timeout_seconds": 120,
        "seed": 0,
        "request_overhead_tokens": 128,
        "context_safety_margin_tokens": 256,
        "approved_models": list(records if records is not None else DEFAULT_RECORDS),
        provider: {"model": model, "strict_free_tier_only": True, **(section or {})},
    }


class _CountingAdapter:
    """Records that it was built and whether anything was ever sent through it."""

    built = 0

    def __init__(self, **kwargs):
        type(self).built += 1
        self.kwargs = kwargs
        self.sent = []
        self.model_id = str(kwargs.get("model_id") or GROQ_MODEL)

    def capabilities(self):
        from ai.models import ProviderCapabilities

        return ProviderCapabilities(
            provider_name="counting", is_local=False, model_ids=(self.model_id,),
            context_limit=131072, max_output_tokens=8192, exposes_rate_limits=True,
        )

    def health_check(self):
        from ai.models import ProviderStatus

        return ProviderStatus.OK

    def list_models(self):
        return [self.model_id]

    def complete(self, request):
        from ai.models import CompletionResult

        self.sent.append(request)
        return CompletionResult(
            text=request.text, model_id=self.model_id, duration_seconds=0.0,
            finish_reason="stop", truncated=False, input_tokens=1, output_tokens=1,
        )


@pytest.fixture
def counting_builder(monkeypatch):
    """Register a fake cloud adapter through the factory's own registry.

    This is the only supported way to inject a cloud adapter since 7a, and it does not
    weaken anything: the guard is keyed on the provider *name* and runs before any
    builder is consulted, so a registered fake is still guarded.
    """
    from ai import factory

    built = []

    def builder(**kwargs):
        adapter = _CountingAdapter(**kwargs)
        built.append(adapter)
        return adapter

    monkeypatch.setitem(factory._BUILDERS, "groq", builder)
    return built


def _run_prefs(tmp_path, **kwargs):
    context = _context(tmp_path, **kwargs)
    return {
        "prefs": _cloud_prefs(),
        "environ": context["environ"],
        "secrets_file": context["secrets_file"],
        "dotenv_path": context["dotenv_path"],
        "settings_file": context["settings_file"],
    }


def test_the_guard_is_what_actually_runs_when_a_cloud_run_starts(
        tmp_path, monkeypatch, counting_builder):
    """Patch the guard; require that it is what ran on the normal entry point.

    No ``create`` is injected — this is the same call ``gui.app._start`` makes.
    """
    from gui import ai_settings

    guard = _guard()
    seen = []

    def recorder(provider, context=None):
        seen.append((provider, dict(context or {}).get("model_id")))
        raise guard.SpendRefused("patched refusal", condition="patched")

    monkeypatch.setattr(guard, "ensure_free_tier_run_allowed", recorder)

    setup = _run_prefs(tmp_path)
    with pytest.raises(guard.SpendRefused) as caught:
        ai_settings.build_ai_editor(
            setup["prefs"],
            environ=setup["environ"],
            secrets_file=setup["secrets_file"],
            dotenv_path=setup["dotenv_path"],
            settings_file=setup["settings_file"],
        )

    assert seen == [("groq", GROQ_MODEL)], "the guard did not run on the real path"
    assert caught.value.condition == "patched"
    assert counting_builder == [], "an adapter was built despite the refusal"


def test_with_the_guard_neutered_the_same_refused_run_goes_through(
        tmp_path, monkeypatch, counting_builder):
    """The other half of the proof: the refusal really is the guard's doing.

    Same run, no key anywhere — refused normally. Neuter the guard and it builds. If
    some other check were doing the work, this would still refuse.
    """
    from gui import ai_settings

    guard = _guard()
    setup = _run_prefs(tmp_path, environ={})

    with pytest.raises(guard.SpendRefused):
        ai_settings.build_ai_editor(setup["prefs"], **{
            k: v for k, v in setup.items() if k != "prefs"})
    assert counting_builder == []

    monkeypatch.setattr(
        guard, "ensure_free_tier_run_allowed",
        lambda provider, context=None: _guard_record(),
    )
    ai_settings.build_ai_editor(setup["prefs"], **{
        k: v for k, v in setup.items() if k != "prefs"})
    assert len(counting_builder) == 1


def _guard_record():
    from ai.approved_models import ApprovedModel

    return ApprovedModel(
        id=GROQ_MODEL, provider="groq", status="stable", context_limit=131072,
        output_limit=8192, reviewed_on="2026-07-25",
        source_url="https://example.invalid", free_tier_confidence="confirmed",
        pilot_status="not-piloted",
    )


def test_a_cleared_run_really_does_reach_the_adapter(tmp_path, counting_builder):
    """The guard must not be a wall: a properly configured run still sends."""
    from gui import ai_settings

    setup = _run_prefs(tmp_path)
    editor = ai_settings.build_ai_editor(setup["prefs"], **{
        k: v for k, v in setup.items() if k != "prefs"})
    editor.edit("The knight walked on.\n\nThe road was long.\n")
    assert len(counting_builder) == 1
    assert counting_builder[0].sent, "a cleared run never reached the provider"


def test_the_guard_runs_before_the_adapter_exists(tmp_path, monkeypatch,
                                                  counting_builder):
    """Ordering, pinned: a refused run never produces an object that could send."""
    from gui import ai_settings

    guard = _guard()
    order = []

    real = guard.ensure_free_tier_run_allowed

    def watched(provider, context=None):
        order.append("guard")
        return real(provider, context)

    monkeypatch.setattr(guard, "ensure_free_tier_run_allowed", watched)
    original_init = _CountingAdapter.__init__

    def spy_init(self, **kwargs):
        order.append("adapter")
        original_init(self, **kwargs)

    monkeypatch.setattr(_CountingAdapter, "__init__", spy_init)

    setup = _run_prefs(tmp_path)
    ai_settings.build_ai_editor(setup["prefs"], **{
        k: v for k, v in setup.items() if k != "prefs"})
    assert order == ["guard", "adapter"]


def test_a_cleared_run_builds_the_real_adapter_with_its_own_arguments(tmp_path):
    """No fake registered: the genuine Groq adapter, built through the genuine path.

    This pins a defect 7a had to fix to make that path real at all. The GUI was handing
    every provider the *local* adapter's constructor arguments (``endpoint``,
    ``keep_alive``, ``context_limit``), which no cloud adapter accepts, so the first real
    cloud run would have died with a ``TypeError`` the moment it tried to build one.
    Construction still loads no SDK and contacts nothing.
    """
    from gui import ai_settings

    setup = _run_prefs(tmp_path)
    factory = ai_settings.build_provider_factory(setup["prefs"], **{
        k: v for k, v in setup.items() if k != "prefs"})
    provider = factory()
    assert type(provider.inner).__name__ == "GroqProvider"
    assert provider.inner.model_id == GROQ_MODEL
    assert provider.inner.approved_record is not None
    assert "groq" not in sys.modules, "constructing an adapter must not load the SDK"


def test_a_builder_registered_under_a_cloud_name_is_still_guarded(tmp_path,
                                                                  counting_builder):
    """The guard is keyed on the name, before the registry is consulted — so
    registering a builder is not a way around it."""
    from ai.factory import create_provider

    guard = _guard()
    with pytest.raises(guard.SpendRefused):
        create_provider("groq", model_id=GROQ_MODEL)
    assert counting_builder == []


def test_the_factory_refuses_a_cloud_provider_with_no_run_context(tmp_path):
    """Fail closed: a caller that supplies nothing has shown nothing."""
    from ai.factory import create_provider

    guard = _guard()
    for provider in ("groq", "gemini"):
        with pytest.raises(guard.SpendRefused) as caught:
            create_provider(provider, model_id=GROQ_MODEL)
        assert caught.value.condition == guard.CONTEXT_MISSING


def test_the_local_provider_is_not_touched_by_the_guard(monkeypatch):
    """No gate, no context, no behaviour change on the path that always works."""
    from ai import factory

    made = []
    monkeypatch.setitem(factory._BUILDERS, "ollama", lambda **kw: made.append(kw) or 1)
    assert factory.create_provider("ollama", model_id="qwen3:14b") == 1
    assert made


# ===========================================================================
# 5. Negative space — no SDK, no network, no editing-layer coupling
# ===========================================================================
GUARD_SOURCE = (
    REPO_ROOT / "scripts" / "Universal" / "ai" / "spend_guard.py"
).read_text(encoding="utf-8")


def test_the_guard_module_imports_no_provider_sdk_and_no_transport():
    lines = [
        line for line in GUARD_SOURCE.splitlines()
        if line.startswith(("import ", "from "))
    ]
    forbidden = ("google", "groq", "ollama", "requests", "httpx", "urllib",
                 "socket", "http.client", "providers")
    for line in lines:
        assert not any(name in line for name in forbidden), line


def test_the_guard_module_does_not_import_the_editing_layer():
    """7a changes no editing logic, and cannot: it does not know that layer exists."""
    for name in ("editor", "validation", "prompt", "chunking"):
        assert f"from .{name} import" not in GUARD_SOURCE
        assert f"import {name}" not in GUARD_SOURCE


def test_importing_the_guard_pulls_in_no_provider_sdk():
    import importlib

    for name in ("google.genai", "google.generativeai", "groq", "ollama"):
        sys.modules.pop(name, None)
    importlib.import_module("ai.spend_guard")
    for name in ("google.genai", "google.generativeai", "groq", "ollama"):
        assert name not in sys.modules, f"{name} must not be imported by the guard"


def test_the_guard_opens_no_socket(tmp_path, monkeypatch):
    """Every branch, with the network physically unavailable."""

    def no_network(*args, **kwargs):
        raise AssertionError("the spend guard must not open a socket")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)

    guard = _guard()
    assert guard.evaluate("groq", _context(tmp_path)).allowed is True
    assert guard.evaluate("groq", _context(tmp_path, environ={})).allowed is False
    assert guard.evaluate("groq", None).allowed is False


def test_the_guard_never_asks_a_provider_about_billing():
    """The honest contract: billing state is never queried, inferred, or asserted.

    The app cannot prove a user-supplied key is unbillable, and nothing here pretends
    otherwise — confirming billing is disabled stays the user's step in the provider's
    own console.
    """
    lowered = GUARD_SOURCE.lower()
    for phrase in ("billing_url", "get_billing", "billing_account", "list_billing",
                   "is_billed", "billing_state"):
        assert phrase not in lowered
    # The word appears only in prose that says the app does *not* determine it.
    assert "never" in lowered


def test_the_whole_guard_works_with_no_keys_and_no_settings_anywhere(tmp_path):
    """Offline, clean machine: refuse, do not crash."""
    guard = _guard()
    verdict = guard.evaluate(
        "gemini",
        {
            "ai_table": {"gemini": {"enabled": True, "model": GEMINI_MODEL},
                         "approved_models": DEFAULT_RECORDS},
            "model_id": GEMINI_MODEL,
            "environ": {},
            "secrets_file": tmp_path / "nope.json",
            "dotenv_path": tmp_path / "nope.env",
            "settings_file": tmp_path / "nope.json",
        },
    )
    assert verdict.allowed is False
    assert verdict.condition == guard.NO_USABLE_KEY
