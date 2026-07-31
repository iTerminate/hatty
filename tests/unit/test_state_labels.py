# hatty — MIT License. See LICENSE file for details.
from hatty.const import binary_state_label


def test_door_device_class_labels():
    assert binary_state_label("on", "door") == "Open"
    assert binary_state_label("off", "door") == "Closed"


def test_unknown_device_class_falls_back_to_on_off():
    assert binary_state_label("on", "") == "On"
    assert binary_state_label("off", "nonexistent_class") == "Off"


def test_non_on_off_state_passes_through():
    assert binary_state_label("unavailable", "door") == "unavailable"
    assert binary_state_label("unknown", "") == "unknown"
