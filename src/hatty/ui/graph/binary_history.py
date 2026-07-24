# hatty — MIT License. See LICENSE file for details.
"""Pure helpers for rendering binary (on/off) entity history as step traces."""

from datetime import datetime


def is_on(value: float) -> bool:
    """The single home for the 0/1 → on/off convention: a plotted value is "on"
    at or above the 0.5 midpoint."""
    return value >= 0.5


def value_to_state(value: float) -> str:
    return "on" if is_on(value) else "off"


def to_step_points(
    data: list[tuple[str, float]], extend_to: str | None = None
) -> list[tuple[str, float]]:
    """Expand state-change samples into square-step segments.

    Binary state changes are instantaneous, so a sloped line between an 'off' at
    09:00 and an 'on' at 14:00 reads as a gradual rise. For consecutive samples
    (t1, v1), (t2, v2) this emits (t1, v1), (t2, v1), (t2, v2), and optionally
    extends the final value to `extend_to` (e.g. the window end or "now").
    """
    if not data:
        return []
    points: list[tuple[str, float]] = [data[0]]
    for (_, prev_value), (ts, value) in zip(data, data[1:]):
        if value != prev_value:
            points.append((ts, prev_value))
        points.append((ts, value))
    last_ts, last_value = data[-1]
    if extend_to is not None and extend_to > last_ts:
        points.append((extend_to, last_value))
    return points


def binary_stats(data: list[tuple[str, float]], end_ts: str | None = None) -> str:
    """Stats line for a binary trace: percentage of time on, change count, last state."""
    if not data:
        return "No history data available."
    changes = sum(1 for (_, a), (_, b) in zip(data, data[1:]) if a != b)
    last_ts, last_value = data[-1]
    last_state = value_to_state(last_value)

    try:
        start = datetime.fromisoformat(data[0][0])
        end = datetime.fromisoformat(end_ts) if end_ts and end_ts > last_ts else datetime.fromisoformat(last_ts)
        total = (end - start).total_seconds()
        on_secs = 0.0
        for (ts, value), (next_ts, _) in zip(data, data[1:]):
            if is_on(value):
                on_secs += (datetime.fromisoformat(next_ts) - datetime.fromisoformat(ts)).total_seconds()
        if is_on(last_value):
            on_secs += (end - datetime.fromisoformat(last_ts)).total_seconds()
        on_pct = f"{on_secs / total * 100:.0f}%" if total > 0 else "—"
    except ValueError:
        on_pct = "—"

    last_hhmm = ""
    try:
        last_hhmm = f" since {datetime.fromisoformat(last_ts).astimezone().strftime('%H:%M')}"
    except ValueError:
        pass
    return f"on {on_pct} of window   {changes} changes   last: {last_state}{last_hhmm}"
