# hatty — MIT License. See LICENSE file for details.
from collections import deque

from hatty.main import _trim_history


def test_empty_buffer_is_a_no_op():
    buf = deque()
    _trim_history(buf, 4)
    assert buf == deque()


def test_nothing_evicted_when_all_entries_within_window():
    buf = deque([("2024-01-01T08:00:00+00:00", 1.0), ("2024-01-01T09:00:00+00:00", 2.0)])
    _trim_history(buf, 4)
    assert list(buf) == [("2024-01-01T08:00:00+00:00", 1.0), ("2024-01-01T09:00:00+00:00", 2.0)]


def test_entries_older_than_window_before_newest_are_evicted():
    buf = deque(
        [
            ("2024-01-01T08:00:00+00:00", 1.0),  # 2h before newest -> evicted (window is 1h)
            ("2024-01-01T09:30:00+00:00", 2.0),  # 30m before newest -> kept
            ("2024-01-01T10:00:00+00:00", 3.0),  # newest
        ]
    )
    _trim_history(buf, 1)
    assert list(buf) == [("2024-01-01T09:30:00+00:00", 2.0), ("2024-01-01T10:00:00+00:00", 3.0)]


def test_eviction_stops_at_first_still_valid_entry_from_the_front():
    buf = deque(
        [
            ("2024-01-01T08:00:00+00:00", 1.0),
            ("2024-01-01T09:59:00+00:00", 2.0),
            ("2024-01-01T10:00:00+00:00", 3.0),
        ]
    )
    _trim_history(buf, 1)
    assert list(buf) == [("2024-01-01T09:59:00+00:00", 2.0), ("2024-01-01T10:00:00+00:00", 3.0)]


def test_dict_shaped_entries_via_custom_ts_of():
    buf = deque(
        [
            {"ts": "2024-01-01T08:00:00+00:00"},
            {"ts": "2024-01-01T09:30:00+00:00"},
        ]
    )
    _trim_history(buf, 1, ts_of=lambda item: item["ts"])
    assert list(buf) == [{"ts": "2024-01-01T09:30:00+00:00"}]


def test_malformed_head_timestamp_is_dropped_defensively():
    buf = deque([("not-a-timestamp", 1.0), ("2024-01-01T10:00:00+00:00", 2.0)])
    _trim_history(buf, 1)
    assert list(buf) == [("2024-01-01T10:00:00+00:00", 2.0)]


def test_malformed_newest_timestamp_leaves_buffer_untouched():
    buf = deque([("2024-01-01T08:00:00+00:00", 1.0), ("not-a-timestamp", 2.0)])
    _trim_history(buf, 1)
    assert list(buf) == [("2024-01-01T08:00:00+00:00", 1.0), ("not-a-timestamp", 2.0)]
