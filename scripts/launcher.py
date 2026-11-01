#!/usr/bin/env python3
"""Web Novel Editor product entry point (launch chain: root launcher -> bootstrap -> here).

Adapted (Phase 02B) from the author's PDF-Splitter ``scripts/launcher.py`` at
``edcbd4fe6db96bb7515e719172fbd4172fe3ef19``.

* ``--help`` and ``--version`` are answered headlessly: no Tk, no application import, no
  display, no provisioning. ``--version`` reads ``[project].version`` from ``config.toml``
  (``tomllib`` on 3.11+, the pinned ``tomli`` on 3.10); there is no second version constant.
* ``--check`` delegates to ``main.py --check``: the full import chain without a window.
* With no flag the GUI is imported lazily and started through ``main.main``. A startup
  failure is printed to stderr, or — under ``pythonw`` where there is no stderr — appended
  to ``files/runtime-data/logs/app-output-latest.log``, and the exit code is non-zero.

This module never calls the bootstrap; the bootstrap calls it. No network access.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
PRODUCT_NAME = "Web Novel Editor"
APP_OUTPUT_LOG = REPO_ROOT / "files" / "runtime-data" / "logs" / "app-output-latest.log"


def _toml():
    try:
        import tomllib
        return tomllib
    except ModuleNotFoundError:  # Python 3.10: the pinned backport
        import tomli
        return tomli


def project_version() -> str:
    """``[project].version`` from ``config.toml`` (single source of truth)."""
    try:
        with (REPO_ROOT / "config.toml").open("rb") as handle:
            version = _toml().load(handle).get("project", {}).get("version")
        return str(version) if version else "unknown"
    except (OSError, ValueError, ImportError):
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="launcher.py",
        description=(f"{PRODUCT_NAME}: offline, deterministic cleanup of web-novel chapter PDF/TXT "
                     "files. Running without arguments opens the application window."))
    parser.add_argument("--version", action="version", version=f"{PRODUCT_NAME} {project_version()}")
    parser.add_argument("--check", action="store_true",
                        help="verify the application can start (imports only, no window), then exit")
    return parser


def _report_failure(message: str) -> None:
    text = message.rstrip() + "\n"
    if sys.stderr is not None:
        try:
            sys.stderr.write(text)
            sys.stderr.flush()
            return
        except (OSError, ValueError):
            pass
    try:
        APP_OUTPUT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with APP_OUTPUT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))
        import main as app_main

        return app_main.main(["--check"] if args.check else [])
    except Exception:  # noqa: BLE001 - last-resort visible report; the bootstrap shows the log
        _report_failure(f"{PRODUCT_NAME} could not start:\n{traceback.format_exc()}"
                        f"Logs: {APP_OUTPUT_LOG.parent}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
