"""Phase 1 scaffold tests — verify package wiring imports and stubs behave.

These prove the structure is sound (every stage module resolves, the Stage 1.5
junk_strip is wired, profile data loads, no-op rule stubs pass text through). Real
behavioral tests per rule arrive with their implementations in Phase 4+.
"""

from __future__ import annotations

import importlib


def test_pipeline_wiring_imports():
    """The one universal pipeline (and thus every stage import) resolves cleanly."""
    mod = importlib.import_module("pipelines.universal")
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


def _toml_module():
    """``tomllib`` (stdlib, Python 3.11+) or the pinned ``tomli`` backport (3.10).

    ``config.toml`` declares ``python_minimum = "3.10"``, so this test must not import
    ``tomllib`` unconditionally (Phase 01A fixed exactly that mismatch).
    """
    import sys

    if sys.version_info >= (3, 11):
        import tomllib

        return tomllib
    import tomli

    return tomli


def _config_version() -> str:
    data = _toml_module().loads((_repo_root() / "config.toml").read_text(encoding="utf-8"))
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


def test_tomli_backport_reads_the_config_exactly_like_the_stdlib():
    """The Python 3.10 path: the pinned ``tomli`` must agree with ``tomllib`` byte for key.

    Both are exercised on every interpreter that has them, so the 3.10 fallback is not
    an untested branch even though this machine runs a newer Python.
    """
    import tomli

    text = (_repo_root() / "config.toml").read_text(encoding="utf-8")
    parsed = tomli.loads(text)
    assert parsed["project"]["python_minimum"] == "3.10"
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10: nothing further to compare against
        return
    assert tomllib.loads(text) == parsed


def test_committed_config_holds_only_project_metadata_and_no_credentials():
    """No credential may be committed - checked by shape, not by keyword - and since
    Phase 01A the file carries project metadata only (no AI tables)."""
    import re

    text = (_repo_root() / "config.toml").read_text(encoding="utf-8")
    parsed = _toml_module().loads(text)
    assert set(parsed) == {"project"}, f"unexpected tables: {sorted(parsed)}"

    assigned = re.findall(
        r"(?im)^\s*([A-Za-z0-9_]*(?:api_?key|apikey|secret|password|credential"
        r"|access_token|auth_token|api_token)[A-Za-z0-9_]*)\s*=",
        text,
    )
    assert assigned == [], f"credential-shaped assignment in config.toml: {assigned}"
    for shape in (r"AIza[0-9A-Za-z_\-]{16,}", r"gsk_[0-9A-Za-z]{16,}", r"sk-[0-9A-Za-z_\-]{16,}"):
        assert not re.search(shape, text), f"a key-shaped value is present: {shape}"


def test_requirements_declare_no_ai_sdk():
    """The three provider SDKs are gone from the declared dependencies for good."""
    import re

    lines = (_repo_root() / "scripts" / "requirements.txt").read_text(encoding="utf-8").splitlines()
    declared = {
        re.split(r"[=<>!~ ]", line.strip(), maxsplit=1)[0].lower()
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert declared.isdisjoint({"ollama", "google-genai", "google-generativeai", "groq"})
    assert {"pdfplumber", "reportlab", "natsort", "tomli", "pytest"} <= declared
