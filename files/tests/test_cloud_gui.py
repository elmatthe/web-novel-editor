"""Plan 2b Phase 6 — the cloud GUI layer: selection, consent, status, ETA, resume.

Everything decided here is decided in tkinter-free functions, the same separation
Plan 2a used for ``gui.ai_settings``: the panel builds widgets and calls one of these,
and every rule below is exercised headlessly with no display, no network, no keys and
no provider SDK installed.

Hermetic by construction: every test passes explicit ``settings_file`` /
``secrets_file`` / ``dotenv_path`` / ``environ`` locations, so a developer who happens
to have a real ``GEMINI_API_KEY`` or a real ``secrets.json`` on this machine cannot
make the suite pass or fail for the wrong reason.

**Generation discipline.** ``test_ai_foundation`` really does pop and re-import the
``ai`` package mid-suite, so two generations of every ``ai`` class can coexist in one
run. ``gui.ai_settings`` imports the AI stack *inside* the functions that use it — a
deliberate 2a decision so a reloaded ``ai.models`` never leaves it holding a stale enum
— which means the product resolves those classes at call time, i.e. the latest
generation. Anything this module **constructs for the product to catch**, or asserts
identity against, therefore has to be resolved at call time too: see :func:`_errors`
and ``_FakeAdapter``. Plain data (status strings, config dicts) is generation-free and
is imported normally.
"""

from __future__ import annotations

import hashlib
import json
import threading

import pytest

from ai import disclosure as disclosure_mod
from ai.cloud import CLOUD_DEFAULTS
from ai.disclosure import DISCLOSURE_VERSION, disclosure_text
from core.run_manifest import RunCheckpoint, find_resumable_run
from gui import ai_settings, cloud_ui


def _errors():
    """The error taxonomy, resolved now rather than at import time. See the docstring."""
    from ai import errors

    return errors


def _disclosure_errors():
    from ai import disclosure

    return disclosure

# A recognisable fake key shape. Never a real credential.
FAKE_GEMINI_KEY = "AIzaSyFAKEKEYFORTESTSONLY000000000000000"
FAKE_GROQ_KEY = "gsk_FAKEKEYFORTESTSONLY0000000000000000000000000000000"


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------
def _record(model_id, provider, **overrides):
    record = {
        "id": model_id,
        "provider": provider,
        "status": "stable",
        "context_limit": 131072,
        "output_limit": 8192,
        "reviewed_on": "2026-07-24",
        "source_url": "https://example.invalid/models",
        "free_tier_confidence": "confirmed",
        "pilot_status": "not-piloted",
    }
    record.update(overrides)
    return record


def _ai_table(*, models=None, gemini=None, groq=None, **top):
    table = {
        "provider": "ollama",
        "model": "",
        "approved_models": list(
            models
            if models is not None
            else [
                _record("gemini-3.6-flash", "gemini"),
                _record("gemini-2.5-flash", "gemini"),
                _record("llama-3.3-70b-versatile", "groq"),
            ]
        ),
        "gemini": dict(gemini or {}),
        "groq": dict(groq or {}),
    }
    table.update(top)
    return table


def _nowhere(tmp_path):
    """Locations that deliberately do not exist, for hermetic key/consent lookups."""
    return {
        "environ": {},
        "secrets_file": tmp_path / "no-such-secrets.json",
        "dotenv_path": tmp_path / "no-such.env",
        "settings_file": tmp_path / "no-such-settings.json",
    }


def _acknowledge(tmp_path, provider, version=DISCLOSURE_VERSION):
    path = tmp_path / "settings.json"
    document = {}
    if path.exists():
        document = json.loads(path.read_text(encoding="utf-8"))
    section = document.setdefault("ai", {})
    section.setdefault("cloud_disclosure", {})[provider] = str(version)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class _FakeAdapter:
    """An in-process stand-in for a cloud adapter. No SDK, no network."""

    def __init__(self, *, exposes_rate_limits=True, raises=None, model_id="m"):
        self.model_id = model_id
        self.calls = []
        self._raises = raises
        self._exposes = exposes_rate_limits
        self.last_rate_limits = None

    def capabilities(self):
        from ai.models import ProviderCapabilities

        return ProviderCapabilities(
            provider_name="fake",
            is_local=False,
            model_ids=(self.model_id,),
            context_limit=131072,
            max_output_tokens=8192,
            exposes_rate_limits=self._exposes,
        )

    def health_check(self):
        from ai.models import ProviderStatus

        return ProviderStatus.OK

    def list_models(self):
        return [self.model_id]

    def complete(self, request):
        from ai.models import CompletionResult

        self.calls.append(request)
        if self._raises is not None:
            raise self._raises()
        return CompletionResult(
            text=request.text,
            model_id=self.model_id,
            duration_seconds=0.1,
            finish_reason="stop",
            truncated=False,
            input_tokens=10,
            output_tokens=10,
        )


# ===========================================================================
# 1. Provider options — status, plain-English reason, selectability
# ===========================================================================
def test_a_cloud_provider_with_key_model_and_consent_is_ready(tmp_path):
    settings = _acknowledge(tmp_path, "gemini")
    options = cloud_ui.provider_options(
        ai_table=_ai_table(gemini={"model": "gemini-3.6-flash"}),
        environ={"GEMINI_API_KEY": FAKE_GEMINI_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=settings,
    )
    gemini = {opt.provider: opt for opt in options}["gemini"]
    assert gemini.ready is True
    assert gemini.selectable is True
    assert gemini.status == "ok"
    assert gemini.reason == ""


def test_a_missing_key_is_reported_with_a_plain_english_reason(tmp_path):
    options = cloud_ui.provider_options(
        ai_table=_ai_table(gemini={"model": "gemini-3.6-flash"}), **_nowhere(tmp_path)
    )
    gemini = {opt.provider: opt for opt in options}["gemini"]
    assert gemini.ready is False
    assert gemini.status == "auth_missing"
    assert "GEMINI_API_KEY" in gemini.reason
    # Still selectable: choosing it is how the user gets told to add a key.
    assert gemini.selectable is True


def test_a_provider_with_no_approved_model_to_offer_is_not_selectable(tmp_path):
    """The drop's hard rule: no provider becomes selectable if its only path forward
    is an unapproved or unknown-free-tier-confidence model."""
    table = _ai_table(
        models=[
            _record("gemini-mystery", "gemini", free_tier_confidence="unknown"),
            _record("llama-3.3-70b-versatile", "groq"),
        ]
    )
    options = {o.provider: o for o in cloud_ui.provider_options(
        ai_table=table, **_nowhere(tmp_path))}
    assert options["gemini"].selectable is False
    assert "approved" in options["gemini"].reason.lower()
    # ...and the provider that does have one is unaffected.
    assert options["groq"].selectable is True


def test_a_provider_whose_only_model_is_preview_is_not_selectable(tmp_path):
    table = _ai_table(
        models=[_record("groq-preview-thing", "groq", status="preview")]
    )
    options = {o.provider: o for o in cloud_ui.provider_options(
        ai_table=table, **_nowhere(tmp_path))}
    assert options["groq"].selectable is False


def test_consent_not_yet_given_is_its_own_reason_not_a_key_problem(tmp_path):
    options = cloud_ui.provider_options(
        ai_table=_ai_table(gemini={"model": "gemini-3.6-flash"}),
        environ={"GEMINI_API_KEY": FAKE_GEMINI_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=tmp_path / "none.json",
    )
    gemini = {o.provider: o for o in options}["gemini"]
    assert gemini.status == cloud_ui.STATUS_CONSENT_REQUIRED
    assert gemini.selectable is True
    assert "leave this computer" in gemini.reason or "accept" in gemini.reason


def test_no_model_chosen_yet_names_the_approved_choices(tmp_path):
    options = cloud_ui.provider_options(ai_table=_ai_table(), **_nowhere(tmp_path))
    groq = {o.provider: o for o in options}["groq"]
    # The key rail is checked before the model rail, so a keyless provider reports the
    # key first — that is Phase 1's precedence and it must not be reordered here.
    assert groq.status == "auth_missing"
    with_key = {o.provider: o for o in cloud_ui.provider_options(
        ai_table=_ai_table(),
        environ={"GROQ_API_KEY": FAKE_GROQ_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=tmp_path / "none.json",
    )}["groq"]
    assert with_key.status == cloud_ui.STATUS_NO_MODEL
    assert "llama-3.3-70b-versatile" in with_key.reason


def test_a_retired_model_is_reported_only_from_a_real_provider_list(tmp_path):
    """Retirement is knowable only by asking the provider. It is never guessed."""
    settings = _acknowledge(tmp_path, "groq")
    common = dict(
        ai_table=_ai_table(groq={"model": "llama-3.3-70b-versatile"}),
        environ={"GROQ_API_KEY": FAKE_GROQ_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=settings,
    )
    # Nothing asked yet: ready, not "retired".
    assert {o.provider: o for o in cloud_ui.provider_options(**common)}["groq"].ready

    retired = cloud_ui.provider_option(
        "groq", discovered_ids=("some-other-model",), **common)
    assert retired.ready is False
    assert retired.status == "model_missing"
    assert "retired" in retired.reason


def test_an_empty_live_list_is_unverifiable_not_retired(tmp_path):
    settings = _acknowledge(tmp_path, "groq")
    option = cloud_ui.provider_option(
        "groq",
        ai_table=_ai_table(groq={"model": "llama-3.3-70b-versatile"}),
        environ={"GROQ_API_KEY": FAKE_GROQ_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=settings,
        discovered_ids=(),
    )
    assert option.ready is True


def test_the_local_provider_is_always_offered_and_always_selectable(tmp_path):
    options = cloud_ui.provider_options(ai_table=_ai_table(), **_nowhere(tmp_path))
    local = {o.provider: o for o in options}[cloud_ui.local_provider()]
    assert local.selectable is True
    assert local.reason == ""
    assert options[0].provider == cloud_ui.local_provider()  # local first


def test_a_chosen_model_is_applied_only_to_the_provider_it_belongs_to(tmp_path):
    """A Groq model ID must not be evaluated as if it were a Gemini model."""
    options = {o.provider: o for o in cloud_ui.provider_options(
        ai_table=_ai_table(),
        selected="groq",
        model_id="llama-3.3-70b-versatile",
        environ={"GROQ_API_KEY": FAKE_GROQ_KEY, "GEMINI_API_KEY": FAKE_GEMINI_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=tmp_path / "none.json",
    )}
    # Groq got the model and is only waiting on consent.
    assert options["groq"].status == cloud_ui.STATUS_CONSENT_REQUIRED
    # Gemini was not blamed for a model that was never meant for it.
    assert options["gemini"].status == cloud_ui.STATUS_NO_MODEL


def test_provider_options_never_contact_a_provider(tmp_path, monkeypatch):
    """Building the dropdown must not construct an adapter or call out."""
    import ai.factory as factory

    def explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("provider_options constructed a provider")

    monkeypatch.setattr(factory, "create_provider", explode)
    cloud_ui.provider_options(ai_table=_ai_table(), **_nowhere(tmp_path))


# ===========================================================================
# 2. The approved-model picker — reviewed records only
# ===========================================================================
def test_the_picker_offers_only_reviewed_approved_records():
    table = _ai_table(
        models=[
            _record("gemini-3.6-flash", "gemini"),
            _record("gemini-preview", "gemini", status="preview"),
            _record("gemini-unknown", "gemini", free_tier_confidence="unknown"),
            _record("gemini-paid", "gemini", free_tier_confidence="not-free"),
            _record("llama-3.3-70b-versatile", "groq"),
        ]
    )
    assert cloud_ui.approved_model_choices("gemini", ai_table=table) == (
        "gemini-3.6-flash",
    )


def test_the_picker_never_calls_list_models(monkeypatch):
    """A live list is availability, not eligibility — it must not populate the picker."""
    source = (cloud_ui.__file__)
    text = open(source, encoding="utf-8").read()
    assert "list_models" not in text


def test_the_picker_for_an_unknown_provider_is_empty():
    assert cloud_ui.approved_model_choices("ollama", ai_table=_ai_table()) == ()


def test_the_picker_honours_a_relaxed_strict_free_tier_setting():
    table = _ai_table(
        models=[_record("gemini-unknown", "gemini", free_tier_confidence="unknown")],
        gemini={"strict_free_tier_only": False},
    )
    assert cloud_ui.approved_model_choices("gemini", ai_table=table) == (
        "gemini-unknown",
    )


# ===========================================================================
# 3. The disclosure — needed, changed, acknowledged
# ===========================================================================
def test_a_never_acknowledged_provider_needs_the_disclosure(tmp_path):
    need = cloud_ui.disclosure_requirement(
        "gemini", settings_file=tmp_path / "none.json")
    assert need.required is True
    assert need.state == cloud_ui.DISCLOSURE_NEW
    assert "leave this computer" in need.body
    assert need.acknowledged_version == ""


def test_an_acknowledged_current_version_needs_nothing(tmp_path):
    settings = _acknowledge(tmp_path, "gemini")
    need = cloud_ui.disclosure_requirement("gemini", settings_file=settings)
    assert need.required is False
    assert need.state == cloud_ui.DISCLOSURE_ACKNOWLEDGED


def test_a_version_bump_forces_a_re_ask_and_says_the_notice_changed(tmp_path):
    settings = _acknowledge(tmp_path, "gemini", version="1")
    need = cloud_ui.disclosure_requirement(
        "gemini", settings_file=settings, version="2")
    assert need.required is True
    assert need.state == cloud_ui.DISCLOSURE_CHANGED
    assert need.acknowledged_version == "1"
    # A changed notice must not be worded as "you never accepted this".
    assert "changed" in need.body.lower()


def test_a_version_bump_invalidates_each_provider_independently(tmp_path):
    settings = _acknowledge(tmp_path, "gemini", version="1")
    _acknowledge(tmp_path, "groq", version="2")
    assert cloud_ui.disclosure_requirement(
        "gemini", settings_file=settings, version="2").required is True
    assert cloud_ui.disclosure_requirement(
        "groq", settings_file=settings, version="2").required is False


def test_acknowledging_one_provider_does_not_acknowledge_the_other(tmp_path):
    settings = tmp_path / "settings.json"
    assert cloud_ui.accept_disclosure("gemini", settings_file=settings) is True
    assert cloud_ui.disclosure_requirement(
        "gemini", settings_file=settings).required is False
    assert cloud_ui.disclosure_requirement(
        "groq", settings_file=settings).required is True


def test_only_the_version_is_ever_stored(tmp_path):
    settings = tmp_path / "settings.json"
    cloud_ui.accept_disclosure("gemini", settings_file=settings)
    stored = json.loads(settings.read_text(encoding="utf-8"))
    assert stored["ai"]["cloud_disclosure"] == {"gemini": DISCLOSURE_VERSION}


def test_the_disclosure_body_carries_the_billing_link_and_the_cancel_option(tmp_path):
    need = cloud_ui.disclosure_requirement(
        "groq", settings_file=tmp_path / "none.json")
    assert "console.groq.com/settings/billing" in need.body
    assert "billing" in need.body.lower()
    assert need.cancel_label
    assert "local" in need.cancel_label.lower() or "script" in need.cancel_label.lower()


# --- the version guard -----------------------------------------------------
# Append-only: every version the disclosure text has ever had, with the hash of that
# text. Editing `disclosure_text` without bumping DISCLOSURE_VERSION makes the first
# assertion fail; "fixing" it by editing an existing hash in place makes the
# append-only assertion fail. The cheap way out is therefore the correct one — add a
# new version.
DISCLOSURE_TEXT_HASHES = {
    "1": "e1f59155910b4c610eeed651f0600c549b67babc727dea04eb00ecb2685383ef",
}


def _disclosure_digest() -> str:
    joined = "\x00".join(
        disclosure_text(name) for name in sorted(disclosure_mod.PROVIDER_LABELS)
    )
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def test_the_shipped_disclosure_text_matches_its_declared_version():
    assert DISCLOSURE_VERSION in DISCLOSURE_TEXT_HASHES, (
        "DISCLOSURE_VERSION was bumped — add the new version and the hash of its text "
        "to DISCLOSURE_TEXT_HASHES."
    )
    assert DISCLOSURE_TEXT_HASHES[DISCLOSURE_VERSION] == _disclosure_digest(), (
        "The disclosure text changed but DISCLOSURE_VERSION did not. If the change is "
        "material, bump the version and append a new entry; users who accepted the old "
        "wording must be asked again."
    )


def test_the_disclosure_version_pin_is_append_only():
    assert DISCLOSURE_VERSION == max(DISCLOSURE_TEXT_HASHES, key=int)
    assert sorted(DISCLOSURE_TEXT_HASHES, key=int) == [
        str(n) for n in range(1, len(DISCLOSURE_TEXT_HASHES) + 1)
    ]


# ===========================================================================
# 4. The ETA
# ===========================================================================
def _estimate(**kwargs):
    base = dict(
        provider="groq",
        model_id="llama-3.3-70b-versatile",
        remaining_files=100,
        settings=CLOUD_DEFAULTS["groq"],
    )
    base.update(kwargs)
    return cloud_ui.estimate_run(**base)


def test_an_eta_with_every_input_known_is_a_labelled_range():
    est = _estimate(
        requests_per_chapter=2.0,
        tokens_per_chapter=6000.0,
        fallback_rate=0.25,
        observed={"rpm": 30, "tpm": 12000, "rpd": 1000, "tpd": 100000,
                  "reset_seconds": 86400},
    )
    assert est.kind == cloud_ui.ETA_RANGE
    assert est.low_seconds is not None and est.high_seconds is not None
    assert est.high_seconds >= est.low_seconds
    assert est.unknowns == ()
    assert "approximately" in est.headline.lower()


def test_the_range_high_end_folds_in_one_whole_reset_per_crossed_day():
    """Reset-time uncertainty is a derived width, not a fudge factor."""
    est = _estimate(
        remaining_files=1000,
        requests_per_chapter=1.0,
        tokens_per_chapter=1000.0,
        fallback_rate=0.0,
        observed={"rpm": 1000, "tpm": 1000000, "rpd": 1000000, "tpd": 100000,
                  "reset_seconds": 86400},
    )
    # 1,000,000 tokens needed at 100,000 TPD = 10 quota-days = 9 crossed resets.
    assert est.binding == "tokens_per_day"
    assert est.high_seconds - est.low_seconds == pytest.approx(9 * 86400)


def test_a_daily_limit_that_does_not_bind_leaves_the_range_undegraded():
    est = _estimate(
        remaining_files=5,
        requests_per_chapter=1.0,
        tokens_per_chapter=100.0,
        fallback_rate=0.0,
        observed={"rpm": 30, "tpm": 12000, "rpd": 1000, "tpd": 100000,
                  "reset_seconds": 86400},
    )
    assert est.kind == cloud_ui.ETA_RANGE
    assert est.low_seconds == pytest.approx(est.high_seconds)
    # A degenerate range is printed as one approximate figure, never as "X–X".
    assert "–" not in est.headline


def test_an_unknown_daily_quota_gives_a_lower_bound_and_says_why():
    est = _estimate(
        requests_per_chapter=2.0,
        tokens_per_chapter=6000.0,
        fallback_rate=0.0,
        observed={"rpm": 30, "tpm": 12000},
    )
    assert est.kind == cloud_ui.ETA_LOWER_BOUND
    assert est.low_seconds is not None
    assert est.high_seconds is None
    assert any("day" in u for u in est.unknowns)
    assert "at least" in est.headline.lower()


def test_an_unknown_per_chapter_cost_gives_no_hours_at_all():
    est = _estimate(observed={"rpm": 30, "tpm": 12000, "rpd": 1000, "tpd": 100000,
                              "reset_seconds": 86400})
    assert est.kind == cloud_ui.ETA_NONE
    assert est.low_seconds is None and est.high_seconds is None
    assert est.unknowns  # every missing input is named, not silently defaulted
    assert "cannot" in est.headline.lower() or "not" in est.headline.lower()


def test_an_unknown_fallback_rate_widens_the_range_to_its_true_worst_case():
    known = _estimate(
        requests_per_chapter=1.0, tokens_per_chapter=1000.0, fallback_rate=0.0,
        observed={"rpm": 60, "tpm": 60000, "rpd": 10**9, "tpd": 10**9,
                  "reset_seconds": 86400},
    )
    unknown = _estimate(
        requests_per_chapter=1.0, tokens_per_chapter=1000.0,
        observed={"rpm": 60, "tpm": 60000, "rpd": 10**9, "tpd": 10**9,
                  "reset_seconds": 86400},
    )
    # 2a retries a rejected chunk at most once, so the worst case is exactly double.
    assert unknown.high_seconds == pytest.approx(2 * known.high_seconds)
    assert unknown.low_seconds == pytest.approx(known.low_seconds)


def test_gemini_says_plainly_that_the_binding_limit_is_unknown():
    est = cloud_ui.estimate_run(
        provider="gemini",
        model_id="gemini-3.6-flash",
        remaining_files=50,
        settings=CLOUD_DEFAULTS["gemini"],
        requests_per_chapter=1.0,
        tokens_per_chapter=5000.0,
        fallback_rate=0.0,
    )
    assert est.kind == cloud_ui.ETA_LOWER_BOUND
    assert est.binding == "unknown"
    body = est.as_text().lower()
    assert "unknown" in body
    assert "google" in body or "gemini" in body


def test_groq_says_that_tokens_per_day_is_never_reported():
    est = _estimate(requests_per_chapter=1.0, tokens_per_chapter=5000.0,
                    fallback_rate=0.0, observed={"rpm": 30, "tpm": 12000})
    assert "tokens" in est.as_text().lower()
    assert "per day" in est.as_text().lower()


def test_the_app_s_own_pacing_floor_is_never_described_as_a_provider_limit():
    est = _estimate(requests_per_chapter=1.0, tokens_per_chapter=5000.0,
                    fallback_rate=0.0)
    text = est.as_text().lower()
    assert "this app" in text or "own pacing" in text


def test_a_zero_token_floor_is_not_a_constraint_and_never_divides_by_zero():
    """Gemini ships tpm_floor = 0 — deliberately, because no Gemini token figure
    exists. Zero must mean 'no token pacing', not 'infinitely slow'."""
    est = cloud_ui.estimate_run(
        provider="gemini",
        model_id="gemini-3.6-flash",
        remaining_files=10,
        settings=CLOUD_DEFAULTS["gemini"],
        requests_per_chapter=1.0,
        tokens_per_chapter=5000.0,
        fallback_rate=0.0,
    )
    assert est.low_seconds is not None
    # 10 chapters at the 10 RPM floor = 1 minute of pacing.
    assert est.low_seconds == pytest.approx(60.0)


def test_nothing_to_process_is_its_own_answer():
    est = _estimate(remaining_files=0, requests_per_chapter=1.0,
                    tokens_per_chapter=1.0, fallback_rate=0.0)
    assert est.kind == cloud_ui.ETA_NONE
    assert est.low_seconds is None


def test_the_estimate_is_always_labelled_as_an_estimate():
    for est in (
        _estimate(requests_per_chapter=1.0, tokens_per_chapter=1.0, fallback_rate=0.0,
                  observed={"rpm": 30, "tpm": 12000, "rpd": 1000, "tpd": 100000,
                            "reset_seconds": 86400}),
        _estimate(requests_per_chapter=1.0, tokens_per_chapter=1.0, fallback_rate=0.0),
        _estimate(),
    ):
        assert "estimate" in est.as_text().lower()


def test_a_cloud_run_warns_that_free_tiers_suit_subsets_not_whole_novels():
    est = _estimate(remaining_files=3000, requests_per_chapter=1.0,
                    tokens_per_chapter=5000.0, fallback_rate=0.0)
    assert "subset" in est.as_text().lower()


def test_duration_wording_scales_from_minutes_to_days():
    assert cloud_ui.format_span(90) == "2 minutes"
    assert cloud_ui.format_span(3600 * 3) == "3 hours"
    assert cloud_ui.format_span(3600 * 100) == "4 days"


# ===========================================================================
# 5. The resume offer
# ===========================================================================
def _finished_partial_run(tmp_path, *, files=3, done=1):
    root = tmp_path / "downloads"
    out = root / "novel-1"
    out.mkdir(parents=True)
    sources = []
    for index in range(files):
        src = tmp_path / f"ch{index}.pdf"
        src.write_text("x", encoding="utf-8")
        sources.append(str(src))
    checkpoint = RunCheckpoint(
        out, sources, novel="Shadow Slave", provider="groq", model_id="m")
    for src in sources[:done]:
        checkpoint.record_completed(src, str(out / "x.pdf"), ai_status="accepted")
    checkpoint.finish(stopped=True)
    return root, sources


def test_accepting_a_resume_continues_the_original_run(tmp_path):
    root, sources = _finished_partial_run(tmp_path, files=3, done=1)
    offer = find_resumable_run(root)
    assert offer.available is True

    plan = cloud_ui.resume_decision(offer, accepted=True)
    assert plan.resumed is True
    assert plan.run_kwargs["pdf_paths"] == list(sources[1:])
    assert plan.run_kwargs["output_dir"] == str(root / "novel-1")
    # The checkpoint continues the ORIGINAL queue from the original index — a fresh
    # queue of just the remainder would silently discard the run's own shape.
    assert plan.checkpoint_kwargs["queue"] == sources
    assert plan.checkpoint_kwargs["start_index"] == 1


def test_a_resumed_checkpoint_completes_the_original_queue(tmp_path):
    root, sources = _finished_partial_run(tmp_path, files=3, done=1)
    plan = cloud_ui.resume_decision(find_resumable_run(root), accepted=True)
    kwargs = dict(plan.checkpoint_kwargs)
    checkpoint = RunCheckpoint(kwargs.pop("output_dir"), kwargs.pop("queue"), **kwargs)
    for src in plan.run_kwargs["pdf_paths"]:
        checkpoint.record_completed(src, "out.pdf")
    checkpoint.finish()
    assert find_resumable_run(root).available is False


def test_declining_a_resume_starts_a_fresh_run(tmp_path):
    root, _sources = _finished_partial_run(tmp_path)
    plan = cloud_ui.resume_decision(find_resumable_run(root), accepted=False)
    assert plan.resumed is False
    assert plan.run_kwargs == {}
    assert plan.checkpoint_kwargs == {}


def test_declining_leaves_the_manifest_untouched(tmp_path):
    root, _sources = _finished_partial_run(tmp_path)
    manifest = root / "novel-1" / "run-manifest.json"
    before = manifest.read_bytes()
    cloud_ui.resume_decision(find_resumable_run(root), accepted=False)
    assert manifest.read_bytes() == before


def test_no_manifest_means_no_offer_and_a_fresh_run(tmp_path):
    root = tmp_path / "downloads"
    root.mkdir()
    offer = find_resumable_run(root)
    assert offer.available is False
    plan = cloud_ui.resume_decision(offer, accepted=True)
    assert plan.resumed is False
    assert plan.message


def test_a_manifest_that_vanishes_between_offer_and_answer_falls_back(tmp_path):
    root, _sources = _finished_partial_run(tmp_path)
    offer = find_resumable_run(root)
    (root / "novel-1" / "run-manifest.json").unlink()
    plan = cloud_ui.resume_decision(offer, accepted=True)
    assert plan.resumed is False
    assert "fresh" in plan.message.lower()


def test_a_resume_carries_the_measured_fallback_rate_forward(tmp_path):
    root = tmp_path / "downloads"
    out = root / "novel-1"
    out.mkdir(parents=True)
    sources = []
    for index in range(4):
        src = tmp_path / f"c{index}.pdf"
        src.write_text("x", encoding="utf-8")
        sources.append(str(src))
    checkpoint = RunCheckpoint(out, sources, novel="N", provider="groq", model_id="m")
    checkpoint.record_completed(sources[0], "a.pdf", ai_status="accepted")
    checkpoint.record_completed(sources[1], "b.pdf", ai_status="fallback")
    checkpoint.finish(stopped=True)

    plan = cloud_ui.resume_decision(find_resumable_run(root), accepted=True)
    assert plan.fallback_rate == pytest.approx(0.5)


def test_an_unmeasured_chapter_is_never_scored_as_a_success():
    assert cloud_ui.measured_fallback_rate({"entries": [{"ai_status": "none"}]}) is None
    assert cloud_ui.measured_fallback_rate(None) is None
    assert cloud_ui.measured_fallback_rate({"entries": []}) is None


def test_the_resume_prompt_states_what_is_left_and_what_is_missing(tmp_path):
    root, sources = _finished_partial_run(tmp_path, files=3, done=1)
    import os

    os.remove(sources[2])
    offer = find_resumable_run(root)
    text = cloud_ui.resume_prompt(offer)
    assert "2" in text          # 2 chapters remaining
    assert "1" in text          # 1 of them can no longer be found
    assert "Shadow Slave" in text


# ===========================================================================
# 6. build_ai_editor — the wiring that makes Phases 4 and 5 live
# ===========================================================================
def _cloud_prefs(tmp_path, provider="groq", model="llama-3.3-70b-versatile"):
    prefs = _ai_table(**{provider: {"model": model}})
    prefs["provider"] = provider
    prefs["model"] = model
    prefs["policy"] = ai_settings.POLICY_PREFER_AI
    return prefs


def test_build_provider_factory_wraps_a_cloud_adapter_in_a_rate_limited_provider(
        tmp_path):
    settings = _acknowledge(tmp_path, "groq")
    adapter = _FakeAdapter(model_id="llama-3.3-70b-versatile")
    factory = ai_settings.build_provider_factory(
        _cloud_prefs(tmp_path),
        create=lambda prefs, model: adapter,
        environ={"GROQ_API_KEY": FAKE_GROQ_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=settings,
    )
    provider = factory()
    # Compared by name, not by identity: the class the product builds comes from
    # whichever generation of `ai.rate_limits` is current when the factory runs.
    assert type(provider).__name__ == "RateLimitedProvider"
    assert provider.inner is adapter


def test_the_local_provider_is_not_wrapped(tmp_path):
    adapter = _FakeAdapter(model_id="qwen3:14b")
    prefs = _ai_table(provider="ollama", model="qwen3:14b")
    factory = ai_settings.build_provider_factory(
        prefs, create=lambda p, m: adapter, **_nowhere(tmp_path))
    assert factory() is adapter


def test_the_limiter_follows_the_adapter_s_declared_capability(tmp_path):
    settings = _acknowledge(tmp_path, "gemini")
    adapter = _FakeAdapter(model_id="gemini-3.6-flash", exposes_rate_limits=False)
    prefs = _cloud_prefs(tmp_path, provider="gemini", model="gemini-3.6-flash")
    factory = ai_settings.build_provider_factory(
        prefs,
        create=lambda p, m: adapter,
        environ={"GEMINI_API_KEY": FAKE_GEMINI_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=settings,
    )
    assert type(factory().limiter).__name__ == "FlooredRateLimiter"


def test_the_checkpoint_quota_callback_is_handed_to_the_limiter(tmp_path):
    settings = _acknowledge(tmp_path, "groq")
    seen = []

    class _Spy:
        def on_quota_stop(self, stop):
            seen.append(stop)

    adapter = _FakeAdapter(
        model_id="llama-3.3-70b-versatile",
        raises=lambda: _errors().DailyQuotaExhausted(
            "free daily quota exhausted", retryable=False),
    )
    factory = ai_settings.build_provider_factory(
        _cloud_prefs(tmp_path),
        create=lambda p, m: adapter,
        checkpoint=_Spy(),
        environ={"GROQ_API_KEY": FAKE_GROQ_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=settings,
    )
    provider = factory()
    with pytest.raises(_errors().DailyQuotaExhausted):
        provider.complete(_request())
    assert len(seen) == 1
    assert seen[0].is_daily is True


def _request():
    from ai.models import CompletionRequest

    return CompletionRequest(
        text="hello",
        system_prompt="s",
        prompt_version="1",
        model_id="llama-3.3-70b-versatile",
        temperature=0.0,
        seed=0,
        timeout_seconds=5,
        max_output_tokens=64,
        request_id="req-1",
    )


def test_build_ai_editor_really_runs_through_the_rate_limited_provider(tmp_path):
    """End to end through the real AIEditor: a daily quota raised by the adapter
    reaches the checkpoint's callback, which can only happen if the limiter is
    genuinely in the call path."""
    settings = _acknowledge(tmp_path, "groq")
    seen = []

    class _Spy:
        def on_quota_stop(self, stop):
            seen.append(stop)

    adapter = _FakeAdapter(
        model_id="llama-3.3-70b-versatile",
        raises=lambda: _errors().DailyQuotaExhausted(
            "free daily quota exhausted", retryable=False),
    )
    editor = ai_settings.build_ai_editor(
        _cloud_prefs(tmp_path),
        create=lambda p, m: adapter,
        checkpoint=_Spy(),
        environ={"GROQ_API_KEY": FAKE_GROQ_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=settings,
    )
    baseline = "The knight walked on.\n\nThe road was long.\n"
    outcome = editor.edit(baseline)
    # Chapter-atomic fallback, byte for byte.
    assert outcome.text == baseline
    assert outcome.used_ai is False
    assert len(seen) == 1


def test_a_stop_event_reaches_the_limiter(tmp_path):
    settings = _acknowledge(tmp_path, "groq")
    stop = threading.Event()
    stop.set()
    adapter = _FakeAdapter(
        model_id="llama-3.3-70b-versatile",
        raises=lambda: _errors().RateLimited("slow down", retryable=True),
    )
    factory = ai_settings.build_provider_factory(
        _cloud_prefs(tmp_path),
        create=lambda p, m: adapter,
        stop_event=stop,
        environ={"GROQ_API_KEY": FAKE_GROQ_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=settings,
    )
    with pytest.raises(_errors().RequestCancelled):
        factory().complete(_request())


# --- the consent gate, end to end -----------------------------------------
def test_an_unacknowledged_disclosure_blocks_the_first_cloud_call(tmp_path):
    adapter = _FakeAdapter(model_id="llama-3.3-70b-versatile")
    factory = ai_settings.build_provider_factory(
        _cloud_prefs(tmp_path),
        create=lambda p, m: adapter,
        environ={"GROQ_API_KEY": FAKE_GROQ_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=tmp_path / "none.json",
    )
    with pytest.raises(_disclosure_errors().DisclosureNotAcknowledged):
        factory()
    assert adapter.calls == []


def test_declining_the_disclosure_falls_back_to_script_only_cleanly(tmp_path):
    adapter = _FakeAdapter(model_id="llama-3.3-70b-versatile")
    editor = ai_settings.build_ai_editor(
        _cloud_prefs(tmp_path),
        create=lambda p, m: adapter,
        environ={"GROQ_API_KEY": FAKE_GROQ_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=tmp_path / "none.json",
    )
    baseline = "The knight walked on.\n\nThe road was long.\n"
    outcome = editor.edit(baseline)
    assert outcome.text == baseline
    assert outcome.used_ai is False
    assert adapter.calls == []  # not one chapter left the machine


def test_a_missing_key_blocks_the_first_cloud_call(tmp_path):
    settings = _acknowledge(tmp_path, "groq")
    adapter = _FakeAdapter(model_id="llama-3.3-70b-versatile")
    factory = ai_settings.build_provider_factory(
        _cloud_prefs(tmp_path),
        create=lambda p, m: adapter,
        environ={},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=settings,
    )
    with pytest.raises(_errors().AuthenticationError):
        factory()


def test_an_unapproved_model_blocks_the_first_cloud_call(tmp_path):
    settings = _acknowledge(tmp_path, "groq")
    prefs = _cloud_prefs(tmp_path, model="llama-3.3-70b-versatile")
    prefs["model"] = "some-other-model"
    prefs["groq"] = {"model": "some-other-model"}
    adapter = _FakeAdapter()
    factory = ai_settings.build_provider_factory(
        prefs,
        create=lambda p, m: adapter,
        environ={"GROQ_API_KEY": FAKE_GROQ_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "none.env",
        settings_file=settings,
    )
    with pytest.raises(_errors().ModelUnavailable):
        factory()


# ===========================================================================
# 7. Condensed-log additions
# ===========================================================================
def test_the_cloud_run_header_is_one_run_scoped_line():
    line, level = cloud_ui.cloud_run_header("groq", "llama-3.3-70b-versatile")
    assert line.count("\n") == 0
    assert "Groq" in line
    assert "llama-3.3-70b-versatile" in line
    assert level


def test_a_daily_quota_stop_tells_the_user_they_can_close_the_app():
    message, level = cloud_ui.quota_stop_message(
        {"is_daily": True, "reset_known": True, "reset_seconds": 3600,
         "provider": "groq", "kind": "requests_per_day"})
    assert "resume" in message.lower()
    assert level == "warn"


def test_an_unknown_reset_time_is_never_guessed():
    message, _level = cloud_ui.quota_stop_message(
        {"is_daily": True, "reset_known": False, "reset_seconds": None,
         "provider": "gemini", "kind": "daily_unspecified"})
    assert "unknown" in message.lower()
    assert "limits" in message.lower()
    # No invented midnight, no provider timezone.
    assert "midnight" not in message.lower()


def test_a_long_wait_stop_is_worded_differently_from_a_daily_quota():
    daily, _ = cloud_ui.quota_stop_message({"is_daily": True, "reset_known": True,
                                            "reset_seconds": 60, "provider": "groq"})
    long_wait, _ = cloud_ui.quota_stop_message({"is_daily": False, "reset_known": True,
                                                "reset_seconds": 4000,
                                                "provider": "groq"})
    assert daily != long_wait
    assert "tomorrow" in daily.lower()


def test_the_condensed_log_event_line_uses_the_existing_indented_shape():
    message, _ = cloud_ui.quota_stop_message({"is_daily": True, "reset_known": False,
                                              "provider": "groq"})
    assert message.startswith("        ⚠ ")


def test_the_local_path_adds_no_cloud_lines():
    assert cloud_ui.cloud_run_header(cloud_ui.local_provider(), "qwen3:14b") is None


# ===========================================================================
# 8. The panel itself — proof the wiring is live, not merely present
# ===========================================================================
# Exercised with the existing synchronous-fake-thread + run_batch-spy idiom from
# `test_app.py` / `test_ai_gui_controls.py`, and skipped when there is no display.
# Dialogs are answered by monkeypatching `messagebox`, which is the only part of this
# flow a human would otherwise have to click.
class _ImmediateThread:
    def __init__(self, target=None, daemon=None):
        self._target = target

    def start(self):
        self._target()


def _new_app(monkeypatch, tmp_path):
    tk = pytest.importorskip("tkinter")
    from ai import secrets as secrets_mod
    from gui import app as appmod

    settings = tmp_path / "settings.json"
    monkeypatch.setattr(appmod.ai_settings, "default_settings_file", lambda: settings)
    # Hermetic key discovery: no real secrets.json and no repo .env can be consulted,
    # so a developer with a live key on this machine cannot change the outcome.
    monkeypatch.setattr(
        secrets_mod, "default_secrets_file", lambda: tmp_path / "no-secrets.json")
    monkeypatch.setattr(secrets_mod, "DEFAULT_DOTENV_PATH", tmp_path / "no.env")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    try:
        app = appmod.WebnovelEditorApp()
    except tk.TclError:
        pytest.skip("no display available for Tk")
    app.withdraw()
    app.update_idletasks()
    return appmod, app


def _wire_batch_spy(appmod, monkeypatch, tmp_path):
    calls = []

    def spy_run_batch(pdf_paths, output_dir, **kwargs):
        calls.append({"pdf_paths": list(pdf_paths), "output_dir": output_dir, **kwargs})
        return {"total": len(pdf_paths), "succeeded": len(pdf_paths), "failed": 0,
                "skipped": 0, "output_dir": output_dir, "outputs": [],
                "novel": "x", "profile_applied": False}

    monkeypatch.setattr(appmod.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(appmod, "run_batch", spy_run_batch)
    monkeypatch.setattr(appmod, "downloads_dir", lambda: tmp_path / "DL")
    monkeypatch.setattr(appmod.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(appmod.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(appmod, "open_in_file_manager", lambda *a, **k: True)
    return calls


def _queue_one_pdf(app, tmp_path):
    src = tmp_path / "chapter.pdf"
    src.write_text("x", encoding="utf-8")
    app.file_paths = [str(src)]
    return str(src)


def _select_cloud(app, monkeypatch, provider="groq",
                  model="llama-3.3-70b-versatile", key=FAKE_GROQ_KEY):
    monkeypatch.setenv("GROQ_API_KEY" if provider == "groq" else "GEMINI_API_KEY", key)
    app.opt_ai_enabled.set(True)
    app._ai_provider = provider
    app.ai_model_var.set(model)
    app._refresh_provider_options()
    app.ai_model_var.set(model)


def test_the_dropdown_lists_every_provider_local_first(monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        values = list(app.ai_provider_combo["values"])
        assert len(values) == 3
        assert values[0] == appmod.cloud_ui.LOCAL_LABEL
    finally:
        app.destroy()


def test_picking_an_unavailable_provider_is_refused_with_its_reason(
        monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        # A provider with no approved model left to offer has nowhere to go.
        app.ai_prefs = dict(app.ai_prefs)
        app.ai_prefs["approved_models"] = [
            _record("groq-preview-only", "groq", status="preview")]
        app._refresh_provider_options()

        before = app._ai_provider
        label = app._provider_labels["groq"]
        assert label.endswith("unavailable")
        app.ai_provider_var.set(label)
        app._on_ai_provider_changed()

        assert app._ai_provider == before          # the selection did not take
        assert "approved" in app.ai_status_var.get().lower()
    finally:
        app.destroy()


def test_choosing_a_cloud_provider_fills_the_picker_from_reviewed_records(
        monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        app.opt_ai_enabled.set(True)
        app.ai_provider_var.set(app._provider_labels["groq"])
        app._on_ai_provider_changed()

        offered = list(app.ai_model_combo["values"])
        assert offered == list(
            appmod.cloud_ui.approved_model_choices("groq", ai_table=app.ai_prefs))
        assert offered  # the committed config really does approve Groq models
    finally:
        app.destroy()


def test_declining_the_disclosure_stops_the_run_before_it_starts(
        monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
        _queue_one_pdf(app, tmp_path)
        _select_cloud(app, monkeypatch)
        monkeypatch.setattr(appmod.messagebox, "askokcancel", lambda *a, **k: False)

        app._start_batch()

        assert calls == []                 # not one chapter was queued for sending
        assert app._running is False
        # Cancelling records nothing at all — not even an empty acknowledgement.
        settings_path = tmp_path / "settings.json"
        stored = (
            json.loads(settings_path.read_text(encoding="utf-8"))
            if settings_path.exists() else {}
        )
        assert "cloud_disclosure" not in stored.get("ai", {})
    finally:
        app.destroy()


def test_accepting_the_disclosure_records_only_the_version_and_runs(
        monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
        _queue_one_pdf(app, tmp_path)
        _select_cloud(app, monkeypatch)
        monkeypatch.setattr(appmod.messagebox, "askokcancel", lambda *a, **k: True)

        app._start_batch()

        assert len(calls) == 1
        settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert settings["ai"]["cloud_disclosure"] == {"groq": DISCLOSURE_VERSION}
    finally:
        app.destroy()


def test_cancelling_the_estimate_stops_the_run(monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
        _queue_one_pdf(app, tmp_path)
        _acknowledge(tmp_path, "groq")
        _select_cloud(app, monkeypatch)
        monkeypatch.setattr(appmod.messagebox, "askokcancel", lambda *a, **k: False)

        app._start_batch()

        assert calls == []
        # The headline is published even when the run is declined.
        assert "estimate" in app.rate_var.get().lower()
    finally:
        app.destroy()


def test_a_cloud_run_hands_run_batch_a_checkpoint(monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
        source = _queue_one_pdf(app, tmp_path)
        _acknowledge(tmp_path, "groq")
        _select_cloud(app, monkeypatch)
        monkeypatch.setattr(appmod.messagebox, "askokcancel", lambda *a, **k: True)

        app._start_batch()

        checkpoint = calls[0]["checkpoint"]
        assert type(checkpoint).__name__ == "RunCheckpoint"
        assert checkpoint.queue == [source]
    finally:
        app.destroy()


def test_a_local_run_still_writes_no_manifest(monkeypatch, tmp_path):
    """Plan 1's session-only behaviour for local runs is deliberately untouched."""
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
        _queue_one_pdf(app, tmp_path)
        app.opt_ai_enabled.set(False)

        app._start_batch()

        assert calls[0]["checkpoint"] is None
    finally:
        app.destroy()


def test_a_cloud_run_logs_the_provider_exactly_once(monkeypatch, tmp_path):
    """Run-scoped facts go on a run-scoped line, never on every per-file line."""
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        _wire_batch_spy(appmod, monkeypatch, tmp_path)
        _queue_one_pdf(app, tmp_path)
        _acknowledge(tmp_path, "groq")
        _select_cloud(app, monkeypatch)
        monkeypatch.setattr(appmod.messagebox, "askokcancel", lambda *a, **k: True)

        app._start_batch()
        app.update()

        assert app.log_text.get("1.0", "end").count("Cloud provider:") == 1
    finally:
        app.destroy()


def _stopped_run(tmp_path, count=3, done=1):
    root = tmp_path / "DL"
    out = root / "novel-1"
    out.mkdir(parents=True)
    sources = []
    for index in range(count):
        src = tmp_path / f"r{index}.pdf"
        src.write_text("x", encoding="utf-8")
        sources.append(str(src))
    checkpoint = RunCheckpoint(out, sources, novel="Shadow Slave", provider="groq")
    for src in sources[:done]:
        checkpoint.record_completed(src, "a.pdf", ai_status="accepted")
    checkpoint.finish(stopped=True)
    return out, sources


def test_accepting_the_resume_offer_continues_the_original_run(
        monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
        out, sources = _stopped_run(tmp_path)
        monkeypatch.setattr(appmod.messagebox, "askyesno", lambda *a, **k: True)
        app.opt_ai_enabled.set(False)

        app._start_batch()

        assert calls[0]["pdf_paths"] == sources[1:]
        assert calls[0]["output_dir"] == str(out)
    finally:
        app.destroy()


def test_declining_the_resume_offer_starts_a_fresh_numbered_folder(
        monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
        out, _sources = _stopped_run(tmp_path)
        manifest = (out / "run-manifest.json").read_bytes()
        monkeypatch.setattr(appmod.messagebox, "askyesno", lambda *a, **k: False)
        fresh = _queue_one_pdf(app, tmp_path)
        app.opt_ai_enabled.set(False)

        app._start_batch()

        assert calls[0]["pdf_paths"] == [fresh]
        assert calls[0]["output_dir"] != str(out)
        # Declining is not a call into the manifest layer at all.
        assert (out / "run-manifest.json").read_bytes() == manifest
    finally:
        app.destroy()


def test_no_manifest_means_the_resume_dialog_is_never_shown(monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        _wire_batch_spy(appmod, monkeypatch, tmp_path)
        (tmp_path / "DL").mkdir()
        asked = []

        def spy_askyesno(*args, **kwargs):
            asked.append(args)
            return False

        monkeypatch.setattr(appmod.messagebox, "askyesno", spy_askyesno)
        _queue_one_pdf(app, tmp_path)
        app.opt_ai_enabled.set(False)

        app._start_batch()

        assert asked == []
    finally:
        app.destroy()


# ===========================================================================
# 9. In-app key entry (Phase 6 gap-fill) — a GUI door onto Phase 1's storage
# ===========================================================================
def test_saving_a_key_goes_through_phase_1s_storage_function(tmp_path, monkeypatch):
    """The GUI must not grow its own storage. Patching Phase 1's function and
    requiring it to be what ran is stronger than checking the file afterwards — the
    file could be correct because the GUI wrote it itself."""
    from ai import secrets as secrets_mod

    seen = []
    monkeypatch.setattr(
        secrets_mod, "store_api_key",
        lambda provider, key, **kw: seen.append((provider, key, kw)) or True)

    outcome = cloud_ui.save_key(
        "groq", FAKE_GROQ_KEY, secrets_file=tmp_path / "secrets.json")

    assert outcome.saved is True
    assert len(seen) == 1
    assert seen[0][0] == "groq"
    assert seen[0][2]["path"] == tmp_path / "secrets.json"


def test_a_saved_key_really_lands_in_the_per_user_secrets_file(tmp_path):
    secrets_file = tmp_path / "secrets.json"
    assert cloud_ui.save_key("groq", FAKE_GROQ_KEY, secrets_file=secrets_file).saved
    stored = json.loads(secrets_file.read_text(encoding="utf-8"))
    assert stored["keys"]["groq"] == FAKE_GROQ_KEY


def test_saving_a_key_never_puts_it_in_the_message_or_the_log(tmp_path):
    outcome = cloud_ui.save_key(
        "groq", FAKE_GROQ_KEY, secrets_file=tmp_path / "secrets.json")
    assert FAKE_GROQ_KEY not in outcome.message
    assert FAKE_GROQ_KEY not in repr(outcome)
    # ...and the redactor now knows it, so it cannot surface downstream either.
    from ai.redaction import redact

    assert FAKE_GROQ_KEY not in redact(f"boom: {FAKE_GROQ_KEY}")


def test_an_unusable_key_is_refused_with_a_reason(tmp_path):
    outcome = cloud_ui.save_key("groq", "   ", secrets_file=tmp_path / "secrets.json")
    assert outcome.saved is False
    assert outcome.message
    assert not (tmp_path / "secrets.json").exists()


def test_a_saved_key_makes_the_provider_ready_for_the_disclosure(tmp_path):
    secrets_file = tmp_path / "secrets.json"
    settings = tmp_path / "settings.json"
    table = _ai_table(groq={"model": "llama-3.3-70b-versatile"})
    locations = dict(environ={}, secrets_file=secrets_file,
                     dotenv_path=tmp_path / "no.env", settings_file=settings)

    before = cloud_ui.provider_option("groq", ai_table=table, **locations)
    assert before.status == "auth_missing"

    cloud_ui.save_key("groq", FAKE_GROQ_KEY, secrets_file=secrets_file)

    after = cloud_ui.provider_option("groq", ai_table=table, **locations)
    assert after.status == cloud_ui.STATUS_CONSENT_REQUIRED


def test_forgetting_a_key_returns_the_provider_to_unavailable(tmp_path):
    secrets_file = tmp_path / "secrets.json"
    table = _ai_table(groq={"model": "llama-3.3-70b-versatile"})
    locations = dict(environ={}, secrets_file=secrets_file,
                     dotenv_path=tmp_path / "no.env",
                     settings_file=tmp_path / "settings.json")
    cloud_ui.save_key("groq", FAKE_GROQ_KEY, secrets_file=secrets_file)

    outcome = cloud_ui.forget_key("groq", secrets_file=secrets_file)

    assert outcome.saved is False          # nothing is stored any more
    assert outcome.removed is True
    assert cloud_ui.provider_option(
        "groq", ai_table=table, **locations).status == "auth_missing"


def test_forgetting_a_key_that_was_never_saved_says_so_without_failing(tmp_path):
    outcome = cloud_ui.forget_key("groq", secrets_file=tmp_path / "none.json")
    assert outcome.removed is False
    assert outcome.message


def test_forgetting_the_saved_key_leaves_the_other_provider_alone(tmp_path):
    secrets_file = tmp_path / "secrets.json"
    cloud_ui.save_key("groq", FAKE_GROQ_KEY, secrets_file=secrets_file)
    cloud_ui.save_key("gemini", FAKE_GEMINI_KEY, secrets_file=secrets_file)

    cloud_ui.forget_key("groq", secrets_file=secrets_file)

    stored = json.loads(secrets_file.read_text(encoding="utf-8"))["keys"]
    assert "groq" not in stored
    assert stored["gemini"] == FAKE_GEMINI_KEY


def test_the_key_prompt_names_the_provider_and_the_winning_source(tmp_path):
    """Phase 1's precedence puts the environment variable above the saved file, so a
    saved key can be correct and still not be the one in use. The prompt says which
    source is winning rather than letting that look like a failed save."""
    prompt = cloud_ui.key_prompt(
        "groq",
        environ={"GROQ_API_KEY": FAKE_GROQ_KEY},
        secrets_file=tmp_path / "none.json",
        dotenv_path=tmp_path / "no.env",
    )
    assert "Groq" in prompt.title
    assert "environment variable" in prompt.current
    assert FAKE_GROQ_KEY not in prompt.current
    assert prompt.can_forget is False       # nothing saved here to forget

    saved = tmp_path / "secrets.json"
    cloud_ui.save_key("groq", FAKE_GROQ_KEY, secrets_file=saved)
    with_saved = cloud_ui.key_prompt(
        "groq", environ={}, secrets_file=saved, dotenv_path=tmp_path / "no.env")
    assert with_saved.can_forget is True


def test_the_local_provider_has_no_key_prompt():
    assert cloud_ui.key_prompt(cloud_ui.local_provider()) is None


def test_a_quota_stop_checkpoints_first_then_logs():
    """Order is load-bearing: the run must be durably stopped before anything is drawn,
    so a logging fault can never cost the user the checkpoint."""
    from gui.app import _QuotaStopRelay

    order = []

    class _Checkpoint:
        def on_quota_stop(self, stop):
            order.append("checkpoint")

    class _Stop:
        def as_dict(self):
            return {"is_daily": True, "reset_known": False, "provider": "groq"}

    relay = _QuotaStopRelay(_Checkpoint(), lambda m, level="info": order.append("log"))
    relay.on_quota_stop(_Stop())
    assert order == ["checkpoint", "log"]


# ===========================================================================
# 10. The panel's key dialog and the stale-model-list bug
# ===========================================================================
def test_the_key_button_is_live_only_for_a_cloud_provider(monkeypatch, tmp_path):
    _appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        app.opt_ai_enabled.set(True)
        app._refresh_ai_children()
        assert "disabled" in app.ai_key_button.state()   # local has no key

        app._ai_provider = "groq"
        app._refresh_provider_options()
        app._refresh_ai_children()
        assert "disabled" not in app.ai_key_button.state()
    finally:
        app.destroy()


def test_the_key_entry_is_masked(monkeypatch, tmp_path):
    _appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        app._ai_provider = "groq"
        app._refresh_provider_options()
        dialog = app._build_key_dialog("groq")
        try:
            assert dialog.entry.cget("show") not in ("", None)
        finally:
            dialog.window.destroy()
    finally:
        app.destroy()


def test_saving_from_the_panel_updates_the_status_line(monkeypatch, tmp_path):
    from ai import secrets as secrets_mod

    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        monkeypatch.setattr(
            secrets_mod, "default_secrets_file", lambda: tmp_path / "secrets.json")
        app.opt_ai_enabled.set(True)
        app._ai_provider = "groq"
        app.ai_model_var.set("llama-3.3-70b-versatile")
        app._refresh_provider_options()
        app._publish_provider_status()
        assert "no api key" in app.ai_status_var.get().lower()

        app._apply_key_entry("groq", FAKE_GROQ_KEY)
        app.update()

        # Reuses Phase 6's status logic: the next rail, not a bespoke message.
        assert "no api key" not in app.ai_status_var.get().lower()
        assert app._provider_option("groq").status == appmod.cloud_ui.STATUS_CONSENT_REQUIRED
        # The key itself never reaches the log.
        assert FAKE_GROQ_KEY not in app.log_text.get("1.0", "end")
    finally:
        app.destroy()


def test_forgetting_from_the_panel_returns_the_provider_to_unavailable(
        monkeypatch, tmp_path):
    from ai import secrets as secrets_mod

    _appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        monkeypatch.setattr(
            secrets_mod, "default_secrets_file", lambda: tmp_path / "secrets.json")
        app.opt_ai_enabled.set(True)
        app._ai_provider = "groq"
        app.ai_model_var.set("llama-3.3-70b-versatile")
        app._apply_key_entry("groq", FAKE_GROQ_KEY)
        assert app._provider_option("groq").status != "auth_missing"

        app._forget_key("groq")

        assert app._provider_option("groq").status == "auth_missing"
    finally:
        app.destroy()


def test_switching_back_to_the_local_provider_repopulates_the_model_list(
        monkeypatch, tmp_path):
    """The reported bug: local -> cloud -> local left the cloud models in the box.

    Reproduces the exact click path through the real handlers, with no checkbox
    toggle (the workaround) anywhere in it.
    """
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        monkeypatch.setattr(appmod.threading, "Thread", _ImmediateThread)
        monkeypatch.setattr(
            appmod.ai_settings, "probe_provider",
            lambda prefs, **kw: appmod.ai_settings.ProviderProbe("ok", ("qwen3:14b",)))

        app.opt_ai_enabled.set(True)
        app._on_ai_toggled()
        app.update()
        assert list(app.ai_model_combo["values"]) == ["qwen3:14b"]

        # -> cloud
        app.ai_provider_var.set(app._provider_labels["groq"])
        app._on_ai_provider_changed()
        app.update()
        cloud_models = list(app.ai_model_combo["values"])
        assert "qwen3:14b" not in cloud_models and cloud_models

        # -> back to local, with no checkbox toggle
        app.ai_provider_var.set(app._provider_labels[appmod.cloud_ui.local_provider()])
        app._on_ai_provider_changed()
        app.update()

        assert list(app.ai_model_combo["values"]) == ["qwen3:14b"]
    finally:
        app.destroy()


def test_a_provider_switch_never_leaves_the_previous_provider_s_models_on_screen(
        monkeypatch, tmp_path):
    """The narrower invariant behind the bug, and the one that matters for safety:
    a model list must never outlive the provider it was built for, not even for the
    moment before a background probe answers — otherwise a cloud model ID is
    selectable while the local provider is active."""
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        probes = []

        class _NeverAnswers:
            """A probe that is started but never delivers, like a slow/absent service."""

            def __init__(self, target=None, daemon=None):
                probes.append(target)

            def start(self):
                pass

        app.opt_ai_enabled.set(True)
        app._ai_provider = "groq"
        app.ai_model_var.set("llama-3.3-70b-versatile")
        app._refresh_provider_options()
        assert list(app.ai_model_combo["values"])          # cloud models are showing

        monkeypatch.setattr(appmod.threading, "Thread", _NeverAnswers)
        app.ai_provider_var.set(app._provider_labels[appmod.cloud_ui.local_provider()])
        app._on_ai_provider_changed()
        app.update()

        assert list(app.ai_model_combo["values"]) == []
        assert app.ai_model_var.get() == ""
        assert probes, "the local probe was never started"
    finally:
        app.destroy()
