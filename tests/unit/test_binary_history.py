# hatty — MIT License. See LICENSE file for details.
from hatty.ui.graph.binary_history import binary_stats, is_on, to_step_points, value_to_state


def test_is_on_uses_half_midpoint():
    assert is_on(1.0) is True
    assert is_on(0.5) is True
    assert is_on(0.49) is False
    assert is_on(0.0) is False


def test_value_to_state_maps_to_on_off():
    assert value_to_state(1.0) == "on"
    assert value_to_state(0.0) == "off"


def test_empty_history_yields_no_steps():
    assert to_step_points([]) == []


def test_single_sample_extends_to_window_end():
    data = [("2024-01-01T10:00:00+00:00", 1.0)]
    steps = to_step_points(data, extend_to="2024-01-01T12:00:00+00:00")
    assert steps == [
        ("2024-01-01T10:00:00+00:00", 1.0),
        ("2024-01-01T12:00:00+00:00", 1.0),
    ]


def test_alternating_states_become_square_steps():
    data = [
        ("2024-01-01T10:00:00+00:00", 0.0),
        ("2024-01-01T11:00:00+00:00", 1.0),
        ("2024-01-01T12:00:00+00:00", 0.0),
    ]
    steps = to_step_points(data)
    assert steps == [
        ("2024-01-01T10:00:00+00:00", 0.0),
        ("2024-01-01T11:00:00+00:00", 0.0),
        ("2024-01-01T11:00:00+00:00", 1.0),
        ("2024-01-01T12:00:00+00:00", 1.0),
        ("2024-01-01T12:00:00+00:00", 0.0),
    ]


def test_extend_to_before_last_sample_is_ignored():
    data = [
        ("2024-01-01T10:00:00+00:00", 0.0),
        ("2024-01-01T12:00:00+00:00", 1.0),
    ]
    steps = to_step_points(data, extend_to="2024-01-01T11:00:00+00:00")
    assert steps[-1] == ("2024-01-01T12:00:00+00:00", 1.0)


def test_binary_stats_reports_on_percentage_and_changes():
    data = [
        ("2024-01-01T10:00:00+00:00", 0.0),
        ("2024-01-01T11:00:00+00:00", 1.0),  # on for 1h of the 2h window
        ("2024-01-01T12:00:00+00:00", 0.0),
    ]
    text = binary_stats(data, end_ts="2024-01-01T12:00:00+00:00")
    assert "on 50% of window" in text
    assert "2 changes" in text
    assert "last: off" in text


def test_binary_stats_extends_final_on_state_to_window_end():
    data = [
        ("2024-01-01T10:00:00+00:00", 0.0),
        ("2024-01-01T11:00:00+00:00", 1.0),
    ]
    text = binary_stats(data, end_ts="2024-01-01T12:00:00+00:00")
    assert "on 50% of window" in text
    assert "last: on" in text


def test_binary_stats_empty():
    assert binary_stats([]) == "No history data available."
