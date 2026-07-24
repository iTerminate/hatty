# hatty — MIT License. See LICENSE file for details.
from textual.containers import VerticalScroll

from hatty.ui.dashboard.screen import DashboardScreen
from tests.conftest import make_config

_HA = make_config(lists={})

_BIG = {**_HA, "dashboards": {"Main": {"rows": 8, "cols": 2, "slots": []}}}
_SMALL = {**_HA, "dashboards": {"Main": {"rows": 2, "cols": 2, "slots": []}}}


async def _open_dashboard(pilot, app) -> DashboardScreen:
    await pilot.press("d")
    await pilot.pause()
    assert isinstance(app.screen, DashboardScreen)
    await pilot.pause()
    return app.screen


async def test_large_dashboard_scrolls(make_app):
    app = make_app(config_data=_BIG)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = await _open_dashboard(pilot, app)
        scroll = screen.query_one("#dashboard_scroll", VerticalScroll)
        assert scroll.max_scroll_y > 0


async def test_small_dashboard_fills_without_scrolling(make_app):
    app = make_app(config_data=_SMALL)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = await _open_dashboard(pilot, app)
        scroll = screen.query_one("#dashboard_scroll", VerticalScroll)
        assert scroll.max_scroll_y == 0


async def test_cursor_to_bottom_scrolls_into_view(make_app):
    app = make_app(config_data=_BIG)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = await _open_dashboard(pilot, app)
        scroll = screen.query_one("#dashboard_scroll", VerticalScroll)
        assert scroll.scroll_offset.y == 0
        for _ in range(7):
            await pilot.press("down")
            await pilot.pause()
        assert screen.cursor_row == 7
        assert scroll.scroll_offset.y > 0
