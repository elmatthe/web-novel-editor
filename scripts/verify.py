"""verify — the single mechanical 'done' gate for a phase (AI-WORKSPACE convention).

Runs three checks and exits non-zero if any fails:
  1. pytest          — the full test suite must pass.
  2. pinned deps     — every requirement in scripts/requirements.txt is pinned with ==.
  3. CHANGELOG bump  — md-instructions/CHANGELOG.md has a top version entry, and it
                       matches the version recorded in md-instructions/BRIEFING.md.
  4. config version  — config.toml's [project] version matches that same entry.

Run from anywhere:  python scripts/verify.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "scripts" / "requirements.txt"
CONFIG = REPO_ROOT / "config.toml"
CHANGELOG = REPO_ROOT / "md-instructions" / "CHANGELOG.md"
BRIEFING = REPO_ROOT / "md-instructions" / "BRIEFING.md"
TESTS_DIR = REPO_ROOT / "files" / "tests"

_VERSION_RE = re.compile(r"v?(\d+\.\d+(?:\.\d+)?)")


def _ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def check_pytest() -> bool:
    print("[1/4] Running pytest...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS_DIR), "-q"],
        cwd=str(REPO_ROOT),
    )
    if result.returncode == 0:
        _ok("test suite passed")
        return True
    _fail("test suite failed")
    return False


def check_pinned_deps() -> bool:
    print("[2/4] Checking dependency pins...")
    if not REQUIREMENTS.exists():
        _fail(f"requirements file not found: {REQUIREMENTS}")
        return False
    unpinned: list[str] = []
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "==" not in line:
            unpinned.append(line)
    if unpinned:
        _fail(f"unpinned dependencies: {', '.join(unpinned)}")
        return False
    _ok("all dependencies pinned with ==")
    return True


def _top_version(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _VERSION_RE.search(line)
        if m and (line.lstrip().startswith("#") or line.lstrip().startswith("##") or "version" in line.lower() or "[" in line):
            return m.group(1)
    return None


def _config_version() -> str | None:
    """The `[project] version` out of config.toml, read as data rather than by regex.

    tomllib is stdlib from 3.11 and config.toml already declares python_minimum 3.10, so
    a 3.10 interpreter falls back to a narrow line scan rather than failing the gate for
    a reason that has nothing to do with the change under test.
    """
    if not CONFIG.exists():
        return None
    try:
        import tomllib

        data = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
        value = data.get("project", {}).get("version")
        return str(value) if value else None
    except ModuleNotFoundError:
        in_project = False
        for line in CONFIG.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("["):
                in_project = stripped == "[project]"
            elif in_project and stripped.startswith("version"):
                _key, _, raw = stripped.partition("=")
                return raw.strip().strip('"').strip("'") or None
        return None
    except (OSError, ValueError):
        return None


def check_config_version(expected: str | None) -> bool:
    """config.toml must agree with the CHANGELOG about what version this is.

    Added 2026-07-27 because it had silently drifted: CHANGELOG and BRIEFING said
    v0.13.0 for a whole plan while config.toml still shipped "0.12.0". Nothing consumed
    the mismatch, which is exactly why nobody noticed — and config.toml is the file a
    release, a bug report and a support conversation all quote.
    """
    print("[4/4] Checking config.toml version...")
    if expected is None:
        _fail("cannot check config.toml version: no CHANGELOG version to compare to")
        return False
    actual = _config_version()
    if not actual:
        _fail("no [project] version found in config.toml")
        return False
    if actual != expected:
        _fail(
            f"config.toml version ({actual}) != CHANGELOG version ({expected}). "
            f"Bump [project] version in config.toml."
        )
        return False
    _ok(f"config.toml at v{actual} (matches CHANGELOG)")
    return True


def check_changelog() -> bool:
    print("[3/4] Checking CHANGELOG bump...")
    if not CHANGELOG.exists():
        _fail(f"CHANGELOG not found: {CHANGELOG}")
        return False
    cl_version = _top_version(CHANGELOG)
    if not cl_version:
        _fail("no version entry found in CHANGELOG.md")
        return False
    br_version = _top_version(BRIEFING)
    if br_version and br_version != cl_version:
        _fail(f"CHANGELOG version ({cl_version}) != BRIEFING version ({br_version})")
        return False
    _ok(f"CHANGELOG at v{cl_version}" + (" (matches BRIEFING)" if br_version else ""))
    return True


def main() -> int:
    print("=" * 48)
    print("  verify - webnovel-editor phase gate")
    print("=" * 48)
    results = [check_pytest(), check_pinned_deps(), check_changelog()]
    results.append(check_config_version(_top_version(CHANGELOG)))
    print("-" * 48)
    if all(results):
        print("  VERIFY: PASS")
        return 0
    print("  VERIFY: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
