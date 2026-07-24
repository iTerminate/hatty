# hatty — MIT License. See LICENSE file for details.
"""Config screen connection UX: on-screen Save/Cancel/Test buttons and live
reconnect on save (issue #185)."""

from textual.widgets import Button, Input, Label, Select

import hatty.ui.config_screen as config_screen
from hatty.ui.config_screen import ConfigScreen
from hatty.ui.entity_table import EntitiesTable
from tests.conftest import make_config

_CONFIG = {**make_config(), "lists": {}}


async def _open_config(app, pilot, category: str | None = None):
    await pilot.pause()
    app.action_show_config()
    await pilot.pause()
    assert isinstance(app.screen, ConfigScreen)
    screen = app.screen
    if category is not None:
        screen.show_category(category)
        await pilot.pause()
    return screen


async def test_save_button_persists_and_dismisses(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot, category="cat_home_assistant")
        screen.query_one("#cfg_url", Input).value = "http://newhost:8123"
        await pilot.pause()

        screen.query_one("#cfg_save", Button).press()
        await pilot.pause()
        await pilot.pause()

        assert not isinstance(app.screen, ConfigScreen)
        assert app.app_config["home_assistant"]["url"] == "http://newhost:8123"


async def test_cancel_button_discards_changes(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot, category="cat_home_assistant")
        screen.query_one("#cfg_url", Input).value = "http://discarded:8123"
        await pilot.pause()

        screen.query_one("#cfg_cancel", Button).press()
        await pilot.pause()

        assert not isinstance(app.screen, ConfigScreen)
        assert app.app_config["home_assistant"]["url"] == make_config()["home_assistant"]["url"]


async def test_test_connection_button_shows_status(make_app, sample_entities, monkeypatch):
    async def fake_probe(url, token, timeout=5.0):
        return True, f"Connected — Home Assistant 2026.7 ({url})"

    monkeypatch.setattr(config_screen, "probe_connection", fake_probe)

    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot, category="cat_home_assistant")
        screen.query_one("#cfg_url", Input).value = "https://myha:8123"
        screen.query_one("#cfg_token", Input).value = "tok"
        await pilot.pause()

        screen.query_one("#cfg_test", Button).press()
        await pilot.pause()
        await pilot.pause()

        status = screen.query_one("#cfg_conn_status", Label)
        assert "Connected" in str(status.content)
        assert status.has_class("-ok")


async def test_send_test_notification_button_shows_status(make_app, sample_entities, monkeypatch):
    async def fake_send_test_ntfy(prefs, title, body, timeout=5.0):
        return True, f"Test notification sent to {prefs['ntfy_topic']}."

    monkeypatch.setattr(config_screen, "send_test_ntfy", fake_send_test_ntfy)

    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot, category="cat_notifications")
        screen.query_one("#cfg_ntfy_topic", Input).value = "alerts"
        await pilot.pause()

        screen.query_one("#cfg_ntfy_test", Button).press()
        await pilot.pause()
        await pilot.pause()

        status = screen.query_one("#cfg_ntfy_status", Label)
        assert "alerts" in str(status.content)
        assert status.has_class("-ok")


async def test_send_test_notification_button_shows_failure(make_app, sample_entities, monkeypatch):
    async def fake_send_test_ntfy(prefs, title, body, timeout=5.0):
        return False, "ntfy rejected the credentials (401)."

    monkeypatch.setattr(config_screen, "send_test_ntfy", fake_send_test_ntfy)

    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot, category="cat_notifications")
        screen.query_one("#cfg_ntfy_topic", Input).value = "alerts"
        await pilot.pause()

        screen.query_one("#cfg_ntfy_test", Button).press()
        await pilot.pause()
        await pilot.pause()

        status = screen.query_one("#cfg_ntfy_status", Label)
        assert "rejected" in str(status.content)
        assert status.has_class("-error")


async def test_test_connection_requires_both_fields(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot, category="cat_home_assistant")
        screen.query_one("#cfg_url", Input).value = "https://myha:8123"
        screen.query_one("#cfg_token", Input).value = ""
        await pilot.pause()

        screen.action_test_connection()
        await pilot.pause()

        status = screen.query_one("#cfg_conn_status", Label)
        assert status.has_class("-error")


async def test_save_with_changed_url_reconnects_live(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot, category="cat_home_assistant")
        old_client = app.client
        screen.query_one("#cfg_url", Input).value = "http://relocated:8123"
        await pilot.pause()

        screen.action_save_and_close()
        await pilot.pause()
        await pilot.pause()

        # URL propagated and a fresh client was started (no restart required).
        assert app.ha_url == "http://relocated:8123"
        assert app.client is not old_client
        assert app.query_one(EntitiesTable).row_count == len(sample_entities)


async def test_letter_keys_do_not_hijack_focus_off_inputs(make_app, sample_entities):
    """Bare single-letter bindings used to fire once focus tabbed onto a non-Input
    widget — a stray "s" dismissed the whole screen (issue #192). With modifier-
    prefixed bindings, letters reach the focused widget instead."""
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot, category="cat_appearance")
        token_masked = screen.query_one("#cfg_token", Input).password

        screen.query_one("#cfg_theme", Select).focus()
        await pilot.pause()

        for key in ("s", "o", "v"):
            await pilot.press(key)
            await pilot.pause()

        # Screen not dismissed by "s", token mask not toggled by "v".
        assert isinstance(app.screen, ConfigScreen)
        assert screen.query_one("#cfg_token", Input).password == token_masked


async def test_ctrl_s_still_saves_and_dismisses(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot)
        screen.query_one("#cfg_url", Input).value = "http://ctrls:8123"
        await pilot.pause()

        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()

        assert not isinstance(app.screen, ConfigScreen)
        assert app.app_config["home_assistant"]["url"] == "http://ctrls:8123"


async def test_save_without_connection_change_keeps_client(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_config(app, pilot)
        old_client = app.client
        # Change only a display preference, not the connection.
        from textual.widgets import Select

        screen.query_one("#cfg_graph_hours", Select).value = 12
        await pilot.pause()

        screen.action_save_and_close()
        await pilot.pause()

        assert app.client is old_client
        assert app.app_config["graph_hours"] == 12
