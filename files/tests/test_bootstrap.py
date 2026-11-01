"""Bootstrap and launcher entry: health proof, discovery simulations, repair guards, launch.

No test deletes or rebuilds the developer's real ``.venv``. Repair/deletion behavior runs
against contained sandboxes created under the test's temporary directory. Interpreter
discovery is simulated (patched ``which``/environment), which proves selection logic but is
not evidence of a genuinely Python-free machine.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"


@pytest.fixture
def bootstrap(tmp_path, monkeypatch):
    """The bootstrap module pointed at a contained sandbox repository."""
    import bootstrap as module
    sandbox = tmp_path / "repo"
    (sandbox / "scripts").mkdir(parents=True)
    (sandbox / "config.toml").write_text('[project]\nname = "Web Novel Editor"\nversion = "0.13.0"\n'
                                         'python_minimum = "3.10"\n', encoding="utf-8")
    (sandbox / "scripts" / "requirements.txt").write_text("pdfplumber==0.11.10\nreportlab==5.0.0\n",
                                                          encoding="utf-8")
    (sandbox / "scripts" / "launcher.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    module._set_root(sandbox)
    yield module
    module._set_root(REPO)


def _venv_shaped(path: Path) -> None:
    (path / ("Scripts" if os.name == "nt" else "bin")).mkdir(parents=True)
    (path / "Lib").mkdir()
    (path / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")


# ---------------------------------------------------------------------------- configuration

def test_stdlib_config_reader_matches_tomllib_on_the_real_config(monkeypatch):
    import bootstrap
    text = (REPO / "config.toml").read_text(encoding="utf-8")
    real = bootstrap.parse_project_table(text)
    monkeypatch.setitem(sys.modules, "tomllib", None)  # simulate Python 3.10 (no stdlib tomllib)
    fallback = bootstrap.parse_project_table(text)
    assert fallback == real and fallback["python_minimum"] == "3.10"
    with pytest.raises(ValueError):
        bootstrap.parse_project_table('[project]\nversion = 4\n')


def test_requirements_must_be_exact_pins(bootstrap):
    assert bootstrap.requirement_pins() == [("pdfplumber", "0.11.10"), ("reportlab", "5.0.0")]
    bootstrap.REQUIREMENTS_PATH.write_text("pdfplumber>=0.11\n", encoding="utf-8")
    with pytest.raises(bootstrap.BootstrapError, match="unpinned"):
        bootstrap.requirement_pins()


def test_real_requirements_are_all_exact_pins_and_ai_free():
    import bootstrap
    names = {name.lower() for name, _ in bootstrap.requirement_pins()}
    assert {"pdfplumber", "reportlab", "natsort", "tomli", "pytest"} <= names
    assert names.isdisjoint({"ollama", "groq", "google-genai"})


# --------------------------------------------------------------------------- discovery

def test_store_alias_paths_are_recognized_and_never_probed(bootstrap, monkeypatch):
    alias = r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python.exe"
    assert bootstrap.is_store_alias(alias) and bootstrap.is_store_alias(alias.replace("\\", "/"))
    assert not bootstrap.is_store_alias(r"C:\Users\x\AppData\Local\Programs\Python\Python313\python.exe")
    probed = []
    monkeypatch.setattr(bootstrap, "run_bounded", lambda args, **k: probed.append(args) or pytest.fail("ran"))
    assert bootstrap.probe_base_python(alias, (3, 10)) is None and probed == []


def test_no_python_simulation_gives_an_actionable_error(bootstrap, monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "empty-local"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "empty-pf"))
    monkeypatch.setattr(bootstrap.glob, "glob", lambda pattern: [])
    monkeypatch.setattr(bootstrap, "running_from_project_venv", lambda: True)
    assert bootstrap.base_python_candidates((3, 10)) == []
    with pytest.raises(bootstrap.BootstrapError, match="python.org"):
        bootstrap.find_base_python((3, 10))


def test_only_a_store_alias_on_path_counts_as_no_python(bootstrap, monkeypatch, tmp_path):
    alias = tmp_path / "Microsoft" / "WindowsApps" / "python.exe"
    alias.parent.mkdir(parents=True)
    alias.write_bytes(b"MZ")
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: str(alias) if name.startswith("python") else None)
    monkeypatch.setattr(bootstrap.glob, "glob", lambda pattern: [])
    monkeypatch.setattr(bootstrap, "running_from_project_venv", lambda: True)
    assert bootstrap.base_python_candidates((3, 10)) == []


def test_tested_versions_are_preferred_over_newer_untested_ones(bootstrap, monkeypatch):
    versions = {"a": (3, 15, 0), "b": (3, 12, 9), "c": (3, 13, 1), "d": (3, 9, 18)}
    monkeypatch.setattr(bootstrap, "base_python_candidates", lambda minimum: list(versions))
    monkeypatch.setattr(bootstrap, "probe_base_python",
                        lambda exe, minimum: versions[exe] if versions[exe][:2] >= minimum else None)
    assert bootstrap.find_base_python((3, 10)) == ("c", (3, 13, 1))
    versions.pop("c")
    versions.pop("b")
    assert bootstrap.find_base_python((3, 10)) == ("a", (3, 15, 0))  # untested but allowed


def test_real_base_python_probe_on_this_host_rejects_the_project_venv():
    import bootstrap
    if sys.platform != "win32":
        pytest.skip("HOME-PC discovery evidence is Windows-specific")
    candidates = bootstrap.base_python_candidates((3, 10))
    assert all(not bootstrap.is_store_alias(c) for c in candidates)
    assert all(not bootstrap.inside_venv_dir(Path(c)) for c in candidates)
    if bootstrap.VENV_PYTHON.is_file():
        assert bootstrap.probe_base_python(str(bootstrap.VENV_PYTHON), (3, 10)) is None


# --------------------------------------------------------------------- deletion guard

def test_venv_shaped_project_venv_is_removed(bootstrap, monkeypatch):
    monkeypatch.setattr(bootstrap, "running_from_project_venv", lambda: False)
    _venv_shaped(bootstrap.VENV_DIR)
    bootstrap.remove_venv()
    assert not bootstrap.VENV_DIR.exists()


def test_venv_with_unexpected_user_files_is_never_deleted(bootstrap, monkeypatch):
    monkeypatch.setattr(bootstrap, "running_from_project_venv", lambda: False)
    _venv_shaped(bootstrap.VENV_DIR)
    (bootstrap.VENV_DIR / "my-chapters").mkdir()
    (bootstrap.VENV_DIR / "my-chapters" / "1.pdf").write_bytes(b"precious")
    with pytest.raises(bootstrap.BootstrapError, match="not part of a Python environment"):
        bootstrap.remove_venv()
    assert (bootstrap.VENV_DIR / "my-chapters" / "1.pdf").read_bytes() == b"precious"


def test_linked_venv_is_never_followed_or_deleted(bootstrap, monkeypatch, tmp_path, directory_link):
    monkeypatch.setattr(bootstrap, "running_from_project_venv", lambda: False)
    unrelated = tmp_path / "unrelated-data"
    _venv_shaped(unrelated)
    (unrelated / "Lib" / "sentinel.txt").write_text("keep", encoding="utf-8")
    directory_link(bootstrap.VENV_DIR, unrelated)
    with pytest.raises(bootstrap.BootstrapError, match="link or junction"):
        bootstrap.remove_venv()
    assert (unrelated / "Lib" / "sentinel.txt").read_text(encoding="utf-8") == "keep"
    assert os.path.lexists(bootstrap.VENV_DIR)


def test_rebuild_from_inside_the_venv_is_refused(bootstrap, monkeypatch):
    _venv_shaped(bootstrap.VENV_DIR)
    monkeypatch.setattr(bootstrap.sys, "executable", str(bootstrap.VENV_PYTHON))
    assert bootstrap.running_from_project_venv()
    with pytest.raises(bootstrap.BootstrapError, match="separate Python"):
        bootstrap.remove_venv()
    assert bootstrap.VENV_DIR.is_dir()


def test_locked_venv_reports_close_the_program(bootstrap, monkeypatch):
    monkeypatch.setattr(bootstrap, "running_from_project_venv", lambda: False)
    _venv_shaped(bootstrap.VENV_DIR)

    def locked(path, *a, **k):
        raise PermissionError(32, "The process cannot access the file because it is being used")
    monkeypatch.setattr(bootstrap.shutil, "rmtree", locked)
    with pytest.raises(bootstrap.BootstrapError, match="Close Web Novel Editor"):
        bootstrap.remove_venv()


def test_reconcile_never_reinstalls_a_satisfied_environment(bootstrap, monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap, "venv_health", lambda m: ("3.13.1", [], []))
    monkeypatch.setattr(bootstrap, "full_health_problems", lambda m: ("3.13.1", []))
    monkeypatch.setattr(bootstrap, "ensure_pip", lambda: calls.append("pip"))
    monkeypatch.setattr(bootstrap, "install_requirements", lambda: calls.append("install"))
    monkeypatch.setattr(bootstrap, "remove_venv", lambda: calls.append("remove"))
    assert bootstrap.reconcile((3, 10), force_rebuild=False) == "3.13.1"
    assert calls == ["pip"]
    assert json.loads(bootstrap.STATE_PATH.read_text(encoding="utf-8"))["result"] == "pass"


def test_reconcile_repairs_missing_pins_in_place_without_rebuilding(bootstrap, monkeypatch):
    calls = []
    health = iter([("3.13.1", [], ["natsort==8.4.0 (installed: missing)"]),
                   ("3.13.1", [], ["natsort==8.4.0 (installed: missing)"])])
    monkeypatch.setattr(bootstrap, "venv_health", lambda m: next(health))
    monkeypatch.setattr(bootstrap, "full_health_problems", lambda m: ("3.13.1", []))
    monkeypatch.setattr(bootstrap, "ensure_pip", lambda: None)
    monkeypatch.setattr(bootstrap, "install_requirements", lambda: calls.append("install"))
    monkeypatch.setattr(bootstrap, "remove_venv", lambda: pytest.fail("rebuilt a repairable environment"))
    bootstrap.reconcile((3, 10), force_rebuild=False)
    assert calls == ["install"]


def test_failed_install_is_reported_honestly(bootstrap, monkeypatch):
    monkeypatch.setattr(bootstrap, "run_streamed", lambda args: 1)
    with pytest.raises(bootstrap.BootstrapError, match="internet connection"):
        bootstrap.install_requirements()


# ---------------------------------------------------------------------- health and launch

def test_broken_sandbox_venv_fails_the_fast_path_without_repair(bootstrap, tmp_path):
    """A real interpreter-only venv (no pip, no packages) is unhealthy; --venv-check exits 3."""
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(bootstrap.VENV_DIR)], check=True,
                   timeout=120, capture_output=True)
    before = sorted(p.relative_to(bootstrap.VENV_DIR) for p in bootstrap.VENV_DIR.rglob("*"))
    healthy, reason = bootstrap.fast_health_check()
    assert not healthy and ("import pdfplumber failed" in reason or "pip is missing" in reason)
    assert sorted(p.relative_to(bootstrap.VENV_DIR) for p in bootstrap.VENV_DIR.rglob("*")) == before
    assert bootstrap.main(["--venv-check"]) == bootstrap.EXIT_VENV_UNHEALTHY


def test_missing_venv_launch_only_requests_setup(bootstrap, capsys):
    assert bootstrap.main(["--launch-only"]) == bootstrap.EXIT_VENV_UNHEALTHY
    assert "Setup or repair is needed" in capsys.readouterr().out


def test_real_project_venv_passes_the_offline_fast_path(offline_python, tmp_path):
    """Healthy offline startup evidence: the real health proof (imports, Tk, pins, pip check,
    entry smoke) under the network guard, which also reaches every probe child."""
    import bootstrap
    if not bootstrap.VENV_PYTHON.is_file():
        pytest.skip("no project .venv in this checkout")
    completed = offline_python.run([str(SCRIPTS / "bootstrap.py"), "--venv-check"], cwd=tmp_path,
                                   capture_output=True, text=True, timeout=240, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.startswith("healthy (Python ")


def test_immediate_launch_failure_is_detected_and_logged(bootstrap, monkeypatch):
    monkeypatch.setattr(bootstrap, "VENV_PYTHONW", Path(sys.executable))
    bootstrap.ENTRY_POINT.write_text("import sys\nprint('boom: startup failed')\nsys.exit(7)\n", encoding="utf-8")
    assert bootstrap.launch_application() == bootstrap.EXIT_LAUNCH_FAILED
    assert "boom: startup failed" in bootstrap.APP_OUTPUT_LOG_PATH.read_text(encoding="utf-8")


def test_a_running_application_counts_as_launched(bootstrap, monkeypatch):
    monkeypatch.setattr(bootstrap, "VENV_PYTHONW", Path(sys.executable))
    monkeypatch.setattr(bootstrap, "LAUNCH_GRACE_SECONDS", 0.5)
    marker = bootstrap.REPO_ROOT / "stop.flag"
    bootstrap.ENTRY_POINT.write_text(
        "import pathlib, time\nflag = pathlib.Path(__file__).resolve().parents[1] / 'stop.flag'\n"
        "end = time.time() + 20\nwhile not flag.exists() and time.time() < end:\n    time.sleep(0.05)\n",
        encoding="utf-8")
    try:
        assert bootstrap.launch_application() == bootstrap.EXIT_OK
    finally:
        marker.write_text("stop", encoding="utf-8")


# ------------------------------------------------------------------------------ launcher

def test_launcher_version_and_help_are_headless_and_read_config(offline_python, tmp_path):
    code = ("import sys, runpy; sys.argv=['launcher.py','--version']\n"
            "try:\n    runpy.run_path(r'%s', run_name='__main__')\nexcept SystemExit as e:\n    code = e.code\n"
            "print('TK_LOADED' if 'tkinter' in sys.modules else 'NO_TK'); print('GUI' if 'gui.app' in sys.modules "
            "else 'NO_GUI')" % (SCRIPTS / "launcher.py"))
    done = offline_python.run(["-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    import bootstrap
    version = bootstrap.parse_project_table((REPO / "config.toml").read_text(encoding="utf-8"))["version"]
    assert f"Web Novel Editor {version}" in done.stdout and "NO_TK" in done.stdout and "NO_GUI" in done.stdout
    helped = offline_python.run([str(SCRIPTS / "launcher.py"), "--help"], cwd=tmp_path, capture_output=True,
                                text=True, timeout=60)
    assert helped.returncode == 0 and "--check" in helped.stdout


def test_launcher_check_delegates_to_main_check(offline_python, tmp_path):
    done = offline_python.run([str(SCRIPTS / "launcher.py"), "--check"], cwd=tmp_path, capture_output=True,
                              text=True, timeout=90)
    assert done.returncode == 0 and "Startup check passed." in done.stdout


def test_launcher_startup_failure_is_visible_and_nonzero(monkeypatch, capsys):
    import launcher

    def broken(argv):
        raise RuntimeError("simulated startup fault")
    import main as app_main
    monkeypatch.setattr(app_main, "main", broken)
    assert launcher.main([]) == 1
    assert "simulated startup fault" in capsys.readouterr().err


def test_launch_chain_has_no_recursion():
    """launcher.py and main.py never import or spawn the bootstrap (or any subprocess)."""
    import ast
    for name in ("launcher.py", "main.py"):
        tree = ast.parse((SCRIPTS / name).read_text(encoding="utf-8"))
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                    for alias in node.names}
        imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        assert not imported & {"bootstrap", "subprocess", "os"}, (name, imported)
    bootstrap_text = (SCRIPTS / "bootstrap.py").read_text(encoding="utf-8")
    assert "--upgrade\", \"pip" not in bootstrap_text and "install --upgrade pip" not in bootstrap_text
