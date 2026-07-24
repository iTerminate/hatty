# hatty — MIT License. See LICENSE file for details.
"""Shared x-axis time helpers for the plotext-based graph surfaces."""

import math
from datetime import datetime, time, timedelta

DAY_SECS = 86400


def secs_since(t0: datetime):
    """A closure mapping an ISO timestamp to seconds elapsed since ``t0`` — the
    x-coordinate every graph surface plots against. Replaces the ``_to_secs``
    closure that was defined verbatim across the graph modules."""

    def _to_secs(ts: str) -> float:
        return (datetime.fromisoformat(ts) - t0).total_seconds()

    return _to_secs


def ts_to_hhmm(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).astimezone().strftime("%H:%M")
    except Exception:
        return "??"


def ts_to_full(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).astimezone().strftime("%b %d %H:%M")
    except Exception:
        return "??"


def midnights_between(start: datetime, end: datetime) -> list[datetime]:
    """Local-time midnights strictly inside (start, end).

    Built from naive local dates re-localized per day (datetime.combine(...).astimezone()),
    not by stepping fixed 24h increments, so DST days keep their wall-clock midnight.
    """
    start_local = start.astimezone()
    end_local = end.astimezone()
    result = []
    day = start_local.date() + timedelta(days=1)
    while True:
        midnight = datetime.combine(day, time(0)).astimezone()
        if midnight >= end_local:
            break
        if midnight > start_local:
            result.append(midnight)
        day += timedelta(days=1)
    return result


def time_axis(t0: datetime, total_secs: float, max_day_ticks: int = 7) -> tuple[list[float], list[str], list[float]]:
    """Tick positions/labels plus day-boundary line positions for a window starting at t0.

    Positions are seconds offset from t0 (the graphs' shared x convention). Windows within
    a day keep the even 6-tick hh:mm axis; longer windows tick at (thinned) midnights with
    date labels and report every midnight for vertical day-change guide lines.
    """
    if total_secs <= DAY_SECS:
        step = total_secs / 5 if total_secs > 0 else 1
        positions = [i * step for i in range(6)]
        labels = [ts_to_hhmm((t0 + timedelta(seconds=s)).isoformat()) for s in positions]
        return positions, labels, []

    midnights = midnights_between(t0, t0 + timedelta(seconds=total_secs))
    day_positions = [(m - t0).total_seconds() for m in midnights]
    if not day_positions:
        step = total_secs / 5
        positions = [i * step for i in range(6)]
        labels = [ts_to_full((t0 + timedelta(seconds=s)).isoformat()) for s in positions]
        return positions, labels, []

    thin = max(1, math.ceil(len(midnights) / max_day_ticks))
    tick_positions = [p for i, p in enumerate(day_positions) if i % thin == 0]
    tick_labels = [m.strftime("%b %d") for i, m in enumerate(midnights) if i % thin == 0]
    return tick_positions, tick_labels, day_positions
