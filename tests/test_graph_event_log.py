# hatty — MIT License. See LICENSE file for details.
"""The fullscreen graph's `a`-toggled activity log (issue #2): the logbook
window follows the graph's own paging so opening the log shows events for
whatever's currently plotted, and closing/escaping tears it back down.

Also `A`'s device-scoped variant (issue #18): entity-only for `a`, entity +
device for `A`, with device-scoped marks drawn in a distinct color."""

from textual.coordinate import Coordinate
from textual.widgets import Label, Log

import hatty.ui.graph.preview_screen as preview_screen_module
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


async def test_A_sends_the_entitys_device_id(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        await _open_preview_on_temperature(pilot, app)

        await pilot.press("A")
        await pilot.pause()
        assert app.client.logbook_calls[-1][3] == ["dev_xyz"]


async def test_A_title_says_device_log(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("A")
        await pilot.pause()
        log_panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        title = str(log_panel.query_one("#log_title", Label).content)
        assert "Device Log" in title
        assert "Temperature Sensor" in title


async def test_A_again_closes_event_log(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("A")
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()

        log_panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        assert not log_panel.has_class("-visible")


async def test_device_scoped_event_renders_and_marks_the_plot_in_cyan(
    make_app, sample_entities, sample_registry, monkeypatch
):
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

        mark_colors = []
        monkeypatch.setattr(
            preview_screen_module,
            "render_event_marks",
            lambda plt, t0, ts, **kw: mark_colors.append(kw.get("color", "magenta")),
        )

        await pilot.press("A")
        await pilot.pause()

        assert any(e["kind"] == "event" for e in preview._events)
        log_panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        assert any("⚡" in line for line in log_panel.query_one("#log_widget", Log).lines)
        assert "cyan" in mark_colors
        assert "magenta" in mark_colors


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
