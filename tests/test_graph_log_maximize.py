# hatty — MIT License. See LICENSE file for details.
"""`f` maximizes the fullscreen graph's activity log (issue #22) — a
graph-screen analogue of the main table's maximize, with its own two-step
escape (un-maximize first, close on a further press) while `a`/`A` still
close outright from either state."""

from textual.widgets import Log

from hatty.ui.activity_log_panel import ActivityLogPanel
from hatty.ui.graph.preview_screen import GraphPreviewScreen
from tests.conftest import NO_LIST_CONFIG
from tests.test_graph_event_log import _open_preview_on_temperature


async def test_f_is_a_noop_when_log_closed(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)
        assert preview.check_action("maximize_log", ()) is False

        await pilot.press("f")
        await pilot.pause()
        panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        assert not panel.has_class("-maximized")


async def test_f_toggles_maximized_class(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a")
        await pilot.pause()
        panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        assert not panel.has_class("-maximized")
        assert preview.check_action("maximize_log", ()) is True

        await pilot.press("f")
        await pilot.pause()
        assert panel.has_class("-maximized")

        await pilot.press("f")
        await pilot.pause()
        assert not panel.has_class("-maximized")


async def test_escape_unmaximizes_before_closing(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a", "f")
        await pilot.pause()
        panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        assert panel.has_class("-maximized")

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)  # stayed on the graph
        assert panel.has_class("-visible")
        assert not panel.has_class("-maximized")

        await pilot.press("escape")
        await pilot.pause()
        assert not panel.has_class("-visible")
        assert isinstance(app.screen, GraphPreviewScreen)  # closing the log, not leaving the graph


async def test_a_closes_outright_even_while_maximized(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a", "f")
        await pilot.pause()
        panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        assert panel.has_class("-maximized")

        await pilot.press("a")
        await pilot.pause()
        assert not panel.has_class("-visible")


async def test_reopening_log_is_not_maximized(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a", "f")
        await pilot.pause()
        panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        assert panel.has_class("-maximized")

        await pilot.press("a")  # close
        await pilot.pause()
        await pilot.press("a")  # reopen
        await pilot.pause()
        assert panel.has_class("-visible")
        assert not panel.has_class("-maximized")


async def test_maximize_reflows_a_truncated_line_wider(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        app.client._logbook_data = [{"when": "2024-01-01T11:30:00+00:00", "name": "A" * 40, "state": "on"}]
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a")
        await pilot.pause()
        log_widget = preview.query_one("#preview_log_panel", ActivityLogPanel).query_one("#log_widget", Log)
        windowed_line = next(line for line in log_widget.lines if "AAA" in line)
        assert windowed_line.endswith("…")

        await pilot.press("f")
        await pilot.pause()
        maximized_line = next(line for line in log_widget.lines if "AAA" in line)
        assert len(maximized_line) > len(windowed_line)
