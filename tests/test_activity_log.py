# hatty — MIT License. See LICENSE file for details.
from textual.coordinate import Coordinate
from textual.widgets import Label, Log

from hatty.ui.activity_log_panel import ActivityLogPanel
from hatty.ui.entity_table import EntitiesTable
from hatty.ui.graph.entity_detail import EntityDetailPanel
from tests.conftest import make_config

_NO_LIST_CONFIG = make_config(lists={})


async def test_a_opens_activity_log_panel(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")


async def test_a_again_closes_activity_log_panel(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert not panel.has_class("-visible")


async def test_activity_log_title_shows_current_list(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        title = str(panel.query_one("#log_title", Label).content)
        assert "my_list" in title


async def test_activity_log_title_shows_all_entities_when_no_list(make_app):
    app = make_app(config_data=_NO_LIST_CONFIG)
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
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
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
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
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
