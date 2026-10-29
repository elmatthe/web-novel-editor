"""Phase 5 — dual-mode dispatch + rule-provenance proof (registry level).

Committed proof (per the Phase-5 plan) that goes beyond inspecting final text:

  * The intentionally-unauthored placeholder novels resolve to the universal-only
    fallback, and they do so BECAUSE the registry says so: registration is the deciding
    factor, not an accident of index-file contents. (Originally proven with The Noble
    Queen / Supreme Magus; Phase 5b registered those two real profiles, so the fallback
    proof now uses Reverend Insanity. Renegade Immortal filled this role until 2026-07-26,
    when it was registered to carry its own Ligou/Ligo -> Liguo substitution; Reverend
    Insanity remains unregistered and is now the profile-less fixture.)
  * A bait string matching an `SS_SPECIAL_FIXES` entry is changed in Shadow Slave mode
    and left untouched in a profile-less run, exercised through the full `run_batch`
    seam (not just the pipeline function).
  * Shadow-Slave-specific special-fix code is never *called* in a universal-only run —
    spy-level proof, not inference from absence of evidence.
  * No `__WE_` placeholder leaks into output text, GUI log lines, or the JSONL
    replacement log in either mode.
  * Run-level dispatch metadata (which novel, which mode/pipeline) is recorded in both
    modes: in the `run_batch` summary dict and as a `run_metadata` header line in the
    JSONL replacement log.

Tests that need a synthesized input PDF skip cleanly when pdfplumber/reportlab are
unavailable. No corpus files are required — everything here is corpus-free.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import novel_registry
from core.novel_registry import NovelDispatch, resolve_dispatch
from core.replacement_log import ReplacementLog
from pipelines import lord_of_mysteries, shadow_slave

# -- dispatch: the two real profile-less corpora + registry-is-the-decider ---------------

@pytest.mark.parametrize(
    "name, index_filename",
    [
        ("Reverend Insanity", "reverend-insanity.txt"),
        ("Circle of Inevitability", "circle-of-inevitability.txt"),
        ("Re Monster", "re-monster.txt"),
    ],
)
def test_unauthored_placeholder_novels_resolve_to_universal_fallback(
    name: str, index_filename: str
) -> None:
    """The intentionally-unauthored placeholders dispatch to universal-only (their
    study-examples indexes are comment-only, so Phase 5b left them unregistered)."""
    d = resolve_dispatch(name)
    assert d.has_profile is False
    assert d.run_pipeline is lord_of_mysteries.run_pipeline
    assert d.canonical_names == frozenset()          # no other novel's floor leaks in
    assert d.index_filename == index_filename        # own (placeholder) index still honored


def test_registration_is_the_deciding_factor_not_index_contents(monkeypatch) -> None:
    """Fallback happens because the name is unregistered — not because its index is empty.

    Proven both directions: a novel with NO index file at all still falls back (so an
    empty index file is not what drives the fallback), and temporarily registering a
    novel whose shipped index IS an empty placeholder flips it to profile dispatch
    without any index change.
    """
    # No index file exists for this name anywhere -> still a clean universal fallback.
    no_index = resolve_dispatch("Zz Registry Probe Novel")
    assert no_index.has_profile is False
    assert no_index.run_pipeline is lord_of_mysteries.run_pipeline

    # "Re Monster" ships an empty placeholder index and is unregistered -> fallback.
    assert resolve_dispatch("Re Monster").has_profile is False

    # Register it (registry entry only — the index file stays the same empty placeholder)
    # and the SAME name now resolves to a profile: the registry decided, not the index.
    fake = NovelDispatch(
        display_name="Re Monster",
        run_pipeline=lord_of_mysteries.run_pipeline,
        canonical_names=frozenset({"Rou"}),
        index_filename="re-monster.txt",
        has_profile=True,
    )
    monkeypatch.setitem(novel_registry._REGISTRY, "re monster", fake)
    registered = resolve_dispatch("Re Monster")
    assert registered.has_profile is True
    assert registered is fake


# -- run_batch-level proof helpers --------------------------------------------------------

# Bait text: a chapter heading, an SS protected name, and TWO SS_SPECIAL_FIXES targets
# ("Almanach" -> "Almanac", "carcassess" -> "carcasses"). Padded past the extractor's
# 100-char low-confidence floor. Short synthetic fragments only — no corpus text.
_BAIT_TEXT = (
    "Chapter 1: The Registry Probe.\n\n"
    "Sunny looked at the Almanach on the shelf and counted the carcassess slowly. "
    "The room was quiet and nothing else in this plain paragraph needs any editing "
    "at all, which keeps the provenance signal unambiguous for this test.\n"
)


def _make_bait_pdf(tmp_path: Path, *, body: str | None = None,
                   name: str = "bait_input.pdf") -> str:
    """Build a one-chapter input PDF. Defaults to the provenance bait text."""
    pytest.importorskip("pdfplumber")
    reportlab = pytest.importorskip("reportlab")  # noqa: F841
    from pdf.builder import build_pdf

    text = _BAIT_TEXT if body is None else f"Chapter 1: The Probe.\n\n{body}"
    src = tmp_path / name
    build_pdf(text, str(src))
    return str(src)


def _run(tmp_path: Path, novel_name, out_name: str):
    """Run the bait PDF through the real run_batch; return (summary, logs, text, jsonl)."""
    from core.batch_runner import run_batch

    src = _make_bait_pdf(tmp_path)
    out_dir = tmp_path / out_name
    logs: list[str] = []
    summary = run_batch(
        [src],
        str(out_dir),
        novel_name=novel_name,
        write_replacement_log=True,
        write_debug_text=True,
        gui_log=lambda m, level="info": logs.append(m),
    )
    assert summary["succeeded"] == 1, f"bait run failed: {logs}"
    debug_txt = next(out_dir.glob("DEBUG_*.txt")).read_text(encoding="utf-8")
    jsonl_path = next(out_dir.glob("*_replacements.jsonl"))
    jsonl_lines = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return summary, logs, debug_txt, jsonl_lines


# -- bait-string provenance through run_batch ---------------------------------------------

def test_bait_string_changed_in_shadow_slave_mode_via_run_batch(tmp_path: Path) -> None:
    _, _, text, jsonl = _run(tmp_path, "Shadow Slave", "out_ss")
    assert "Almanach" not in text and "Almanac" in text
    assert "carcassess" not in text and "carcasses" in text
    assert "Sunny" in text  # protected name survived its own profile's masking
    fix_rules = [e for e in jsonl if e.get("rule") == "special_fixes"]
    assert {e["original"] for e in fix_rules} == {"Almanach", "carcassess"}


def test_bait_string_untouched_in_universal_mode_via_run_batch(tmp_path: Path) -> None:
    _, _, text, jsonl = _run(tmp_path, "Reverend Insanity", "out_ri")
    assert "Almanach" in text          # SS's forced fix did NOT run
    assert "carcassess" in text
    assert all(e.get("rule") != "special_fixes" for e in jsonl)


# -- spy-level proof: SS special-fix code is never CALLED in universal mode ---------------

def test_ss_special_fix_code_not_called_in_universal_mode(
    tmp_path: Path, monkeypatch
) -> None:
    """Prove provenance directly: the SS special-fix function is never invoked when a
    profile-less novel is selected (run_pipeline resolves `_apply_special_fixes` from its
    module globals at call time, so the spy is seen even through the registry's stored
    pipeline reference)."""
    calls: list[str] = []
    real = shadow_slave._apply_special_fixes

    def spy(text, repl_log):
        calls.append("called")
        return real(text, repl_log)

    monkeypatch.setattr(shadow_slave, "_apply_special_fixes", spy)

    _run(tmp_path, "Reverend Insanity", "out_spy_ri")
    assert calls == []                 # universal-only run never touched SS fix code

    _run(tmp_path, "Shadow Slave", "out_spy_ss")
    assert len(calls) == 1             # sanity: the spy is live and SS mode does call it


# -- no __WE_ placeholder leaks in either mode --------------------------------------------

@pytest.mark.parametrize("novel_name", ["Shadow Slave", "Reverend Insanity"])
def test_no_placeholder_leaks_in_output_logs_or_jsonl(tmp_path: Path, novel_name) -> None:
    _, logs, text, jsonl = _run(tmp_path, novel_name, "out_leak")
    assert "__WE_" not in text
    assert all("__WE_" not in line for line in logs)
    assert "__WE_" not in json.dumps(jsonl)


# -- run-level dispatch metadata (summary + JSONL run header) -----------------------------

def test_run_summary_records_dispatch_metadata(tmp_path: Path) -> None:
    ss_summary, _, _, _ = _run(tmp_path, "Shadow Slave", "out_meta_ss")
    assert ss_summary["novel"] == "Shadow Slave"
    assert ss_summary["profile_applied"] is True

    ri_summary, _, _, _ = _run(tmp_path, "Reverend Insanity", "out_meta_ri")
    assert ri_summary["novel"] == "Reverend Insanity"
    assert ri_summary["profile_applied"] is False


def test_jsonl_first_line_is_run_metadata_header_in_both_modes(tmp_path: Path) -> None:
    _, _, _, ss_jsonl = _run(tmp_path, "Shadow Slave", "out_hdr_ss")
    header = ss_jsonl[0]
    assert header["record"] == "run_metadata"
    assert header["novel"] == "Shadow Slave"
    assert header["mode"] == "novel-profile"
    assert header["pipeline"] == "pipelines.shadow_slave"
    # Replacement entries follow the header and are untouched by it.
    assert any(e.get("rule") == "special_fixes" for e in ss_jsonl[1:])

    _, _, _, ri_jsonl = _run(tmp_path, "Reverend Insanity", "out_hdr_ri")
    header = ri_jsonl[0]
    assert header["record"] == "run_metadata"
    assert header["novel"] == "Reverend Insanity"
    assert header["mode"] == "universal-only"
    assert header["pipeline"] == "pipelines.lord_of_mysteries"


def test_replacement_log_metadata_header_is_optional(tmp_path: Path) -> None:
    """Backward compatibility: no metadata -> no header line; len() counts entries only."""
    log = ReplacementLog()
    log.record("a", "b", "some_rule")
    path = tmp_path / "plain.jsonl"
    log.write_jsonl(str(path))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["rule"] == "some_rule"

    log.metadata = {"novel": "X", "mode": "universal-only"}
    assert len(log) == 1  # metadata never counts as an entry
    log.write_jsonl(str(path))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["record"] == "run_metadata"


# -- author-ruled normalizations land BEFORE the AI/gate ever see the text ----------------

class _CaptureProvider:
    """Records every request the AI stage is handed, and echoes it back unchanged."""

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.system_prompts: list[str] = []

    def capabilities(self):
        from ai.models import ProviderCapabilities

        return ProviderCapabilities("capture", True, ("fake-1",), 8000, 4096)

    def health_check(self):
        from ai.models import ProviderStatus

        return ProviderStatus.OK

    def list_models(self):
        return ["fake-1"]

    def complete(self, request):
        from ai.models import CompletionResult

        self.texts.append(request.text)
        self.system_prompts.append(request.system_prompt)
        return CompletionResult(request.text, "fake-1", 0.01, "stop", False)


@pytest.mark.parametrize(
    "novel_name, typo, canonical",
    [
        ("The Noble Queen", "Kraii", "Kraai"),
        ("Renegade Immortal", "Ligou", "Liguo"),
    ],
)
def test_normalization_reaches_the_ai_stage_already_canonical(
    tmp_path: Path, monkeypatch, novel_name: str, typo: str, canonical: str
) -> None:
    """The AI provider must never be shown the source typo.

    The substitution runs inside the scripted pipeline (Block B), and `run_batch` hands
    the pipeline's output to `AIEditor.edit`. So by the time any model or the validation
    gate sees the chapter, only the canonical spelling exists. Proven by capturing what
    the provider is actually sent rather than by inspecting the final file.
    """
    pytest.importorskip("pdfplumber")
    pytest.importorskip("reportlab")

    from ai.editor import AIEditor, EditorOptions
    from ai.models import RunPolicy
    from core.batch_runner import run_batch

    body = (
        f"King {typo} walked to the gate that evening and {typo}'s servant followed "
        "close behind him through the long and very quiet stone corridor beyond it.\n"
    )
    src = _make_bait_pdf(tmp_path, body=body, name=f"norm_{canonical}.pdf")

    provider = _CaptureProvider()
    editor = AIEditor(
        lambda: provider,
        EditorOptions("fake-1", RunPolicy.PREFER_AI,
                      request_overhead_tokens=0, safety_margin_tokens=0),
    )
    logs: list[str] = []
    summary = run_batch(
        [src],
        str(tmp_path / f"out_norm_{canonical}"),
        novel_name=novel_name,
        write_debug_text=True,
        gui_log=lambda m, level="info": logs.append(m),
        ai_editor=editor,
    )
    assert summary["succeeded"] == 1, f"run failed: {logs}"
    assert provider.texts, "the AI stage was never invoked"

    # What the model was actually sent.
    seen = "\n".join(provider.texts)
    assert typo not in seen, f"the AI stage was shown the source typo {typo!r}"

    # The canonical form reached the AI either literally or as a protected placeholder;
    # either way the typo is gone before any model or gate looks at the chapter.
    assert canonical in seen or "__WE_P_" in seen
