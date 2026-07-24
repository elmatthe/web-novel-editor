"""Plan 2a Phase 7 — the GUI AI controls.

Two layers are covered here:

* ``gui.ai_settings`` — the tkinter-free preference/probe/rate logic, exercised
  headlessly with fake providers (no Ollama, no network, no display); and
* the panel itself in ``gui.app``, exercised with the existing synchronous-fake-
  thread + run_batch-spy idiom from ``test_app.py`` (skipped when no display).

The panel must never construct a provider while the AI pass is off, and the
status line must report the provider's own ``ProviderStatus`` values rather than
a simplified GUI-invented subset.
"""

from __future__ import annotations

import json
import sys

import pytest

from ai.models import ProviderStatus
from gui import ai_settings


# ---------------------------------------------------------------------------
# Fakes — a provider stand-in with no SDK, no service, and no network.
# ---------------------------------------------------------------------------
class _FakeProvider:
    def __init__(self, status, models=(), *, model_id="", raises=None):
        self._status = status
        self._models = list(models)
        self.model_id = model_id
        self._raises = raises

    def health_check(self):
        if self._raises is not None:
            raise self._raises
        return self._status

    def list_models(self):
        return list(self._models)


def _factory(provider, seen=None):
    """Return a ``create`` callable matching probe_provider's injection point."""

    def create(prefs, model_id):
        if seen is not None:
            seen.append(model_id)
        provider.model_id = model_id
        return provider

    return create


# ---------------------------------------------------------------------------
# Preference resolution and persistence
# ---------------------------------------------------------------------------
def test_ai_always_starts_disabled_even_when_settings_persisted_enabled(tmp_path):
    """The opt-in switch is session-only: a persisted ``enabled`` never turns the
    AI pass back on at launch, while the user's other choices are remembered."""
    config = tmp_path / "config.toml"
    config.write_text("[ai]\nenabled = false\nprovider = 'ollama'\n", encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"ai": {"enabled": True, "model": "remembered:tag",
                           "policy": "ai_required"}}),
        encoding="utf-8",
    )

    prefs = ai_settings.load_ai_preferences(config_path=config, settings_file=settings)

    assert prefs["enabled"] is False
    assert prefs["model"] == "remembered:tag"
    assert prefs["policy"] == "ai_required"


def test_preferences_follow_config_then_settings_then_in_code_defaults(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        "[ai]\nenabled = false\nmodel = 'from-config:1'\ntimeout_seconds = 90\n",
        encoding="utf-8",
    )
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"ai": {"model": "from-settings:2"}}),
                        encoding="utf-8")

    prefs = ai_settings.load_ai_preferences(config_path=config, settings_file=settings)

    assert prefs["model"] == "from-settings:2"   # settings beat config
    assert prefs["timeout_seconds"] == 90        # config beats in-code default
    assert prefs["keep_alive"] == "30m"          # in-code default survives
    assert prefs["policy"] == ai_settings.DEFAULT_POLICY


def test_missing_config_and_settings_files_yield_safe_defaults(tmp_path):
    prefs = ai_settings.load_ai_preferences(
        config_path=tmp_path / "nope.toml", settings_file=tmp_path / "nope.json"
    )
    assert prefs["enabled"] is False
    assert prefs["model"] == ""
    assert prefs["policy"] == ai_settings.DEFAULT_POLICY


def test_save_persists_only_the_user_choices_and_merges_other_keys(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"window": {"x": 1}, "ai": {"model": "old:1", "unrelated": 7}}),
        encoding="utf-8",
    )

    assert ai_settings.save_ai_preferences(
        {"model": "new:2", "policy": "ai_required", "enabled": True,
         "endpoint": "http://127.0.0.1:11434"},
        settings_file=settings,
    ) is True

    written = json.loads(settings.read_text(encoding="utf-8"))
    assert written["ai"]["model"] == "new:2"
    assert written["ai"]["policy"] == "ai_required"
    assert written["window"] == {"x": 1}          # unrelated sections untouched
    assert written["ai"]["unrelated"] == 7        # unrelated ai keys untouched
    # Never persisted: the opt-in switch, and no endpoint/secret-shaped copy.
    assert "enabled" not in written["ai"]
    assert "endpoint" not in written["ai"]
    assert set(ai_settings.PERSISTED_KEYS) == {"model", "policy"}


def test_save_reports_failure_instead_of_raising_when_unwritable(tmp_path):
    blocked = tmp_path / "file.txt"
    blocked.write_text("not a directory", encoding="utf-8")
    # settings under a path whose parent is a regular file: mkdir must fail.
    assert ai_settings.save_ai_preferences(
        {"model": "x:1", "policy": "prefer_ai"},
        settings_file=blocked / "nested" / "settings.json",
    ) is False


def test_corrupt_settings_file_does_not_break_startup(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{ this is not json", encoding="utf-8")
    prefs = ai_settings.load_ai_preferences(
        config_path=tmp_path / "nope.toml", settings_file=settings
    )
    assert prefs["enabled"] is False
    assert prefs["model"] == ""


# ---------------------------------------------------------------------------
# Status reporting — every real provider state, honestly
# ---------------------------------------------------------------------------
def test_every_provider_status_has_its_own_message():
    """No provider state is collapsed into a generic 'unavailable' line."""
    messages = {}
    for status in ProviderStatus:
        text, level = ai_settings.describe_status(status.value, model="qwen3:8b")
        assert text.strip(), f"{status} has no message"
        assert level in {"success", "info", "muted", "warn", "error"}
        messages[status.value] = text
    assert len(set(messages.values())) == len(messages), "statuses share a message"


def test_gui_level_states_are_additive_not_substitutes():
    """The two GUI-only states describe situations the provider cannot express;
    they never stand in for a real ProviderStatus value."""
    assert ai_settings.STATUS_UNCHECKED not in {s.value for s in ProviderStatus}
    assert ai_settings.STATUS_NO_MODEL not in {s.value for s in ProviderStatus}
    for state in (ai_settings.STATUS_UNCHECKED, ai_settings.STATUS_NO_MODEL):
        text, level = ai_settings.describe_status(state)
        assert text.strip()
        assert level in {"success", "info", "muted", "warn", "error"}


def test_status_message_names_the_offending_model_tag():
    text, level = ai_settings.describe_status(
        ProviderStatus.MODEL_MISSING.value, model="qwen3:14b"
    )
    assert "qwen3:14b" in text
    assert level == "warn"


def test_ok_status_is_reported_as_ready():
    text, level = ai_settings.describe_status(ProviderStatus.OK.value, model="qwen3:8b")
    assert level == "success"
    assert "qwen3:8b" in text


# ---------------------------------------------------------------------------
# Probing — real health_check()/list_models(), never a GUI reimplementation
# ---------------------------------------------------------------------------
def test_probe_reports_ok_and_the_installed_tags():
    provider = _FakeProvider(ProviderStatus.OK, ["qwen3:14b", "qwen3:8b"])
    probe = ai_settings.probe_provider(
        {"provider": "ollama", "model": "qwen3:8b"}, create=_factory(provider)
    )
    assert probe.status == ProviderStatus.OK.value
    assert probe.models == ("qwen3:14b", "qwen3:8b")


def test_probe_passes_the_service_down_state_straight_through():
    provider = _FakeProvider(ProviderStatus.SERVICE_DOWN, ["never-read:1"])
    probe = ai_settings.probe_provider(
        {"provider": "ollama", "model": "qwen3:8b"}, create=_factory(provider)
    )
    assert probe.status == ProviderStatus.SERVICE_DOWN.value
    # An unreachable service cannot have produced a trustworthy model list.
    assert probe.models == ()


@pytest.mark.parametrize(
    "status",
    [
        ProviderStatus.PACKAGE_UNAVAILABLE,
        ProviderStatus.INVALID_CONFIGURATION,
        ProviderStatus.TIMEOUT,
        ProviderStatus.PROVIDER_ERROR,
    ],
)
def test_probe_preserves_each_failure_state_verbatim(status):
    probe = ai_settings.probe_provider(
        {"provider": "ollama", "model": "qwen3:8b"},
        create=_factory(_FakeProvider(status)),
    )
    assert probe.status == status.value


def test_probe_reports_model_missing_but_still_offers_the_real_tags():
    provider = _FakeProvider(ProviderStatus.MODEL_MISSING, ["qwen3:8b"])
    probe = ai_settings.probe_provider(
        {"provider": "ollama", "model": "not-installed:9"}, create=_factory(provider)
    )
    assert probe.status == ProviderStatus.MODEL_MISSING.value
    assert probe.models == ("qwen3:8b",)


def test_probe_without_a_chosen_model_lists_tags_and_blames_no_one():
    """With no model chosen the probe must still enumerate installed tags. It uses
    a placeholder tag, so the provider's literal 'model_missing' would blame the
    service for a choice the user has not made — report the GUI state instead."""
    seen: list[str] = []
    provider = _FakeProvider(ProviderStatus.MODEL_MISSING, ["qwen3:14b", "qwen3:8b"])
    probe = ai_settings.probe_provider(
        {"provider": "ollama", "model": ""}, create=_factory(provider, seen)
    )
    assert seen == [ai_settings.LISTING_PLACEHOLDER_TAG]
    assert ":" in ai_settings.LISTING_PLACEHOLDER_TAG  # a complete, valid-shaped tag
    assert probe.status == ai_settings.STATUS_NO_MODEL
    assert probe.models == ("qwen3:14b", "qwen3:8b")


def test_probe_survives_a_provider_that_cannot_be_constructed():
    def exploding_create(prefs, model_id):
        raise RuntimeError("no adapter in this build")

    probe = ai_settings.probe_provider(
        {"provider": "ollama", "model": "qwen3:8b"}, create=exploding_create
    )
    assert probe.status == ProviderStatus.PACKAGE_UNAVAILABLE.value
    assert probe.models == ()


def test_probe_survives_a_health_check_that_raises():
    provider = _FakeProvider(ProviderStatus.OK, raises=OSError("socket exploded"))
    probe = ai_settings.probe_provider(
        {"provider": "ollama", "model": "qwen3:8b"}, create=_factory(provider)
    )
    assert probe.status == ProviderStatus.PROVIDER_ERROR.value


def test_probe_survives_a_model_listing_that_raises():
    class _Listless(_FakeProvider):
        def list_models(self):
            raise OSError("listing exploded")

    probe = ai_settings.probe_provider(
        {"provider": "ollama", "model": "qwen3:8b"},
        create=_factory(_Listless(ProviderStatus.OK)),
    )
    assert probe.status == ProviderStatus.OK.value
    assert probe.models == ()


# ---------------------------------------------------------------------------
# Editor construction — nothing is built until the batch actually runs
# ---------------------------------------------------------------------------
def test_build_ai_editor_constructs_no_provider():
    from ai.models import ProviderRunState

    built: list[str] = []

    def create(prefs, model_id):
        built.append(model_id)
        return _FakeProvider(ProviderStatus.OK)

    editor = ai_settings.build_ai_editor(
        {"provider": "ollama", "model": "qwen3:8b", "policy": "prefer_ai",
         "protection_strategy": "mask", "timeout_seconds": 120, "seed": 0,
         "request_overhead_tokens": 128, "context_safety_margin_tokens": 256},
        create=create,
    )
    assert built == [], "constructing the editor must not construct a provider"
    assert editor.run_state is ProviderRunState.UNINITIALIZED


def test_build_ai_editor_maps_the_gui_choices_onto_editor_options():
    from ai.models import ProtectionStrategy, RunPolicy

    editor = ai_settings.build_ai_editor(
        {"provider": "ollama", "model": "qwen3:14b", "policy": "ai_required",
         "protection_strategy": "verify", "timeout_seconds": 45, "seed": 7,
         "request_overhead_tokens": 128, "context_safety_margin_tokens": 256},
        create=lambda prefs, model_id: _FakeProvider(ProviderStatus.OK),
    )
    assert editor.options.model_id == "qwen3:14b"
    assert editor.options.policy is RunPolicy.AI_REQUIRED
    assert editor.options.protection_strategy is ProtectionStrategy.VERIFY
    assert editor.options.timeout_seconds == 45.0


def test_unknown_policy_falls_back_to_the_safe_default():
    from ai.models import RunPolicy

    editor = ai_settings.build_ai_editor(
        {"provider": "ollama", "model": "x:1", "policy": "nonsense",
         "protection_strategy": "also-nonsense", "timeout_seconds": 120, "seed": 0,
         "request_overhead_tokens": 128, "context_safety_margin_tokens": 256},
        create=lambda prefs, model_id: _FakeProvider(ProviderStatus.OK),
    )
    assert editor.options.policy is RunPolicy.PREFER_AI


# ---------------------------------------------------------------------------
# Running average and ETA
# ---------------------------------------------------------------------------
def test_rate_is_unknown_before_the_first_chapter_completes():
    rate = ai_settings.compute_rate(0, 10, 4.0)
    assert rate.seconds_per_file is None
    assert rate.eta_seconds is None
    assert ai_settings.format_rate(rate) == ""


def test_rate_is_a_running_average_with_an_eta():
    rate = ai_settings.compute_rate(2, 10, 24.0)
    assert rate.seconds_per_file == pytest.approx(12.0)
    assert rate.eta_seconds == pytest.approx(96.0)
    text = ai_settings.format_rate(rate)
    assert "12.0 s/chapter" in text
    assert "1m 36s" in text


def test_rate_drops_the_eta_once_every_chapter_is_done():
    rate = ai_settings.compute_rate(4, 4, 40.0)
    assert rate.eta_seconds is None
    text = ai_settings.format_rate(rate)
    assert "10.0 s/chapter" in text
    assert "left" not in text


def test_rate_ignores_impossible_inputs():
    assert ai_settings.compute_rate(3, 2, 10.0).eta_seconds is None
    assert ai_settings.compute_rate(1, 5, 0.0).seconds_per_file is None
    assert ai_settings.compute_rate(1, 5, -3.0).seconds_per_file is None


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0.4, "0s"), (9.0, "9s"), (59.6, "1m 00s"), (96.0, "1m 36s"),
     (600.0, "10m 00s"), (3725.0, "1h 02m")],
)
def test_duration_formatting(seconds, expected):
    assert ai_settings.format_duration(seconds) == expected


# ---------------------------------------------------------------------------
# No recommended model is baked into the UI
# ---------------------------------------------------------------------------
def test_no_model_tag_is_hardcoded_in_the_gui():
    """Model choice is deferred to the Plan 2a pilot: the dropdown may only be
    filled from a live list_models(), never from a shipped 'recommended' tag."""
    from pathlib import Path

    gui_dir = Path(ai_settings.__file__).resolve().parent
    for name in ("ai_settings.py", "app.py"):
        source = (gui_dir / name).read_text(encoding="utf-8").lower()
        assert "qwen" not in source, f"{name} names a specific model"
        assert "llama3" not in source, f"{name} names a specific model"


# ---------------------------------------------------------------------------
# The panel itself
# ---------------------------------------------------------------------------
class _ImmediateThread:
    """Test double for threading.Thread: runs the target synchronously."""

    def __init__(self, target=None, daemon=None):
        self._target = target

    def start(self):
        self._target()


def _new_app(monkeypatch, tmp_path):
    """Construct the window with per-user settings redirected into tmp_path."""
    tk = pytest.importorskip("tkinter")
    from gui import app as appmod

    monkeypatch.setattr(
        appmod.ai_settings, "default_settings_file", lambda: tmp_path / "settings.json"
    )
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
    return calls


def test_panel_defaults_to_off_with_its_controls_disabled(monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        assert app.opt_ai_enabled.get() is False
        assert app.opt_ai_dry_run.get() is False
        for widget in (app.ai_model_combo, app.ai_check_button):
            assert "disabled" in widget.state()
        # Nothing has been asked of any provider yet.
        expected, _ = appmod.ai_settings.describe_status(
            appmod.ai_settings.STATUS_UNCHECKED)
        assert app.ai_status_var.get() == expected
    finally:
        app.destroy()


def test_constructing_the_window_never_imports_the_ollama_sdk(monkeypatch, tmp_path):
    """Core app startup must work on a machine with no Ollama and no AI packages."""
    _appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        assert "ollama" not in sys.modules
    finally:
        app.destroy()


def test_turning_the_pass_on_enables_the_controls_and_probes_once(
        monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        monkeypatch.setattr(appmod.threading, "Thread", _ImmediateThread)
        probes = []

        def fake_probe(prefs, **kwargs):
            probes.append(dict(prefs))
            return appmod.ai_settings.ProviderProbe(
                ProviderStatus.OK.value, ("installed-a:1", "installed-b:2"))

        monkeypatch.setattr(appmod.ai_settings, "probe_provider", fake_probe)

        app.opt_ai_enabled.set(True)
        app._on_ai_toggled()
        app.update()

        assert len(probes) == 1
        assert "disabled" not in app.ai_model_combo.state()
        assert "disabled" not in app.ai_check_button.state()
        # The dropdown is filled from the probe alone.
        assert list(app.ai_model_combo["values"]) == ["installed-a:1", "installed-b:2"]
    finally:
        app.destroy()


def test_turning_the_pass_off_disables_controls_and_clears_the_status(
        monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        monkeypatch.setattr(appmod.threading, "Thread", _ImmediateThread)
        monkeypatch.setattr(
            appmod.ai_settings, "probe_provider",
            lambda prefs, **kw: appmod.ai_settings.ProviderProbe(
                ProviderStatus.OK.value, ("installed-a:1",)),
        )
        app.opt_ai_enabled.set(True)
        app._on_ai_toggled()
        app.update()

        app.opt_ai_enabled.set(False)
        app._on_ai_toggled()
        app.update()

        assert "disabled" in app.ai_model_combo.state()
        expected, _ = appmod.ai_settings.describe_status(
            appmod.ai_settings.STATUS_UNCHECKED)
        assert app.ai_status_var.get() == expected
    finally:
        app.destroy()


def test_status_line_shows_the_real_provider_state(monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        app.ai_model_var.set("chosen:1")
        app._apply_probe(appmod.ai_settings.ProviderProbe(
            ProviderStatus.MODEL_MISSING.value, ("other:2",)))
        app.update_idletasks()

        expected, _ = appmod.ai_settings.describe_status(
            ProviderStatus.MODEL_MISSING.value, model="chosen:1")
        assert app.ai_status_var.get() == expected
        assert "chosen:1" in app.ai_status_var.get()
    finally:
        app.destroy()


def test_ai_off_start_passes_no_editor_at_all(monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"%PDF-stub")
        app.file_paths.append(str(pdf))
        app._refresh_file_list()
        app._start_batch()
        app.update()

        assert len(calls) == 1
        assert calls[0]["ai_editor"] is None
        assert calls[0]["use_ai_in_dry_run"] is False
    finally:
        app.destroy()


def test_ai_on_without_a_model_warns_and_refuses_to_start(monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
        warnings = []
        monkeypatch.setattr(appmod.messagebox, "showwarning",
                            lambda *a, **k: warnings.append(a))

        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"%PDF-stub")
        app.file_paths.append(str(pdf))
        app._refresh_file_list()
        app.opt_ai_enabled.set(True)
        app.ai_model_var.set("")
        app._start_batch()
        app.update_idletasks()

        assert calls == []
        assert warnings
        assert app._running is False
    finally:
        app.destroy()


def test_ai_on_start_passes_an_editor_carrying_the_chosen_model_and_policy(
        monkeypatch, tmp_path):
    from ai.models import RunPolicy

    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"%PDF-stub")
        app.file_paths.append(str(pdf))
        app._refresh_file_list()

        app.opt_ai_enabled.set(True)
        app.ai_model_var.set("chosen:1")
        app.ai_policy_var.set(RunPolicy.AI_REQUIRED.value)
        app._start_batch()
        app.update()

        assert len(calls) == 1
        editor = calls[0]["ai_editor"]
        assert editor is not None
        assert editor.options.model_id == "chosen:1"
        assert editor.options.policy is RunPolicy.AI_REQUIRED
    finally:
        app.destroy()


def test_dry_run_ai_opt_in_is_passed_through_only_when_ticked(monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        calls = _wire_batch_spy(appmod, monkeypatch, tmp_path)
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"%PDF-stub")
        app.file_paths.append(str(pdf))
        app._refresh_file_list()

        app.opt_ai_enabled.set(True)
        app.ai_model_var.set("chosen:1")
        app.opt_dry_run.set(True)
        app._start_batch()
        app.update()
        assert calls[0]["use_ai_in_dry_run"] is False

        app.opt_ai_dry_run.set(True)
        app._start_batch()
        app.update()
        assert calls[1]["use_ai_in_dry_run"] is True
    finally:
        app.destroy()


def test_model_and_policy_choices_persist_but_the_switch_does_not(
        monkeypatch, tmp_path):
    from ai.models import RunPolicy

    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        app.opt_ai_enabled.set(True)
        app.ai_model_var.set("chosen:1")
        app.ai_policy_var.set(RunPolicy.AI_REQUIRED.value)
        app._persist_ai_choices()

        written = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert written["ai"] == {"model": "chosen:1", "policy": "ai_required"}
    finally:
        app.destroy()

    # A fresh window remembers the choices but comes up with the pass switched off.
    _appmod2, app2 = _new_app(monkeypatch, tmp_path)
    try:
        assert app2.opt_ai_enabled.get() is False
        assert app2.ai_model_var.get() == "chosen:1"
        assert app2.ai_policy_var.get() == RunPolicy.AI_REQUIRED.value
    finally:
        app2.destroy()


def test_ai_controls_are_locked_while_a_batch_runs(monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        app.opt_ai_enabled.set(True)
        app._set_ai_controls_running(True)
        app.update_idletasks()
        assert "disabled" in app.ai_enable_check.state()
        assert "disabled" in app.ai_model_combo.state()

        app._set_ai_controls_running(False)
        app.update_idletasks()
        assert "disabled" not in app.ai_enable_check.state()
        assert "disabled" not in app.ai_model_combo.state()
    finally:
        app.destroy()


def test_every_fixed_row_fits_inside_the_minimum_window_height(monkeypatch, tmp_path):
    """The AI card must not push the Start button or the status strip off the bottom.

    Only the log row flexes; every other row keeps its requested height at any
    window size, so their total (plus padding) has to clear MIN_HEIGHT or the
    controls below them are simply not on screen.
    """
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        root = app.winfo_children()[0]
        log_frame = app.log_text.master
        fixed = 0
        for child in root.winfo_children():
            info = child.grid_info()
            pady = info.get("pady", 0)
            pady = sum(pady) if isinstance(pady, tuple) else int(pady)
            if child is log_frame:
                fixed += pady        # the log itself may shrink; its padding may not
            else:
                fixed += child.winfo_reqheight() + pady
        fixed += 2 * appmod.PAD_M     # the root frame's own padding

        assert fixed <= appmod.MIN_HEIGHT, (
            f"fixed rows need {fixed}px but the window can be as short as "
            f"{appmod.MIN_HEIGHT}px — the bottom controls would be clipped"
        )
    finally:
        app.destroy()


def test_progress_updates_publish_a_running_average_and_eta(monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        clock = {"now": 100.0}
        monkeypatch.setattr(appmod.time, "monotonic", lambda: clock["now"])

        app._begin_rate_tracking(4)
        clock["now"] = 124.0
        app._set_progress(2)
        app.update_idletasks()

        text = app.rate_var.get()
        assert "12.0 s/chapter" in text
        assert "24s" in text          # 2 chapters left at 12 s each
    finally:
        app.destroy()


def test_rate_readout_clears_between_runs(monkeypatch, tmp_path):
    appmod, app = _new_app(monkeypatch, tmp_path)
    try:
        clock = {"now": 0.0}
        monkeypatch.setattr(appmod.time, "monotonic", lambda: clock["now"])
        app._begin_rate_tracking(2)
        clock["now"] = 10.0
        app._set_progress(1)
        assert app.rate_var.get() != ""

        app._begin_rate_tracking(2)
        assert app.rate_var.get() == ""
    finally:
        app.destroy()
