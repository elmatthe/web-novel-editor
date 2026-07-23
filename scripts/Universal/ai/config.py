"""Secret-free defaults plus per-user override resolution."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by the supported Python 3.10 runtime
    import tomli as tomllib

IN_CODE_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "provider": "ollama",
    "model": "",
    "timeout_seconds": 120,
    "strategy": "minimal",
    "prompt_version": "1",
    "gate_version": "1",
}


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    ai = data.get("ai", {})
    return dict(ai) if isinstance(ai, dict) else {}


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data.get("ai", {})) if isinstance(data, dict) else {}


def resolve_ai_config(
    *,
    config_defaults: Mapping[str, Any] | None = None,
    user_settings: Mapping[str, Any] | None = None,
    gui_choices: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = dict(IN_CODE_DEFAULTS)
    resolved.update(config_defaults or {})
    resolved.update(user_settings or {})
    resolved.update(gui_choices or {})
    return resolved
