# hatty — MIT License. See LICENSE file for details.
from textual.coordinate import Coordinate
from textual.widgets import Button, Input

from hatty.ui.entity_table import EntitiesTable
from hatty.ui.rename_entity_popup import RenameEntityPopup
from tests.conftest import make_config, notified

_NO_LIST_CONFIG = make_config(lists={})

# Alphabetical order for sample_entities (see tests/conftest.py):
# Row 0: Fan Switch, 1: Kitchen Light, 2: Living Room Lamp, 3: Temperature Sensor


async def test_local_name_override_applied_on_initial_load(make_app, sample_entities):
    config_data = dict(_NO_LIST_CONFIG)
    config_data["entity_names"] = {"light.living_room_lamp": "Reading Light"}
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        names = [str(table.get_row_at(i)[0]) for i in range(table.row_count)]
        assert "Reading Light" in names
        assert "Living Room Lamp" not in names


async def test_name_override_survives_state_changed_event(make_app, sample_entities):
    config_data = dict(_NO_LIST_CONFIG)
    config_data["entity_names"] = {"switch.fan": "Overhead Fan"}
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client.inject_state_change(
            {
                "entity_id": "switch.fan",
                "state": "on",
                "attributes": {"friendly_name": "Fan Switch"},
                "last_changed": "2024-01-15T11:00:00.000000+00:00",
            }
        )
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        names = [str(table.get_row_at(i)[0]) for i in range(table.row_count)]
        assert "Overhead Fan" in names
        assert "Fan Switch" not in names


async def test_r_opens_rename_popup_with_current_name_prefilled(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(2, 0)  # Living Room Lamp
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        assert isinstance(app.screen, RenameEntityPopup)
        assert app.screen.query_one("#rename_input", Input).value == "Living Room Lamp"


async def test_r_opens_rename_popup_without_override_indicator(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(2, 0)  # Living Room Lamp
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        assert not app.screen.query(".override-hint")
        assert not app.screen.query("#btn_revert")


async def test_r_opens_rename_popup_with_override_indicator(make_app, sample_entities):
    config_data = dict(_NO_LIST_CONFIG)
    config_data["entity_names"] = {"light.living_room_lamp": "Reading Light"}
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(2, 0)  # Reading Light (overridden)
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        assert app.screen.query_one(".override-hint")
        assert app.screen.query_one("#btn_revert", Button)


async def test_revert_button_clears_override_and_restores_ha_name(make_app, sample_entities):
    config_data = dict(_NO_LIST_CONFIG)
    config_data["entity_names"] = {"light.living_room_lamp": "Reading Light"}
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(2, 0)  # Reading Light (overridden)
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()

        app.screen.query_one("#btn_revert", Button).press()
        await pilot.pause()

        assert not isinstance(app.screen, RenameEntityPopup)
        assert "light.living_room_lamp" not in app.entity_names
        names = [str(table.get_row_at(i)[0]) for i in range(table.row_count)]
        assert "Living Room Lamp" in names
        assert "Reading Light" not in names


async def test_save_locally_updates_table_display_immediately(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(2, 0)  # Living Room Lamp
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()

        app.screen.query_one("#rename_input", Input).value = "Reading Light"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(app.screen, RenameEntityPopup)
        names = [str(table.get_row_at(i)[0]) for i in range(table.row_count)]
        assert "Reading Light" in names
        assert "Living Room Lamp" not in names


async def test_save_locally_persists_to_config_file(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(2, 0)  # Living Room Lamp
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()

        app.screen.query_one("#rename_input", Input).value = "Reading Light"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        # entity_names persists to SQLite now (#63).
        assert app.storage.load_all()["entity_names"] == {"light.living_room_lamp": "Reading Light"}


async def test_save_locally_with_blank_name_clears_override(make_app, sample_entities):
    config_data = dict(_NO_LIST_CONFIG)
    config_data["entity_names"] = {"light.living_room_lamp": "Reading Light"}
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(2, 0)  # alphabetically: Fan, Kitchen, Reading Light, Temperature
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()

        app.screen.query_one("#rename_input", Input).value = ""
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert "light.living_room_lamp" not in app.entity_names
        names = [str(table.get_row_at(i)[0]) for i in range(table.row_count)]
        assert "Living Room Lamp" in names
        assert "Reading Light" not in names


async def test_escape_in_rename_popup_does_not_change_name(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(2, 0)  # Living Room Lamp
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()

        app.screen.query_one("#rename_input", Input).value = "Should Not Save"
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, RenameEntityPopup)
        assert app.entity_names == {}
        names = [str(table.get_row_at(i)[0]) for i in range(table.row_count)]
        assert "Living Room Lamp" in names


async def test_rename_noop_on_empty_table(make_app):
    app = make_app(entities=[], config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        assert not isinstance(app.screen, RenameEntityPopup)


async def test_save_to_ha_dispatches_update_entity_registry_call(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(2, 0)  # Living Room Lamp
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()

        app.screen.query_one("#rename_input", Input).value = "Reading Light"
        await pilot.pause()
        app.screen.query_one("#btn_save_ha", Button).press()
        await pilot.pause()

        assert app.client.update_entity_registry_calls == [("light.living_room_lamp", "Reading Light")]


async def test_save_to_ha_does_not_change_local_display_until_event_arrives(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(2, 0)  # Living Room Lamp
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()

        app.screen.query_one("#rename_input", Input).value = "Reading Light"
        await pilot.pause()
        app.screen.query_one("#btn_save_ha", Button).press()
        await pilot.pause()

        names = [str(table.get_row_at(i)[0]) for i in range(table.row_count)]
        assert "Living Room Lamp" in names
        assert "Reading Light" not in names


async def test_state_changed_event_after_ha_rename_updates_display(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(2, 0)  # Living Room Lamp
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()

        app.screen.query_one("#rename_input", Input).value = "Reading Light"
        await pilot.pause()
        app.screen.query_one("#btn_save_ha", Button).press()
        await pilot.pause()

        app.client.inject_state_change(
            {
                "entity_id": "light.living_room_lamp",
                "state": "on",
                "attributes": {"friendly_name": "Reading Light"},
                "last_changed": "2024-01-15T11:00:00.000000+00:00",
            }
        )
        await pilot.pause()

        names = [str(table.get_row_at(i)[0]) for i in range(table.row_count)]
        assert "Reading Light" in names
        assert "Living Room Lamp" not in names


async def test_save_to_ha_with_blank_name_sends_none(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(2, 0)  # Living Room Lamp
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()

        app.screen.query_one("#rename_input", Input).value = ""
        await pilot.pause()
        app.screen.query_one("#btn_save_ha", Button).press()
        await pilot.pause()

        assert app.client.update_entity_registry_calls == [("light.living_room_lamp", None)]


async def test_failed_ha_rename_notifies_error(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client.inject_failed_result("update_entity_registry")
        await pilot.pause()
        assert notified(app, title="Rename Error", message_contains="Failed to rename entity")
