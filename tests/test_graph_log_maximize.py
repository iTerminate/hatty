# hatty — MIT License. See LICENSE file for details.
"""`f` maximizes the fullscreen graph's activity log (issue #22) — a
graph-screen analogue of the main table's maximize, with its own two-step
escape (un-maximize first, close on a further press) while `a`/`A` still
close outright from either state. Issue #38 turns the maximized state into
a genuinely interactive, selectable list — see LogOptionList.check_action
for how `left`/`right`/`enter` still reach the graph's own paging/inspect-
mode bindings even while that list is focused."""

from textual.widgets import Log, OptionList, Static

from hatty.ui.activity_log_panel import ActivityLogPanel, LogOptionList
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
        options = preview.query_one("#preview_log_panel", ActivityLogPanel).query_one("#log_options", OptionList)
        maximized_line = str(options.get_option_at_index(0).prompt)
        assert len(maximized_line) > len(windowed_line)


async def test_f_focuses_the_option_list_and_shows_detail(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        app.client._logbook_data = [{"when": "2024-01-01T11:30:00+00:00", "name": "Front Door", "state": "on"}]
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a", "f")
        await pilot.pause()
        assert isinstance(app.focused, LogOptionList)
        panel = preview.query_one("#preview_log_panel", ActivityLogPanel)
        detail = panel.query_one("#log_detail", Static)
        assert "Front Door" in str(detail.content)


async def test_left_right_page_the_graph_while_the_option_list_is_focused(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        await _open_preview_on_temperature(pilot, app)

        await pilot.press("a", "f")
        await pilot.pause()
        assert isinstance(app.focused, LogOptionList)
        calls_before = len(app.client.logbook_calls)

        await pilot.press("left")
        await pilot.pause()
        # left paged the graph window (and refetched the log for it), not the list.
        assert len(app.client.logbook_calls) > calls_before


async def test_enter_still_toggles_inspect_mode_while_the_option_list_is_focused(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a", "f")
        await pilot.pause()
        assert isinstance(app.focused, LogOptionList)

        await pilot.press("enter")
        await pilot.pause()
        assert preview._cursor_mode is True


async def test_unmaximize_blurs_the_option_list(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("a", "f")
        await pilot.pause()
        assert isinstance(app.focused, LogOptionList)

        await pilot.press("f")
        await pilot.pause()
        assert not isinstance(app.focused, LogOptionList)
        options = preview.query_one("#preview_log_panel", ActivityLogPanel).query_one("#log_options", LogOptionList)
        assert options.can_focus is False
