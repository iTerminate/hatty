# hatty — MIT License. See LICENSE file for details.
"""Acceptance tests for the config screen's Keybindings category (issue #50):
selecting a row and pressing a key rebinds it, conflicts are blocked with an
inline error, and a save takes effect live without a restart."""

from textual.widgets import Button, DataTable, Static

from hatty.controllers import keybindings as kb
from hatty.ui.config_screen import ConfigScreen
from hatty.ui.key_capture_popup import KeyCapturePopup
from tests.conftest import make_config


async def _open_keybindings(app, pilot):
    await pilot.pause()
    app.action_show_config()
    await pilot.pause()
    assert isinstance(app.screen, ConfigScreen)
    app.screen.show_category("cat_keybindings")
    await pilot.pause()
    return app.screen


async def test_config_screen_boots_with_an_override_applied(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data={**make_config(), "keybindings": {"log.toggle": "A"}})
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "A" in app.screen.active_bindings
        assert app.screen.active_bindings["A"].binding.action == "toggle_activity_log"
        assert "a" not in app.screen.active_bindings


async def test_rebind_via_capture_popup_and_save_takes_effect_live(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=make_config())
    async with app.run_test() as pilot:
        screen = await _open_keybindings(app, pilot)

        table = screen.query_one("#cfg_keys", DataTable)
        row = table.get_row_index("log.toggle")
        table.move_cursor(row=row)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, KeyCapturePopup)
        await pilot.press("A")
        await pilot.pause()

        # back on the config screen, the table reflects the new key
        assert isinstance(app.screen, ConfigScreen)
        assert screen._keybindings["log.toggle"] == "A"

        await pilot.press("ctrl+s")
        await pilot.pause()

        assert app.app_config["keybindings"] == {"log.toggle": "A"}
        assert "A" in app.screen.active_bindings
        assert "a" not in app.screen.active_bindings


async def test_conflicting_key_keeps_popup_open_with_an_error(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=make_config())
    async with app.run_test() as pilot:
        screen = await _open_keybindings(app, pilot)

        table = screen.query_one("#cfg_keys", DataTable)
        table.move_cursor(row=table.get_row_index("log.toggle"))
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        popup = app.screen
        assert isinstance(popup, KeyCapturePopup)
        # "v" is log.scope's default key, in the same scopes as log.toggle.
        await pilot.press("v")
        await pilot.pause()

        assert app.screen is popup
        error_text = str(popup.query_one("#key_capture_error", Static)._Static__content)
        assert "Scope" in error_text

        # cancel out cleanly
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert isinstance(app.screen, ConfigScreen)
        assert "log.toggle" not in screen._keybindings


async def test_reserved_key_keeps_popup_open_with_an_error(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=make_config())
    async with app.run_test() as pilot:
        screen = await _open_keybindings(app, pilot)

        table = screen.query_one("#cfg_keys", DataTable)
        table.move_cursor(row=table.get_row_index("log.toggle"))
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        popup = app.screen
        assert isinstance(popup, KeyCapturePopup)
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert app.screen is popup
        assert "reserved" in str(popup.query_one("#key_capture_error", Static)._Static__content)


async def test_delete_resets_to_default_in_capture_popup(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data={**make_config(), "keybindings": {"log.toggle": "A"}})
    async with app.run_test() as pilot:
        screen = await _open_keybindings(app, pilot)
        assert screen._keybindings == {"log.toggle": "A"}

        table = screen.query_one("#cfg_keys", DataTable)
        table.move_cursor(row=table.get_row_index("log.toggle"))
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, KeyCapturePopup)
        await pilot.press("delete")
        await pilot.pause()

        assert isinstance(app.screen, ConfigScreen)
        assert "log.toggle" not in screen._keybindings


async def test_reset_all_button_clears_every_override(make_app, sample_entities):
    app = make_app(
        entities=sample_entities,
        config_data={**make_config(), "keybindings": {"log.toggle": "A", "nav.back": "backspace"}},
    )
    async with app.run_test() as pilot:
        screen = await _open_keybindings(app, pilot)
        assert screen._keybindings == {"log.toggle": "A", "nav.back": "backspace"}

        screen.query_one("#cfg_keys_reset", Button).press()
        await pilot.pause()

        assert screen._keybindings == {}

        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.app_config["keybindings"] == {}
        assert kb.resolve_keymap({})["log.toggle"] == "a"
        assert "a" in app.screen.active_bindings
