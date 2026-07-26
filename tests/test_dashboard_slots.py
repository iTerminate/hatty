# hatty — MIT License. See LICENSE file for details.
from textual.coordinate import Coordinate
from textual.widgets import Button, ListView, Select, Static

from hatty.ui.dashboard.screen import DashboardScreen, DashboardSlotWidget
from hatty.ui.dashboard.slot_popup import DashboardSlotPopup
from hatty.ui.dashboard.widgets.graph import GraphSlotWidget
from hatty.ui.dashboard.widgets.text import TextSlotWidget
from hatty.ui.entity_table import EntitiesTable
from hatty.ui.search_input import SearchInput
from tests.conftest import make_config


def _panel_list_labels(popup) -> list[str]:
    list_view = popup.query_one("#panel_added_list", ListView)
    return [str(item.children[0].content) for item in list_view.children]


async def test_a_opens_slot_popup_and_assigns_widget(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # enter edit mode
        await pilot.press("a")
        await pilot.pause()
        assert isinstance(app.screen, DashboardSlotPopup)

        app.screen.query_one("#btn_next_step", Button).press()
        await pilot.pause()

        await pilot.click("#entity_search_input")
        await pilot.press(*"temperature")
        await pilot.pause()
        await pilot.press("enter")  # submit search -> focuses entity table
        await pilot.press("enter")  # select highlighted (only) match
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)
        assert app.dashboards["Main"]["slots"] == [
            {"row": 0, "col": 0, "widget_type": "graph", "entity_id": "sensor.temperature"}
        ]
        selected = next(w for w in app.screen.query(DashboardSlotWidget) if w.row == 0 and w.col == 0)
        graph_widget = selected.query_one(GraphSlotWidget)
        assert graph_widget.entity_id == "sensor.temperature"
        assert "Temperature Sensor" in str(graph_widget.query_one("#slot_title").content)


async def test_assign_slot_with_no_entity_via_picker(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # enter edit mode
        await pilot.press("a")
        await pilot.pause()
        assert isinstance(app.screen, DashboardSlotPopup)

        app.screen.query_one("#btn_next_step", Button).press()
        await pilot.pause()

        await pilot.press("enter")  # submit empty search -> focuses entity table, cursor on "(no entity)"
        await pilot.press("enter")  # select "(no entity)"
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)
        assert app.dashboards["Main"]["slots"] == [{"row": 0, "col": 0, "widget_type": "graph", "entity_id": None}]


async def test_edit_existing_slot_starts_cursor_on_current_entity(make_app, open_dashboard):
    config_data = {
        **make_config(),
        "lists": {},
        "dashboards": {
            "Main": {
                "rows": 3,
                "cols": 3,
                "slots": [{"row": 0, "col": 0, "widget_type": "graph", "entity_id": "sensor.temperature"}],
            }
        },
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # enter edit mode
        await pilot.press("a")
        await pilot.pause()

        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)
        popup.query_one("#btn_next_step", Button).press()
        await pilot.pause()
        table = popup.query_one("#entity_picker_table", EntitiesTable)
        cell_key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0))
        assert cell_key.row_key.value == "sensor.temperature"


async def test_escape_cancels_slot_popup_without_changes(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # enter edit mode
        await pilot.press("a")
        await pilot.pause()
        assert isinstance(app.screen, DashboardSlotPopup)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
        assert app.dashboards["Main"]["slots"] == []


async def test_escape_in_entity_step_returns_to_type_step(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # enter edit mode
        await pilot.press("a")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)

        popup.query_one("#btn_next_step", Button).press()
        await pilot.pause()
        assert popup.query_one("#entity_picker_table").display is True

        await pilot.press("escape")
        await pilot.pause()

        assert isinstance(app.screen, DashboardSlotPopup)
        assert popup.query_one("#widget_type_select").display is True
        assert popup.query_one("#entity_picker_table").display is False

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)


async def test_clear_slot_removes_assignment(make_app, open_dashboard):
    config_data = {
        **make_config(),
        "lists": {},
        "dashboards": {
            "Main": {
                "rows": 3,
                "cols": 3,
                "slots": [{"row": 0, "col": 0, "widget_type": "graph", "entity_id": "sensor.temperature"}],
            }
        },
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # enter edit mode
        await pilot.press("delete")
        await pilot.pause()
        assert app.dashboards["Main"]["slots"] == []
        selected = next(w for w in app.screen.query(DashboardSlotWidget) if w.row == 0 and w.col == 0)
        assert str(selected.query_one("#slot_empty", Static).content) == "Empty"


async def test_panel_slot_built_via_pick_one_add_continue_flow(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # enter edit mode
        await pilot.press("a")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)

        popup.query_one("#widget_type_select", Select).value = "panel"
        await pilot.pause()
        popup.query_one("#btn_next_step", Button).press()
        await pilot.pause()

        await pilot.click("#entity_search_input")
        await pilot.press(*"fan")
        await pilot.pause()
        await pilot.press("enter")  # submit search -> focuses entity table
        await pilot.press("enter")  # select highlighted (only) match: switch.fan
        await pilot.pause()

        # the popup stays open after adding the first entity; filter is preserved
        assert isinstance(app.screen, DashboardSlotPopup)
        assert "Fan Switch" in _panel_list_labels(popup)

        # escape clears the current filter (stays in entity step), then search for kitchen
        await pilot.press("escape")
        await pilot.pause()
        await pilot.click("#entity_search_input")
        await pilot.press(*"kitchen")
        await pilot.pause()
        await pilot.press("enter")  # submit search -> focuses entity table
        await pilot.press("enter")  # select highlighted (only) match: light.kitchen_light
        await pilot.pause()

        assert "Kitchen Light" in _panel_list_labels(popup)

        popup.query_one("#btn_panel_done", Button).press()
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)
        assert app.dashboards["Main"]["slots"] == [
            {
                "row": 0,
                "col": 0,
                "widget_type": "panel",
                "entity_id": None,
                "entity_ids": ["switch.fan", "light.kitchen_light"],
            }
        ]


async def test_slot_popup_initially_focuses_widget_type_select(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # edit mode
        await pilot.press("a")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)
        assert popup.focused is popup.query_one("#widget_type_select", Select)


async def test_slot_popup_select_widget_type_auto_focuses_next_button(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # edit mode
        await pilot.press("a")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)

        popup.query_one("#widget_type_select", Select).value = "switch"
        await pilot.pause()

        assert popup.focused is popup.query_one("#btn_next_step", Button)


async def test_slot_popup_panel_reselect_removes_entity(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # edit mode
        await pilot.press("a")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)

        popup.query_one("#widget_type_select", Select).value = "panel"
        await pilot.pause()
        popup.query_one("#btn_next_step", Button).press()
        await pilot.pause()

        # add switch.fan
        await pilot.click("#entity_search_input")
        await pilot.press(*"fan")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.press("enter")
        await pilot.pause()
        assert "Fan Switch" in _panel_list_labels(popup)
        assert "switch.fan" in popup._panel_entity_ids

        # re-select switch.fan to remove it: focus is on entity table with "fan" still filtered
        await pilot.press("enter")
        await pilot.pause()
        assert "Fan Switch" not in _panel_list_labels(popup)
        assert popup._panel_entity_ids == []
        assert _panel_list_labels(popup) == ["(none yet)"]  # empty-state placeholder


async def test_slot_popup_escape_with_search_clears_search_stays_in_entity_step(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # edit mode
        await pilot.press("a")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)

        popup.query_one("#btn_next_step", Button).press()
        await pilot.pause()
        assert popup.query_one("#entity_picker_table").display is True

        await pilot.click("#entity_search_input")
        await pilot.press(*"temperature")
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()

        # Still in entity step (table still displayed, not back to type step)
        assert isinstance(app.screen, DashboardSlotPopup)
        assert popup.query_one("#entity_picker_table").display is True
        assert popup.query_one("#entity_search_input", SearchInput).value == ""


async def test_entity_first_picks_entity_then_restricts_type_choices(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # enter edit mode
        await pilot.press("a")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)

        popup.query_one("#btn_entity_first", Button).press()
        await pilot.pause()
        assert popup._entity_first is True
        assert popup._step == "entity"
        # No synthetic "no entity" row in entity-first order, and no type filter
        # yet — every sample entity is browsable.
        assert popup.query_one("#entity_picker_table", EntitiesTable).row_count == 4

        await pilot.click("#entity_search_input")
        await pilot.press(*"temperature")
        await pilot.pause()
        await pilot.press("enter")  # submit search -> focuses entity table
        await pilot.press("enter")  # select highlighted (only) match
        await pilot.pause()

        assert popup._step == "type"
        assert popup._current_entity_id == "sensor.temperature"
        # Numeric sensor -> "sensor" (domain match) hoisted ahead of graph/gauge.
        assert popup.query_one("#widget_type_select", Select).value == "sensor"
        assert str(popup.query_one("#btn_next_step", Button).label) == "Assign"

        popup.query_one("#btn_next_step", Button).press()
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)
        assert app.dashboards["Main"]["slots"] == [
            {"row": 0, "col": 0, "widget_type": "sensor", "entity_id": "sensor.temperature"}
        ]


async def test_entity_first_escape_ladder(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # enter edit mode
        await pilot.press("a")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)

        popup.query_one("#btn_entity_first", Button).press()
        await pilot.pause()
        await pilot.click("#entity_search_input")
        await pilot.press(*"temperature")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.press("enter")
        await pilot.pause()
        assert popup._step == "type"  # the type step, restricted, entity already chosen

        await pilot.press("escape")  # type step -> back to entity step (same order)
        await pilot.pause()
        assert popup._entity_first is True
        assert popup._step == "entity"
        # _advance_to_entity_step's re-focus resets the search filter, so
        # there's nothing left to clear on the next escape.
        assert popup.query_one("#entity_search_input", SearchInput).value == ""

        await pilot.press("escape")  # entity step, no search left -> drop back to type-first step 1
        await pilot.pause()
        assert popup._entity_first is False
        assert popup._step == "type"
        assert popup.query_one("#widget_type_select").display is True
        assert popup.query_one("#btn_entity_first").display is True

        await pilot.press("escape")  # type-first step 1 -> dismiss
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
        assert app.dashboards["Main"]["slots"] == []


async def test_widget_preview_tracks_type_and_entity(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # enter edit mode
        await pilot.press("a")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)

        popup.query_one("#btn_entity_first", Button).press()
        await pilot.pause()
        await pilot.click("#entity_search_input")
        await pilot.press(*"temperature")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.press("enter")
        await pilot.pause()

        preview = popup.query_one("#widget_preview")
        assert preview.display is True
        sensor_preview = preview.query_one(TextSlotWidget)
        assert sensor_preview.entity_id == "sensor.temperature"

        # Switching the (still interactive) type Select updates the preview live.
        popup.query_one("#widget_type_select", Select).value = "graph"
        await pilot.pause()
        graph_preview = preview.query_one(GraphSlotWidget)
        assert graph_preview.entity_id == "sensor.temperature"
