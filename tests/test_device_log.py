# hatty — MIT License. See LICENSE file for details.
import pytest
from textual.coordinate import Coordinate
from textual.widgets import Label, Log

from hatty.ui.activity_log_panel import ActivityLogPanel
from tests.conftest import make_config

_NO_LIST_CONFIG = make_config(lists={})


@pytest.fixture
def sample_registry():
    return [
        {"entity_id": "light.living_room_lamp", "device_id": "dev_abc"},
        {"entity_id": "light.kitchen_light", "device_id": "dev_abc"},
        {"entity_id": "sensor.temperature", "device_id": "dev_xyz"},
        {"entity_id": "switch.fan", "device_id": None},
    ]


# With _NO_LIST_CONFIG + sample_entities, alphabetical sort by friendly name:
# Row 0: switch.fan         (Fan Switch)
# Row 1: light.kitchen_light  (Kitchen Light)
# Row 2: light.living_room_lamp  (Living Room Lamp)
# Row 3: sensor.temperature  (Temperature Sensor)


async def test_A_opens_device_log_panel(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(2, 0)  # light.living_room_lamp
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")


async def test_device_log_title_shows_device_log_and_entity_name(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(2, 0)  # light.living_room_lamp
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        title = str(panel.query_one("#log_title", Label).content)
        assert "Device Log" in title
        assert "Living Room Lamp" in title


async def test_device_log_tracks_sibling_entity_ids(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(2, 0)  # light.living_room_lamp
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        assert app._log_entity_ids == {"light.living_room_lamp", "light.kitchen_light"}


async def test_A_closes_panel_when_already_open(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG, registry=sample_registry)
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
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG, registry=sample_registry)
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
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG, registry=sample_registry)
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
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG, registry=sample_registry)
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
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        entity_ids, label, device_found = app._get_device_entity_ids("light.living_room_lamp")
        assert device_found is True
        assert set(entity_ids) == {"light.living_room_lamp", "light.kitchen_light"}
        assert "Living Room Lamp" in label


async def test_get_device_entity_ids_fallback_empty_device_id(make_app, sample_entities):
    registry_with_empty = [
        {"entity_id": "light.living_room_lamp", "device_id": ""},
    ]
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG, registry=registry_with_empty)
    async with app.run_test():
        entity_ids, label, device_found = app._get_device_entity_ids("light.living_room_lamp")
        assert device_found is False
        assert entity_ids == ["light.living_room_lamp"]


async def test_A_when_no_entities_stays_hidden(make_app):
    app = make_app(entities=[], config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert not panel.has_class("-visible")


async def test_a_when_device_log_open_closes_panel(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(2, 0)
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        assert app.query_one("#activity_log_panel", ActivityLogPanel).has_class("-visible")
        await pilot.press("a")
        await pilot.pause()
        assert not app.query_one("#activity_log_panel", ActivityLogPanel).has_class("-visible")


async def test_A_opens_device_log_for_entity_with_different_device(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.cursor_coordinate = Coordinate(3, 0)  # sensor.temperature (dev_xyz, solo)
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        assert app._log_entity_ids == {"sensor.temperature"}
