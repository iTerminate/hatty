# hatty — MIT License. See LICENSE file for details.
"""Maximize toggle for the activity/device log panel (issue #70), and its
issue #38 upgrade into a genuinely interactive, selectable list with an
inline detail region."""

from textual.widgets import Log, OptionList, Static

from hatty.ui.activity_log_panel import ActivityLogPanel, LogOptionList
from tests.conftest import NO_LIST_CONFIG


async def test_f_toggles_maximized_class(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert not panel.has_class("-maximized")

        await pilot.press("f")
        await pilot.pause()
        assert panel.has_class("-maximized")

        await pilot.press("f")
        await pilot.pause()
        assert not panel.has_class("-maximized")


async def test_f_is_a_noop_when_log_hidden(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert not panel.has_class("-visible")

        await pilot.press("f")
        await pilot.pause()
        assert not panel.has_class("-maximized")
        # check_action gates the binding off while the panel is hidden.
        assert app.check_action("maximize_log", ()) is False


async def test_escape_unmaximizes_before_closing(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.press("f")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-maximized")

        await pilot.press("escape")
        await pilot.pause()
        # Still visible, just restored to normal width.
        assert panel.has_class("-visible")
        assert not panel.has_class("-maximized")


async def test_maximize_reflows_a_truncated_line_wider(make_app):
    """Maximizing swaps to the full-width selectable list, whose rows are
    truncated at the new (wider) width rather than the docked ticker's
    stale, narrower strings (issue #22, extended by #38's selectable list)."""
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = [{"when": "2024-01-15T10:30:00+00:00", "name": "A" * 40, "state": "on"}]
        await pilot.press("a")
        await pilot.pause()
        log_widget = app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_widget", Log)
        windowed_line = next(line for line in log_widget.lines if "AAA" in line)
        assert windowed_line.endswith("…")

        await pilot.press("f")
        await pilot.pause()
        options = app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_options", OptionList)
        maximized_line = str(options.get_option_at_index(0).prompt)
        assert not maximized_line.endswith("…")
        assert len(maximized_line) > len(windowed_line)

        await pilot.press("f")
        await pilot.pause()
        re_truncated_line = next(line for line in log_widget.lines if "AAA" in line)
        assert re_truncated_line == windowed_line


async def test_maximize_with_empty_log_keeps_the_placeholder(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = []
        await pilot.press("a")
        await pilot.pause()
        log_widget = app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_widget", Log)
        assert list(log_widget.lines) == ["(no history available)"]

        await pilot.press("f")
        await pilot.pause()
        assert list(log_widget.lines) == ["(no history available)"]
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        options = panel.query_one("#log_options", OptionList)
        assert options.option_count == 0
        detail = panel.query_one("#log_detail", Static)
        assert str(detail.content) == "(no history available)"


async def test_f_focuses_the_option_list_and_shows_the_newest_entrys_detail(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = [
            {"when": "2024-01-15T10:30:00+00:00", "name": "Living Room Lamp", "state": "on"},
            {"when": "2024-01-15T10:31:00+00:00", "name": "Kitchen Light", "state": "off"},
        ]
        await pilot.press("a")
        await pilot.pause()

        await pilot.press("f")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        options = panel.query_one("#log_options", LogOptionList)
        assert isinstance(app.focused, LogOptionList)
        assert options.highlighted == options.option_count - 1
        detail = panel.query_one("#log_detail", Static)
        assert "Kitchen Light" in str(detail.content)
        assert "2024-01-15" in str(detail.content)


async def test_up_moves_selection_and_updates_the_detail_region(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = [
            {"when": "2024-01-15T10:30:00+00:00", "name": "Living Room Lamp", "state": "on"},
            {"when": "2024-01-15T10:31:00+00:00", "name": "Kitchen Light", "state": "off"},
        ]
        await pilot.press("a")
        await pilot.press("f")
        await pilot.pause()

        await pilot.press("up")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        options = panel.query_one("#log_options", OptionList)
        assert options.highlighted == 0
        detail = panel.query_one("#log_detail", Static)
        assert "Living Room Lamp" in str(detail.content)


async def test_left_right_still_page_while_the_option_list_is_focused(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.press("f")
        await pilot.pause()
        assert isinstance(app.focused, LogOptionList)

        await pilot.press("left")
        await pilot.pause()
        assert app.log_ctl.session_for(app).end is not None


async def test_unmaximize_blurs_and_refocuses_the_table(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.press("f")
        await pilot.pause()
        assert isinstance(app.focused, LogOptionList)

        await pilot.press("f")
        await pilot.pause()
        assert app.query_one("#entities_table").has_focus
        options = app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_options", LogOptionList)
        assert options.can_focus is False


async def test_live_append_while_maximized_preserves_the_selection(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = [
            {"when": "2024-01-15T10:30:00+00:00", "name": "Living Room Lamp", "state": "on"},
            {"when": "2024-01-15T10:31:00+00:00", "name": "Kitchen Light", "state": "off"},
        ]
        await pilot.press("a")
        await pilot.press("f")
        await pilot.pause()
        await pilot.press("up")  # select the older (first) entry
        await pilot.pause()

        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        options = panel.query_one("#log_options", OptionList)
        assert options.highlighted == 0

        app.client.logbook_subscription_id = None  # exercise the state_changed fallback append
        app.client.inject_state_change(
            {
                "entity_id": "switch.fan",
                "state": "on",
                "attributes": {"friendly_name": "Fan Switch"},
                "last_changed": "2024-01-15T10:32:00.000000+00:00",
            }
        )
        await pilot.pause()

        assert options.option_count == 3
        assert options.highlighted == 0  # unmoved by the append
        detail = panel.query_one("#log_detail", Static)
        assert "Living Room Lamp" in str(detail.content)


async def test_reopening_log_is_not_maximized(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.press("f")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-maximized")

        # Close and reopen via the toggle key.
        await pilot.press("a")
        await pilot.pause()
        assert not panel.has_class("-visible")
        await pilot.press("a")
        await pilot.pause()
        assert panel.has_class("-visible")
        assert not panel.has_class("-maximized")
