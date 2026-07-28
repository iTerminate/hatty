# hatty — MIT License. See LICENSE file for details.
"""hatty.logbook's pure normalizer (issue #17) — resolving the shape
difference between REST /api/logbook entries and WS logbook/get_events
entries (epoch `when`, missing `name` on state entries) into one LogEntry."""

from datetime import datetime, timezone

from hatty.logbook import (
    compact_message,
    entry_kind,
    entry_when_iso,
    format_log_time,
    normalize_entries,
    normalize_entry,
    resolve_name,
)


def test_entry_when_iso_converts_epoch_float():
    when = entry_when_iso(1705320000.0)
    assert when == datetime.fromtimestamp(1705320000.0, timezone.utc).isoformat()


def test_entry_when_iso_passes_through_iso_string():
    assert entry_when_iso("2024-01-15T12:00:00+00:00") == "2024-01-15T12:00:00+00:00"


def test_entry_when_iso_stamps_utc_on_naive_iso_string():
    assert entry_when_iso("2024-01-15T12:00:00") == "2024-01-15T12:00:00+00:00"


def test_entry_when_iso_returns_empty_string_on_garbage():
    assert entry_when_iso("not a timestamp") == ""
    assert entry_when_iso(None) == ""
    assert entry_when_iso({}) == ""


def test_entry_kind_state_when_state_key_present():
    assert entry_kind({"state": "on", "entity_id": "light.x"}) == "state"


def test_entry_kind_event_when_only_message_present():
    assert entry_kind({"message": "was fired"}) == "event"


def test_entry_kind_defaults_to_state_when_neither_present():
    assert entry_kind({}) == "state"


def test_compact_message_trims_trailing_params():
    msg = "remote_button_short_press event was fired with parameters: {'device_ieee': '00:11'}"
    assert compact_message(msg) == "remote_button_short_press"


def test_compact_message_is_a_noop_without_the_marker():
    assert compact_message("something unrelated") == "something unrelated"


def test_resolve_name_prefers_raw_name():
    raw = {"name": "Living Room Button", "entity_id": "sensor.x"}
    assert resolve_name(raw, {"sensor.x": "Other Name"}, {}) == "Living Room Button"


def test_resolve_name_falls_back_to_entity_names():
    raw = {"entity_id": "sensor.x"}
    assert resolve_name(raw, {"sensor.x": "Kitchen Sensor"}, {}) == "Kitchen Sensor"


def test_resolve_name_falls_back_to_device_names():
    raw = {"device_id": "dev_1"}
    assert resolve_name(raw, {}, {"dev_1": "Living Room Button"}) == "Living Room Button"


def test_resolve_name_falls_back_to_entity_id():
    raw = {"entity_id": "sensor.unknown"}
    assert resolve_name(raw, {}, {}) == "sensor.unknown"


def test_resolve_name_falls_back_to_domain():
    raw = {"domain": "zha"}
    assert resolve_name(raw, {}, {}) == "zha"


def test_resolve_name_last_resort_literal():
    assert resolve_name({}, {}, {}) == "unknown"


def test_normalize_entry_state_shape():
    raw = {"when": "2024-01-15T12:00:00+00:00", "name": "Kitchen Light", "state": "on", "entity_id": "light.k"}
    entry = normalize_entry(raw, {}, {})
    assert entry == {
        "when": "2024-01-15T12:00:00+00:00",
        "name": "Kitchen Light",
        "detail": "on",
        "entity_id": "light.k",
        "kind": "state",
    }


def test_normalize_entry_event_shape_compacts_message():
    raw = {
        "when": 1705320000.0,
        "name": "Living Room Button",
        "message": "remote_button_short_press event was fired with parameters: {'x': 1}",
        "domain": "zha",
    }
    entry = normalize_entry(raw, {}, {})
    assert entry["kind"] == "event"
    assert entry["detail"] == "remote_button_short_press"
    assert entry["entity_id"] == ""
    assert entry["name"] == "Living Room Button"


def test_normalize_entries_skips_non_dicts_and_preserves_order():
    raw = [
        {"when": "2024-01-15T10:00:00+00:00", "state": "on"},
        "garbage",
        None,
        {"when": "2024-01-15T11:00:00+00:00", "state": "off"},
    ]
    entries = normalize_entries(raw, {}, {})
    assert [e["when"] for e in entries] == ["2024-01-15T10:00:00+00:00", "2024-01-15T11:00:00+00:00"]


def test_format_log_time_handles_empty_and_malformed():
    assert format_log_time("") == "??:??:??"
    assert format_log_time("garbage") == "??:??:??"  # too short for the [:8] fallback
    assert format_log_time("not-a-real-timestamp") == "not-a-re"  # [:8] fallback on longer garbage
