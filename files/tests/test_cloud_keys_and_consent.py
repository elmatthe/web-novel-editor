"""Plan 2b Phase 1 — keys, redaction, approved models, consent, and the cloud gate.

Every test here runs **offline**: no provider SDK is imported, no network call is made,
no real API key is read, and no per-user file outside ``tmp_path`` is touched. Each test
passes explicit ``secrets_file`` / ``settings_file`` / ``dotenv_path`` locations so a
developer who happens to have a real key on this machine cannot make the suite pass (or
fail) for the wrong reason.

The fake keys below are deliberately shaped like the real thing — ``AIza...`` for Google
and ``gsk_...`` for Groq — so the pattern half of the redactor is exercised as well as
the registered-literal half.
"""

from __future__ import annotations

import json
import os
import stat
import sys

import pytest

from ai import redaction
from ai.approved_models import (
    ApprovedModel,
    ensure_model_approved,
    ensure_model_available,
    load_approved_models,
    parse_approved_models,
    selectable_models,
)
from ai.cloud import (
    CLOUD_PROVIDERS,
    STATUS_CONSENT_REQUIRED,
    STATUS_PROVIDER_DISABLED,
    check_readiness,
    ensure_cloud_request_allowed,
    is_cloud_provider,
    provider_settings,
)
from ai.disclosure import (
    DISCLOSURE_VERSION,
    DisclosureNotAcknowledged,
    disclosure_text,
    is_acknowledged,
    read_acknowledgements,
    record_acknowledgement,
)
from ai.errors import AuthenticationError, ModelUnavailable
from ai.models import ProviderStatus
from ai.secrets import (
    ENV_VARS,
    KeySource,
    clear_session_keys,
    describe_key,
    resolve_api_key,
    secrets_path,
    set_session_key,
    store_api_key,
)

FAKE_GEMINI_KEY = "AIzaSyFAKEgeminikeyfortestsonly0000000001"
FAKE_GROQ_KEY = "gsk_FAKEgroqkeyfortestsonly00000000000000002"

# A minimal but realistic [ai] table: two approved Gemini records (one confirmed, one
# unknown), one Groq record, plus the [ai.gemini] / [ai.groq] subtables.
AI_TABLE = {
    "approved_models": [
        {
            "id": "gemini-3.5-flash",
            "provider": "gemini",
            "status": "stable",
            "context_limit": 1048576,
            "output_limit": 65536,
            "reviewed_on": "2026-07-24",
            "source_url": "https://ai.google.dev/",
            "free_tier_confidence": "confirmed",
            "pilot_status": "not-piloted",
        },
        {
            "id": "gemini-9.9-mystery",
            "provider": "gemini",
            "status": "stable",
            "context_limit": 1048576,
            "output_limit": 65536,
            "reviewed_on": "2026-07-24",
            "source_url": "https://ai.google.dev/",
            "free_tier_confidence": "unknown",
            "pilot_status": "not-piloted",
        },
        {
            "id": "llama-3.3-70b-versatile",
            "provider": "groq",
            "status": "stable",
            "context_limit": 131072,
            "output_limit": 32768,
            "reviewed_on": "2026-07-24",
            "source_url": "https://console.groq.com/docs/models",
            "free_tier_confidence": "confirmed",
            "pilot_status": "not-piloted",
        },
    ],
    "gemini": {"enabled": True, "model": "gemini-3.5-flash"},
    "groq": {"enabled": True, "model": "llama-3.3-70b-versatile"},
}


@pytest.fixture(autouse=True)
def _clean_secret_state():
    """No secret or session key may survive a test into the next one."""
    redaction.forget_secrets()
    clear_session_keys()
    yield
    redaction.forget_secrets()
    clear_session_keys()


@pytest.fixture
def paths(tmp_path):
    """Explicit, hermetic locations for every file the key/consent layer may touch."""
    return {
        "secrets_file": tmp_path / "secrets.json",
        "settings_file": tmp_path / "settings.json",
        "dotenv_path": tmp_path / ".env",
    }


def _key_paths(paths):
    """Only the locations the key layer reads — the consent file is not one of them."""
    return {"secrets_file": paths["secrets_file"], "dotenv_path": paths["dotenv_path"]}


# ---------------------------------------------------------------------------
# 1. Key precedence — present in each slot, and absent
# ---------------------------------------------------------------------------
def test_key_found_in_environment(paths):
    key, source = resolve_api_key(
        "gemini", environ={ENV_VARS["gemini"]: FAKE_GEMINI_KEY}, **_key_paths(paths)
    )
    assert key == FAKE_GEMINI_KEY
    assert source is KeySource.ENVIRONMENT


def test_key_found_in_per_user_secrets_file(paths):
    store_api_key("groq", FAKE_GROQ_KEY, path=paths["secrets_file"])
    key, source = resolve_api_key("groq", environ={}, **_key_paths(paths))
    assert key == FAKE_GROQ_KEY
    assert source is KeySource.SECRETS_FILE


def test_key_found_in_session_memory_only(paths):
    set_session_key("gemini", FAKE_GEMINI_KEY)
    key, source = resolve_api_key("gemini", environ={}, **_key_paths(paths))
    assert key == FAKE_GEMINI_KEY
    assert source is KeySource.SESSION
    # A session key is memory-only: nothing was written anywhere.
    assert not paths["secrets_file"].exists()
    clear_session_keys()
    assert resolve_api_key("gemini", environ={}, **_key_paths(paths))[0] is None


def test_key_found_in_developer_dotenv_override(paths):
    paths["dotenv_path"].write_text(
        f"# developer override\nGEMINI_API_KEY='{FAKE_GEMINI_KEY}'\n", encoding="utf-8"
    )
    key, source = resolve_api_key("gemini", environ={}, **_key_paths(paths))
    assert key == FAKE_GEMINI_KEY
    assert source is KeySource.DEV_DOTENV


def test_key_absent_everywhere(paths):
    key, source = resolve_api_key("gemini", environ={}, **_key_paths(paths))
    assert key is None
    assert source is KeySource.NONE


def test_precedence_order_is_env_then_file_then_session_then_dotenv(paths):
    store_api_key("gemini", "AIzaFILEkey00000000000000000000000000001", path=paths["secrets_file"])
    set_session_key("gemini", "AIzaSESSIONkey000000000000000000000000001")
    paths["dotenv_path"].write_text(
        "GEMINI_API_KEY=AIzaDOTENVkey0000000000000000000000000001\n", encoding="utf-8"
    )

    env = {ENV_VARS["gemini"]: FAKE_GEMINI_KEY}
    assert resolve_api_key("gemini", environ=env, **_key_paths(paths))[1] is KeySource.ENVIRONMENT
    assert resolve_api_key("gemini", environ={}, **_key_paths(paths))[1] is KeySource.SECRETS_FILE
    paths["secrets_file"].unlink()
    assert resolve_api_key("gemini", environ={}, **_key_paths(paths))[1] is KeySource.SESSION
    clear_session_keys()
    assert resolve_api_key("gemini", environ={}, **_key_paths(paths))[1] is KeySource.DEV_DOTENV


def test_dotenv_is_never_written_and_never_mutates_the_process_environment(paths):
    paths["dotenv_path"].write_text(f"GROQ_API_KEY={FAKE_GROQ_KEY}\n", encoding="utf-8")
    before = dict(os.environ)
    resolve_api_key("groq", environ={}, **_key_paths(paths))
    assert dict(os.environ) == before
    # The store path refuses to touch the developer override.
    store_api_key("groq", FAKE_GROQ_KEY, path=paths["secrets_file"])
    assert paths["dotenv_path"].read_text(encoding="utf-8").strip().endswith(FAKE_GROQ_KEY)


def test_secrets_file_is_written_atomically_and_permission_restricted(paths):
    store_api_key("gemini", FAKE_GEMINI_KEY, path=paths["secrets_file"])
    store_api_key("groq", FAKE_GROQ_KEY, path=paths["secrets_file"])
    document = json.loads(paths["secrets_file"].read_text(encoding="utf-8"))
    assert set(document["keys"]) == {"gemini", "groq"}
    # No temp file survived the atomic replace.
    assert list(paths["secrets_file"].parent.glob("*.tmp")) == []
    if sys.platform != "win32":
        mode = stat.S_IMODE(paths["secrets_file"].stat().st_mode)
        assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0


def test_secrets_path_uses_the_2a_per_user_runtime_directory():
    win = secrets_path(platform="win32", environ={"LOCALAPPDATA": r"C:\Users\T\AppData\Local"})
    assert str(win).endswith(r"WebNovelEditor\secrets.json")
    with pytest.raises(OSError):
        secrets_path(platform="linux")


def test_unusable_secret_values_are_ignored_not_half_accepted(paths):
    for junk in ("", "   ", "xx"):
        assert resolve_api_key(
            "gemini", environ={ENV_VARS["gemini"]: junk}, **_key_paths(paths)
        ) == (None, KeySource.NONE)


# ---------------------------------------------------------------------------
# 2. Presence-only reporting — a key value must never be surfaced
# ---------------------------------------------------------------------------
def test_presence_report_names_the_source_but_never_the_value(paths):
    found = describe_key("gemini", environ={ENV_VARS["gemini"]: FAKE_GEMINI_KEY}, **_key_paths(paths))
    assert found.found is True
    assert found.source == KeySource.ENVIRONMENT.value
    assert ENV_VARS["gemini"] in found.message
    blob = repr(found) + str(found) + json.dumps(found.as_dict())
    assert FAKE_GEMINI_KEY not in blob
    assert not any(FAKE_GEMINI_KEY in str(v) for v in vars(found).values())


def test_presence_report_explains_absence_in_plain_english(paths):
    missing = describe_key("groq", environ={}, **_key_paths(paths))
    assert missing.found is False
    assert missing.source == KeySource.NONE.value
    assert ENV_VARS["groq"] in missing.message
    assert "no api key" in missing.message.lower()


def test_gui_key_presence_helper_is_presence_only(paths):
    from gui import ai_settings

    message, level = ai_settings.describe_key_presence(
        "gemini", environ={ENV_VARS["gemini"]: FAKE_GEMINI_KEY}, **_key_paths(paths)
    )
    assert FAKE_GEMINI_KEY not in message
    assert level in {"success", "warn", "error", "muted", "info"}


# ---------------------------------------------------------------------------
# 3. Redaction — the single boundary
# ---------------------------------------------------------------------------
def test_registered_key_is_redacted_from_plain_text():
    redaction.register_secret(FAKE_GEMINI_KEY)
    out = redaction.redact(f"calling gemini with key={FAKE_GEMINI_KEY} now")
    assert FAKE_GEMINI_KEY not in out
    assert redaction.REDACTED in out


def test_resolving_a_key_registers_it_with_the_redactor(paths):
    resolve_api_key("groq", environ={ENV_VARS["groq"]: FAKE_GROQ_KEY}, **_key_paths(paths))
    assert FAKE_GROQ_KEY not in redaction.redact(f"authorization: Bearer {FAKE_GROQ_KEY}")


def test_unregistered_keys_are_still_caught_by_shape():
    """Defence in depth: a key that never went through resolve_api_key is still masked."""
    assert FAKE_GEMINI_KEY not in redaction.redact(f"x-goog-api-key: {FAKE_GEMINI_KEY}")
    assert FAKE_GROQ_KEY not in redaction.redact(f"Authorization: Bearer {FAKE_GROQ_KEY}")
    assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in redaction.redact(
        "token sk-abcdefghijklmnopqrstuvwxyz012345"
    )


def test_redaction_covers_serialized_structures_manifests_and_argv():
    redaction.register_secret(FAKE_GROQ_KEY)
    payload = {
        "provider": "groq",
        "headers": {"Authorization": f"Bearer {FAKE_GROQ_KEY}"},
        "manifest": [{"api_key": FAKE_GROQ_KEY}, ("nested", FAKE_GROQ_KEY)],
    }
    serialized = json.dumps(redaction.redact_obj(payload))
    assert FAKE_GROQ_KEY not in serialized
    assert "groq" in serialized  # non-secret content survives untouched

    argv = redaction.redact_argv(["prog", "--api-key", FAKE_GROQ_KEY, "--verbose"])
    assert FAKE_GROQ_KEY not in " ".join(argv)
    assert argv[0] == "prog" and argv[-1] == "--verbose"


def test_redaction_covers_exception_messages_and_tracebacks():
    redaction.register_secret(FAKE_GEMINI_KEY)
    try:
        raise RuntimeError(f"401 unauthorized for key {FAKE_GEMINI_KEY}")
    except RuntimeError as exc:
        assert FAKE_GEMINI_KEY not in redaction.redact_exception(exc)
        assert FAKE_GEMINI_KEY not in redaction.redact_traceback(exc)


def test_logging_filter_redacts_message_and_args(caplog):
    import logging

    redaction.register_secret(FAKE_GEMINI_KEY)
    logger = logging.getLogger("webnovel.test.redaction")
    logger.addFilter(redaction.RedactingFilter())
    with caplog.at_level(logging.INFO, logger="webnovel.test.redaction"):
        logger.info("key is %s", FAKE_GEMINI_KEY)
        logger.info("inline %s", f"key={FAKE_GEMINI_KEY}")
    assert FAKE_GEMINI_KEY not in caplog.text


def test_gui_log_sink_routes_through_the_redactor():
    """The one GUI log entry point must not be bypassable."""
    import inspect

    from gui import app as gui_app

    source = inspect.getsource(gui_app.WebnovelEditorApp._log)
    assert "redact(" in source, "gui _log must route every message through the redactor"


def test_secret_registry_never_exposes_its_contents():
    redaction.register_secret(FAKE_GEMINI_KEY)
    assert redaction.registered_secret_count() == 1
    module_blob = repr(sorted(vars(redaction).items()))
    assert FAKE_GEMINI_KEY not in redaction.redact(module_blob)


# ---------------------------------------------------------------------------
# 4. Approved-model records — loading
# ---------------------------------------------------------------------------
def test_approved_records_load_from_the_committed_config():
    from pathlib import Path

    from ai.config import load_config

    root = Path(__file__).resolve().parents[2]
    models = load_approved_models(load_config(root / "config.toml"))
    assert len(models) >= 9
    assert all(isinstance(m, ApprovedModel) for m in models)
    assert {m.provider for m in models} == {"gemini", "groq"}
    assert all(m.reviewed_on and m.source_url for m in models)
    assert all("latest" not in m.id.lower() for m in models)
    assert all(m.status == "stable" for m in models)


def test_malformed_records_are_skipped_with_a_reason_not_crashed():
    models, problems = parse_approved_models(
        [
            {"id": "good-1", "provider": "groq", "status": "stable", "context_limit": 10,
             "output_limit": 5, "reviewed_on": "2026-07-24", "source_url": "u",
             "free_tier_confidence": "confirmed", "pilot_status": "not-piloted"},
            {"provider": "groq"},                       # no id
            {"id": "gemini-flash-latest", "provider": "gemini", "status": "stable",
             "context_limit": 1, "output_limit": 1, "reviewed_on": "2026-07-24",
             "source_url": "u", "free_tier_confidence": "confirmed",
             "pilot_status": "not-piloted"},           # moving alias
            "not-a-table",
        ]
    )
    assert [m.id for m in models] == ["good-1"]
    assert len(problems) == 3
    assert any("latest" in p for p in problems)


def test_selectable_models_hide_non_free_and_unknown_in_strict_mode():
    models = load_approved_models(AI_TABLE)
    strict = {m.id for m in selectable_models(models, "gemini", strict_free_only=True)}
    relaxed = {m.id for m in selectable_models(models, "gemini", strict_free_only=False)}
    assert strict == {"gemini-3.5-flash"}
    assert "gemini-9.9-mystery" in relaxed


# ---------------------------------------------------------------------------
# 5-7. Refusal rules — non-approved, unknown confidence, retired
# ---------------------------------------------------------------------------
def test_non_approved_model_is_refused():
    models = load_approved_models(AI_TABLE)
    with pytest.raises(ModelUnavailable) as caught:
        ensure_model_approved("gemini-3.5-pro", provider="gemini", models=models)
    assert caught.value.retryable is False
    assert "approved" in str(caught.value).lower()


def test_a_model_approved_for_another_provider_is_refused():
    models = load_approved_models(AI_TABLE)
    with pytest.raises(ModelUnavailable):
        ensure_model_approved("llama-3.3-70b-versatile", provider="gemini", models=models)


def test_latest_style_alias_is_refused_even_if_someone_edits_it_in():
    models = load_approved_models(AI_TABLE)
    with pytest.raises(ModelUnavailable) as caught:
        ensure_model_approved("gemini-flash-latest", provider="gemini", models=models)
    assert "alias" in str(caught.value).lower()


def test_unknown_free_tier_confidence_is_refused_in_strict_mode():
    models = load_approved_models(AI_TABLE)
    with pytest.raises(ModelUnavailable) as caught:
        ensure_model_approved("gemini-9.9-mystery", provider="gemini", models=models)
    assert "free" in str(caught.value).lower()
    # ...and allowed only when strict free-only mode is explicitly turned off.
    picked = ensure_model_approved(
        "gemini-9.9-mystery", provider="gemini", models=models, strict_free_only=False
    )
    assert picked.id == "gemini-9.9-mystery"


def test_empty_model_selection_is_refused_rather_than_defaulted():
    models = load_approved_models(AI_TABLE)
    with pytest.raises(ModelUnavailable):
        ensure_model_approved("", provider="gemini", models=models)


def test_retired_model_marks_the_provider_unavailable_and_never_substitutes():
    models = load_approved_models(AI_TABLE)
    configured = ensure_model_approved("gemini-3.5-flash", provider="gemini", models=models)
    # The provider's live list no longer contains it, but does contain another approved one.
    with pytest.raises(ModelUnavailable) as caught:
        ensure_model_available(configured, ["gemini-9.9-mystery", "gemini-2.5-flash"])
    message = str(caught.value)
    assert "retired" in message.lower()
    assert "gemini-9.9-mystery" not in message  # no substitute is suggested or chosen
    assert caught.value.retryable is False


def test_unverifiable_model_list_does_not_fake_a_retirement():
    models = load_approved_models(AI_TABLE)
    configured = ensure_model_approved("gemini-3.5-flash", provider="gemini", models=models)
    ensure_model_available(configured, [])  # empty list == "could not check", not "retired"


def test_no_fallback_or_substitution_helper_exists():
    import ai.approved_models as mod

    banned = {"pick_newest", "newest_model", "fallback_model", "any_available_model"}
    assert banned.isdisjoint(set(dir(mod)))


# ---------------------------------------------------------------------------
# 8. Disclosure and acknowledgement
# ---------------------------------------------------------------------------
def test_disclosure_text_is_honest_about_what_leaves_the_machine():
    text = disclosure_text("gemini").lower()
    assert "leave this computer" in text
    assert "billing" in text
    assert "script-only" in text or "local" in text


def test_acknowledgement_record_stores_only_the_version(paths):
    record_acknowledgement("gemini", settings_file=paths["settings_file"])
    document = json.loads(paths["settings_file"].read_text(encoding="utf-8"))
    section = document["ai"]["cloud_disclosure"]
    assert section == {"gemini": DISCLOSURE_VERSION}
    blob = json.dumps(document)
    for leak in ("user", "email", "name", "key", "chapter", "path"):
        assert leak not in blob.lower()


def test_acknowledging_one_provider_does_not_acknowledge_the_other(paths):
    record_acknowledgement("gemini", settings_file=paths["settings_file"])
    assert is_acknowledged("gemini", settings_file=paths["settings_file"]) is True
    assert is_acknowledged("groq", settings_file=paths["settings_file"]) is False


def test_a_bumped_disclosure_version_invalidates_an_old_acknowledgement(paths):
    record_acknowledgement("groq", settings_file=paths["settings_file"], version="0")
    assert read_acknowledgements(settings_file=paths["settings_file"]) == {"groq": "0"}
    assert is_acknowledged("groq", settings_file=paths["settings_file"]) is False


def test_acknowledgement_merges_into_existing_settings_without_loss(paths):
    paths["settings_file"].write_text(
        json.dumps({"ai": {"model": "qwen3:14b", "policy": "prefer_ai"}}), encoding="utf-8"
    )
    record_acknowledgement("groq", settings_file=paths["settings_file"])
    document = json.loads(paths["settings_file"].read_text(encoding="utf-8"))
    assert document["ai"]["model"] == "qwen3:14b"
    assert document["ai"]["cloud_disclosure"] == {"groq": DISCLOSURE_VERSION}


# ---------------------------------------------------------------------------
# 9. The cloud gate — nothing may call out before every rail is satisfied
# ---------------------------------------------------------------------------
def _allow_kwargs(paths, **overrides):
    kwargs = {
        "ai_table": AI_TABLE,
        "environ": {ENV_VARS["gemini"]: FAKE_GEMINI_KEY, ENV_VARS["groq"]: FAKE_GROQ_KEY},
        **paths,
    }
    kwargs.update(overrides)
    return kwargs


def test_gate_blocks_until_the_disclosure_is_acknowledged(paths):
    with pytest.raises(DisclosureNotAcknowledged) as caught:
        ensure_cloud_request_allowed("gemini", **_allow_kwargs(paths))
    assert caught.value.retryable is False
    assert "acknowledg" in str(caught.value).lower()

    record_acknowledgement("gemini", settings_file=paths["settings_file"])
    approved = ensure_cloud_request_allowed("gemini", **_allow_kwargs(paths))
    assert approved.id == "gemini-3.5-flash"


def test_gate_blocks_when_no_key_is_available(paths):
    record_acknowledgement("gemini", settings_file=paths["settings_file"])
    with pytest.raises(AuthenticationError) as caught:
        ensure_cloud_request_allowed("gemini", **_allow_kwargs(paths, environ={}))
    assert FAKE_GEMINI_KEY not in str(caught.value)


def test_gate_blocks_a_non_approved_model_even_with_key_and_consent(paths):
    record_acknowledgement("gemini", settings_file=paths["settings_file"])
    table = dict(AI_TABLE, gemini={"enabled": True, "model": "gemini-3.5-pro"})
    with pytest.raises(ModelUnavailable):
        ensure_cloud_request_allowed("gemini", **_allow_kwargs(paths, ai_table=table))


def test_gate_blocks_a_disabled_provider(paths):
    record_acknowledgement("groq", settings_file=paths["settings_file"])
    table = dict(AI_TABLE, groq={"enabled": False, "model": "llama-3.3-70b-versatile"})
    with pytest.raises(Exception) as caught:
        ensure_cloud_request_allowed("groq", **_allow_kwargs(paths, ai_table=table))
    assert "not enabled" in str(caught.value).lower()


def test_gate_refuses_an_unknown_provider(paths):
    with pytest.raises(Exception):
        ensure_cloud_request_allowed("openai", **_allow_kwargs(paths))
    assert is_cloud_provider("gemini") and is_cloud_provider("groq")
    assert not is_cloud_provider("ollama")
    assert set(CLOUD_PROVIDERS) == {"gemini", "groq"}


# ---------------------------------------------------------------------------
# 10. Readiness reporting — greyed out with a plain-English reason, never a raise
# ---------------------------------------------------------------------------
def test_readiness_reports_missing_key_without_raising(paths):
    state = check_readiness("gemini", **_allow_kwargs(paths, environ={}))
    assert state.ready is False
    assert state.key_present is False
    assert state.status == ProviderStatus.AUTH_MISSING.value
    assert ENV_VARS["gemini"] in state.message
    assert FAKE_GEMINI_KEY not in state.message


def test_readiness_reports_consent_still_required(paths):
    state = check_readiness("gemini", **_allow_kwargs(paths))
    assert state.ready is False
    assert state.key_present is True
    assert state.status == STATUS_CONSENT_REQUIRED
    assert state.disclosure_acknowledged is False


def test_readiness_reports_a_disabled_provider(paths):
    table = dict(AI_TABLE, groq={"enabled": False, "model": "llama-3.3-70b-versatile"})
    state = check_readiness("groq", **_allow_kwargs(paths, ai_table=table))
    assert state.status == STATUS_PROVIDER_DISABLED
    assert state.ready is False


def test_readiness_is_ready_when_every_rail_is_satisfied(paths):
    record_acknowledgement("groq", settings_file=paths["settings_file"])
    state = check_readiness("groq", **_allow_kwargs(paths))
    assert state.ready is True
    assert state.status == ProviderStatus.OK.value
    assert state.model_id == "llama-3.3-70b-versatile"
    assert FAKE_GROQ_KEY not in json.dumps(state.as_dict())


def test_readiness_never_raises_on_a_broken_configuration(paths):
    for table in ({}, {"gemini": "not-a-table"}, {"approved_models": "junk"}):
        state = check_readiness("gemini", **_allow_kwargs(paths, ai_table=table))
        assert state.ready is False
        assert state.message


# ---------------------------------------------------------------------------
# 11. Committed configuration
# ---------------------------------------------------------------------------
def test_committed_config_has_secret_free_cloud_subtables():
    from pathlib import Path

    from ai.config import load_config

    root = Path(__file__).resolve().parents[2]
    ai_table = load_config(root / "config.toml")
    for name in CLOUD_PROVIDERS:
        settings = provider_settings(ai_table, name)
        assert settings["enabled"] is False, f"{name} must ship disabled"
        assert settings["model"] == "", f"{name} must ship with no pre-selected model"
        assert settings["strict_free_tier_only"] is True
        assert settings["billing_url"].startswith("https://")
        assert not any(
            k in settings for k in ("api_key", "key", "secret", "token")
        ), f"{name} subtable must be secret-free"


def test_cloud_settings_do_not_disturb_the_local_defaults():
    from pathlib import Path

    from ai.config import load_config, resolve_ai_config

    root = Path(__file__).resolve().parents[2]
    resolved = resolve_ai_config(config_defaults=load_config(root / "config.toml"))
    assert resolved["enabled"] is False
    assert resolved["provider"] == "ollama"
    assert resolved["model"] == "qwen3:14b"
    assert resolved["protection_strategy"] == "mask"


# ---------------------------------------------------------------------------
# 12. Offline guarantees
# ---------------------------------------------------------------------------
def test_phase1_modules_import_no_provider_sdk():
    for module in ("google", "google.genai", "google.generativeai", "groq", "ollama"):
        assert module not in sys.modules, f"{module} must not be imported by Phase 1"


def test_script_only_output_is_byte_identical_with_the_cloud_layer_present(paths):
    """AI off (and cloud fully unconfigured) must still be the deterministic result."""
    from ai.editor import AIEditor, EditorOptions
    from ai.models import RunPolicy
    from core.protected_lexicon import ProtectedLexicon
    from pipelines import shadow_slave

    lexicon = ProtectedLexicon()
    text = 'Chapter 1: Test.\n\n“He scored 6/7 today — Then he left.”'
    baseline = shadow_slave.run_pipeline(text, lexicon)

    # Everything the cloud layer can do, done — and none of it may change a byte.
    redaction.register_secret(FAKE_GEMINI_KEY)
    set_session_key("gemini", FAKE_GEMINI_KEY)
    record_acknowledgement("gemini", settings_file=paths["settings_file"])
    check_readiness("gemini", **_allow_kwargs(paths))

    assert shadow_slave.run_pipeline(text, lexicon) == baseline

    editor = AIEditor(
        lambda: pytest.fail("script-only must never construct a provider"),
        EditorOptions("", RunPolicy.SCRIPT_ONLY),
    )
    outcome = editor.edit(baseline)
    assert outcome.text == baseline
    assert outcome.used_ai is False
