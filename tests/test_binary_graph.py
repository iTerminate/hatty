# hatty — MIT License. See LICENSE file for details.
from textual.coordinate import Coordinate
from textual.widgets import Label

from hatty.ui.entity_table import EntitiesTable
from hatty.ui.graph.entity_detail import EntityDetailPanel
from hatty.ui.graph.preview_screen import GraphPreviewScreen
from tests.conftest import make_config

_NO_LIST_CONFIG = make_config(lists={})

_BINARY_ENTITIES = [
    {
        "entity_id": "binary_sensor.front_door",
        "state": "on",
        "attributes": {"friendly_name": "Front Door", "device_class": "door"},
        "last_changed": "2024-01-15T10:30:00.000000+00:00",
    },
    {
        "entity_id": "binary_sensor.motion",
        "state": "off",
        "attributes": {"friendly_name": "Motion", "device_class": "motion"},
        "last_changed": "2024-01-15T10:30:00.000000+00:00",
    },
    {
        "entity_id": "sensor.temperature",
        "state": "21.5",
        "attributes": {"friendly_name": "Temperature", "unit_of_measurement": "°C"},
        "last_changed": "2024-01-15T10:30:00.000000+00:00",
    },
    {
        "entity_id": "sensor.humidity",
        "state": "40",
        "attributes": {"friendly_name": "Humidity", "unit_of_measurement": "%"},
        "last_changed": "2024-01-15T10:30:00.000000+00:00",
    },
]

_DOOR_HISTORY = [
    ("2024-01-15T08:00:00+00:00", 0.0),
    ("2024-01-15T09:00:00+00:00", 1.0),
    ("2024-01-15T10:00:00+00:00", 0.0),
    ("2024-01-15T10:30:00+00:00", 1.0),
]

# Alphabetical rows: 0 Front Door, 1 Humidity, 2 Motion, 3 Temperature


def _label_text(widget) -> str:
    return str(widget.content)


async def test_g_opens_binary_history_panel(make_app):
    app = make_app(entities=_BINARY_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"binary_sensor.front_door": list(_DOOR_HISTORY)}

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        panel = app.query_one("#detail_panel", EntityDetailPanel)
        assert panel.has_class("-visible")
        assert panel._is_binary
        title = _label_text(panel.query_one("#detail_title", Label))
        assert "Front Door" in title and "Timeline" in title
        stats = _label_text(panel.query_one("#detail_stats", Label))
        assert "changes" in stats and "last: on" in stats


async def test_fullscreen_binary_graph_renders_with_binary_stats(make_app):
    app = make_app(entities=_BINARY_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"binary_sensor.front_door": list(_DOOR_HISTORY)}

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert preview._is_binary
        stats = _label_text(app.screen.query_one("#preview_stats", Label))
        assert "changes" in stats

        # Plot-type cycling is meaningless for a step timeline.
        assert app.screen.check_action("cycle_plot_type", ()) is False


async def test_binary_cursor_mode_shows_on_off_values(make_app):
    app = make_app(entities=_BINARY_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"binary_sensor.front_door": list(_DOOR_HISTORY)}

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        stats = _label_text(app.screen.query_one("#preview_stats", Label))
        assert "Front Door: on" in stats


async def test_binary_cannot_be_added_to_numeric_comparison(make_app):
    app = make_app(entities=_BINARY_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {
            "sensor.temperature": [("2024-01-15T08:00:00+00:00", 20.0)],
            "sensor.humidity": [("2024-01-15T08:00:00+00:00", 40.0)],
            "binary_sensor.front_door": list(_DOOR_HISTORY),
        }

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # Temperature
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        table.cursor_coordinate = Coordinate(1, 0)  # Humidity — numeric comparison
        await pilot.pause()
        await pilot.press("plus")
        await pilot.pause()
        assert app._graph_extra_ids == ["sensor.humidity"]

        table.cursor_coordinate = Coordinate(0, 0)  # Front Door — binary, refused
        await pilot.pause()
        await pilot.press("plus")
        await pilot.pause()
        assert app._graph_extra_ids == ["sensor.humidity"]


async def test_binary_plus_binary_comparison_is_allowed(make_app):
    app = make_app(entities=_BINARY_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {
            "binary_sensor.front_door": list(_DOOR_HISTORY),
            "binary_sensor.motion": [("2024-01-15T08:00:00+00:00", 0.0)],
        }

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        table.cursor_coordinate = Coordinate(2, 0)  # Motion
        await pilot.pause()
        await pilot.press("plus")
        await pilot.pause()
        assert app._graph_extra_ids == ["binary_sensor.motion"]


async def test_binary_state_changes_append_to_history_live(make_app):
    app = make_app(entities=_BINARY_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"binary_sensor.front_door": list(_DOOR_HISTORY)}

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        app.client.inject_state_change(
            {
                "entity_id": "binary_sensor.front_door",
                "state": "off",
                "attributes": {"friendly_name": "Front Door", "device_class": "door"},
                "last_changed": "2024-01-15T11:00:00+00:00",
            }
        )
        await pilot.pause()
        history = list(app.entity_history["binary_sensor.front_door"])
        assert history[-1] == ("2024-01-15T11:00:00+00:00", 0.0)
