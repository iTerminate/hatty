# hatty — MIT License. See LICENSE file for details.
import time as time_module
from datetime import datetime, timedelta, timezone

import pytest

from hatty.ui.graph.plot_time import midnights_between, secs_since, time_axis, ts_to_full, ts_to_hhmm


def test_secs_since_returns_elapsed_seconds():
    t0 = datetime.fromisoformat("2026-07-07T10:00:00+00:00")
    to_secs = secs_since(t0)
    assert to_secs("2026-07-07T10:00:00+00:00") == 0.0
    assert to_secs("2026-07-07T11:30:00+00:00") == 5400.0
    assert to_secs("2026-07-07T09:00:00+00:00") == -3600.0


@pytest.fixture
def warsaw_tz(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Warsaw")
    time_module.tzset()
    yield
    monkeypatch.delenv("TZ", raising=False)
    time_module.tzset()


def test_short_window_has_no_midnights(warsaw_tz):
    start = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    assert midnights_between(start, start + timedelta(hours=4)) == []


def test_36h_window_has_expected_midnights(warsaw_tz):
    # 12:00 local July 1 → 00:00 local July 2 and July 3 fall inside a 36h+ window
    start = datetime(2026, 7, 1, 12, 0).astimezone()
    mids = midnights_between(start, start + timedelta(hours=38))
    assert [m.hour for m in mids] == [0, 0]
    assert [(m.month, m.day) for m in mids] == [(7, 2), (7, 3)]


def test_midnight_start_is_excluded(warsaw_tz):
    start = datetime(2026, 7, 1, 0, 0).astimezone()
    mids = midnights_between(start, start + timedelta(hours=24))
    assert mids == []  # start midnight excluded, end midnight excluded (strictly inside)


def test_dst_spring_forward_day_is_23_hours(warsaw_tz):
    # Europe/Warsaw jumps 02:00→03:00 on 2026-03-29, so that day has 23 hours.
    start = datetime(2026, 3, 28, 12, 0).astimezone()
    mids = midnights_between(start, start + timedelta(hours=48))
    positions = [(m - start).total_seconds() for m in mids]
    assert positions == [12 * 3600, (12 + 23) * 3600]


def test_time_axis_short_window_even_hhmm_ticks(warsaw_tz):
    t0 = datetime(2026, 7, 1, 10, 0).astimezone()
    positions, labels, day_lines = time_axis(t0, 4 * 3600)
    assert len(positions) == 6
    assert positions[0] == 0
    assert positions[-1] == 4 * 3600
    assert labels[0] == "10:00"
    assert day_lines == []


def test_time_axis_multiday_ticks_at_midnights(warsaw_tz):
    t0 = datetime(2026, 7, 1, 12, 0).astimezone()
    total = 3 * 24 * 3600.0
    positions, labels, day_lines = time_axis(t0, total)
    assert positions == day_lines == [12 * 3600, 36 * 3600, 60 * 3600]
    assert labels == ["Jul 02", "Jul 03", "Jul 04"]


def test_time_axis_long_window_thins_ticks_but_keeps_all_day_lines(warsaw_tz):
    t0 = datetime(2026, 7, 1, 12, 0).astimezone()
    total = 21 * 24 * 3600.0  # 21 midnights
    positions, labels, day_lines = time_axis(t0, total)
    assert len(day_lines) == 21
    assert len(positions) <= 7
    assert set(positions) <= set(day_lines)
    assert len(labels) == len(positions)


def test_ts_helpers_tolerate_garbage():
    assert ts_to_hhmm("not-a-date") == "??"
    assert ts_to_full("not-a-date") == "??"
