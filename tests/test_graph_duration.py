# hatty — MIT License. See LICENSE file for details.
from textual.coordinate import Coordinate
from textual.widgets import Input, RadioSet

from hatty.ui.entity_table import EntitiesTable
from hatty.ui.graph.duration_popup import GraphDurationPopup
from tests.conftest import make_config

_NO_LIST_CONFIG = make_config(lists={})


async def test_duration_popup_initially_focuses_radio_set(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()

        await pilot.press("T")
        await pilot.pause()

        popup = app.screen
        assert isinstance(popup, GraphDurationPopup)
        assert app.focused is popup.query_one(RadioSet)


async def test_custom_duration_input_overrides_preset_selection(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()

        await pilot.press("T")
        await pilot.pause()

        popup = app.screen
        assert isinstance(popup, GraphDurationPopup)
        popup.query_one("#duration_hours_input", Input).value = "1"
        popup.query_one("#duration_minutes_input", Input).value = "30"
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        assert app.app_config["graph_hours"] == 1.5


async def test_custom_minutes_only_input(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()

        await pilot.press("T")
        await pilot.pause()

        popup = app.screen
        popup.query_one("#duration_minutes_input", Input).value = "90"
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        assert app.app_config["graph_hours"] == 1.5


async def test_blank_custom_inputs_fall_back_to_preset_radio(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()

        await pilot.press("T")
        await pilot.pause()

        popup = app.screen
        radio_set = popup.query_one(RadioSet)
        radio_set.action_toggle_button()  # highlighted button starts at index 0 (1 hour)
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        assert app.app_config["graph_hours"] == 1


async def test_invalid_custom_duration_does_not_dismiss_popup(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()

        await pilot.press("T")
        await pilot.pause()

        popup = app.screen
        assert isinstance(popup, GraphDurationPopup)
        popup.query_one("#duration_hours_input", Input).value = "not-a-number"
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        assert app.screen is popup


async def test_confirm_with_no_selection_and_no_custom_input_is_a_no_op(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.app_config["graph_hours"] = 1.5  # a custom value, so no radio button starts pressed

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()

        await pilot.press("T")
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        assert app.app_config["graph_hours"] == 1.5


async def test_reopening_popup_with_custom_value_prefills_custom_inputs(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.app_config["graph_hours"] = 1.5

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()

        await pilot.press("T")
        await pilot.pause()

        popup = app.screen
        assert isinstance(popup, GraphDurationPopup)
        assert popup.query_one("#duration_hours_input", Input).value == "1"
        assert popup.query_one("#duration_minutes_input", Input).value == "30"
        assert popup.query_one(RadioSet).pressed_index == -1
