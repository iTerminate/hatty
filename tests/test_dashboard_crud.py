# hatty — MIT License. See LICENSE file for details.
import json

from textual.widgets import Input, Label, ListItem, ListView
from textual_fspicker import FileOpen, FileSave

from hatty.ui.dashboard.screen import DashboardScreen, DashboardSlotWidget
from hatty.ui.dashboard.selection_popup import DashboardSelectionPopup
from tests.conftest import make_config, notified


async def test_create_dashboard_via_popup(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, DashboardSelectionPopup)

        app.screen.query_one("#new_dashboard_name", Input).value = "Bedroom"
        app.screen.query_one("#new_dashboard_rows", Input).value = "2"
        app.screen.query_one("#new_dashboard_cols", Input).value = "4"
        app.screen.query_one("#new_dashboard_cols", Input).focus()
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)
        assert app.current_dashboard_name == "Bedroom"
        assert app.dashboards["Bedroom"] == {"rows": 2, "cols": 4, "slots": []}
        assert len(app.screen.query(DashboardSlotWidget)) == 8


async def test_create_dashboard_with_row_height_via_popup(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()

        app.screen.query_one("#new_dashboard_name", Input).value = "Bedroom"
        app.screen.query_one("#new_dashboard_rows", Input).value = "2"
        app.screen.query_one("#new_dashboard_cols", Input).value = "4"
        app.screen.query_one("#new_dashboard_row_height", Input).value = "12"
        app.screen.query_one("#new_dashboard_row_height", Input).focus()
        await pilot.press("enter")
        await pilot.pause()

        assert app.dashboards["Bedroom"] == {"rows": 2, "cols": 4, "slots": [], "row_height": 12}


async def test_edit_dashboard_sets_row_height(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSelectionPopup)
        popup.query_one("#new_dashboard_row_height", Input).value = "10"
        await pilot.press("enter")
        await pilot.pause()

        assert app.dashboards["Main"]["row_height"] == 10


async def test_edit_dashboard_clears_row_height(make_app, open_dashboard):
    config_data = {
        **make_config(),
        "lists": {},
        "dashboards": {"Main": {"rows": 3, "cols": 3, "slots": [], "row_height": 10}},
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSelectionPopup)
        assert popup.query_one("#new_dashboard_row_height", Input).value == "10"
        popup.query_one("#new_dashboard_row_height", Input).value = ""
        await pilot.press("enter")
        await pilot.pause()

        assert "row_height" not in app.dashboards["Main"]


async def test_switch_dashboard_via_popup(make_app, open_dashboard):
    config_data = {
        **make_config(),
        "lists": {},
        "dashboards": {
            "Main": {"rows": 3, "cols": 3, "slots": []},
            "Office": {"rows": 2, "cols": 2, "slots": []},
        },
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        assert app.current_dashboard_name == "Main"
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_dashboard_name == "Office"
        assert len(app.screen.query(DashboardSlotWidget)) == 4


async def test_dashboard_header_shows_active_dashboard_name(make_app, open_dashboard):
    # Issue #237: the header should reflect the dashboard being viewed, not the
    # main table's active list.
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        assert app.screen.sub_title == "Dashboard: Main"


async def test_dashboard_header_updates_on_switch(make_app, open_dashboard):
    config_data = {
        **make_config(),
        "lists": {},
        "dashboards": {
            "Main": {"rows": 3, "cols": 3, "slots": []},
            "Office": {"rows": 2, "cols": 2, "slots": []},
        },
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_dashboard_name == "Office"
        assert app.screen.sub_title == "Dashboard: Office"


async def test_rename_dashboard_via_popup(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("e")  # combined edit (name + dimensions)
        await pilot.pause()
        name_input = app.screen.query_one("#new_dashboard_name", Input)
        assert name_input.value == "Main"
        name_input.value = "Living Room"
        await pilot.press("enter")
        await pilot.pause()

        assert "Living Room" in app.dashboards
        assert "Main" not in app.dashboards
        assert app.current_dashboard_name == "Living Room"
        assert app.screen.sub_title == "Dashboard: Living Room"


async def test_resize_dashboard_via_popup_drops_out_of_bounds_slots(make_app, open_dashboard):
    config_data = {
        **make_config(),
        "lists": {},
        "dashboards": {
            "Main": {
                "rows": 3,
                "cols": 3,
                "slots": [
                    {"row": 0, "col": 0, "widget_type": "graph", "entity_id": "sensor.temperature"},
                    {"row": 2, "col": 2, "widget_type": "graph", "entity_id": "sensor.temperature"},
                ],
            }
        },
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        rows_input = app.screen.query_one("#new_dashboard_rows", Input)
        cols_input = app.screen.query_one("#new_dashboard_cols", Input)
        assert rows_input.value == "3"
        assert cols_input.value == "3"
        rows_input.value = "2"
        cols_input.value = "2"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)
        assert app.dashboards["Main"]["rows"] == 2
        assert app.dashboards["Main"]["cols"] == 2
        assert app.dashboards["Main"]["slots"] == [
            {"row": 0, "col": 0, "widget_type": "graph", "entity_id": "sensor.temperature"}
        ]
        assert len(app.screen.query(DashboardSlotWidget)) == 4


async def test_delete_dashboard_via_popup(make_app, open_dashboard):
    config_data = {
        **make_config(),
        "lists": {},
        "dashboards": {
            "Main": {"rows": 3, "cols": 3, "slots": []},
            "Office": {"rows": 2, "cols": 2, "slots": []},
        },
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("down")
        await pilot.press("delete")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert "Office" not in app.dashboards
        assert app.current_dashboard_name == "Main"


async def test_set_default_dashboard_via_popup(make_app, open_dashboard):
    config_data = {
        **make_config(),
        "lists": {},
        "dashboards": {
            "Main": {"rows": 3, "cols": 3, "slots": []},
            "Office": {"rows": 2, "cols": 2, "slots": []},
        },
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("down")
        await pilot.press("d")
        await pilot.pause()
        assert app.default_dashboard_name == "Office"
        # setting the default switches to it right away, like lists do
        assert app.current_dashboard_name == "Office"

        # the default is marked with a trailing '*' in the popup list
        await pilot.press("d")
        await pilot.pause()
        labels = [str(item.children[0].content) for item in app.screen.query(ListItem)]
        assert "Office*" in labels


async def test_default_dashboard_wins_over_last_viewed(make_app, open_dashboard):
    config_data = {
        **make_config(),
        "lists": {},
        "dashboards": {
            "Main": {"rows": 3, "cols": 3, "slots": []},
            "Office": {"rows": 2, "cols": 2, "slots": []},
        },
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("down")
        await pilot.press("d")  # set "Office" as default
        await pilot.pause()

        # view "Main" instead, then leave and come back: the default still wins
        app.dash_ctl.switch("Main")
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("y")  # confirm "Leave dashboard?"
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)
        assert app.current_dashboard_name == "Office"


async def test_rename_default_dashboard_updates_default(make_app, open_dashboard):
    config_data = {
        **make_config(),
        "lists": {},
        "dashboards": {"Main": {"rows": 3, "cols": 3, "slots": []}},
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("d")  # set "Main" as default
        await pilot.pause()
        assert app.default_dashboard_name == "Main"

        await pilot.press("d")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        app.screen.query_one("#new_dashboard_name", Input).value = "Living Room"
        await pilot.press("enter")
        await pilot.pause()

        assert app.default_dashboard_name == "Living Room"


async def test_delete_default_dashboard_clears_default(make_app, open_dashboard):
    config_data = {
        **make_config(),
        "lists": {},
        "dashboards": {
            "Main": {"rows": 3, "cols": 3, "slots": []},
            "Office": {"rows": 2, "cols": 2, "slots": []},
        },
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("down")
        await pilot.press("d")  # set "Office" as default
        await pilot.pause()
        assert app.default_dashboard_name == "Office"

        await pilot.press("d")
        await pilot.pause()
        await pilot.press("down")
        await pilot.press("delete")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()

        assert app.default_dashboard_name is None


async def test_delete_last_dashboard_is_refused(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("delete")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert "Main" in app.dashboards
        assert notified(app, title="Delete Error", message_contains="only remaining dashboard")


async def test_edit_dashboard_rename_and_resize_in_one_operation(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSelectionPopup)
        popup.query_one("#new_dashboard_name", Input).value = "Office"
        popup.query_one("#new_dashboard_rows", Input).value = "2"
        popup.query_one("#new_dashboard_cols", Input).value = "4"
        popup.query_one("#new_dashboard_cols", Input).focus()
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)
        assert "Office" in app.dashboards
        assert "Main" not in app.dashboards
        assert app.dashboards["Office"]["rows"] == 2
        assert app.dashboards["Office"]["cols"] == 4
        assert len(app.screen.query(DashboardSlotWidget)) == 8


async def test_edit_cancel_clears_fields_and_returns_to_list(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSelectionPopup)
        assert popup._edit_target == "Main"
        assert popup.query_one("#new_dashboard_name", Input).value == "Main"

        await pilot.press("escape")
        await pilot.pause()

        assert isinstance(app.screen, DashboardSelectionPopup)
        assert popup._edit_target is None
        assert popup.query_one("#new_dashboard_name", Input).value == ""


async def test_field_labels_stay_visible_once_inputs_are_prefilled(make_app, open_dashboard):
    # Rows/Cols labels used to be placeholder-only text, which vanishes once an
    # Input has a value — exactly what the Edit flow does immediately (#222).
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.press("e")  # pre-fills Name/Rows/Cols with the current dashboard
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSelectionPopup)
        assert popup.query_one("#new_dashboard_rows", Input).value == "3"
        assert popup.query_one("#new_dashboard_cols", Input).value == "3"

        labels = {str(label.content) for label in popup.query(Label) if label.has_class("field-label")}
        assert labels == {"Name", "Rows", "Columns", "Row height"}


async def test_shift_down_reorders_dashboard(make_app, open_dashboard):
    # Mirrors the column-config Shift+up/down reorder (#212).
    config_data = {
        **make_config(),
        "lists": {},
        "dashboards": {
            "Main": {"rows": 3, "cols": 3, "slots": []},
            "Office": {"rows": 2, "cols": 2, "slots": []},
            "Bedroom": {"rows": 1, "cols": 1, "slots": []},
        },
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSelectionPopup)
        original_order = list(app.dashboard_names)
        popup.query_one(ListView).index = 0

        await pilot.press("shift+down")
        await pilot.pause()

        expected = original_order[:]
        expected[0], expected[1] = expected[1], expected[0]
        assert app.dashboard_names == expected
        # Persisted order follows dict insertion order, not just dashboard_names.
        assert list(app.dashboards) == expected
        assert popup.query_one(ListView).index == 1


async def test_export_dashboard_writes_file(make_app, open_dashboard, tmp_path):
    config_data = {
        **make_config(),
        "lists": {},
        "dashboards": {
            "Main": {
                "rows": 2,
                "cols": 2,
                "slots": [{"row": 0, "col": 0, "widget_type": "graph", "entity_id": "sensor.temperature"}],
            }
        },
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert isinstance(app.screen, FileSave)

        out_path = tmp_path / "export.json"
        input_widget = app.screen.query_one(Input)
        input_widget.value = str(out_path)
        input_widget.focus()
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)
        payload = json.loads(out_path.read_text())
        assert payload == {
            "hatty_dashboard": 1,
            "name": "Main",
            "dashboard": app.dashboards["Main"],
        }
        assert notified(app, title="Dashboard Exported")


async def test_import_dashboard_from_file(make_app, open_dashboard, tmp_path):
    app = make_app()
    payload = {
        "hatty_dashboard": 1,
        "name": "Imported Dashboard",
        "dashboard": {
            "rows": 2,
            "cols": 2,
            "slots": [{"row": 0, "col": 0, "widget_type": "graph", "entity_id": "sensor.temperature"}],
        },
    }
    in_path = tmp_path / "import.json"
    in_path.write_text(json.dumps(payload))

    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        assert isinstance(app.screen, FileOpen)

        input_widget = app.screen.query_one(Input)
        input_widget.value = str(in_path)
        input_widget.focus()
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)
        assert "Imported Dashboard" in app.dashboards
        assert app.dashboards["Imported Dashboard"] == payload["dashboard"]
        assert app.current_dashboard_name == "Imported Dashboard"
        assert notified(app, title="Dashboard Imported")


async def test_import_dashboard_rejects_malformed_file(make_app, open_dashboard, tmp_path):
    app = make_app()
    in_path = tmp_path / "bad.json"
    in_path.write_text(json.dumps({"not": "a dashboard export"}))

    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()

        input_widget = app.screen.query_one(Input)
        input_widget.value = str(in_path)
        input_widget.focus()
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)
        assert list(app.dashboards) == ["Main"]
        assert notified(app, title="Import Failed")
