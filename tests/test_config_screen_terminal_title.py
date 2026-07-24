# hatty — MIT License. See LICENSE file for details.
from textual.widgets import Input, SelectionList

from hatty.ui.config_screen import ConfigScreen
from tests.conftest import make_config


async def test_config_screen_shows_terminal_title_fields(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=make_config())
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_show_config()
        await pilot.pause()

        assert isinstance(app.screen, ConfigScreen)
        toggle = app.screen.query_one("#cfg_terminal_title_enabled", SelectionList)
        assert "enabled" in toggle.selected
        title_input = app.screen.query_one("#cfg_terminal_title", Input)
        assert title_input.value == "hatty"


async def test_saving_config_screen_persists_terminal_title(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=make_config())
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_show_config()
        await pilot.pause()

        app.screen.query_one("#cfg_terminal_title", Input).value = "my-hatty"
        await pilot.pause()

        await pilot.press("ctrl+s")
        await pilot.pause()

        assert app.app_config["terminal_title"] == "my-hatty"
        assert app.app_config["terminal_title_enabled"] is True


async def test_disabling_terminal_title_toggle_persists_disabled(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=make_config())
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_show_config()
        await pilot.pause()

        toggle = app.screen.query_one("#cfg_terminal_title_enabled", SelectionList)
        toggle.deselect("enabled")
        await pilot.pause()

        await pilot.press("ctrl+s")
        await pilot.pause()

        assert app.app_config["terminal_title_enabled"] is False
