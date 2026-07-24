# hatty — MIT License. See LICENSE file for details.
from hatty.ui.dashboard.widgets.thermostat import gauge_position, render_gauge


def test_gauge_position_at_min():
    assert gauge_position(60.0, 60.0, 80.0, width=10) == 0


def test_gauge_position_at_max():
    assert gauge_position(80.0, 60.0, 80.0, width=10) == 9


def test_gauge_position_midpoint():
    assert gauge_position(70.0, 60.0, 80.0, width=10) == 4 or gauge_position(70.0, 60.0, 80.0, width=10) == 5


def test_gauge_position_clamps_below_min():
    assert gauge_position(50.0, 60.0, 80.0, width=10) == 0


def test_gauge_position_clamps_above_max():
    assert gauge_position(90.0, 60.0, 80.0, width=10) == 9


def test_gauge_position_degenerate_range_returns_zero():
    assert gauge_position(70.0, 60.0, 60.0, width=10) == 0


def test_render_gauge_produces_two_lines_with_caret():
    text = render_gauge(current=65.0, setpoint=70.0, min_v=60.0, max_v=80.0, width=10)
    bar_line, caret_line = text.split("\n")
    assert len(bar_line) == 10
    assert set(bar_line) <= {"█", "·"}
    assert caret_line.index("▲") == gauge_position(70.0, 60.0, 80.0, width=10)


def test_render_gauge_without_setpoint_omits_caret_line():
    text = render_gauge(current=65.0, setpoint=None, min_v=60.0, max_v=80.0, width=10)
    assert "\n" not in text
    assert len(text) == 10


def test_render_gauge_fill_grows_with_current():
    low = render_gauge(current=60.0, setpoint=None, min_v=60.0, max_v=80.0, width=10)
    high = render_gauge(current=80.0, setpoint=None, min_v=60.0, max_v=80.0, width=10)
    assert low.count("█") < high.count("█")
