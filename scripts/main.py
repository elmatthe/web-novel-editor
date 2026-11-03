"""Webnovel Editor — application entry point.

The application entry compatibility boundary. Supported launch chain:
`Setup_and_Run-Web-Novel-Editor.bat` / `.command` -> `scripts/bootstrap.py` ->
`scripts/launcher.py` -> `main.main()`. Running `python scripts/main.py` directly also works.

`--check` runs the full import/startup chain (tkinter + the GUI package) and exits
without opening a window. `launcher.py --check` delegates here, and the bootstrap's health
proof runs it with the console interpreter before detaching to `pythonw.exe`, so a fatal
startup error is visible instead of vanishing behind the windowless launch.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    check_only = "--check" in argv

    try:
        import tkinter  # noqa: F401  (presence check before importing the app)
    except Exception:
        # tkinter is bundled with standard Python on Windows/macOS; absence is an
        # edge case (some stripped Linux builds). Fail with a clear message, not a
        # raw traceback, per the build spec.
        print("ERROR: Tkinter is not available in this Python installation.")
        print("Tkinter ships with standard Python on Windows and macOS. If you are")
        print("on Linux, install it with your package manager (e.g. 'sudo apt install")
        print("python3-tk') and re-run.")
        return 1

    from gui.app import launch  # noqa: F401  (import validates the app can start)

    if check_only:
        # Preflight only: the import chain above is what would fail at startup.
        print("Startup check passed.")
        return 0

    launch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
