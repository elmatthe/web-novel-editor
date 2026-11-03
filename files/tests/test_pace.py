"""Running-average pace and ETA readout (``utils.pace``).

Re-homed from ``test_ai_gui_controls`` in Phase 01A, when the AI GUI module was removed:
the readout is general batch behaviour and always was.
"""

from __future__ import annotations

import pytest

from utils.pace import compute_rate, format_duration, format_rate


def test_rate_is_unknown_before_the_first_chapter_completes():
    rate = compute_rate(0, 10, 4.0)
    assert rate.seconds_per_file is None
    assert rate.eta_seconds is None
    assert format_rate(rate) == ""


def test_rate_is_a_running_average_with_an_eta():
    rate = compute_rate(2, 10, 24.0)
    assert rate.seconds_per_file == pytest.approx(12.0)
    assert rate.eta_seconds == pytest.approx(96.0)
    text = format_rate(rate)
    assert "12.0 s/chapter" in text
    assert "1m 36s" in text


def test_rate_drops_the_eta_once_every_chapter_is_done():
    rate = compute_rate(4, 4, 40.0)
    assert rate.eta_seconds is None
    text = format_rate(rate)
    assert "10.0 s/chapter" in text
    assert "left" not in text


def test_rate_ignores_impossible_inputs():
    assert compute_rate(3, 2, 10.0).eta_seconds is None
    assert compute_rate(1, 5, 0.0).seconds_per_file is None
    assert compute_rate(1, 5, -3.0).seconds_per_file is None


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0.4, "0s"), (9.0, "9s"), (59.6, "1m 00s"), (96.0, "1m 36s"),
     (600.0, "10m 00s"), (3725.0, "1h 02m")],
)
def test_duration_formatting(seconds, expected):
    assert format_duration(seconds) == expected
