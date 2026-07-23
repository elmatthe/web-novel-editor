"""Phase 6A Ollama adapter tests. Every transport is an in-process fake."""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from ai.errors import (
    ContextTooLong,
    InvalidResponse,
    ModelUnavailable,
    ProviderUnavailable,
    TransientNetworkError,
)
from ai.factory import create_provider
from ai.models import CompletionRequest, ProviderStatus
from ai.providers.ollama import OllamaProvider

MODEL = "qwen-test:exact"
ENDPOINT = "http://127.0.0.1:11434"
SECRET = "FAKE_SECRET_DO_NOT_LEAK"


def request(
    text: str = "He walk home.",
    *,
    system: str = "Correct only certain grammar errors.",
    model: str = MODEL,
    maximum: int = 500,
) -> CompletionRequest:
    return CompletionRequest(
        text,
        system,
        "1.0",
        model,
        0.0,
        17,
        12.5,
        maximum,
        "request-test",
    )


class FakeClient:
    def __init__(self, *, models=(MODEL,), response=None, list_error=None, chat_error=None):
        self.models = models
        self.response = response or {
            "model": MODEL,
            "done": True,
            "done_reason": "stop",
            "total_duration": 2_000_000,
            "prompt_eval_count": 23,
            "eval_count": 7,
            "message": {"content": "He walks home.", "thinking": ""},
        }
        self.list_error = list_error
        self.chat_error = chat_error
        self.chat_calls = []
        self.list_calls = 0

    def list(self):
        self.list_calls += 1
        if self.list_error:
            raise self.list_error
        return {"models": [{"model": name} for name in self.models]}

    def chat(self, **kwargs):
        self.chat_calls.append(kwargs)
        if self.chat_error:
            raise self.chat_error
        return self.response


def provider(client=None, **kwargs):
    return OllamaProvider(model_id=MODEL, client=client or FakeClient(), **kwargs)


def test_factory_constructs_adapter_without_loading_sdk():
    loaded = []
    result = create_provider(
        "ollama",
        model_id=MODEL,
        sdk_loader=lambda: loaded.append(True),
    )
    # Foundation import-isolation tests deliberately reload the ``ai`` package;
    # assert the lazy factory result without depending on stale class identity.
    assert type(result).__name__ == "OllamaProvider"
    assert result.capabilities().provider_name == "ollama"
    assert loaded == []


def test_sdk_client_uses_exact_configured_local_endpoint():
    constructed = []

    class SDK:
        @staticmethod
        def Client(**kwargs):
            constructed.append(kwargs)
            return FakeClient()

    result = OllamaProvider(model_id=MODEL, endpoint=ENDPOINT, sdk_loader=lambda: SDK)
    assert result.health_check() is ProviderStatus.OK
    assert constructed == [{"host": ENDPOINT, "timeout": 120.0}]


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:11434",
        "http://192.168.1.5:11434",
        "http://example.com:11434",
        "http://user:pass@localhost:11434",
        "http://localhost:11434/api",
        "http://localhost",
        "not-a-url",
    ],
)
def test_unsafe_or_invalid_endpoint_is_rejected_without_client_use(endpoint):
    client = FakeClient()
    result = OllamaProvider(model_id=MODEL, endpoint=endpoint, client=client)
    assert result.health_check() is ProviderStatus.INVALID_CONFIGURATION
    with pytest.raises(ProviderUnavailable):
        result.complete(request())
    assert client.list_calls == 0 and client.chat_calls == []


@pytest.mark.parametrize("model", ["", "qwen-test"])
def test_complete_model_tag_is_required(model):
    result = OllamaProvider(model_id=model, client=FakeClient())
    assert result.health_check() is ProviderStatus.INVALID_CONFIGURATION


def test_health_ready_and_missing_model_are_distinct():
    assert provider(FakeClient()).health_check() is ProviderStatus.OK
    assert (
        provider(FakeClient(models=("other:exact",))).health_check()
        is ProviderStatus.MODEL_MISSING
    )


def test_package_unavailable_and_stopped_service_are_distinct():
    def missing():
        raise ImportError("no package")

    absent = OllamaProvider(model_id=MODEL, sdk_loader=missing)
    stopped = provider(FakeClient(list_error=ConnectionError(SECRET)))
    assert absent.health_check() is ProviderStatus.PACKAGE_UNAVAILABLE
    assert stopped.health_check() is ProviderStatus.SERVICE_DOWN


def test_health_timeout_and_unknown_provider_error_are_distinct():
    timeout = provider(FakeClient(list_error=TimeoutError(SECRET)))

    class BrokenProvider(OllamaProvider):
        def list_models(self):
            raise RuntimeError(SECRET)

    broken = BrokenProvider(model_id=MODEL, client=FakeClient())
    assert timeout.health_check() is ProviderStatus.TIMEOUT
    assert broken.health_check() is ProviderStatus.PROVIDER_ERROR


def test_list_models_preserves_exact_installed_tags():
    tags = ["qwen3:8b-q4_K_M", "qwen3:14b-q5_K_M"]
    assert provider(FakeClient(models=tags)).list_models() == tags


def test_complete_builds_full_deterministic_nonstreaming_request():
    client = FakeClient()
    result = provider(client, keep_alive="30m").complete(request())
    call = client.chat_calls[0]
    assert call["model"] == MODEL
    assert call["messages"] == [
        {"role": "system", "content": "Correct only certain grammar errors."},
        {"role": "user", "content": "He walk home."},
    ]
    assert call["stream"] is False and call["think"] is False
    assert call["keep_alive"] == "30m"
    assert call["options"]["temperature"] == 0.0
    assert call["options"]["seed"] == 17
    assert call["options"]["num_ctx"] > call["options"]["num_predict"] > 0
    assert call["options"]["num_predict"] != -1
    assert result.text == "He walks home."
    assert result.input_tokens == 23 and result.output_tokens == 7
    assert result.execution_backend is None


def test_computed_budgets_are_deterministic_bounded_and_request_specific():
    result = provider(FakeClient(), output_margin_tokens=9)
    short = result.request_budget(request("Short.", maximum=100))
    long = result.request_budget(request("Long words. " * 30, maximum=100))
    capped = result.request_budget(request("Long words. " * 30, maximum=7))
    assert short == result.request_budget(request("Short.", maximum=100))
    assert long.input_tokens > short.input_tokens
    assert long.output_tokens > short.output_tokens
    assert capped.output_tokens == 7
    assert long.num_ctx == (
        long.input_tokens + long.output_tokens + result.context_safety_margin_tokens
    )


def test_over_limit_fails_before_chat_call():
    client = FakeClient()
    result = provider(
        client,
        context_limit=100,
        request_overhead_tokens=0,
        context_safety_margin_tokens=0,
        output_margin_tokens=0,
    )
    with pytest.raises(ContextTooLong):
        result.complete(request("A" * 1000))
    assert client.chat_calls == []


@pytest.mark.parametrize("error_type", [TimeoutError])
def test_timeout_maps_to_typed_transient_error_without_payload(error_type):
    result = provider(FakeClient(chat_error=error_type(SECRET)))
    with pytest.raises(TransientNetworkError) as caught:
        result.complete(request())
    assert SECRET not in str(caught.value)


def test_generic_and_missing_model_errors_are_sanitized_and_typed():
    generic = provider(FakeClient(chat_error=RuntimeError(SECRET)))
    with pytest.raises(ProviderUnavailable) as caught:
        generic.complete(request())
    assert SECRET not in str(caught.value)

    class MissingError(RuntimeError):
        status_code = 404

    missing = provider(FakeClient(chat_error=MissingError(SECRET)))
    with pytest.raises(ModelUnavailable) as caught:
        missing.complete(request())
    assert SECRET not in str(caught.value)


@pytest.mark.parametrize(
    "response",
    [
        {"model": MODEL, "done": False, "done_reason": "", "message": {"content": "partial"}},
        {"model": MODEL, "done": True, "done_reason": "length", "message": {"content": "partial"}},
        {"model": MODEL, "done": True, "done_reason": "stop", "message": {"content": ""}},
    ],
)
def test_incomplete_truncated_or_empty_response_is_rejected(response):
    with pytest.raises(InvalidResponse):
        provider(FakeClient(response=response)).complete(request())


@pytest.mark.parametrize(
    "message",
    [
        {"content": "He walks home.", "thinking": "hidden reasoning"},
        {"content": "<think>reasoning</think>\nHe walks home.", "thinking": ""},
    ],
)
def test_reasoning_output_is_never_returned_as_candidate(message):
    response = {
        "model": MODEL,
        "done": True,
        "done_reason": "stop",
        "message": message,
    }
    with pytest.raises(InvalidResponse):
        provider(FakeClient(response=response)).complete(request())


def test_model_mismatch_fails_before_chat():
    client = FakeClient()
    with pytest.raises(ModelUnavailable):
        provider(client).complete(request(model="other:exact"))
    assert client.chat_calls == []


def test_concurrency_is_serialized_to_one_request():
    class CountingClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.active = 0
            self.maximum_active = 0
            self.guard = threading.Lock()

        def chat(self, **kwargs):
            with self.guard:
                self.active += 1
                self.maximum_active = max(self.maximum_active, self.active)
            time.sleep(0.03)
            with self.guard:
                self.active -= 1
            return self.response

    client = CountingClient()
    result = provider(client)
    errors = []

    def run():
        try:
            result.complete(request())
        except Exception as exc:  # pragma: no cover - assertion reports thread error
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert client.maximum_active == 1


def test_errors_never_include_prompt_chapter_lexicon_or_secret():
    raw = f"{SECRET} FULL CHAPTER protected lexicon"
    result = provider(FakeClient(chat_error=RuntimeError(raw)))
    with pytest.raises(ProviderUnavailable) as caught:
        result.complete(request(raw, system=raw))
    message = str(caught.value)
    assert SECRET not in message
    assert "FULL CHAPTER" not in message
    assert "protected lexicon" not in message


def test_release_shaped_script_only_startup_needs_no_ollama_or_dev_tree(tmp_path):
    root = Path(__file__).resolve().parents[2]
    universal = tmp_path / "release" / "scripts" / "Universal"
    shutil.copytree(root / "scripts" / "Universal", universal)
    # If ordinary startup ever imports the SDK, this shadow module makes it fail.
    (universal / "ollama.py").write_text(
        "raise ImportError('Ollama intentionally absent')\n", encoding="utf-8"
    )
    assert not (tmp_path / "release" / "files").exists()
    assert not (tmp_path / "release" / ".git").exists()
    completed = subprocess.run(
        [sys.executable, str(universal / "main.py"), "--check"],
        cwd=tmp_path / "release",
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Startup check passed." in completed.stdout


def test_ollama_name_is_confined_to_provider_factory_and_configuration_boundary():
    root = Path(__file__).resolve().parents[2]
    universal = root / "scripts" / "Universal"
    allowed = {
        universal / "ai" / "factory.py",
        universal / "ai" / "config.py",
        universal / "ai" / "providers" / "ollama.py",
    }
    offenders = []
    for path in universal.rglob("*.py"):
        if path in allowed:
            continue
        if "ollama" in path.read_text(encoding="utf-8").lower():
            offenders.append(path.relative_to(root).as_posix())
    assert offenders == []
