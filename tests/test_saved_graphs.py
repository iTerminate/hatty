# hatty — MIT License. See LICENSE file for details.
from textual.coordinate import Coordinate

from hatty.ui.entity_table import EntitiesTable
from hatty.ui.graph.preview_screen import GraphPreviewScreen
from hatty.ui.graph.saved_graphs_popup import SavedGraphsPopup, SaveGraphNamePopup
from hatty.ui.list_selection_popup import ListSelectionPopup
from tests.conftest import make_config

_NO_LIST_CONFIG = make_config(lists={})

# Alphabetical order with no list:
# Row 0: Fan Switch (switch.fan, off)
# Row 1: Kitchen Light (light.kitchen_light, off)
# Row 2: Living Room Lamp (light.living_room_lamp, on)
# Row 3: Temperature Sensor (sensor.temperature, 21.5)

_TWO_SENSOR_ENTITIES = [
    {
        "entity_id": "sensor.temperature",
        "state": "21.5",
        "attributes": {"friendly_name": "Temperature Sensor", "unit_of_measurement": "°C"},
        "last_changed": "2024-01-15T10:30:00.000000+00:00",
    },
    {
        "entity_id": "sensor.humidity",
        "state": "40",
        "attributes": {"friendly_name": "Humidity Sensor", "unit_of_measurement": "%"},
        "last_changed": "2024-01-15T10:30:00.000000+00:00",
    },
]


async def _open_fullscreen_graph(pilot, app, row: int) -> GraphPreviewScreen:
    table = app.query_one(EntitiesTable)
    table.cursor_coordinate = Coordinate(row, 0)
    await pilot.pause()
    await pilot.press("g")
    await pilot.pause()
    await pilot.pause()
    await pilot.press("G")
    await pilot.pause()
    assert isinstance(app.screen, GraphPreviewScreen)
    return app.screen


async def test_save_graph_from_fullscreen_persists_to_config(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_fullscreen_graph(pilot, app, row=3)

        await pilot.press("S")
        await pilot.pause()
        assert isinstance(app.screen, SaveGraphNamePopup)

        app.screen.query_one("#save_graph_name_input").value = "My Graph"
        await pilot.press("enter")
        await pilot.pause()

        assert "My Graph" in app.saved_graphs
        assert app.saved_graphs["My Graph"]["entity_ids"] == ["sensor.temperature"]
        assert app.saved_graphs["My Graph"]["graph_type"] == "line"
        assert app.saved_graphs["My Graph"]["hours"] == app.app_config.get("graph_hours", 4)
        assert app.app_config["saved_graphs"]["My Graph"] == app.saved_graphs["My Graph"]


async def test_save_multi_entity_comparison_graph_and_reopen_restores_state(make_app):
    app = make_app(entities=_TWO_SENSOR_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_fullscreen_graph(pilot, app, row=1)
        await pilot.pause()

        app._graph_extra_ids = ["sensor.humidity"]
        await pilot.press("escape")
        await pilot.pause()

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(1, 0)
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()
        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert preview._entity_ids == ["sensor.temperature", "sensor.humidity"]

        await pilot.press("t")
        await pilot.pause()

        await pilot.press("S")
        await pilot.pause()
        app.screen.query_one("#save_graph_name_input").value = "Cmp"
        await pilot.press("enter")
        await pilot.pause()

        saved = app.saved_graphs["Cmp"]
        assert saved["entity_ids"] == ["sensor.temperature", "sensor.humidity"]
        assert saved["graph_type"] == "scatter"
        assert saved["hours"] == app.app_config.get("graph_hours", 4)

        await pilot.press("escape")
        await pilot.pause()

        app.app_config["graph_hours"] = 999
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, SavedGraphsPopup)
        await pilot.press("enter")
        await pilot.pause()

        reopened = app.screen
        assert isinstance(reopened, GraphPreviewScreen)
        assert reopened._entity_ids == ["sensor.temperature", "sensor.humidity"]
        assert app.app_config["graph_hours"] == saved["hours"]


async def test_s_opens_saved_graphs_popup(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, SavedGraphsPopup)


async def test_open_saved_graph_from_popup(make_app, sample_entities):
    config_data = {
        **_NO_LIST_CONFIG,
        "saved_graphs": {
            "Temp Trend": {"entity_ids": ["sensor.temperature"], "graph_type": "scatter", "hours": 12},
        },
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert preview._entity_ids == ["sensor.temperature"]
        assert app.app_config["graph_hours"] == 12


async def test_rename_saved_graph_via_popup(make_app, sample_entities):
    config_data = {
        **_NO_LIST_CONFIG,
        "saved_graphs": {
            "Old Name": {"entity_ids": ["sensor.temperature"], "graph_type": "line", "hours": 4},
        },
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()

        app.screen.query_one("#saved_graph_rename_input").value = "New Name"
        await pilot.press("enter")
        await pilot.pause()

        assert "Old Name" not in app.saved_graphs
        assert "New Name" in app.saved_graphs
        assert app.saved_graphs["New Name"]["entity_ids"] == ["sensor.temperature"]


async def test_delete_saved_graph_via_popup(make_app, sample_entities):
    config_data = {
        **_NO_LIST_CONFIG,
        "saved_graphs": {
            "Doomed": {"entity_ids": ["sensor.temperature"], "graph_type": "line", "hours": 4},
        },
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("delete")
        await pilot.pause()

        assert "Doomed" not in app.saved_graphs
        assert not isinstance(app.screen, SavedGraphsPopup)


async def test_saved_graphs_popup_cancel_via_escape(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, SavedGraphsPopup)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, SavedGraphsPopup)


async def test_u_updates_saved_graph_in_place_without_popup(make_app, sample_entities):
    config_data = {
        **_NO_LIST_CONFIG,
        "saved_graphs": {
            "Temp Trend": {"entity_ids": ["sensor.temperature"], "graph_type": "line", "hours": 4},
        },
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert preview._saved_graph_name == "Temp Trend"

        await pilot.press("t")  # cycle line -> scatter
        await pilot.pause()

        await pilot.press("u")
        await pilot.pause()

        assert isinstance(app.screen, GraphPreviewScreen)  # no popup opened
        assert app.saved_graphs["Temp Trend"]["graph_type"] == "scatter"


async def test_update_action_disabled_when_not_opened_from_saved_graph(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        preview = await _open_fullscreen_graph(pilot, app, row=3)
        assert preview._saved_graph_name is None
        assert app.screen.check_action("update_graph", ()) is False

        shown_keys = {active.binding.key for active in app.screen.active_bindings.values() if active.binding.show}
        assert "u" not in shown_keys


async def test_entities_get_distinct_default_colors(make_app):
    app = make_app(entities=_TWO_SENSOR_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_fullscreen_graph(pilot, app, row=1)
        app._graph_extra_ids = ["sensor.humidity"]
        await pilot.press("escape")
        await pilot.pause()

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(1, 0)
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        colors = preview._colors
        assert colors["sensor.temperature"] != colors["sensor.humidity"]


async def test_cycle_color_changes_active_entitys_color_and_persists_on_save(make_app):
    app = make_app(entities=_TWO_SENSOR_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_fullscreen_graph(pilot, app, row=1)
        app._graph_extra_ids = ["sensor.humidity"]
        await pilot.press("escape")
        await pilot.pause()

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(1, 0)
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert app.screen.check_action("cycle_color", ()) is True

        original_color = preview._colors["sensor.temperature"]
        await pilot.press("c")
        await pilot.pause()
        assert preview._colors["sensor.temperature"] != original_color

        await pilot.press("S")
        await pilot.pause()
        app.screen.query_one("#save_graph_name_input").value = "Colored"
        await pilot.press("enter")
        await pilot.pause()

        assert app.saved_graphs["Colored"]["colors"]["sensor.temperature"] == preview._colors["sensor.temperature"]


async def test_tab_cycles_active_entity_for_recoloring(make_app):
    app = make_app(entities=_TWO_SENSOR_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_fullscreen_graph(pilot, app, row=1)
        app._graph_extra_ids = ["sensor.humidity"]
        await pilot.press("escape")
        await pilot.pause()

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(1, 0)
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert preview._active_entity_index == 0

        await pilot.press("tab")
        await pilot.pause()
        assert preview._active_entity_index == 1


async def test_single_entity_graph_allows_color_but_not_entity_cycling(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_fullscreen_graph(pilot, app, row=3)
        # single-entity graph: recoloring is still meaningful, but cycling
        # which entity is "active" is not.
        assert app.screen.check_action("next_entity", ()) is False
        assert app.screen.check_action("cycle_color", ()) is True


async def test_reopening_saved_graph_restores_colors(make_app):
    config_data = {
        **_NO_LIST_CONFIG,
        "saved_graphs": {
            "Cmp": {
                "entity_ids": ["sensor.temperature", "sensor.humidity"],
                "graph_type": "line",
                "hours": 4,
                "colors": {"sensor.temperature": "red", "sensor.humidity": "cyan"},
            },
        },
    }
    app = make_app(entities=_TWO_SENSOR_ENTITIES, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert preview._colors == {"sensor.temperature": "red", "sensor.humidity": "cyan"}


async def test_capital_c_opens_color_picker_and_applies_choice(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        preview = await _open_fullscreen_graph(pilot, app, row=3)

        await pilot.press("C")
        await pilot.pause()
        from hatty.ui.graph.color_popup import GraphColorPopup

        assert isinstance(app.screen, GraphColorPopup)

        option_list = app.screen.query_one("#graph_color_list")
        option_list.highlighted = 4  # "magenta" in ALL_PLOT_COLORS
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, GraphPreviewScreen)
        assert preview._colors["sensor.temperature"] == "magenta"


async def test_picked_color_persists_via_update(make_app, sample_entities):
    config_data = {
        **_NO_LIST_CONFIG,
        "saved_graphs": {
            "Temp Trend": {"entity_ids": ["sensor.temperature"], "graph_type": "line", "hours": 4},
        },
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)

        await pilot.press("C")
        await pilot.pause()
        option_list = app.screen.query_one("#graph_color_list")
        option_list.highlighted = 5  # "cyan"
        await pilot.press("enter")
        await pilot.pause()

        await pilot.press("u")
        await pilot.pause()
        assert app.saved_graphs["Temp Trend"]["colors"]["sensor.temperature"] == "cyan"


async def test_save_as_prefills_name_when_opened_from_saved_graph(make_app, sample_entities):
    config_data = {
        **_NO_LIST_CONFIG,
        "saved_graphs": {
            "Temp Trend": {"entity_ids": ["sensor.temperature"], "graph_type": "line", "hours": 4},
        },
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)

        await pilot.press("S")
        await pilot.pause()
        assert isinstance(app.screen, SaveGraphNamePopup)
        assert app.screen.query_one("#save_graph_name_input").value == "Temp Trend"


async def test_opening_saved_graph_replaces_current_graph_screen(make_app, sample_entities):
    # #154: opening a saved graph while a fullscreen graph is already up should
    # replace it in place, never stacking a second GraphPreviewScreen.
    config_data = {
        **_NO_LIST_CONFIG,
        "saved_graphs": {
            "Temp Trend": {"entity_ids": ["sensor.temperature"], "graph_type": "scatter", "hours": 12},
        },
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_fullscreen_graph(pilot, app, row=3)

        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, SavedGraphsPopup)
        await pilot.press("enter")
        await pilot.pause()

        graphs = [s for s in app.screen_stack if isinstance(s, GraphPreviewScreen)]
        assert len(graphs) == 1
        assert app.screen is graphs[0]
        assert app.screen._entity_ids == ["sensor.temperature"]
        assert app.app_config["graph_hours"] == 12


async def test_l_on_fullscreen_graph_jumps_back_to_list(make_app, sample_entities):
    # #155: l on a fullscreen graph should dismiss it and jump to the default/last
    # list, not open a ListSelectionPopup behind the still-visible graph.
    config_data = {
        **make_config(),
        "lists": {"Faves": ["sensor.temperature"]},
        "default_list": "Faves",
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_fullscreen_graph(pilot, app, row=3)

        await pilot.press("l")
        await pilot.pause()

        assert not isinstance(app.screen, GraphPreviewScreen)
        assert not isinstance(app.screen, ListSelectionPopup)
        assert app.current_list_name == "Faves"


async def test_l_on_fullscreen_graph_opens_picker_when_no_list(make_app, sample_entities):
    # #155: with no list to jump back to, l should fall back to the ListSelectionPopup.
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_fullscreen_graph(pilot, app, row=3)

        await pilot.press("l")
        await pilot.pause()

        assert isinstance(app.screen, ListSelectionPopup)
