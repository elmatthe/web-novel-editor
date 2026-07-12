"""Phase 5 — dual-mode dispatch + rule-provenance proof (registry level).

Committed proof (per the Phase-5 plan) that goes beyond inspecting final text:

  * The Noble Queen and Supreme Magus — the two real profile-less corpora — resolve to
    the universal-only fallback, and they do so BECAUSE the registry says so:
    registration is the deciding factor, not an accident of index-file contents.
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
        ("The Noble Queen", "the-noble-queen.txt"),
        ("Supreme Magus", "supreme-magus.txt"),
    ],
)
def test_noble_queen_and_supreme_magus_resolve_to_universal_fallback(
    name: str, index_filename: str
) -> None:
    """The two user-added corpora dispatch to universal-only until Phase 5b registers them."""
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


def _make_bait_pdf(tmp_path: Path) -> str:
    pytest.importorskip("pdfplumber")
    reportlab = pytest.importorskip("reportlab")  # noqa: F841
    from pdf.builder import build_pdf

    src = tmp_path / "bait_input.pdf"
    build_pdf(_BAIT_TEXT, str(src))
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
    _, _, text, jsonl = _run(tmp_path, "The Noble Queen", "out_nq")
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

    _run(tmp_path, "The Noble Queen", "out_spy_nq")
    assert calls == []                 # universal-only run never touched SS fix code

    _run(tmp_path, "Shadow Slave", "out_spy_ss")
    assert len(calls) == 1             # sanity: the spy is live and SS mode does call it


# -- no __WE_ placeholder leaks in either mode --------------------------------------------

@pytest.mark.parametrize("novel_name", ["Shadow Slave", "The Noble Queen"])
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

    nq_summary, _, _, _ = _run(tmp_path, "The Noble Queen", "out_meta_nq")
    assert nq_summary["novel"] == "The Noble Queen"
    assert nq_summary["profile_applied"] is False


def test_jsonl_first_line_is_run_metadata_header_in_both_modes(tmp_path: Path) -> None:
    _, _, _, ss_jsonl = _run(tmp_path, "Shadow Slave", "out_hdr_ss")
    header = ss_jsonl[0]
    assert header["record"] == "run_metadata"
    assert header["novel"] == "Shadow Slave"
    assert header["mode"] == "novel-profile"
    assert header["pipeline"] == "pipelines.shadow_slave"
    # Replacement entries follow the header and are untouched by it.
    assert any(e.get("rule") == "special_fixes" for e in ss_jsonl[1:])

    _, _, _, nq_jsonl = _run(tmp_path, "The Noble Queen", "out_hdr_nq")
    header = nq_jsonl[0]
    assert header["record"] == "run_metadata"
    assert header["novel"] == "The Noble Queen"
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
