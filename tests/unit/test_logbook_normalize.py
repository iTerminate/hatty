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
    is_continuous_sensor,
    normalize_entries,
    normalize_entry,
    resolve_name,
    state_detail,
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


def test_state_detail_labels_binary_sensor_by_device_class():
    assert state_detail("binary_sensor.front_door", "on", "door") == "Open"
    assert state_detail("binary_sensor.front_door", "off", "door") == "Closed"


def test_state_detail_leaves_non_binary_sensor_domains_unchanged():
    assert state_detail("cover.garage", "open", "door") == "open"
    assert state_detail("switch.fan", "on", "switch") == "on"


def test_normalize_entry_applies_device_class_label_for_binary_sensor():
    raw = {"when": "2024-01-15T12:00:00+00:00", "name": "Front Door", "state": "on", "entity_id": "binary_sensor.d"}
    entry = normalize_entry(raw, {}, {}, {"binary_sensor.d": "door"})
    assert entry["detail"] == "Open"


def test_normalize_entry_without_device_classes_map_still_capitalizes_binary_sensor():
    """No device_classes map -> device_class defaults to "" -> the generic
    On/Off label (same fallback the dashboard binary_sensor widget uses)."""
    raw = {"when": "2024-01-15T12:00:00+00:00", "name": "Front Door", "state": "on", "entity_id": "binary_sensor.d"}
    entry = normalize_entry(raw, {}, {})
    assert entry["detail"] == "On"


def test_normalize_entry_leaves_non_binary_sensor_state_raw():
    raw = {"when": "2024-01-15T12:00:00+00:00", "name": "Fan", "state": "on", "entity_id": "switch.fan"}
    entry = normalize_entry(raw, {}, {})
    assert entry["detail"] == "on"


def test_format_log_time_handles_empty_and_malformed():
    assert format_log_time("") == "??:??:??"
    assert format_log_time("garbage") == "??:??:??"  # too short for the [:8] fallback
    assert format_log_time("not-a-real-timestamp") == "not-a-re"  # [:8] fallback on longer garbage


def test_is_continuous_sensor_true_for_unit_or_state_class():
    assert is_continuous_sensor("sensor.temp", {"unit_of_measurement": "°C"}) is True
    assert is_continuous_sensor("sensor.count", {"state_class": "total_increasing"}) is True


def test_is_continuous_sensor_false_for_non_sensor_domain():
    assert is_continuous_sensor("binary_sensor.door", {"unit_of_measurement": "°C"}) is False


def test_is_continuous_sensor_false_without_unit_or_state_class():
    assert is_continuous_sensor("sensor.mode", {}) is False


def test_state_detail_appends_unit_for_numeric_state():
    assert state_detail("sensor.temp", "21.5", "", "°C") == "21.5 °C"


def test_state_detail_omits_unit_for_non_numeric_state():
    assert state_detail("sensor.temp", "unavailable", "", "°C") == "unavailable"
    assert state_detail("sensor.temp", "unknown", "", "°C") == "unknown"


def test_state_detail_unit_is_a_noop_when_absent():
    assert state_detail("sensor.temp", "21.5", "") == "21.5"


def test_state_detail_binary_sensor_ignores_unit():
    assert state_detail("binary_sensor.door", "on", "door", "°C") == "Open"


def test_normalize_entry_applies_unit_for_numeric_sensor():
    raw = {"when": "2024-01-15T12:00:00+00:00", "name": "Temp", "state": "21.5", "entity_id": "sensor.temp"}
    entry = normalize_entry(raw, {}, {}, units={"sensor.temp": "°C"})
    assert entry["detail"] == "21.5 °C"
