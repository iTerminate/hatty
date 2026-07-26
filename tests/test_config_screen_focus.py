# hatty — MIT License. See LICENSE file for details.
from textual.widgets import Input, ListView

from hatty.ui.config_screen import ConfigScreen
from hatty.ui.help_popup import HelpPopup
from tests.conftest import make_config

_CONFIG = {
    **make_config(),
    "lists": {},
}


async def test_config_screen_initially_focuses_category_menu(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_show_config()
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, ConfigScreen)
        assert app.focused is screen.query_one("#cfg_category_list", ListView)


async def test_question_mark_opens_help_on_config_screen(make_app, sample_entities):
    """Issue #7: ConfigScreen isn't one of HACLI.action_show_help's six known
    pages, so "?" used to silently show the unrelated Main page instead."""
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_show_config()
        await pilot.pause()
        assert isinstance(app.screen, ConfigScreen)

        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpPopup)
        assert app.screen._pages[0][0] == "Config"
        assert app.screen._active_index == 0
        descriptions = [desc for _, desc in app.screen._binding_rows]
        assert "Save" in descriptions
        assert "Back/Cancel" in descriptions


async def test_entering_home_assistant_category_focuses_url_input(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_show_config()
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, ConfigScreen)
        screen.show_category("cat_home_assistant")
        await pilot.pause()

        assert app.focused is screen.query_one("#cfg_url", Input)


async def test_space_does_not_toggle_list_membership_on_config_screen(make_app, sample_entities):
    # Regression (#187): main-table bindings must not leak to the hidden base
    # table while ConfigScreen (or any other pushed screen) is active.
    app = make_app(entities=sample_entities)  # default config selects "my_list"
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name is not None
        before = dict(app.entity_lists)

        app.action_show_config()
        await pilot.pause()
        assert isinstance(app.screen, ConfigScreen)
        assert app.check_action("toggle_list_membership", ()) is False

        await pilot.press("space")
        await pilot.pause()
        assert isinstance(app.screen, ConfigScreen)
        assert app.entity_lists == before
