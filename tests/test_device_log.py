# hatty — MIT License. See LICENSE file for details.
from textual.coordinate import Coordinate
from textual.widgets import Label, Log

from hatty.ui.activity_log_panel import ActivityLogPanel
from tests.conftest import NO_LIST_CONFIG

# sample_registry fixture is shared from tests/conftest.py.

# With NO_LIST_CONFIG + sample_entities, alphabetical sort by friendly name:
# Row 0: switch.fan         (Fan Switch)
# Row 1: light.kitchen_light  (Kitchen Light)
# Row 2: light.living_room_lamp  (Living Room Lamp)
# Row 3: sensor.temperature  (Temperature Sensor)


async def test_i_v_advances_to_device_view_and_sends_the_entitys_device_id(
    make_app, sample_entities, sample_registry
):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(2, 0)  # light.living_room_lamp
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()

        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")
        title = str(panel.query_one("#log_title", Label).content)
        assert "Device Log" in title
        assert "Living Room Lamp" in title
        # This view widens the event-type query, not the entity set.
        assert app.log_ctl.session_for(app).entity_ids == {"light.living_room_lamp"}
        # issue #17: the device view is the one scope that queries device-scoped events.
        assert app.client.logbook_calls[-1][3] == ["dev_abc"]


async def test_v_sends_no_device_id_when_entity_has_no_device(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(0, 0)  # switch.fan (no device_id)
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        assert app.client.logbook_calls[-1][3] == []


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
        await pilot.press("v")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")
        await pilot.press("a")
        await pilot.pause()
        assert not panel.has_class("-visible")


async def test_device_log_live_update_from_sibling(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(2, 0)  # light.living_room_lamp
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("v")  # base_devices
        await pilot.pause()
        await pilot.press("v")  # cursor
        await pilot.pause()
        await pilot.press("v")  # cursor_device: sibling kitchen_light is now in scope
        await pilot.pause()
        # Opening a live log auto-subscribes to logbook/event_stream (issue #19);
        # the raw state_changed append is then the fallback path, so simulate it
        # not being active here to keep testing the pre-#19 append mechanism.
        app.client.logbook_subscription_id = None
        log_widget = app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_widget", Log)
        count_before = log_widget.line_count

        app.client.inject_state_change(
            {
                "entity_id": "light.kitchen_light",
                "state": "on",
                "attributes": {"friendly_name": "Kitchen Light"},
                "last_changed": "2024-01-15T10:32:00.000000+00:00",
            }
        )
        await pilot.pause()
        assert log_widget.line_count == count_before + 1


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


async def test_v_is_a_noop_when_no_entities(make_app):
    app = make_app(entities=[], config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert not panel.has_class("-visible")


async def test_v_opens_device_log_for_entity_with_different_device(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(3, 0)  # sensor.temperature (dev_xyz, solo)
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        assert app.log_ctl.session_for(app).entity_ids == {"sensor.temperature"}


async def test_v_scopes_to_graphed_entity_and_wraps_after_two_views(make_app, sample_entities, sample_registry):
    """A graphed entity's device takes priority over expanding the whole
    active list's devices (issue #14) — sensor.temperature (dev_xyz, solo)
    graphed while `my_list` (light.living_room_lamp + sensor.temperature,
    spanning dev_abc and dev_xyz) is active should log only dev_xyz. A fixed
    (graph-based) scope offers no cursor views, so `v` wraps after 2 presses,
    unlike the 4-view table-base cycle (issue #27)."""
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

        await pilot.press("v")
        await pilot.pause()
        assert app.log_ctl.session_for(app).entity_ids == {"sensor.temperature"}
        title = str(app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_title", Label).content)
        assert "Device Log" in title
        assert "Temperature Sensor" in title
        assert "devices)" not in title  # a single device never shows the count suffix

        await pilot.press("v")  # wraps back to the plain entity view
        await pilot.pause()
        title = str(app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_title", Label).content)
        assert title.startswith("Activity Log")
