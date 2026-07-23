from __future__ import annotations

import json

import pytest

from ai.chunking import plan_chunks, safe_input_budget
from ai.editor import AIEditor, EditorOptions
from ai.errors import InvalidResponse, ModelUnavailable, ProviderUnavailable
from ai.models import CompletionResult, ProviderCapabilities, ProviderStatus, RunPolicy


class FakeProvider:
    def __init__(self, responses=(), *, error=None, context=5000, output=2000):
        self.responses = list(responses)
        self.error = error
        self.calls = []
        self._caps = ProviderCapabilities("fake", True, ("fake-1",), context, output)

    def capabilities(self):
        return self._caps

    def health_check(self):
        return ProviderStatus.OK

    def list_models(self):
        return ["fake-1"]

    def complete(self, request):
        self.calls.append(request)
        if self.error:
            error = self.error
            self.error = None
            raise error
        value = self.responses.pop(0) if self.responses else request.text
        if isinstance(value, Exception):
            raise value
        if isinstance(value, CompletionResult):
            return value
        return CompletionResult(value, "fake-1", 0.01, "stop", False)


def editor(provider, policy=RunPolicy.PREFER_AI):
    return AIEditor(lambda: provider, EditorOptions("fake-1", policy, request_overhead_tokens=0, safety_margin_tokens=0))


def test_fitting_input_is_one_chunk_and_heading_stays_outside_body():
    text = "Chapter 1: One.\n\nFirst paragraph.\n\nSecond paragraph."
    plan = plan_chunks(text, max_input_tokens=1000)
    assert len(plan.chunks) == 1
    assert "Chapter 1" not in plan.chunks[0].text
    assert plan.reassemble([plan.chunks[0].text]) == text


def test_greedy_paragraph_packing_and_exact_reassembly():
    text = "A" * 9 + "\n\n" + "B" * 9 + "\n\n\n" + "C" * 9
    plan = plan_chunks(text, max_input_tokens=10, estimator=len)
    assert [chunk.text for chunk in plan.chunks] == ["A" * 9, "B" * 9, "C" * 9]
    assert plan.reassemble([chunk.text for chunk in plan.chunks]) == text


@pytest.mark.parametrize("text", ["  lead\n\nbody  ", "\n\nlead\n\n\nbody\n\n", "one\r\n\r\ntwo\r\n\r\n"])
def test_whitespace_and_separator_forms_round_trip(text):
    plan = plan_chunks(text, max_input_tokens=20, estimator=len)
    assert plan.reassemble([chunk.text for chunk in plan.chunks]) == text


def test_single_over_limit_paragraph_uses_fallback_without_provider_call():
    provider = FakeProvider(context=20, output=10)
    outcome = editor(provider).edit("A" * 100)
    assert outcome.fallback_used and outcome.text == "A" * 100
    assert provider.calls == []


def test_safe_budget_reserves_prompt_overhead_output_and_margin():
    assert safe_input_budget(context_limit=4096, max_output_limit=2000, serialized_prompt_tokens=500, request_overhead_tokens=100, safety_margin_tokens=496) == 1500


def test_success_and_exact_validated_text_returned():
    baseline = "Chapter 1: Test.\n\nAfter the long journey, he walk home alone."
    provider = FakeProvider(["After the long journey, he walks home alone."])
    outcome = editor(provider).edit(baseline)
    assert outcome.used_ai
    assert outcome.text == "Chapter 1: Test.\n\nAfter the long journey, he walks home alone."
    assert outcome.chunk_count == 1


@pytest.mark.parametrize(
    "responses",
    [
        ["", ""],
        ["A rewritten unrelated story.", "Still unrelated."],
        [
            CompletionResult("text", "fake-1", 0.1, "length", True),
            CompletionResult("text", "fake-1", 0.1, "length", True),
        ],
    ],
)
def test_malformed_paraphrase_and_truncation_retry_then_fallback(responses):
    baseline = "A simple paragraph remains intact."
    outcome = editor(FakeProvider(responses)).edit(baseline)
    assert outcome.fallback_used and outcome.text == baseline and outcome.retry_count == 1


def test_one_retry_then_success():
    baseline = "After the long journey, he walk home alone."
    provider = FakeProvider(["", "After the long journey, he walks home alone."])
    outcome = editor(provider).edit(baseline)
    assert outcome.used_ai and outcome.retry_count == 1 and len(provider.calls) == 2


@pytest.mark.parametrize(
    "error",
    [
        InvalidResponse("bad"),
        ProviderUnavailable("down"),
        TimeoutError("timeout"),
        OSError("network"),
    ],
)
def test_retryable_or_transient_failures_fallback_after_bound(error):
    baseline = "Text stays."
    provider = FakeProvider([error, error])
    outcome = editor(provider).edit(baseline)
    assert outcome.fallback_used and outcome.text == baseline


def test_non_retryable_model_error_has_no_retry():
    baseline = "Text stays."
    provider = FakeProvider([ModelUnavailable("missing")])
    outcome = editor(provider).edit(baseline)
    assert outcome.fallback_used and len(provider.calls) == 1


def test_protected_term_rejection_discards_changes():
    baseline = "Sunny walks home."
    provider = FakeProvider(["Sunless walks home.", "Sunless walks home."])
    outcome = editor(provider).edit(baseline, protected_terms=("Sunny",))
    assert outcome.fallback_used and outcome.text == baseline


def test_middle_chunk_failure_stops_future_calls_and_discards_first_edit():
    baseline = "He walk home.\n\n" + ("B" * 80) + "\n\nFinal text."
    provider = FakeProvider(["He walks home.", "", ""])
    instance = AIEditor(lambda: provider, EditorOptions("fake-1", RunPolicy.PREFER_AI, request_overhead_tokens=0, safety_margin_tokens=0))
    # Force small capacity after prompt reservation while keeping each paragraph viable.
    provider._caps = ProviderCapabilities("fake", True, ("fake-1",), 1100, 200)
    outcome = instance.edit(baseline)
    assert outcome.fallback_used and outcome.text == baseline
    assert len(provider.calls) < outcome.chunk_count + 2


@pytest.mark.parametrize("failure_index", [0, 1, 2])
def test_first_middle_and_last_chunk_failure_are_chapter_atomic(monkeypatch, failure_index):
    baseline = "First paragraph.\n\nMiddle paragraph.\n\nFinal paragraph."
    from ai import editor as editor_module

    plan = plan_chunks(baseline, max_input_tokens=18, estimator=len)
    monkeypatch.setattr(editor_module, "plan_chunks", lambda *a, **k: plan)
    responses = []
    for index, chunk in enumerate(plan.chunks):
        if index == failure_index:
            responses.extend(["", ""])
            break
        responses.append(chunk.text)
    provider = FakeProvider(responses)
    outcome = editor(provider).edit(baseline)
    assert outcome.fallback_used and outcome.text == baseline
    assert len(provider.calls) == failure_index + 2


def test_whole_chapter_gate_catches_cross_chunk_reordering(monkeypatch):
    baseline = "First sentence.\n\nSecond sentence."
    provider = FakeProvider()
    instance = editor(provider)
    from ai import editor as editor_module

    original = editor_module.plan_chunks
    plan = original(baseline, max_input_tokens=16, estimator=len)
    monkeypatch.setattr(editor_module, "plan_chunks", lambda *a, **k: plan)
    provider.responses = ["Second sentence.", "First sentence."]
    real_validate = editor_module.validate_candidate
    validation_calls = 0

    def accept_chunks_then_validate_chapter(base, response, **kwargs):
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls <= 2:
            from ai.validation import ValidationResult

            return ValidationResult(True, (), response)
        return real_validate(base, response, **kwargs)

    monkeypatch.setattr(editor_module, "validate_candidate", accept_chunks_then_validate_chapter)
    outcome = instance.edit(baseline)
    assert outcome.fallback_used and outcome.text == baseline


def test_script_only_never_constructs_provider():
    calls = []
    instance = AIEditor(lambda: calls.append(True), EditorOptions("fake-1", RunPolicy.SCRIPT_ONLY))
    outcome = instance.edit("unchanged")
    assert outcome.status == "script_only" and not calls


def test_ai_required_raises_when_unavailable():
    instance = AIEditor(None, EditorOptions("fake-1", RunPolicy.AI_REQUIRED))
    with pytest.raises(ProviderUnavailable):
        instance.edit("text")


def test_provenance_never_contains_full_chapter():
    baseline = "He walk home."
    outcome = editor(FakeProvider(["He walks home."])).edit(baseline)
    serialized = json.dumps(outcome.provenance)
    assert baseline not in serialized
