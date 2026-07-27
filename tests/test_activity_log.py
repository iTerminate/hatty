# hatty — MIT License. See LICENSE file for details.
from datetime import datetime, timedelta, timezone

from textual.coordinate import Coordinate
from textual.widgets import Input, Label, Log, RadioSet

from hatty.ui.activity_log_panel import ActivityLogPanel
from hatty.ui.entity_table import EntitiesTable
from hatty.ui.graph.duration_popup import GraphDurationPopup
from hatty.ui.graph.entity_detail import EntityDetailPanel
from tests.conftest import NO_LIST_CONFIG


async def test_a_opens_activity_log_panel_and_a_again_closes_it(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")

        hint = str(panel.query_one("#log_hint", Label).content)
        assert "f" in hint and "maximize" in hint
        title = str(panel.query_one("#log_title", Label).content)
        assert "my_list" in title

        await pilot.press("a")
        await pilot.pause()
        assert not panel.has_class("-visible")


async def test_activity_log_title_shows_all_entities_when_no_list(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        title = str(panel.query_one("#log_title", Label).content)
        assert "All Entities" in title


async def test_activity_log_loads_logbook_history(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = [{"when": "2024-01-15T10:30:00+00:00", "name": "Living Room Lamp", "state": "on"}]
        await pilot.press("a")
        await pilot.pause()
        log_widget = app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_widget", Log)
        assert log_widget.line_count >= 1


async def test_opening_activity_log_closes_graph_panel(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # sensor.temperature
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        graph_panel = app.query_one("#detail_panel", EntityDetailPanel)
        assert graph_panel.has_class("-visible")

        await pilot.press("a")
        await pilot.pause()
        assert not graph_panel.has_class("-visible")
        assert app.query_one("#activity_log_panel", ActivityLogPanel).has_class("-visible")


async def test_opening_graph_closes_activity_log(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        log_panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert log_panel.has_class("-visible")

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # sensor.temperature
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        assert not log_panel.has_class("-visible")
        assert app.query_one("#detail_panel", EntityDetailPanel).has_class("-visible")


_GRAPHED_LIST_CONFIG = {
    "home_assistant": {"url": "http://fake.ha.local:8123", "token": "fake_token_abc"},
    "default_list": "my_list",
    "lists": {"my_list": ["sensor.temperature"]},
}

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


async def test_a_scopes_to_graphed_entity_over_list_scope(make_app, sample_entities):
    """`a` with the inline graph open logs the graphed entity, not the active
    list — opening the log from a graph used to silently switch scope (issue #14)."""
    app = make_app(entities=sample_entities, config_data=_GRAPHED_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.jump_cursor_to_row_key("sensor.temperature")
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        assert app.query_one("#detail_panel", EntityDetailPanel).has_class("-visible")

        await pilot.press("a")
        await pilot.pause()
        assert app._log_entity_ids == {"sensor.temperature"}
        title = str(app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_title", Label).content)
        assert "Temperature Sensor" in title
        assert "my_list" not in title


async def test_a_includes_comparison_entities_when_graphed(make_app):
    """A `+` comparison line stays in scope too — the log should cover
    everything currently plotted, titled with a "+N more" suffix."""
    app = make_app(entities=_TWO_SENSOR_ENTITIES, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.jump_cursor_to_row_key("sensor.temperature")
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        app._graph_extra_ids = ["sensor.humidity"]

        await pilot.press("a")
        await pilot.pause()
        assert app._log_entity_ids == {"sensor.temperature", "sensor.humidity"}
        assert app.client.logbook_calls[-1][0] == ["sensor.temperature", "sensor.humidity"]
        title = str(app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_title", Label).content)
        assert "Temperature Sensor" in title
        assert "+1 more" in title


async def test_i_scopes_to_graphed_entity_when_graph_panel_open(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_GRAPHED_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.jump_cursor_to_row_key("sensor.temperature")
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()

        await pilot.press("i")
        await pilot.pause()
        assert app._log_entity_ids == {"sensor.temperature"}
        title = str(app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_title", Label).content)
        assert "my_list" not in title


async def test_i_opens_single_entity_activity_log_and_i_again_closes_it(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # sensor.temperature
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")
        assert app._log_entity_ids == {"sensor.temperature"}
        title = str(panel.query_one("#log_title", Label).content)
        assert "Temperature Sensor" in title

        await pilot.press("i")
        await pilot.pause()
        assert not panel.has_class("-visible")


async def test_left_arrow_pages_log_older_when_open(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert app._log_end is None

        await pilot.press("left")
        await pilot.pause()

        assert app._log_end is not None
        last_call = app.client.logbook_calls[-1]
        assert last_call[1] == app.log_hours  # hours
        assert last_call[2] == app._log_end  # end


async def test_left_arrow_is_inert_while_log_closed(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("left")
        await pilot.pause()
        assert app._log_end is None
        assert not app.query_one("#activity_log_panel", ActivityLogPanel).has_class("-visible")


async def test_right_arrow_pages_log_newer(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("left")
        await pilot.press("left")
        await pilot.pause()
        paged_back_end = app._log_end
        assert paged_back_end is not None

        await pilot.press("right")
        await pilot.pause()

        assert app._log_end is not None
        assert app._log_end > paged_back_end


async def test_right_arrow_snaps_back_to_live(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        # Far enough in the past that one log_hours step forward can't reach it
        # by accident, but close enough that the next step clears "now".
        app._log_end = datetime.now(timezone.utc) - timedelta(hours=1)

        await pilot.press("right")
        await pilot.pause()

        assert app._log_end is None


async def test_paged_back_log_ignores_live_state_change(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("left")
        await pilot.pause()
        log_widget = app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_widget", Log)
        count_before = log_widget.line_count

        app.client.inject_state_change(
            {
                "entity_id": "light.living_room_lamp",
                "state": "off",
                "attributes": {"friendly_name": "Living Room Lamp"},
                "last_changed": "2024-01-15T10:31:00.000000+00:00",
            }
        )
        await pilot.pause()
        assert log_widget.line_count == count_before


async def test_T_opens_log_duration_popup_when_log_open(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()

        await pilot.press("T")
        await pilot.pause()

        popup = app.screen
        assert isinstance(popup, GraphDurationPopup)
        assert app.focused is popup.query_one(RadioSet)


async def test_confirming_log_duration_popup_updates_log_hours_and_reloads(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()

        await pilot.press("T")
        await pilot.pause()

        popup = app.screen
        assert isinstance(popup, GraphDurationPopup)
        popup.query_one("#duration_hours_input", Input).value = "12"
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        assert app.app_config["log_hours"] == 12
        assert app.client.logbook_calls[-1][1] == 12


async def test_live_state_change_appends_to_activity_log(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        log_widget = app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_widget", Log)
        count_before = log_widget.line_count

        app.client.inject_state_change(
            {
                "entity_id": "light.living_room_lamp",
                "state": "off",
                "attributes": {"friendly_name": "Living Room Lamp"},
                "last_changed": "2024-01-15T10:31:00.000000+00:00",
            }
        )
        await pilot.pause()
        assert log_widget.line_count == count_before + 1
