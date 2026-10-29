"""Phase 1 scaffold tests — verify package wiring imports and stubs behave.

These prove the structure is sound (every stage module resolves, the Stage 1.5
junk_strip is wired, profile data loads, no-op rule stubs pass text through). Real
behavioral tests per rule arrive with their implementations in Phase 4+.
"""

from __future__ import annotations

import importlib


def test_pipeline_wiring_imports():
    """The Shadow Slave pipeline (and thus every stage import) resolves cleanly."""
    mod = importlib.import_module("pipelines.shadow_slave")
    assert callable(mod.run_pipeline)


def test_junk_strip_stub_is_passthrough():
    """Stage 1.5 stub exists and is a safe no-op until Phase 4."""
    from rules import junk_strip

    sample = "He walked to novelbin.net and kept going."
    assert junk_strip.strip_junk(sample) == sample


def test_insurance_rules_preserve_clean_prose():
    """The conservative 'insurance' rules must never alter already-clean prose.

    (Phase 4 superseded the Phase-1 no-op stub check: the rules are now real, so the
    invariant worth guarding is that clean text passes through them untouched.)
    """
    from rules import grammar, ligature_cleanup, ocr_repair, punctuation, unicode_cleanup

    clean = "The warrior raised his sword and waited for the gate to open."
    assert ocr_repair.repair_ocr(clean) == clean
    assert punctuation.repair_punctuation(clean) == clean
    assert grammar.repair_grammar(clean) == clean
    assert ligature_cleanup.normalize_ligatures(clean) == clean
    assert unicode_cleanup.normalize_unicode(clean) == clean


def test_profile_data_loads():
    """Built-in canonical names and forced fixes are present and well-formed."""
    from profiles.shadow_slave.canonical_names import SS_CANONICAL_NAMES
    from profiles.shadow_slave.special_fixes import SS_SPECIAL_FIXES

    assert "Sunny" in SS_CANONICAL_NAMES
    assert "Nephis" in SS_CANONICAL_NAMES
    assert SS_SPECIAL_FIXES["Obers"] == "Obels"
    assert SS_SPECIAL_FIXES["Almanach"] == "Almanac"


def test_dataclass_shapes_exist():
    """Core dataclasses are importable with their Phase-1 shapes."""
    from core.protected_lexicon import ProtectedLexicon
    from core.replacement_log import ReplacementEntry, ReplacementLog

    lex = ProtectedLexicon()
    assert lex.terms == ()
    entry = ReplacementEntry(original="a", replacement="b", rule="r")
    assert entry.rule == "r"
    assert ReplacementLog().entries == []


# ---------------------------------------------------------------------------
# Version drift: config.toml vs CHANGELOG (added 2026-07-27)
# ---------------------------------------------------------------------------
# This had already happened. CHANGELOG.md and BRIEFING.md said v0.13.0 for an entire
# plan while config.toml still shipped "0.12.0". Nothing in the app consumed the
# mismatch, which is exactly why nobody noticed -- and config.toml is the file a
# release, a bug report and a support conversation all quote. `verify` now fails on it;
# this pins the same rule at the pytest layer so a bare `pytest` run catches it too.

def _repo_root():
    import pathlib as _p

    return _p.Path(__file__).resolve().parents[2]


def _changelog_top_version() -> str:
    import re

    text = (_repo_root() / "md-instructions" / "CHANGELOG.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        match = re.search(r"v?(\d+\.\d+(?:\.\d+)?)", line)
        if match and line.lstrip().startswith("#"):
            return match.group(1)
    raise AssertionError("no version heading found in CHANGELOG.md")


def _config_version() -> str:
    import tomllib

    data = tomllib.loads((_repo_root() / "config.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_config_toml_version_matches_the_changelog():
    assert _config_version() == _changelog_top_version()


def test_verify_gate_actually_checks_the_config_version():
    """The check must exist in verify.py, not only here -- `verify` is the gate the
    workflow runs before a commit, and a rule only this file knows is a rule that gets
    skipped whenever someone runs verify instead of pytest."""
    import sys

    sys.path.insert(0, str(_repo_root() / "scripts"))
    import verify

    assert hasattr(verify, "check_config_version")
    assert verify.check_config_version(_changelog_top_version()) is True
    # And it must FAIL on a mismatch, or it is decoration.
    assert verify.check_config_version("99.99.99") is False
