# hatty — MIT License. See LICENSE file for details.
"""demo_data's device-scoped logbook events (issue #17): --demo's proof that
the device log (A) surfaces more than entities do, plus the mixed epoch-float
/ ISO-string `when` sort that broke before the fix."""

from datetime import datetime

from hatty.demo.demo_data import demo_device_events, demo_logbook


def test_demo_device_events_only_for_known_devices():
    entries = demo_device_events(["dev_lr_button"], hours=24)
    assert entries
    assert all(e["domain"] == "zha" for e in entries)
    assert all(isinstance(e["when"], float) for e in entries)  # WS-shaped
    assert all("entity_id" not in e for e in entries)


def test_demo_device_events_empty_for_unknown_device():
    assert demo_device_events(["dev_unknown"], hours=24) == []


def test_demo_device_events_empty_for_no_devices():
    assert demo_device_events([], hours=24) == []


def test_demo_logbook_omits_device_events_without_device_ids():
    entries = demo_logbook(["light.living_room_lamp"], hours=24)
    assert all("message" not in e for e in entries)


def test_demo_logbook_includes_device_events_with_device_ids():
    entries = demo_logbook(["light.living_room_lamp"], hours=24, device_ids=["dev_lr_button"])
    assert any("message" in e for e in entries)
    assert any("state" in e for e in entries)


def test_demo_logbook_mixed_when_types_sort_without_raising():
    """The regression this fixes: entries.sort() on mixed str/float `when`
    used to raise TypeError before _when_key normalized both."""
    entries = demo_logbook(
        ["light.living_room_lamp", "switch.coffee_maker"], hours=24, device_ids=["dev_lr_button", "dev_front_door"]
    )
    whens = [w if isinstance(w := e["when"], float) else datetime.fromisoformat(w).timestamp() for e in entries]
    assert whens == sorted(whens, reverse=True)
