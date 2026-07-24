# hatty — MIT License. See LICENSE file for details.
from textual.coordinate import Coordinate

from hatty.ui.entity_table import EntitiesTable
from tests.conftest import make_config

_NO_LIST_CONFIG = make_config(lists={})

# Alphabetical order with no list:
# Row 0: Fan Switch (switch.fan, off)
# Row 1: Kitchen Light (light.kitchen_light, off)
# Row 2: Living Room Lamp (light.living_room_lamp, on)
# Row 3: Temperature Sensor (sensor.temperature, 21.5)


async def test_enter_calls_turn_on_for_off_switch(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        calls = app.client.call_service_calls
        assert calls == [("switch", "turn_on", {"entity_id": "switch.fan"})]


async def test_enter_calls_turn_off_for_on_light(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(2, 0)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        calls = app.client.call_service_calls
        assert calls == [("light", "turn_off", {"entity_id": "light.living_room_lamp"})]


async def test_enter_does_nothing_for_sensor(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.client.call_service_calls == []


async def test_state_change_event_updates_table(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        assert str(table.get_row_at(0)[1]) == "off"

        app.client.inject_state_change(
            {
                "entity_id": "switch.fan",
                "state": "on",
                "attributes": {"friendly_name": "Fan Switch"},
                "last_changed": "2024-01-15T11:00:00.000000+00:00",
            }
        )
        await pilot.pause()

        assert str(table.get_row_at(0)[1]) == "on"
