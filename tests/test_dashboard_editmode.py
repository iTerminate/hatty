# hatty — MIT License. See LICENSE file for details.
from hatty.ui.dashboard.panel_manage_popup import PanelManagePopup
from hatty.ui.dashboard.screen import DashboardScreen
from hatty.ui.dashboard.widgets.panel import PanelSlotWidget
from hatty.ui.entity_table import EntitiesTable
from tests.conftest import make_config

_TWO_SLOT_CONFIG = {
    **make_config(),
    "lists": {},
    "dashboards": {
        "Main": {
            "rows": 3,
            "cols": 3,
            "slots": [
                {"row": 0, "col": 0, "widget_type": "graph", "entity_id": "sensor.temperature"},
                {"row": 0, "col": 1, "widget_type": "switch", "entity_id": "switch.fan"},
            ],
        }
    },
}


def _slot_at(app, row, col):
    slots = app.dashboards["Main"]["slots"]
    return next((s for s in slots if s["row"] == row and s["col"] == col), None)


async def test_shift_e_enters_edit_mode_and_escape_returns_to_use(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        assert app.screen.edit_mode is False

        await pilot.press("E")
        await pilot.pause()
        assert app.screen.edit_mode is True
        assert app.screen.has_class("-edit")

        await pilot.press("escape")
        await pilot.pause()
        # Esc in edit mode returns to use mode rather than leaving the dashboard.
        assert isinstance(app.screen, DashboardScreen)
        assert app.screen.edit_mode is False


async def test_use_mode_ignores_assign_and_clear(make_app, open_dashboard):
    app = make_app(config_data=_TWO_SLOT_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        # 'a' must not open the slot editor while in use mode...
        await pilot.press("a")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)

        # ...and Delete must not clear the slot under the cursor.
        await pilot.press("delete")
        await pilot.pause()
        assert _slot_at(app, 0, 0) is not None


async def test_grab_move_swaps_two_slots(make_app, open_dashboard):
    app = make_app(config_data=_TWO_SLOT_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # edit mode
        await pilot.press("enter")  # grab the slot at (0, 0)
        await pilot.press("right")  # move cursor to (0, 1)
        await pilot.press("enter")  # drop -> swap (0,0) <-> (0,1)
        await pilot.pause()

        assert _slot_at(app, 0, 0)["entity_id"] == "switch.fan"
        assert _slot_at(app, 0, 1)["entity_id"] == "sensor.temperature"


async def test_grab_move_into_empty_cell(make_app, open_dashboard):
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
        await pilot.press("E")
        await pilot.press("enter")  # grab (0, 0)
        await pilot.press("right")  # cursor to empty (0, 1)
        await pilot.press("enter")  # drop into empty cell

        await pilot.pause()
        assert _slot_at(app, 0, 0) is None
        assert _slot_at(app, 0, 1)["entity_id"] == "sensor.temperature"


_PANEL_REORDER_CONFIG = {
    **make_config(),
    "lists": {},
    "dashboards": {
        "Main": {
            "rows": 1,
            "cols": 1,
            "slots": [
                {
                    "row": 0,
                    "col": 0,
                    "widget_type": "panel",
                    "entity_id": None,
                    "entity_ids": ["switch.fan", "light.kitchen_light"],
                }
            ],
        }
    },
}


async def test_panel_r_opens_manage_popup_in_edit_mode(make_app, open_dashboard):
    app = make_app(config_data=_PANEL_REORDER_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")
        await pilot.pause()
        assert app.screen.edit_mode is True

        await pilot.press("r")
        await pilot.pause()
        assert isinstance(app.screen, PanelManagePopup)


async def test_panel_manage_reorder_persists(make_app, open_dashboard):
    app = make_app(config_data=_PANEL_REORDER_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        assert isinstance(app.screen, PanelManagePopup)

        await pilot.press("shift+down")  # move top entity (switch.fan) down
        await pilot.pause()
        await pilot.press("escape")  # done → persist
        await pilot.pause()

        panel_widget = app.screen.query_one(PanelSlotWidget)
        assert panel_widget.entity_ids == ["light.kitchen_light", "switch.fan"]
        slot = next(s for s in app.dashboards["Main"]["slots"] if s["row"] == 0 and s["col"] == 0)
        assert slot["entity_ids"] == ["light.kitchen_light", "switch.fan"]


async def test_panel_manage_remove_persists(make_app, open_dashboard):
    app = make_app(config_data=_PANEL_REORDER_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()

        await pilot.press("delete")  # remove highlighted (switch.fan)
        await pilot.pause()
        await pilot.press("escape")  # done → persist
        await pilot.pause()

        panel_widget = app.screen.query_one(PanelSlotWidget)
        assert panel_widget.entity_ids == ["light.kitchen_light"]
        slot = next(s for s in app.dashboards["Main"]["slots"] if s["row"] == 0 and s["col"] == 0)
        assert slot["entity_ids"] == ["light.kitchen_light"]


async def test_panel_manage_add_persists(make_app, open_dashboard):
    from hatty.ui.controls.entity_picker_modal import EntityPickerModal

    app = make_app(config_data=_PANEL_REORDER_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()

        await pilot.press("a")  # open the entity picker
        await pilot.pause()
        assert isinstance(app.screen, EntityPickerModal)
        table = app.screen.query_one("#entity_picker_table", EntitiesTable)
        table.focus()
        table.jump_cursor_to_row_key("light.living_room_lamp")
        await pilot.pause()
        await pilot.press("enter")  # pick it → back to manage popup
        await pilot.pause()
        assert isinstance(app.screen, PanelManagePopup)

        await pilot.press("escape")  # done → persist
        await pilot.pause()

        slot = next(s for s in app.dashboards["Main"]["slots"] if s["row"] == 0 and s["col"] == 0)
        assert slot["entity_ids"] == ["switch.fan", "light.kitchen_light", "light.living_room_lamp"]
