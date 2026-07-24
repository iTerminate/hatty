# hatty — MIT License. See LICENSE file for details.
"""Shared plotext rendering helpers for the three graph surfaces
(entity_detail panel, fullscreen graph_preview_screen, dashboard graph
widget), which previously each carried their own copy of this logic."""

from collections.abc import Sequence
from datetime import datetime

from hatty.ui.graph.binary_history import to_step_points
from hatty.ui.graph.climate_history import hvac_action_runs
from hatty.ui.graph.downsample import minmax_downsample
from hatty.ui.graph.plot_time import secs_since, time_axis

# A binary step trace: (label, history, color). label/color may be None.
BinarySeries = tuple[str | None, list[tuple[str, float]], str | None]

# A numeric line/scatter series: (label, history, color). label/color may be None.
NumericSeries = tuple[str | None, list[tuple[str, float]], str | None]

# The canonical plotext mode registry; surfaces that also offer a sparkline
# mode prepend their own sparkline entries.
PLOTEXT_MODES = [
    ("line", "Line"),
    ("scatter", "Scatter"),
]

# Default per-line cycling palette for comparison graphs. Every entry must be
# a valid plotext color name present in graph_color_popup.ALL_PLOT_COLORS
# (the full picker list; guarded by a test there).
DEFAULT_COLOR_PALETTE = ["blue", "red", "green", "orange", "magenta", "cyan", "green+", "red+"]

NO_CLIMATE_DATA = "No climate history data available."


def plot_width(plot, fallback: int = 200) -> int:
    """Usable plot width in cells for downsampling; a robust fallback keeps it
    sane before the first layout pass sizes the widget."""
    width = getattr(plot.size, "width", 0) or 0
    return max(20, width if width > 0 else fallback)


def earliest_t0(primary: list[tuple[str, float]], *extra_series: list) -> datetime:
    """The graphs' shared x origin: the primary series' first timestamp,
    pulled earlier by any extra series that starts before it."""
    t0 = datetime.fromisoformat(primary[0][0])
    for hist in extra_series:
        if hist:
            t_first = datetime.fromisoformat(hist[0][0])
            if t_first < t0:
                t0 = t_first
    return t0


def apply_time_axis(plt, t0: datetime, total_secs: float) -> None:
    """Set the hh:mm / date xticks and the gray day-change guide lines."""
    tick_pos, tick_labels, day_positions = time_axis(t0, total_secs)
    plt.xticks(tick_pos, tick_labels)
    for day_pos in day_positions:
        plt.vline(day_pos, color="gray")


def plot_numeric_series(plt, kind: str, indices: list[float], values: list[float], width: int, label=None, color=None):
    """One line/scatter series, min/max-downsampled to the plot width. The raw
    series is untouched, so stats and cursor inspection still see every reading."""
    ds_i, ds_v = minmax_downsample(indices, values, width)
    if kind == "line":
        plt.plot(ds_i, ds_v, label=label, color=color)
    else:
        plt.scatter(ds_i, ds_v, label=label, color=color)


def render_numeric(
    plt,
    kind: str,
    primary: NumericSeries,
    extras: Sequence[NumericSeries],
    width: int,
    *,
    cursor_index: int | None = None,
) -> None:
    """Plot a numeric line/scatter trace for `primary` plus any non-empty
    `extras`, all sharing one x-origin and time axis.

    Owns the shared draw both graph surfaces used to hand-roll: the shared
    x-origin over primary+extras, the `apply_time_axis`, and the per-series
    `plot_numeric_series` calls. When `cursor_index` is given, drops a white
    inspection vline at the primary series' sample at that index (clamped)."""
    _, primary_data, primary_color = primary
    t0 = earliest_t0(primary_data, *(data for _, data, _ in extras))
    to_secs = secs_since(t0)
    indices = [to_secs(ts) for ts, _ in primary_data]
    values = [v for _, v in primary_data]
    total_secs = max(indices) if indices else 1
    apply_time_axis(plt, t0, total_secs)
    plot_numeric_series(plt, kind, indices, values, width, label=primary[0], color=primary_color)

    for label, data, color in extras:
        if not data:
            continue
        extra_indices = [to_secs(ts) for ts, _ in data]
        extra_values = [v for _, v in data]
        plot_numeric_series(plt, kind, extra_indices, extra_values, width, label=label, color=color)

    if cursor_index is not None and indices:
        cursor_index = max(0, min(len(indices) - 1, cursor_index))
        plt.vline(indices[cursor_index], color="white")


def set_binary_axis(plt) -> None:
    plt.yticks([0, 1], ["off", "on"])
    plt.ylim(-0.15, 1.15)


def render_binary(plt, primary: BinarySeries, extras, *, extend_to: str | None) -> datetime:
    """Plot a binary (on/off) step trace for `primary` plus any binary-shaped
    `extras`, extending each trace to `extend_to` (the window edge or "now").

    Owns the shared draw both graph surfaces used to hand-roll: the binary-only
    extras filter (numeric series can't sit on the 0/1 axis), the shared x-origin
    and time axis, the `to_step_points → plt.plot` loop, and `set_binary_axis`.
    Returns t0 (the x-origin) so a caller can place a cursor marker."""
    series: list[BinarySeries] = [primary] + [s for s in extras if s[1] and all(v in (0.0, 1.0) for _, v in s[1])]
    t0 = min(datetime.fromisoformat(hist[0][0]) for _, hist, _ in series)
    to_secs = secs_since(t0)
    total_secs = (
        max(
            max((to_secs(hist[-1][0]) for _, hist, _ in series), default=1.0),
            to_secs(extend_to) if extend_to else 0.0,
        )
        or 1.0
    )
    apply_time_axis(plt, t0, total_secs)
    for label, hist, color in series:
        steps = to_step_points(hist, extend_to=extend_to)
        plt.plot([to_secs(ts) for ts, _ in steps], [v for _, v in steps], label=label, color=color)
    set_binary_axis(plt)
    return t0


def numeric_stats_line(values: list[float], unit: str) -> str:
    mn, mx = min(values), max(values)
    avg = sum(values) / len(values)
    return f"min: {mn:.1f}{unit}   avg: {avg:.1f}{unit}   max: {mx:.1f}{unit}   ({len(values)} readings)"


def render_climate(plt, data: list[dict]) -> str:
    """Plot the fixed climate view (Current/Target temperature lines plus the
    red/blue hvac_action strip along the floor) onto `plt` and return the
    stats line. Returns NO_CLIMATE_DATA without plotting when there is nothing
    usable to show."""
    current_pts = [(e["ts"], e["current_temperature"]) for e in data if e.get("current_temperature") is not None]
    target_pts = [(e["ts"], e["target_temperature"]) for e in data if e.get("target_temperature") is not None]

    if not data or (not current_pts and not target_pts):
        return NO_CLIMATE_DATA

    t0 = datetime.fromisoformat(data[0]["ts"])
    _to_secs = secs_since(t0)

    total_secs = max((_to_secs(e["ts"]) for e in data), default=1) or 1
    apply_time_axis(plt, t0, total_secs)

    all_values = [v for _, v in current_pts] + [v for _, v in target_pts]
    if current_pts:
        plt.plot([_to_secs(ts) for ts, _ in current_pts], [v for _, v in current_pts], label="Current")
    if target_pts:
        plt.plot([_to_secs(ts) for ts, _ in target_pts], [v for _, v in target_pts], label="Target")

    floor = min(all_values) - 1
    runs = hvac_action_runs(data)
    for start_ts, end_ts, action in runs:
        color = "red" if action == "heating" else "blue"
        plt.plot([_to_secs(start_ts), _to_secs(end_ts)], [floor, floor], color=color)

    last = data[-1]
    parts = []
    if last.get("current_temperature") is not None:
        parts.append(f"current: {last['current_temperature']:.1f}")
    if last.get("target_temperature") is not None:
        parts.append(f"target: {last['target_temperature']:.1f}")
    stats_text = "   ".join(parts)
    if runs:
        stats_text += "   (red=heating  blue=cooling)"
    return stats_text or NO_CLIMATE_DATA
