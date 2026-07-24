# hatty — MIT License. See LICENSE file for details.
from textual.widgets import Static

from hatty.main import HACommandProvider
from hatty.ui.dashboard.screen import DashboardScreen, DashboardSlotWidget
from hatty.ui.graph.preview_screen import GraphPreviewScreen
from hatty.ui.graph.saved_graphs_popup import SavedGraphsPopup
from hatty.ui.list_selection_popup import ListSelectionPopup
from tests.conftest import make_config


async def test_d_opens_dashboard_screen_with_auto_created_main(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        assert isinstance(app.screen, DashboardScreen)
        assert app.current_dashboard_name == "Main"
        assert app.dashboards["Main"] == {"rows": 3, "cols": 3, "slots": []}

        slots = app.screen.query(DashboardSlotWidget)
        assert len(slots) == 9
        assert all(str(s.query_one("#slot_empty", Static).content) == "Empty" for s in slots)


async def test_escape_closes_dashboard_screen(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        assert isinstance(app.screen, DashboardScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, DashboardScreen)


async def test_l_jumps_back_to_last_shown_list(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name == "my_list"
        app.current_list_name = None
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
        await pilot.press("l")
        await pilot.pause()
        assert not isinstance(app.screen, DashboardScreen)
        assert app.current_list_name == "my_list"


async def test_l_falls_back_to_default_list_when_last_shown_invalid(make_app):
    app = make_app(
        config_data={
            **make_config(),
            "default_list": "my_list",
            "lists": {"my_list": ["light.living_room_lamp"], "other": []},
        }
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        app._last_list_name = "deleted_list"
        app.current_list_name = None
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        assert not isinstance(app.screen, DashboardScreen)
        assert app.current_list_name == "my_list"


async def test_l_opens_list_popup_when_no_lists_exist(make_app, open_dashboard):
    app = make_app(
        config_data={
            **make_config(),
        }
    )
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        assert isinstance(app.screen, DashboardScreen)
        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.screen, ListSelectionPopup)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)


async def test_palette_switch_list_pops_dashboard_and_restores_list(make_app):
    # Regression test: invoking "Lists" from the command palette while a
    # screen was pushed on top (e.g. the dashboard) updated current_list_name
    # in the background but left the pushed screen visible.
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name == "my_list"

        app.current_list_name = None
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
        assert len(app.screen_stack) == 2

        app.action_palette_switch_list()
        await pilot.pause()

        assert len(app.screen_stack) == 1
        assert not isinstance(app.screen, DashboardScreen)
        assert app.current_list_name == "my_list"


async def test_s_opens_saved_graphs_from_dashboard(make_app, sample_entities, open_dashboard):
    # Regression test: check_action's blanket DashboardScreen carve-out
    # (return action == "quit") silently disabled the global "s" binding,
    # so saved graphs couldn't be reopened while viewing the dashboard.
    config_data = {
        **make_config(),
        "lists": {},
        "saved_graphs": {
            "Temp Trend": {"entity_ids": ["sensor.temperature"], "graph_type": "line", "hours": 4},
        },
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        assert isinstance(app.screen, DashboardScreen)

        assert app.check_action("show_saved_graphs_popup", ()) is True

        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, SavedGraphsPopup)

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)


async def test_show_dashboard_pops_other_screens_first(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(ListSelectionPopup())
        await pilot.pause()
        assert len(app.screen_stack) == 2

        app.action_show_dashboard()
        await pilot.pause()

        assert len(app.screen_stack) == 2
        assert isinstance(app.screen, DashboardScreen)


async def test_existing_dashboards_are_not_overwritten(make_app, open_dashboard):
    config_data = {
        **make_config(),
        "lists": {},
        "dashboards": {
            "Custom": {
                "rows": 2,
                "cols": 2,
                "slots": [{"row": 0, "col": 0, "widget_type": "graph", "entity_id": "sensor.temperature"}],
            }
        },
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        assert app.current_dashboard_name == "Custom"
        assert list(app.dashboards.keys()) == ["Custom"]


async def test_command_palette_has_one_static_entry_per_category(make_app):
    config_data = {
        **make_config(),
        "lists": {"list_a": [], "list_b": [], "list_c": []},
        "dashboards": {
            "Main": {"rows": 3, "cols": 3, "slots": []},
            "Office": {"rows": 2, "cols": 2, "slots": []},
        },
    }
    app = make_app(config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        provider = HACommandProvider(app.screen)
        candidates = provider._candidates()
        titles = [text for text, _help, _command in candidates]
        assert titles == ["Configuration", "Lists", "Dashboard", "Setup wizard"]


async def test_palette_switch_list_jumps_to_last_used_no_popup(make_app, sample_entities):
    config_data = {
        **make_config(),
        "lists": {"list_a": ["switch.fan"], "list_b": []},
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.select_or_create_list("list_b")
        await pilot.pause()
        assert app.current_list_name == "list_b"

        app.action_palette_switch_list()
        await pilot.pause()

        assert app.current_list_name == "list_b"
        assert not isinstance(app.screen, ListSelectionPopup)
