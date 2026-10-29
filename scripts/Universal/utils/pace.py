"""Running-average pace and ETA readout for a batch.

Extracted from the retired ``gui.ai_settings`` (Phase 01A) unchanged: the readout is a
plain observed average over the chapters finished so far, and it says nothing until a
chapter has actually completed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunRate:
    """Observed pace of the current batch. ``None`` means 'not yet knowable'."""

    completed: int
    total: int
    seconds_per_file: float | None
    eta_seconds: float | None


def compute_rate(completed: int, total: int, elapsed_seconds: float) -> RunRate:
    """A plain running average over the chapters finished so far."""
    if completed <= 0 or elapsed_seconds <= 0:
        return RunRate(completed, total, None, None)
    per_file = elapsed_seconds / completed
    remaining = total - completed
    eta = per_file * remaining if remaining > 0 else None
    return RunRate(completed, total, per_file, eta)


def format_duration(seconds: float) -> str:
    """Compact human duration: ``9s`` / ``1m 36s`` / ``1h 02m``."""
    total = int(round(max(0.0, seconds)))
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m {total % 60:02d}s"
    return f"{total // 3600}h {(total % 3600) // 60:02d}m"


def format_rate(rate: RunRate) -> str:
    """One short readout, or '' while the pace is still unknown."""
    if rate.seconds_per_file is None:
        return ""
    text = f"average {rate.seconds_per_file:.1f} s/chapter"
    if rate.eta_seconds is not None:
        text += f" — about {format_duration(rate.eta_seconds)} left"
    return text
