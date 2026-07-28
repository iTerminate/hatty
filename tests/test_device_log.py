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


async def test_A_opens_device_log_panel_with_title_and_sibling_ids(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(2, 0)  # light.living_room_lamp
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()

        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")
        title = str(panel.query_one("#log_title", Label).content)
        assert "Device Log" in title
        assert "Living Room Lamp" in title
        assert app._log_entity_ids == {"light.living_room_lamp", "light.kitchen_light"}
        # issue #17: A is the one scope that queries device-scoped events.
        assert app.client.logbook_calls[-1][3] == ["dev_abc"]


async def test_A_sends_no_device_id_when_entity_has_no_device(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(0, 0)  # switch.fan (no device_id)
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        assert app.client.logbook_calls[-1][3] == []


async def test_A_closes_panel_when_already_open(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(2, 0)
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert not panel.has_class("-visible")


async def test_a_closes_device_log_panel(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(2, 0)
        await pilot.pause()
        await pilot.press("A")
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
        await pilot.press("A")
        await pilot.pause()
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
        await pilot.press("A")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")
        assert app._log_entity_ids == {"switch.fan"}


async def test_get_device_entity_ids_returns_siblings(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        entity_ids, label, device_id = app._get_device_entity_ids("light.living_room_lamp")
        assert device_id == "dev_abc"
        assert set(entity_ids) == {"light.living_room_lamp", "light.kitchen_light"}
        assert "Living Room Lamp" in label


async def test_get_device_entity_ids_fallback_empty_device_id(make_app, sample_entities):
    registry_with_empty = [
        {"entity_id": "light.living_room_lamp", "device_id": ""},
    ]
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=registry_with_empty)
    async with app.run_test():
        entity_ids, label, device_id = app._get_device_entity_ids("light.living_room_lamp")
        assert device_id is None
        assert entity_ids == ["light.living_room_lamp"]


async def test_A_when_no_entities_stays_hidden(make_app):
    app = make_app(entities=[], config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert not panel.has_class("-visible")


async def test_A_opens_device_log_for_entity_with_different_device(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(3, 0)  # sensor.temperature (dev_xyz, solo)
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        assert app._log_entity_ids == {"sensor.temperature"}


async def test_A_scopes_to_graphed_entity_over_list_device_expansion(make_app, sample_entities, sample_registry):
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

        await pilot.press("A")
        await pilot.pause()
        assert app._log_entity_ids == {"sensor.temperature"}
        title = str(app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_title", Label).content)
        assert "Temperature Sensor" in title

        # A graph-scoped device log is already a single device — a second
        # press has nothing to narrow to, so it closes (issue #18).
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        await pilot.press("A")
        await pilot.pause()
        assert not panel.has_class("-visible")
        assert "devices)" not in title
