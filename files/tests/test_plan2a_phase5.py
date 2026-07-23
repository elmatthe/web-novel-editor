"""Plan 2a Phase 5: provider-neutral batch seam, dry-run policy, and safe stop."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

import core.batch_runner as batch_runner
from ai.editor import AIEditor, EditorOptions
from ai.errors import ProviderUnavailable
from ai.models import (
    CompletionResult,
    ProviderCapabilities,
    ProviderStatus,
    RunPolicy,
)
from core.batch_runner import run_batch
from core.novel_registry import NovelDispatch

BASELINE = (
    "Chapter 1: Test.\n\n"
    "After the very long journey through the silent city, he walk home alone. "
    "The lamps remained bright while the quiet road stretched toward the distant gate."
)
CANDIDATE = (
    "Chapter 1: Test.\n\n"
    "After the very long journey through the silent city, he walks home alone. "
    "The lamps remained bright while the quiet road stretched toward the distant gate."
)


class FakeProvider:
    def __init__(self, *, transform=None, errors=()):
        self.transform = transform or (lambda text: text)
        self.errors = list(errors)
        self.capability_calls = 0
        self.complete_calls = 0

    def capabilities(self):
        self.capability_calls += 1
        return ProviderCapabilities("fake", True, ("fake-1",), 5000, 2000)

    def health_check(self):
        return ProviderStatus.OK

    def list_models(self):
        return ["fake-1"]

    def complete(self, request):
        self.complete_calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return CompletionResult(
            self.transform(request.text), "fake-1", 0.01, "stop", False
        )


def _editor(provider, policy=RunPolicy.PREFER_AI, factory_calls=None):
    calls = factory_calls if factory_calls is not None else []

    def factory():
        calls.append(1)
        return provider

    return AIEditor(
        factory,
        EditorOptions(
            "fake-1",
            policy,
            request_overhead_tokens=0,
            safety_margin_tokens=0,
        ),
    )


def _dispatch():
    return NovelDispatch(
        display_name="Universal",
        run_pipeline=lambda text, lexicon, **kwargs: text,
        canonical_names=frozenset(),
        index_filename="",
        has_profile=False,
    )


def _wire(monkeypatch, built):
    monkeypatch.setattr(batch_runner, "extract_text_from_pdf", lambda _path: BASELINE)
    monkeypatch.setattr(batch_runner, "resolve_dispatch", lambda _name: _dispatch())
    monkeypatch.setattr(
        batch_runner, "build_pdf", lambda text, path: built.append((text, path))
    )


def _inputs(tmp_path: Path, count=1):
    paths = []
    for index in range(count):
        path = tmp_path / f"{index}.pdf"
        path.write_bytes(b"%PDF-source")
        paths.append(str(path))
    return paths


def test_ai_disabled_preserves_exact_build_text_and_constructs_no_provider(
    tmp_path, monkeypatch
):
    built = []
    _wire(monkeypatch, built)
    factory_calls = []
    unused = _editor(FakeProvider(), factory_calls=factory_calls)

    summary = run_batch(_inputs(tmp_path), str(tmp_path / "out"))

    assert summary["succeeded"] == 1
    assert built[0][0] == BASELINE
    assert factory_calls == []
    assert unused.run_state.value == "uninitialized"


def test_prefer_ai_accepted_text_reaches_build_pdf_exactly(tmp_path, monkeypatch):
    built = []
    _wire(monkeypatch, built)
    provider = FakeProvider(
        transform=lambda text: text.replace("he walk home", "he walks home")
    )

    run_batch(
        _inputs(tmp_path), str(tmp_path / "out"), ai_editor=_editor(provider)
    )

    assert built[0][0] == CANDIDATE
    assert provider.capability_calls == 1 and provider.complete_calls == 1


def test_rejected_result_builds_complete_script_fallback(tmp_path, monkeypatch):
    built = []
    _wire(monkeypatch, built)
    provider = FakeProvider(transform=lambda _text: "A rewritten story.")

    summary = run_batch(
        _inputs(tmp_path), str(tmp_path / "out"), ai_editor=_editor(provider)
    )

    assert summary["succeeded"] == 1 and built[0][0] == BASELINE


def test_ai_required_preflight_aborts_before_processing(tmp_path, monkeypatch):
    built = []
    _wire(monkeypatch, built)
    extraction_calls = []
    monkeypatch.setattr(
        batch_runner,
        "extract_text_from_pdf",
        lambda path: extraction_calls.append(path) or BASELINE,
    )

    def unavailable():
        raise ProviderUnavailable("offline", retryable=False)

    editor = AIEditor(
        unavailable, EditorOptions("fake-1", RunPolicy.AI_REQUIRED)
    )
    with pytest.raises(ProviderUnavailable):
        run_batch(_inputs(tmp_path), str(tmp_path / "out"), ai_editor=editor)
    assert extraction_calls == [] and built == []


def test_ai_required_mid_run_outage_never_builds_fallback(tmp_path, monkeypatch):
    built = []
    _wire(monkeypatch, built)
    provider = FakeProvider(
        errors=[
            ProviderUnavailable("down"),
            ProviderUnavailable("down"),
        ]
    )
    summary = run_batch(
        _inputs(tmp_path, 2),
        str(tmp_path / "out"),
        ai_editor=_editor(provider, policy=RunPolicy.AI_REQUIRED),
    )
    assert summary["succeeded"] == 0 and summary["failed"] == 2
    assert built == []


def test_outage_warns_once_and_later_files_do_not_call_provider(
    tmp_path, monkeypatch
):
    built = []
    _wire(monkeypatch, built)
    provider = FakeProvider(
        errors=[
            ProviderUnavailable("down"),
            ProviderUnavailable("down"),
        ]
    )
    logs = []
    summary = run_batch(
        _inputs(tmp_path, 3),
        str(tmp_path / "out"),
        ai_editor=_editor(provider),
        gui_log=lambda message, level="info": logs.append((level, message)),
    )

    assert summary["succeeded"] == 3
    assert [text for text, _ in built] == [BASELINE, BASELINE, BASELINE]
    assert provider.complete_calls == 2
    assert sum("AI provider unavailable" in message for _, message in logs) == 1


def test_default_dry_run_never_initializes_ai_and_writes_no_pdf(
    tmp_path, monkeypatch
):
    built = []
    _wire(monkeypatch, built)
    calls = []
    provider = FakeProvider()
    summary = run_batch(
        _inputs(tmp_path),
        str(tmp_path / "out"),
        dry_run=True,
        ai_editor=_editor(provider, factory_calls=calls),
    )
    assert summary["succeeded"] == 1 and calls == [] and built == []
    assert not (tmp_path / "out").exists()


def test_explicit_ai_dry_run_calls_provider_but_writes_no_pdf(
    tmp_path, monkeypatch
):
    built = []
    _wire(monkeypatch, built)
    provider = FakeProvider()
    summary = run_batch(
        _inputs(tmp_path),
        str(tmp_path / "out"),
        dry_run=True,
        use_ai_in_dry_run=True,
        ai_editor=_editor(provider),
    )
    assert summary["succeeded"] == 1 and provider.complete_calls == 1
    assert built == [] and not (tmp_path / "out").exists()


def test_default_dry_run_ai_required_still_does_not_preflight(
    tmp_path, monkeypatch
):
    built = []
    _wire(monkeypatch, built)
    factory_calls = []
    editor = AIEditor(
        lambda: factory_calls.append(1),
        EditorOptions("fake-1", RunPolicy.AI_REQUIRED),
    )
    summary = run_batch(
        _inputs(tmp_path),
        str(tmp_path / "out"),
        dry_run=True,
        ai_editor=editor,
    )
    assert summary["succeeded"] == 1 and factory_calls == [] and built == []


def test_stop_during_pdf_write_finishes_current_then_stops(tmp_path, monkeypatch):
    built = []
    stop = threading.Event()
    _wire(monkeypatch, built)

    def build(text, path):
        built.append((text, path))
        stop.set()

    monkeypatch.setattr(batch_runner, "build_pdf", build)
    summary = run_batch(
        _inputs(tmp_path, 3), str(tmp_path / "out"), stop_event=stop
    )
    assert len(built) == 1
    assert summary["succeeded"] == 1 and summary["stopped"] is True


def test_stop_already_requested_begins_no_file(tmp_path, monkeypatch):
    built = []
    _wire(monkeypatch, built)
    stop = threading.Event()
    stop.set()
    summary = run_batch(
        _inputs(tmp_path, 2), str(tmp_path / "out"), stop_event=stop
    )
    assert built == [] and summary["succeeded"] == 0 and summary["stopped"] is True


def test_pause_is_still_consulted_only_between_ai_files(tmp_path, monkeypatch):
    built = []
    _wire(monkeypatch, built)

    class Gate:
        def __init__(self):
            self.checks = 0
            self.waits = 0

        def is_set(self):
            self.checks += 1
            return False

        def wait(self):
            self.waits += 1

    gate = Gate()
    run_batch(
        _inputs(tmp_path, 2),
        str(tmp_path / "out"),
        pause_gate=gate,
        ai_editor=_editor(FakeProvider()),
    )
    assert gate.checks == 1 and gate.waits == 1 and len(built) == 2


def test_ai_jsonl_is_bounded_and_excludes_source_and_fake_secret(
    tmp_path, monkeypatch
):
    built = []
    _wire(monkeypatch, built)
    fake_secret = "NOT_A_REAL_SECRET_MUST_NEVER_APPEAR"
    provider = FakeProvider(
        transform=lambda text: text.replace("he walk home", "he walks home")
    )
    run_batch(
        _inputs(tmp_path),
        str(tmp_path / "out"),
        ai_editor=_editor(provider),
        write_replacement_log=True,
    )
    # The fake builder does not create a PDF, but run_batch still writes the sidecar.
    jsonl = next((tmp_path / "out").glob("*_replacements.jsonl"))
    payload = jsonl.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in payload.splitlines()]
    assert any(row.get("record") == "ai_provenance" for row in rows)
    assert BASELINE not in payload and fake_secret not in payload
    assert len(payload) < 10_000


def test_source_pdf_bytes_and_mtime_are_unchanged(tmp_path, monkeypatch):
    built = []
    _wire(monkeypatch, built)
    source = Path(_inputs(tmp_path)[0])
    before = (source.read_bytes(), source.stat().st_mtime_ns)
    run_batch(
        [str(source)], str(tmp_path / "out"), ai_editor=_editor(FakeProvider())
    )
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


def test_ai_enabled_still_isolates_pdf_build_failure(tmp_path, monkeypatch):
    built = []
    _wire(monkeypatch, built)

    def build(text, path):
        if Path(path).name == "1.pdf":
            raise OSError("locked")
        built.append((text, path))

    monkeypatch.setattr(batch_runner, "build_pdf", build)
    summary = run_batch(
        _inputs(tmp_path, 3),
        str(tmp_path / "out"),
        ai_editor=_editor(FakeProvider()),
    )
    assert summary["succeeded"] == 2 and summary["failed"] == 1
    assert [Path(path).name for _, path in built] == ["0.pdf", "2.pdf"]
