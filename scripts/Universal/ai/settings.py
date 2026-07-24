"""Per-user runtime paths and atomic settings persistence."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping


def runtime_dir(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    platform = platform or sys.platform
    environ = environ or os.environ
    home = home or Path.home()
    if platform == "win32":
        base = environ.get("LOCALAPPDATA")
        if not base:
            base = str(home / "AppData" / "Local")
        return Path(base) / "WebNovelEditor"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "WebNovelEditor"
    raise OSError(f"Unsupported platform: {platform}")


def settings_path(**kwargs) -> Path:
    return runtime_dir(**kwargs) / "settings.json"


def write_settings_atomic(path: Path, settings: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dict(settings), indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
