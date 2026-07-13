"""verify — the single mechanical 'done' gate for a phase (AI-WORKSPACE convention).

Runs three checks and exits non-zero if any fails:
  1. pytest          — the full test suite must pass.
  2. pinned deps     — every requirement in scripts/requirements.txt is pinned with ==.
  3. CHANGELOG bump  — md-instructions/CHANGELOG.md has a top version entry, and it
                       matches the version recorded in md-instructions/BRIEFING.md.

Run from anywhere:  python scripts/verify.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "scripts" / "requirements.txt"
CHANGELOG = REPO_ROOT / "md-instructions" / "CHANGELOG.md"
BRIEFING = REPO_ROOT / "md-instructions" / "BRIEFING.md"
TESTS_DIR = REPO_ROOT / "files" / "tests"

_VERSION_RE = re.compile(r"v?(\d+\.\d+(?:\.\d+)?)")


def _ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def check_pytest() -> bool:
    print("[1/3] Running pytest...")
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
    print("[2/3] Checking dependency pins...")
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


def check_changelog() -> bool:
    print("[3/3] Checking CHANGELOG bump...")
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
    print("-" * 48)
    if all(results):
        print("  VERIFY: PASS")
        return 0
    print("  VERIFY: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
