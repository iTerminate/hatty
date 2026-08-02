# hatty — MIT License. See LICENSE file for details.
"""format_log_detail/format_log_datetime (issue #23): the untruncated
per-field text a LogEntryPopup shows for a selected entry — mirrors
test_log_line_format.py's style for format_log_line."""

from hatty.logbook import LogEntry, format_log_datetime, format_log_detail, format_log_time

_WHEN = "2024-01-15T12:00:00+00:00"
_HH_MM_SS = format_log_time(_WHEN)
_YYYY_MM_DD = format_log_datetime(_WHEN).split(" ")[0]


def _state_entry(**overrides) -> LogEntry:
    entry: LogEntry = {
        "when": _WHEN,
        "name": "Kitchen Light",
        "detail": "on",
        "entity_id": "light.kitchen",
        "kind": "state",
    }
    entry.update(overrides)
    return entry


def _event_entry(**overrides) -> LogEntry:
    entry: LogEntry = {
        "when": _WHEN,
        "name": "Living Room Button",
        "detail": "remote_button_short_press",
        "entity_id": "",
        "kind": "event",
    }
    entry.update(overrides)
    return entry


def test_datetime_combines_date_and_time():
    assert format_log_datetime(_WHEN) == f"{_YYYY_MM_DD} {_HH_MM_SS}"


def test_datetime_falls_back_on_empty_string():
    assert format_log_datetime("") == "??"


def test_datetime_falls_back_on_unparseable_string():
    assert format_log_datetime("not-a-date") == "not-a-date"


def test_state_entry_detail_has_four_lines():
    entry = _state_entry()
    detail = format_log_detail(entry)
    assert detail == f"{format_log_datetime(_WHEN)}\nKitchen Light\non\nlight.kitchen"


def test_event_entry_uses_lightning_prefixed_name():
    entry = _event_entry()
    detail = format_log_detail(entry)
    assert detail.splitlines()[1] == "⚡ Living Room Button"


def test_event_entry_with_no_entity_id_omits_that_line():
    entry = _event_entry()
    detail = format_log_detail(entry)
    assert len(detail.splitlines()) == 3


def test_detail_is_never_truncated_regardless_of_length():
    long_detail = "B" * 500
    entry = _state_entry(detail=long_detail)
    detail = format_log_detail(entry)
    assert long_detail in detail
    assert "…" not in detail


def test_detail_survives_empty_when():
    entry = _state_entry(when="")
    detail = format_log_detail(entry)
    assert detail.startswith("??\n")
