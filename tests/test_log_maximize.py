# hatty — MIT License. See LICENSE file for details.
"""Maximize toggle for the activity/device log panel (issue #70)."""

from hatty.ui.activity_log_panel import ActivityLogPanel
from tests.conftest import make_config

_NO_LIST_CONFIG = make_config(lists={})


async def test_f_toggles_maximized_class(make_app):
    app = make_app(config_data=_NO_LIST_CONFIG)
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
    app = make_app(config_data=_NO_LIST_CONFIG)
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
    app = make_app(config_data=_NO_LIST_CONFIG)
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


async def test_reopening_log_is_not_maximized(make_app):
    app = make_app(config_data=_NO_LIST_CONFIG)
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
