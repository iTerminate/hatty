# hatty — MIT License. See LICENSE file for details.
from textual.app import App, ComposeResult
from textual.widgets import Button, Input

from hatty.ui.rename_entity_popup import RenameEntityPopup


class PopupApp(App):
    def compose(self) -> ComposeResult:
        yield Button("open")


async def test_input_prefilled_with_current_name():
    app = PopupApp()
    async with app.run_test() as pilot:
        await app.push_screen(RenameEntityPopup("light.lamp", "Lamp"))
        await pilot.pause()
        assert app.screen.query_one("#rename_input", Input).value == "Lamp"


async def test_save_locally_dismisses_with_local_scope():
    app = PopupApp()
    result = None

    async with app.run_test() as pilot:

        def callback(value):
            nonlocal result
            result = value

        app.push_screen(RenameEntityPopup("light.lamp", "Lamp"), callback)
        await pilot.pause()
        app.screen.query_one("#rename_input", Input).value = "New Name"
        await pilot.pause()
        app.screen.query_one("#btn_save_local", Button).press()
        await pilot.pause()

    assert result == {"name": "New Name", "scope": "local"}


async def test_save_to_ha_dismisses_with_ha_scope():
    app = PopupApp()
    result = None

    async with app.run_test() as pilot:

        def callback(value):
            nonlocal result
            result = value

        app.push_screen(RenameEntityPopup("light.lamp", "Lamp"), callback)
        await pilot.pause()
        app.screen.query_one("#rename_input", Input).value = "New Name"
        await pilot.pause()
        app.screen.query_one("#btn_save_ha", Button).press()
        await pilot.pause()

    assert result == {"name": "New Name", "scope": "ha"}


async def test_cancel_dismisses_with_none():
    app = PopupApp()
    result = "sentinel"

    async with app.run_test() as pilot:

        def callback(value):
            nonlocal result
            result = value

        app.push_screen(RenameEntityPopup("light.lamp", "Lamp"), callback)
        await pilot.pause()
        app.screen.query_one("#btn_cancel", Button).press()
        await pilot.pause()

    assert result is None


async def test_blank_name_dismisses_with_none_value():
    app = PopupApp()
    result = None

    async with app.run_test() as pilot:

        def callback(value):
            nonlocal result
            result = value

        app.push_screen(RenameEntityPopup("light.lamp", "Lamp"), callback)
        await pilot.pause()
        app.screen.query_one("#rename_input", Input).value = "   "
        await pilot.pause()
        app.screen.query_one("#btn_save_local", Button).press()
        await pilot.pause()

    assert result == {"name": None, "scope": "local"}


async def test_enter_triggers_save_locally():
    app = PopupApp()
    result = None

    async with app.run_test() as pilot:

        def callback(value):
            nonlocal result
            result = value

        app.push_screen(RenameEntityPopup("light.lamp", "Lamp"), callback)
        await pilot.pause()
        app.screen.query_one("#rename_input", Input).focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    assert result == {"name": "Lamp", "scope": "local"}


async def test_no_override_hides_hint_and_revert_button():
    app = PopupApp()
    async with app.run_test() as pilot:
        await app.push_screen(RenameEntityPopup("light.lamp", "Lamp"))
        await pilot.pause()
        assert not app.screen.query(".override-hint")
        assert not app.screen.query("#btn_revert")


async def test_override_shows_hint_and_revert_button():
    app = PopupApp()
    async with app.run_test() as pilot:
        await app.push_screen(RenameEntityPopup("light.lamp", "My Lamp", has_override=True))
        await pilot.pause()
        assert app.screen.query_one(".override-hint")
        assert app.screen.query_one("#btn_revert", Button)


async def test_revert_dismisses_clearing_local_override():
    app = PopupApp()
    result = "sentinel"

    async with app.run_test() as pilot:

        def callback(value):
            nonlocal result
            result = value

        app.push_screen(RenameEntityPopup("light.lamp", "My Lamp", has_override=True), callback)
        await pilot.pause()
        app.screen.query_one("#btn_revert", Button).press()
        await pilot.pause()

    assert result == {"name": None, "scope": "local"}


async def test_arrow_keys_cycle_focus_across_three_buttons():
    app = PopupApp()
    async with app.run_test() as pilot:
        await app.push_screen(RenameEntityPopup("light.lamp", "Lamp"))
        await pilot.pause()
        local_btn = app.screen.query_one("#btn_save_local", Button)
        ha_btn = app.screen.query_one("#btn_save_ha", Button)
        cancel_btn = app.screen.query_one("#btn_cancel", Button)

        local_btn.focus()
        await pilot.pause()

        await pilot.press("right")
        await pilot.pause()
        assert app.screen.focused is ha_btn

        await pilot.press("right")
        await pilot.pause()
        assert app.screen.focused is cancel_btn

        await pilot.press("right")
        await pilot.pause()
        assert app.screen.focused is local_btn


async def test_arrow_keys_cycle_focus_across_four_buttons_with_override():
    app = PopupApp()
    async with app.run_test() as pilot:
        await app.push_screen(RenameEntityPopup("light.lamp", "My Lamp", has_override=True))
        await pilot.pause()
        local_btn = app.screen.query_one("#btn_save_local", Button)
        ha_btn = app.screen.query_one("#btn_save_ha", Button)
        revert_btn = app.screen.query_one("#btn_revert", Button)
        cancel_btn = app.screen.query_one("#btn_cancel", Button)

        local_btn.focus()
        await pilot.pause()

        for expected in (ha_btn, revert_btn, cancel_btn, local_btn):
            await pilot.press("right")
            await pilot.pause()
            assert app.screen.focused is expected

        await pilot.press("left")
        await pilot.pause()
        assert app.screen.focused is cancel_btn
