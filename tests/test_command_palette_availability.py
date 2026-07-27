# hatty — MIT License. See LICENSE file for details.
"""Regression tests for issue #9: HACLI.check_action's per-screen carve-outs
(the DashboardScreen/DeviceTreeScreen/GraphPreviewScreen/"any other pushed
screen" branches) each list their own small set of still-live app actions, and
`command_palette` was missing from every one of them — so Ctrl+P silently did
nothing anywhere except the base entity table. Dashboard and List are both
primary displays a user switches between, and the palette is how that switch
happens, so it must stay reachable regardless of which screen is on top."""
from textual.command import CommandPalette
from textual.coordinate import Coordinate

from hatty.ui.config_screen import ConfigScreen
from hatty.ui.device_tree_screen import DeviceTreeScreen
from hatty.ui.entity_table import EntitiesTable
from hatty.ui.graph.preview_screen import GraphPreviewScreen
from tests.conftest import NO_LIST_CONFIG, make_config


async def test_command_palette_opens_from_dashboard(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        assert app.check_action("command_palette", ()) is True

        await pilot.press("ctrl+p")
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)


async def test_command_palette_opens_from_device_tree(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        assert isinstance(app.screen, DeviceTreeScreen)
        assert app.check_action("command_palette", ()) is True

        await pilot.press("ctrl+p")
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)


async def test_command_palette_opens_from_fullscreen_graph(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)
        assert app.check_action("command_palette", ()) is True

        await pilot.press("ctrl+p")
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)


async def test_command_palette_opens_from_generic_pushed_screen(make_app):
    # Covers check_action's fallback branch for any other pushed screen
    # (ConfigScreen, LightControlScreen, popups, …).
    app = make_app(config_data={**make_config(), "lists": {}})
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_show_config()
        await pilot.pause()
        assert isinstance(app.screen, ConfigScreen)
        assert app.check_action("command_palette", ()) is True

        await pilot.press("ctrl+p")
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)
