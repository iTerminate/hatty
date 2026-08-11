# hatty — MIT License. See LICENSE file for details.
"""The fullscreen graph's `a`-toggled activity log (issue #2): the logbook
window follows the graph's own paging so opening the log shows events for
whatever's currently plotted, and closing/escaping tears it back down.

`v`'s scope popup (issue #38, replacing the old blind cycle from #21) is
covered in test_log_scope_popup.py; this file covers opening/closing/paging
the panel and the device-widened scope (issue #18, e.g. a zha_event button
press) rendering in the log list."""

from textual.coordinate import Coordinate
from textual.widgets import Label, Log

from hatty.ui.activity_log_panel import ActivityLogPanel
from hatty.ui.entity_table import EntitiesTable
from hatty.ui.graph.preview_screen import GraphPreviewScreen
from tests.conftest import NO_LIST_CONFIG


async def _open_preview_on_temperature(pilot, app) -> GraphPreviewScreen:
    table = app.query_one(EntitiesTable)
    table.cursor_coordinate = Coordinate(3, 0)  # sensor.temperature
    await pilot.pause()
    await pilot.press("g")
    await pilot.pause()
    await pilot.pause()
    await pilot.press("G")
    await pilot.pause()
    assert isinstance(app.screen, GraphPreviewScreen)
    return app.screen


async def test_a_opens_event_log_on_fullscreen_graph(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a")
        await pilot.pause()

        log_panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        assert log_panel.has_class("-visible")
        assert app.client.logbook_calls  # fetched for the plotted entity


async def test_a_again_closes_event_log(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a")
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()

        log_panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        assert not log_panel.has_class("-visible")


async def test_event_log_title_names_the_entity(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a")
        await pilot.pause()

        log_panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        title = str(log_panel.query_one("#log_title", Label).content)
        assert "Temperature Sensor" in title


async def test_paging_graph_refetches_event_log(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a")
        await pilot.pause()
        calls_after_open = len(app.client.logbook_calls)
        assert calls_after_open >= 1

        await pilot.press("left")
        await pilot.pause()

        assert len(app.client.logbook_calls) > calls_after_open
        last_end = app.client.logbook_calls[-1][2]
        assert last_end == preview._window_end


async def test_a_sends_no_device_ids(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        await _open_preview_on_temperature(pilot, app)

        await pilot.press("a")
        await pilot.pause()
        assert app.client.logbook_calls[-1][3] == []


async def test_v_is_a_noop_when_log_closed(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)
        assert preview.check_action("show_log_scope", ()) is False

        await pilot.press("v")
        await pilot.pause()
        log_panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        assert not log_panel.has_class("-visible")


async def test_capital_a_does_nothing_on_the_graph_screen(make_app, sample_entities):
    """`A` used to be the device-log toggle here (issue #18); it's now `v`
    (issue #21). `A` isn't bound on the main screen either anymore (issue
    #27), so this just proves the key is a no-op while a graph is open."""
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("A")
        await pilot.pause()
        log_panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        assert not log_panel.has_class("-visible")


async def test_device_scoped_event_renders_in_the_log(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        app.client._logbook_device_data = [
            {
                "when": 1704110400.0,
                "name": "Temperature Sensor Hub",
                "message": "device_offline event was fired with parameters: {}",
                "domain": "zha",
            }
        ]
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a", "v")
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()

        log_panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        assert any("⚡" in line for line in log_panel.query_one("#log_widget", Log).lines)


async def test_escape_closes_event_log_before_leaving_graph(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a")
        await pilot.pause()
        log_panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        assert log_panel.has_class("-visible")

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)
        assert not log_panel.has_class("-visible")

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, GraphPreviewScreen)


async def test_numeric_sensor_log_renders_history_derived_entries(make_app, sample_entities):
    """Issue #29: HA's own logbook silently excludes continuous sensors, so
    the fullscreen graph's `a` log used to render nothing at all for
    sensor.temperature — fetch_log_entries fills the gap from history."""
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        app.client._logbook_data = []  # real HA returns nothing for a continuous sensor
        app.client._state_log_data = {
            "sensor.temperature": [
                {"when": "2024-01-01T11:00:00+00:00", "entity_id": "sensor.temperature", "state": "21.5"}
            ]
        }
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a")
        await pilot.pause()

        log_panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        assert any("21.5 °C" in line for line in log_panel.query_one("#log_widget", Log).lines)
