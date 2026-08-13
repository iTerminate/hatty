# hatty — MIT License. See LICENSE file for details.
"""The docked activity log ticker stays pinned to its newest entry unless
the reader has scrolled away from it (issue #44) — reloads, live appends and
reflows all respect that rule."""

from textual.widgets import Log

from hatty.ui.activity_log_panel import ActivityLogPanel
from tests.conftest import NO_LIST_CONFIG

# 60 entries comfortably overflows the ~22-row docked log body at the
# default 80x24 test terminal size, so max_scroll_y > 0.
_MANY = 60


def _entries(n: int, *, start_minute: int = 0) -> list[dict]:
    return [
        {
            "when": f"2024-01-15T10:{(start_minute + i) % 60:02d}:00+00:00",
            "name": f"Entity {i}",
            "state": "on",
        }
        for i in range(n)
    ]


def _log_widget(app) -> Log:
    panel = app.query_one("#activity_log_panel", ActivityLogPanel)
    return panel.query_one("#log_widget", Log)


async def test_long_history_opens_pinned_to_the_newest_entry(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = _entries(_MANY)
        await pilot.press("a")
        await pilot.pause()

        log = _log_widget(app)
        assert log.max_scroll_y > 0
        assert log.scroll_offset.y == log.max_scroll_y


async def test_live_append_follows_when_pinned_to_the_newest(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = _entries(_MANY)
        await pilot.press("a")
        await pilot.pause()

        log = _log_widget(app)
        count_before = log.line_count
        app.client.inject_logbook_event(
            [{"when": "2024-01-15T11:30:00+00:00", "name": "New Entity", "state": "on"}]
        )
        await pilot.pause()

        assert log.line_count == count_before + 1
        assert log.scroll_offset.y == log.max_scroll_y


async def test_live_append_leaves_a_scrolled_up_reader_alone(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = _entries(_MANY)
        await pilot.press("a")
        await pilot.pause()

        log = _log_widget(app)
        log.scroll_to(y=0, animate=False, immediate=True)
        await pilot.pause()
        assert log.scroll_offset.y == 0
        count_before = log.line_count

        app.client.inject_logbook_event(
            [{"when": "2024-01-15T11:30:00+00:00", "name": "New Entity", "state": "on"}]
        )
        await pilot.pause()

        assert log.line_count == count_before + 1
        assert log.scroll_offset.y == 0


async def test_a_longer_reload_repins_to_the_newest(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = _entries(40)
        await pilot.press("a")
        await pilot.pause()

        app.client._logbook_data = _entries(120)
        await pilot.press("left")  # pages back, forcing a refetch/reload
        await pilot.pause()

        log = _log_widget(app)
        assert log.max_scroll_y > 0
        assert log.scroll_offset.y == log.max_scroll_y


async def test_scrolled_up_reader_is_repinned_by_a_reload_and_then_follows_again(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = _entries(_MANY)
        await pilot.press("a")
        await pilot.pause()

        log = _log_widget(app)
        log.scroll_to(y=0, animate=False, immediate=True)
        await pilot.pause()
        assert log.scroll_offset.y == 0

        app.client._logbook_data = _entries(_MANY)
        await pilot.press("left")  # any reload starts a reader fresh, pinned to newest
        await pilot.pause()
        assert log.scroll_offset.y == log.max_scroll_y

        app.client.inject_logbook_event(
            [{"when": "2024-01-15T11:30:00+00:00", "name": "New Entity", "state": "on"}]
        )
        await pilot.pause()
        assert log.scroll_offset.y == log.max_scroll_y


async def test_empty_history_is_visible_after_a_scrolled_up_reload(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = _entries(_MANY)
        await pilot.press("a")
        await pilot.pause()

        log = _log_widget(app)
        log.scroll_to(y=0, animate=False, immediate=True)
        await pilot.pause()

        app.client._logbook_data = []
        await pilot.press("left")
        await pilot.pause()

        assert log.scroll_offset.y == 0
        assert "(no history available)" in log.lines[0]


async def test_reflow_keeps_a_pinned_reader_pinned(make_app):
    """_reflow_lines only ever runs when the log's rendered width has
    actually changed (unreachable via a docked, fixed-width panel in the
    headless test driver), so this drives it directly rather than through a
    terminal resize — see the plan's investigation notes."""
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = _entries(_MANY)
        await pilot.press("a")
        await pilot.pause()

        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        log = _log_widget(app)
        assert log.scroll_offset.y == log.max_scroll_y

        panel._rendered_width = 0  # force _reflow_lines to treat width as changed
        panel._reflow_lines()
        await pilot.pause()

        assert log.scroll_offset.y == log.max_scroll_y


async def test_reflow_preserves_a_scrolled_up_position(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = _entries(_MANY)
        await pilot.press("a")
        await pilot.pause()

        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        log = _log_widget(app)
        log.scroll_to(y=3, animate=False, immediate=True)
        await pilot.pause()
        assert log.scroll_offset.y == 3

        panel._rendered_width = 0
        panel._reflow_lines()
        await pilot.pause()

        assert log.scroll_offset.y == 3
