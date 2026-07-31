# hatty — MIT License. See LICENSE file for details.
"""format_log_line (issue #17): the display line for the activity/device log
panel, a 52-column docked, non-scrollable widget — overflow must truncate,
never wrap or get clipped by Textual silently."""

from hatty.logbook import LogEntry, format_log_line, format_log_time

_WHEN = "2024-01-15T12:00:00+00:00"
# format_log_time renders local wall-clock time — compute the expected prefix
# the same way rather than hardcoding a timezone-dependent string.
_HH_MM_SS = format_log_time(_WHEN)


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


def test_state_entry_uses_arrow_form():
    line = format_log_line(_state_entry(), width=50)
    assert line == f"[{_HH_MM_SS}] Kitchen Light → on"


def test_event_entry_uses_lightning_and_colon_form():
    line = format_log_line(_event_entry(), width=100)
    assert line == f"[{_HH_MM_SS}] ⚡ Living Room Button: remote_button_short_press"


def test_line_within_width_is_not_truncated():
    line = format_log_line(_state_entry(), width=100)
    assert not line.endswith("…")


def test_line_over_width_is_truncated_with_ellipsis():
    entry = _state_entry(name="A Very Long Entity Name That Goes On And On And On")
    line = format_log_line(entry, width=30)
    assert len(line) == 30
    assert line.endswith("…")


def test_event_line_budgets_one_cell_less_for_the_wide_lightning_glyph():
    """"⚡" (U+26A1) is East-Asian-Wide — 2 cells for 1 code point — so an
    event line that exactly fills a state line's budget must truncate one
    character earlier than a state line at the same width (issue #22)."""
    entry = _event_entry(name="A", detail="B" * 40)
    state_equivalent = _state_entry(name="A", detail="B" * 40)
    event_line = format_log_line(entry, width=30)
    state_line = format_log_line(state_equivalent, width=30)
    assert len(event_line) == len(state_line) - 1


def test_timestamp_prefix_is_never_truncated():
    entry = _state_entry(name="X" * 200)
    line = format_log_line(entry, width=20)
    assert line.startswith(f"[{_HH_MM_SS}] ")
