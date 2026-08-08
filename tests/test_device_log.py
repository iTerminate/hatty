# hatty — MIT License. See LICENSE file for details.
"""Device-scoped activity log on the main screen (issue #18), reached via
the `v` scope popup (issue #38, replacing the old blind cycle from #27)."""

from textual.coordinate import Coordinate
from textual.widgets import Label

from hatty.ui.activity_log_panel import ActivityLogPanel
from tests.conftest import NO_LIST_CONFIG, notified
from tests.test_log_scope_popup import _pick_via_popup

# sample_registry fixture is shared from tests/conftest.py.

# With NO_LIST_CONFIG + sample_entities, alphabetical sort by friendly name:
# Row 0: switch.fan         (Fan Switch)
# Row 1: light.kitchen_light  (Kitchen Light)
# Row 2: light.living_room_lamp  (Living Room Lamp)
# Row 3: sensor.temperature  (Temperature Sensor)


async def test_i_v_applies_device_scope_via_popup(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(2, 0)  # light.living_room_lamp
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()

        await _pick_via_popup(pilot, 1)  # entities_devices

        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")
        title = str(panel.query_one("#log_title", Label).content)
        assert "Device Log" in title
        assert "Living Room Lamp" in title
        # This view widens the event-type query, not the entity set.
        assert app.log_ctl.session_for(app).entity_ids == {"light.living_room_lamp"}
        # issue #17: the device view is the one scope that queries device-scoped events.
        assert app.client.logbook_calls[-1][3] == ["dev_abc"]


async def test_capital_a_is_no_longer_bound(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(2, 0)
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert not panel.has_class("-visible")


async def test_a_closes_device_log_view(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(2, 0)
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        await _pick_via_popup(pilot, 1)  # entities_devices
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")
        await pilot.press("a")
        await pilot.pause()
        assert not panel.has_class("-visible")


async def test_device_log_fallback_when_no_device_id(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(0, 0)  # switch.fan (no device_id)
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")
        assert app.log_ctl.session_for(app).entity_ids == {"switch.fan"}


async def test_cursor_device_with_no_device_notifies_and_omits_device_id(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(0, 0)  # switch.fan (no device_id)
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()

        await _pick_via_popup(pilot, 3)  # cursor_device

        assert app.client.logbook_calls[-1][3] == []
        assert notified(app, title="Device Log", message_contains="No device found")


async def test_v_scopes_to_graphed_entitys_device_over_the_lists_devices(make_app, sample_entities, sample_registry):
    """A graphed entity's device takes priority over expanding the whole
    active list's devices (issue #14) — sensor.temperature (dev_xyz, solo)
    graphed while `my_list` (light.living_room_lamp + sensor.temperature,
    spanning dev_abc and dev_xyz) is active should log only dev_xyz."""
    config = {
        "home_assistant": {"url": "http://fake.ha.local:8123", "token": "fake_token_abc"},
        "default_list": "my_list",
        "lists": {"my_list": ["sensor.temperature", "light.living_room_lamp"]},
    }
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.jump_cursor_to_row_key("sensor.temperature")
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()

        await pilot.press("a")
        await pilot.pause()
        assert app.log_ctl.session_for(app).entity_ids == {"sensor.temperature"}

        await _pick_via_popup(pilot, 1)  # entities_devices

        assert app.log_ctl.session_for(app).entity_ids == {"sensor.temperature"}
        title = str(app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_title", Label).content)
        assert "Device Log" in title
        assert "Temperature Sensor" in title
        assert "devices)" not in title  # a single device never shows the count suffix
