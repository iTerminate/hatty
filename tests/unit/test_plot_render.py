# hatty — MIT License. See LICENSE file for details.
"""Unit tests for the pure plotext rendering helpers (issue #169).

The functions that draw onto plotext take a `plt` object; we pass a small
recording double that captures each call so tests can assert *which* plotext
method ran with *what* args without a real terminal.
"""

from datetime import datetime

from hatty.ui.graph.plot_render import (
    NO_CLIMATE_DATA,
    apply_time_axis,
    earliest_t0,
    numeric_stats_line,
    plot_numeric_series,
    plot_width,
    render_binary,
    render_climate,
    render_event_marks,
    render_numeric,
    set_binary_axis,
)


class _RecordingPlt:
    """Captures plotext calls as (method, args, kwargs) tuples."""

    def __init__(self):
        self.calls = []

    def _record(self, name):
        def _fn(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return _fn

    def __getattr__(self, name):
        return self._record(name)

    def names(self):
        return [name for name, _, _ in self.calls]


class _Size:
    def __init__(self, width):
        self.width = width


class _Plot:
    def __init__(self, width):
        self.size = _Size(width)


# ── plot_width (pure, needs a .size stub) ─────────────────────────────────────


def test_plot_width_uses_actual_width_when_positive():
    assert plot_width(_Plot(120)) == 120


def test_plot_width_falls_back_when_zero():
    assert plot_width(_Plot(0), fallback=200) == 200


def test_plot_width_floored_at_twenty():
    assert plot_width(_Plot(5)) == 20


def test_plot_width_object_without_size_uses_fallback():
    class _NoSize:
        size = None

    assert plot_width(_NoSize(), fallback=80) == 80


# ── earliest_t0 (pure) ────────────────────────────────────────────────────────


def test_earliest_t0_primary_only():
    from datetime import datetime

    primary = [("2026-07-07T10:00:00", 1.0), ("2026-07-07T11:00:00", 2.0)]
    assert earliest_t0(primary) == datetime.fromisoformat("2026-07-07T10:00:00")


def test_earliest_t0_pulled_back_by_earlier_extra():
    from datetime import datetime

    primary = [("2026-07-07T10:00:00", 1.0)]
    extra = [("2026-07-07T08:00:00", 5.0)]
    assert earliest_t0(primary, extra) == datetime.fromisoformat("2026-07-07T08:00:00")


def test_earliest_t0_not_moved_by_later_extra():
    from datetime import datetime

    primary = [("2026-07-07T10:00:00", 1.0)]
    extra = [("2026-07-07T12:00:00", 5.0)]
    assert earliest_t0(primary, extra) == datetime.fromisoformat("2026-07-07T10:00:00")


def test_earliest_t0_skips_empty_extra():
    from datetime import datetime

    primary = [("2026-07-07T10:00:00", 1.0)]
    assert earliest_t0(primary, [], None) == datetime.fromisoformat("2026-07-07T10:00:00")


# ── numeric_stats_line (pure) ─────────────────────────────────────────────────


def test_numeric_stats_line_format():
    line = numeric_stats_line([10.0, 20.0, 30.0], "°C")
    assert "min: 10.0°C" in line
    assert "avg: 20.0°C" in line
    assert "max: 30.0°C" in line
    assert "(3 readings)" in line


def test_numeric_stats_line_single_value():
    line = numeric_stats_line([7.0], "%")
    assert "min: 7.0%" in line and "avg: 7.0%" in line and "max: 7.0%" in line
    assert "(1 readings)" in line


# ── plot_numeric_series (needs plt) ───────────────────────────────────────────


def test_plot_numeric_series_line_calls_plot():
    plt = _RecordingPlt()
    plot_numeric_series(plt, "line", [0, 1, 2], [1.0, 2.0, 3.0], width=200, label="L", color="red")
    assert plt.names() == ["plot"]
    _, _, kwargs = plt.calls[0]
    assert kwargs == {"label": "L", "color": "red"}


def test_plot_numeric_series_other_kind_calls_scatter():
    plt = _RecordingPlt()
    plot_numeric_series(plt, "scatter", [0, 1], [1.0, 2.0], width=200)
    assert plt.names() == ["scatter"]


def test_plot_numeric_series_downsamples_long_series():
    plt = _RecordingPlt()
    n = 5000
    plot_numeric_series(plt, "line", list(range(n)), [float(i) for i in range(n)], width=100)
    _, args, _ = plt.calls[0]
    ds_i = args[0]
    # Down to at most ~2 points per column, far below the raw 5000.
    assert len(ds_i) <= 2 * 100
    assert len(ds_i) < n


# ── set_binary_axis (needs plt) ───────────────────────────────────────────────


def test_set_binary_axis_sets_off_on_ticks_and_ylim():
    plt = _RecordingPlt()
    set_binary_axis(plt)
    assert ("yticks", ([0, 1], ["off", "on"]), {}) in plt.calls
    assert any(name == "ylim" for name, _, _ in plt.calls)


# ── apply_time_axis (needs plt) ───────────────────────────────────────────────


def test_apply_time_axis_sets_xticks_and_day_lines():
    from datetime import datetime

    plt = _RecordingPlt()
    # A >24h span so time_axis emits at least one midnight day-line. Real graph
    # timestamps carry a tz offset (midnights_between needs an aware datetime).
    apply_time_axis(plt, datetime.fromisoformat("2026-07-06T00:00:00+00:00"), 48 * 3600)
    assert "xticks" in plt.names()
    assert "vline" in plt.names()


def test_apply_time_axis_no_day_lines_within_a_day():
    from datetime import datetime

    plt = _RecordingPlt()
    # A sub-24h span has no midnight boundary, so no day-change guide lines.
    apply_time_axis(plt, datetime.fromisoformat("2026-07-07T10:00:00+00:00"), 3 * 3600)
    assert "xticks" in plt.names()
    assert "vline" not in plt.names()


# ── render_climate (needs plt) ────────────────────────────────────────────────


def test_render_climate_no_data_returns_placeholder_without_plotting():
    plt = _RecordingPlt()
    assert render_climate(plt, []) == NO_CLIMATE_DATA
    assert plt.calls == []


def test_render_climate_only_missing_temps_returns_placeholder():
    plt = _RecordingPlt()
    data = [{"ts": "2026-07-07T10:00:00", "current_temperature": None, "target_temperature": None}]
    assert render_climate(plt, data) == NO_CLIMATE_DATA
    assert plt.calls == []


def test_render_climate_plots_current_and_target_with_stats():
    plt = _RecordingPlt()
    data = [
        {
            "ts": "2026-07-07T10:00:00",
            "current_temperature": 19.0,
            "target_temperature": 21.0,
            "hvac_action": "heating",
        },
        {
            "ts": "2026-07-07T11:00:00",
            "current_temperature": 20.5,
            "target_temperature": 21.0,
            "hvac_action": "idle",
        },
    ]
    stats = render_climate(plt, data)
    assert "current: 20.5" in stats
    assert "target: 21.0" in stats
    # Two temperature lines were plotted (plus any hvac-strip segments).
    assert plt.names().count("plot") >= 2


# ── render_numeric (needs plt) ────────────────────────────────────────────────


def test_render_numeric_plots_primary_and_axis():
    plt = _RecordingPlt()
    primary = ("Temp", [("2026-07-07T10:00:00+00:00", 1.0), ("2026-07-07T11:00:00+00:00", 2.0)], "red")
    render_numeric(plt, "line", primary, [], width=200)
    assert "xticks" in plt.names()
    plot_calls = [c for c in plt.calls if c[0] == "plot"]
    assert len(plot_calls) == 1
    _, _, kwargs = plot_calls[0]
    assert kwargs == {"label": "Temp", "color": "red"}


def test_render_numeric_plots_each_nonempty_extra_and_skips_empty():
    plt = _RecordingPlt()
    primary = ("Temp", [("2026-07-07T10:00:00+00:00", 1.0)], None)
    extras = [
        ("Humidity", [("2026-07-07T10:00:00+00:00", 40.0)], "blue"),
        ("Empty", [], "green"),
    ]
    render_numeric(plt, "line", primary, extras, width=200)
    labels = [kwargs.get("label") for name, _, kwargs in plt.calls if name == "plot"]
    assert labels == ["Temp", "Humidity"]  # the empty extra is skipped


def test_render_numeric_scatter_kind_uses_scatter():
    plt = _RecordingPlt()
    primary = ("Temp", [("2026-07-07T10:00:00+00:00", 1.0)], None)
    render_numeric(plt, "scatter", primary, [], width=200)
    assert "scatter" in plt.names()
    assert "plot" not in plt.names()


def test_render_numeric_no_cursor_by_default():
    plt = _RecordingPlt()
    primary = ("Temp", [("2026-07-07T10:00:00+00:00", 1.0), ("2026-07-07T11:00:00+00:00", 2.0)], None)
    render_numeric(plt, "line", primary, [], width=200)
    # No cursor index → no white inspection vline (day-line vlines only appear >24h).
    assert not any(kwargs.get("color") == "white" for name, _, kwargs in plt.calls if name == "vline")


def test_render_numeric_cursor_index_draws_white_vline():
    plt = _RecordingPlt()
    primary = ("Temp", [("2026-07-07T10:00:00+00:00", 1.0), ("2026-07-07T11:00:00+00:00", 2.0)], None)
    render_numeric(plt, "line", primary, [], width=200, cursor_index=1)
    white_vlines = [c for c in plt.calls if c[0] == "vline" and c[2].get("color") == "white"]
    assert len(white_vlines) == 1
    # The marker sits at the selected sample's x-position (3600s after t0).
    assert white_vlines[0][1][0] == 3600.0


def test_render_numeric_cursor_index_clamped_to_series():
    plt = _RecordingPlt()
    primary = ("Temp", [("2026-07-07T10:00:00+00:00", 1.0), ("2026-07-07T11:00:00+00:00", 2.0)], None)
    render_numeric(plt, "line", primary, [], width=200, cursor_index=99)
    white_vlines = [c for c in plt.calls if c[0] == "vline" and c[2].get("color") == "white"]
    assert white_vlines[0][1][0] == 3600.0  # clamped to the last sample


def test_render_numeric_returns_t0():
    plt = _RecordingPlt()
    primary = ("Temp", [("2026-07-07T10:00:00+00:00", 1.0), ("2026-07-07T11:00:00+00:00", 2.0)], None)
    t0 = render_numeric(plt, "line", primary, [], width=200)
    assert t0 == datetime.fromisoformat("2026-07-07T10:00:00+00:00")


# ── render_binary (needs plt) ─────────────────────────────────────────────────


def test_render_binary_plots_primary_step_trace_and_binary_axis():
    plt = _RecordingPlt()
    primary = [("2026-07-07T10:00:00+00:00", 0.0), ("2026-07-07T11:00:00+00:00", 1.0)]
    t0 = render_binary(plt, ("Door", primary, "red"), [], extend_to="2026-07-07T12:00:00+00:00")
    assert t0 == datetime.fromisoformat("2026-07-07T10:00:00+00:00")
    # One step-trace plot for the primary, plus the shared time axis + on/off axis.
    plot_calls = [c for c in plt.calls if c[0] == "plot"]
    assert len(plot_calls) == 1
    _, _, kwargs = plot_calls[0]
    assert kwargs == {"label": "Door", "color": "red"}
    assert ("yticks", ([0, 1], ["off", "on"]), {}) in plt.calls
    assert "xticks" in plt.names()


def test_render_binary_includes_binary_extra_but_drops_numeric_extra():
    plt = _RecordingPlt()
    primary = [("2026-07-07T10:00:00+00:00", 1.0)]
    binary_extra = ("Window", [("2026-07-07T10:00:00+00:00", 0.0)], "blue")
    numeric_extra = ("Temp", [("2026-07-07T10:00:00+00:00", 21.5)], "green")
    render_binary(plt, ("Door", primary, None), [binary_extra, numeric_extra], extend_to=None)
    labels = [kwargs.get("label") for name, _, kwargs in plt.calls if name == "plot"]
    assert labels == ["Door", "Window"]  # numeric companion excluded from the 0/1 axis


def test_render_binary_extends_axis_to_extend_to():
    plt = _RecordingPlt()
    # Last sample at +1h but the trace extends to +3h; the axis span must cover it.
    primary = [("2026-07-07T10:00:00+00:00", 1.0), ("2026-07-07T11:00:00+00:00", 0.0)]
    render_binary(plt, ("Door", primary, None), [], extend_to="2026-07-07T13:00:00+00:00")
    xticks_call = next(c for c in plt.calls if c[0] == "xticks")
    # apply_time_axis is fed total_secs; the largest xtick position reflects the span.
    tick_positions = xticks_call[1][0]
    assert max(tick_positions) >= 3 * 3600 - 1


# ── render_event_marks (needs plt) ────────────────────────────────────────────


def test_render_event_marks_one_vline_per_event():
    plt = _RecordingPlt()
    t0 = datetime.fromisoformat("2026-07-07T10:00:00+00:00")
    events = ["2026-07-07T10:30:00+00:00", "2026-07-07T11:00:00+00:00"]
    render_event_marks(plt, t0, events)
    vlines = [c for c in plt.calls if c[0] == "vline"]
    assert len(vlines) == 2
    assert vlines[0][1][0] == 1800.0
    assert vlines[1][1][0] == 3600.0
    assert all(kwargs.get("color") == "magenta" for _, _, kwargs in vlines)


def test_render_event_marks_skips_events_before_t0():
    plt = _RecordingPlt()
    t0 = datetime.fromisoformat("2026-07-07T10:00:00+00:00")
    events = ["2026-07-07T09:00:00+00:00", "2026-07-07T10:30:00+00:00"]
    render_event_marks(plt, t0, events)
    vlines = [c for c in plt.calls if c[0] == "vline"]
    assert len(vlines) == 1
    assert vlines[0][1][0] == 1800.0


def test_render_event_marks_honours_limit():
    plt = _RecordingPlt()
    t0 = datetime.fromisoformat("2026-07-07T10:00:00+00:00")
    events = [f"2026-07-07T10:{m:02d}:00+00:00" for m in range(0, 10)]
    render_event_marks(plt, t0, events, limit=3)
    vlines = [c for c in plt.calls if c[0] == "vline"]
    assert len(vlines) == 3


def test_render_event_marks_ignores_unparseable_timestamps():
    plt = _RecordingPlt()
    t0 = datetime.fromisoformat("2026-07-07T10:00:00+00:00")
    render_event_marks(plt, t0, ["not-a-timestamp", "2026-07-07T10:30:00+00:00"])
    vlines = [c for c in plt.calls if c[0] == "vline"]
    assert len(vlines) == 1
