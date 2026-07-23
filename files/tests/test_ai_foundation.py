from __future__ import annotations

import importlib
import json
import sys
from dataclasses import FrozenInstanceError

import pytest

from ai.config import IN_CODE_DEFAULTS, load_config, resolve_ai_config
from ai.errors import (
    AuthenticationError,
    ContextTooLong,
    DailyQuotaExhausted,
    InvalidResponse,
    ModelUnavailable,
    ProviderUnavailable,
    RateLimited,
    RequestCancelled,
    TransientNetworkError,
)
from ai.factory import create_provider, register_provider
from ai.models import CompletionRequest, CompletionResult, ProviderCapabilities, ProviderStatus
from ai.provider import AIProvider
from ai.settings import runtime_dir, settings_path, write_settings_atomic


class FakeProvider:
    def __init__(self, result_text: str = "unchanged"):
        self.result_text = result_text
        self.requests = []

    def capabilities(self):
        return ProviderCapabilities("fake", True, ("fake-1",), 4096, 2048)

    def health_check(self):
        return ProviderStatus.OK

    def list_models(self):
        return ["fake-1"]

    def complete(self, request):
        self.requests.append(request)
        return CompletionResult(self.result_text, request.model_id, 0.01, "stop", False)


def test_contracts_are_frozen_and_protocol_conforms():
    caps = ProviderCapabilities("fake", True, ("fake-1",), 4096, 2048)
    with pytest.raises(FrozenInstanceError):
        caps.provider_name = "changed"
    assert isinstance(FakeProvider(), AIProvider)
    assert ProviderStatus.AUTH_MISSING.value == "auth_missing"


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (ProviderUnavailable, True),
        (AuthenticationError, False),
        (ModelUnavailable, False),
        (ContextTooLong, False),
        (RateLimited, True),
        (DailyQuotaExhausted, False),
        (TransientNetworkError, True),
        (InvalidResponse, True),
        (RequestCancelled, False),
    ],
)
def test_error_retryability(error, retryable):
    assert error("test").retryable is retryable


def test_factory_registration_and_unknown_provider():
    register_provider("unit-fake", FakeProvider)
    assert isinstance(create_provider("UNIT-FAKE"), FakeProvider)
    with pytest.raises(ProviderUnavailable) as caught:
        create_provider("unknown")
    assert caught.value.retryable is False


def test_unimplemented_known_provider_is_unavailable():
    with pytest.raises(ProviderUnavailable):
        create_provider("ollama")


def test_configuration_precedence_and_toml(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[ai]\nenabled = false\nprovider = 'ollama'\ntimeout_seconds = 90\n")
    defaults = load_config(path)
    resolved = resolve_ai_config(
        config_defaults=defaults,
        user_settings={"enabled": True, "timeout_seconds": 60},
        gui_choices={"timeout_seconds": 30},
    )
    assert resolved["enabled"] is True
    assert resolved["provider"] == "ollama"
    assert resolved["timeout_seconds"] == 30
    assert IN_CODE_DEFAULTS["enabled"] is False


def test_per_user_paths():
    win = settings_path(
        platform="win32",
        environ={"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"},
    )
    mac = settings_path(platform="darwin", home=__import__("pathlib").Path("/Users/test"))
    assert str(win).endswith(r"WebNovelEditor\settings.json")
    assert mac == __import__("pathlib").Path(
        "/Users/test/Library/Application Support/WebNovelEditor/settings.json"
    )
    with pytest.raises(OSError):
        runtime_dir(platform="linux")


def test_atomic_settings_write_and_no_leftover(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    write_settings_atomic(path, {"ai": {"enabled": True}})
    assert json.loads(path.read_text()) == {"ai": {"enabled": True}}
    assert list(path.parent.glob("*.tmp")) == []


def test_import_has_no_filesystem_or_sdk_side_effects(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.iterdir())
    for key in [name for name in sys.modules if name == "ai" or name.startswith("ai.")]:
        sys.modules.pop(key)
    module = importlib.import_module("ai")
    assert module.ProviderStatus.OK.value == "ok"
    assert set(tmp_path.iterdir()) == before
    assert "ollama" not in sys.modules
    assert "google.generativeai" not in sys.modules
    assert "groq" not in sys.modules


def test_committed_config_is_disabled_and_secret_free():
    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    text = (root / "config.toml").read_text(encoding="utf-8")
    loaded = load_config(root / "config.toml")
    assert loaded["enabled"] is False
    assert not any(word in text.lower() for word in ("api_key", "secret", "password", "token ="))
