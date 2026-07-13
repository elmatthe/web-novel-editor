"""Webnovel Editor — application entry point.

Launched by the startup scripts (`Setup_and_Run.bat` / `Setup_and_Run.command`)
via `python scripts/Universal/main.py`. Opens the Tkinter GUI (Phase 2).
"""

from __future__ import annotations

import sys


def main() -> int:
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

    from gui.app import launch

    launch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
