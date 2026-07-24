# hatty — MIT License. See LICENSE file for details.
"""Config screen top-level category menu (issue #252): opening Configuration
shows a menu first, drilling into a category swaps the body in place, and
escape is back-aware (returns to the menu before dismissing the screen)."""

from textual.widgets import ContentSwitcher, Input, Label, ListView

from hatty.ui.config_screen import ConfigScreen
from tests.conftest import make_config

_CONFIG = {**make_config(), "lists": {}}


async def _open_config(app, pilot):
    await pilot.pause()
    app.action_show_config()
    await pilot.pause()
    assert isinstance(app.screen, ConfigScreen)
    return app.screen


async def test_config_screen_opens_on_category_menu(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot)

        switcher = screen.query_one("#cfg_switcher", ContentSwitcher)
        assert switcher.current == "cat_menu"
        assert str(screen.query_one("#cfg_breadcrumb", Label).content) == "Configuration"


async def test_selecting_a_category_swaps_the_pane_and_updates_breadcrumb(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot)

        screen.show_category("cat_home_assistant")
        await pilot.pause()

        switcher = screen.query_one("#cfg_switcher", ContentSwitcher)
        assert switcher.current == "cat_home_assistant"
        assert "Home Assistant" in str(screen.query_one("#cfg_breadcrumb", Label).content)
        assert app.focused is screen.query_one("#cfg_url", Input)


async def test_list_view_selected_on_category_menu_drills_in(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot)

        list_view = screen.query_one("#cfg_category_list", ListView)
        list_view.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        switcher = screen.query_one("#cfg_switcher", ContentSwitcher)
        assert switcher.current == "cat_home_assistant"


async def test_escape_inside_a_category_returns_to_menu_without_dismissing(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot)
        screen.show_category("cat_notifications")
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()

        assert isinstance(app.screen, ConfigScreen)
        switcher = screen.query_one("#cfg_switcher", ContentSwitcher)
        assert switcher.current == "cat_menu"
        assert app.focused is screen.query_one("#cfg_category_list", ListView)


async def test_escape_at_the_menu_dismisses_the_screen(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot)
        switcher = screen.query_one("#cfg_switcher", ContentSwitcher)
        assert switcher.current == "cat_menu"

        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, ConfigScreen)


async def test_cancel_button_dismisses_even_from_inside_a_category(make_app, sample_entities):
    """The on-screen Cancel button (unlike escape) always abandons and closes,
    even when pressed from inside a category pane."""
    from textual.widgets import Button

    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot)
        screen.show_category("cat_home_assistant")
        await pilot.pause()

        screen.query_one("#cfg_cancel", Button).press()
        await pilot.pause()

        assert not isinstance(app.screen, ConfigScreen)


async def test_widgets_in_every_category_remain_queryable_while_menu_is_shown(make_app, sample_entities):
    """ContentSwitcher mounts every pane up front, so save logic can keep
    reading widgets across categories regardless of which pane is visible."""
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot)

        switcher = screen.query_one("#cfg_switcher", ContentSwitcher)
        assert switcher.current == "cat_menu"
        # These live in other categories' panes but must still resolve.
        assert screen.query_one("#cfg_url", Input) is not None
        assert screen.query_one("#cfg_ntfy_topic", Input) is not None
