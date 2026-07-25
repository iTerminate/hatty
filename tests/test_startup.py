# hatty — MIT License. See LICENSE file for details.
import asyncio

import hatty.main as main_module
from hatty.main import HACLI
from hatty.ui.entity_table import EntitiesTable
from hatty.ui.splash_screen import SplashScreen
from tests.conftest import NO_LIST_CONFIG, FakeHAClient, make_config


class _HoldingClient(FakeHAClient):
    """FakeHAClient that withholds the initial get_states until told to deliver."""

    async def listen(self):
        pass

    def deliver_states(self):
        states_id = self._next_id()
        self.pending_requests[states_id] = "get_states"
        self.on_message({"id": states_id, "type": "result", "success": True, "result": list(self._initial_entities)})


def _holding_factory(entities):
    def factory(url, token, on_message, logger):
        fake = _HoldingClient(url, token, on_message, logger)
        fake._initial_entities = list(entities)
        return fake

    return factory


_HTTPS_CONFIG = {
    **make_config(url="https://fake.ha.local:8123"),
    "lists": {},
}


def _http_warning_count(app):
    return sum(1 for n in app._notifications if n.title == "Insecure connection")


async def test_http_token_warning_fires_once(make_app, sample_entities):
    # A cleartext http:// URL warns the user their token is sent unencrypted (#158),
    # but only once per run — a later reconnect must not re-warn.
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert _http_warning_count(app) == 1
        app.conn_ctl._on_ha_connected({"attempt": 1})
        await pilot.pause()
        assert _http_warning_count(app) == 1


async def test_https_url_does_not_warn(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_HTTPS_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert _http_warning_count(app) == 0


async def test_app_boots_and_shows_entities(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one(EntitiesTable).row_count == len(sample_entities)


async def test_app_shows_default_list_on_startup(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        assert table.row_count == 1
        assert "my_list" in app.sub_title


async def test_app_missing_config_launches_onboarding():
    # A missing config now opens the first-run wizard instead of dead-ending (#72).
    from hatty.ui.onboarding_screen import OnboardingScreen

    app = HACLI(config_path="/nonexistent/config.yaml")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, OnboardingScreen)


async def test_app_parse_error_shows_in_subtitle(tmp_path):
    # A file that fails to parse is a real error, not a first-run — don't clobber it.
    bad = tmp_path / "config.yaml"
    bad.write_text("home_assistant: [this is not: valid mapping\n")
    app = HACLI(config_path=str(bad))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "Error" in app.sub_title


async def test_app_shows_all_entities_when_no_list_configured(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name is None
        assert app.query_one(EntitiesTable).row_count == len(sample_entities)


async def test_app_subtitle_shows_connected_url_when_no_list(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "fake.ha.local" in app.sub_title


async def test_app_state_initialized_on_mount(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name == "my_list"
        assert isinstance(app.all_entities, list)
        assert len(app.all_entities) > 0


async def test_splash_shown_until_states_arrive_then_auto_dismissed(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    app._client_factory = _holding_factory(sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, SplashScreen)

        app.client.deliver_states()
        await pilot.pause()

        assert not isinstance(app.screen, SplashScreen)
        assert app.query_one(EntitiesTable).row_count == len(sample_entities)


async def test_splash_dismissed_early_by_keypress(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    app._client_factory = _holding_factory(sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, SplashScreen)

        await pilot.press("x")
        await pilot.pause()
        assert not isinstance(app.screen, SplashScreen)

        # A late get_states must not pop whatever screen the user is on now.
        stack_depth = len(app.screen_stack)
        app.client.deliver_states()
        await pilot.pause()
        assert len(app.screen_stack) == stack_depth
        assert app.query_one(EntitiesTable).row_count == len(sample_entities)


async def test_splash_shows_connection_retry_status(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    app._client_factory = _holding_factory(sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        splash = app.screen
        assert isinstance(splash, SplashScreen)

        app.handle_ha_message({"type": "ha_connect_failed", "error": "refused", "attempt": 2})
        await pilot.pause()
        status = str(splash.query_one("#splash_status")._Static__content)
        assert "retry 2" in status.lower()


async def test_demo_splash_is_held_before_auto_dismiss(monkeypatch):
    # Issue #268: in --demo mode the seeded DemoHAClient answers get_states
    # almost instantly, so the splash must be held for DEMO_SPLASH_SECONDS
    # instead of popping the moment states arrive — otherwise it never appears
    # in the recorded screencast. Shrink the hold so the test runs fast.
    monkeypatch.setattr(main_module, "DEMO_SPLASH_SECONDS", 2.0)
    app = HACLI(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        # The (real, near-instant) demo client has already delivered states…
        assert len(app.all_entities) > 0
        # …but the demo hold keeps the splash up a moment longer regardless.
        assert isinstance(app.screen, SplashScreen)

        await asyncio.sleep(2.5)
        await pilot.pause()
        assert not isinstance(app.screen, SplashScreen)


async def test_demo_splash_still_key_dismissable_during_hold(monkeypatch):
    # A keypress must still skip the demo hold early; the deferred auto-dismiss
    # timer firing afterward must be a no-op rather than popping a later screen.
    monkeypatch.setattr(main_module, "DEMO_SPLASH_SECONDS", 2.0)
    app = HACLI(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, SplashScreen)

        await pilot.press("x")
        await pilot.pause()
        assert not isinstance(app.screen, SplashScreen)

        stack_depth = len(app.screen_stack)
        await asyncio.sleep(2.5)
        await pilot.pause()
        assert len(app.screen_stack) == stack_depth


async def test_auth_failure_dismisses_splash(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    app._client_factory = _holding_factory(sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, SplashScreen)

        app.handle_ha_message({"type": "ha_auth_failed", "error": "invalid"})
        await pilot.pause()
        assert not isinstance(app.screen, SplashScreen)
        assert "token" in app.sub_title.lower()


async def test_onboarding_path_never_shows_splash():
    from hatty.ui.onboarding_screen import OnboardingScreen

    app = HACLI(config_path="/nonexistent/config.yaml")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, OnboardingScreen)
        assert not any(isinstance(s, SplashScreen) for s in app.screen_stack)


async def test_connect_failed_message_shows_retry_status(make_app, sample_entities):
    # Reconnect status is surfaced in the sub_title (issue #71), not a dead end.
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.handle_ha_message({"type": "ha_connect_failed", "error": "refused", "attempt": 1})
        await pilot.pause()
        assert "unreachable" in app.sub_title.lower()
        assert "retry" in app.sub_title.lower()


async def test_reconnecting_message_shows_countdown(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.handle_ha_message({"type": "ha_reconnecting", "attempt": 2, "delay": 10})
        await pilot.pause()
        assert "10s" in app.sub_title
        assert "attempt 2" in app.sub_title


async def test_auth_failed_message_prompts_token_fix(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.handle_ha_message({"type": "ha_auth_failed", "error": "invalid"})
        await pilot.pause()
        assert "token" in app.sub_title.lower()


async def test_disconnect_reshows_splash_then_reconnect_dismisses(make_app, sample_entities):
    # Issue #243: a mid-session drop re-shows the splash; a subsequent successful
    # get_states result (mirroring what a real reconnect does) dismisses it again.
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert not isinstance(app.screen, SplashScreen)

        app.handle_ha_message({"type": "ha_disconnect"})
        await pilot.pause()
        assert isinstance(app.screen, SplashScreen)
        status = str(app.screen.query_one("#splash_status")._Static__content)
        assert "reconnect" in status.lower()

        states_id = app.client._next_id()
        app.client.pending_requests[states_id] = "get_states"
        app.handle_ha_message(
            {"id": states_id, "type": "result", "success": True, "result": list(sample_entities)}
        )
        await pilot.pause()
        assert not isinstance(app.screen, SplashScreen)


async def test_reconnect_splash_is_key_dismissable_and_not_resticky(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()

        app.handle_ha_message({"type": "ha_disconnect"})
        await pilot.pause()
        assert isinstance(app.screen, SplashScreen)

        await pilot.press("x")
        await pilot.pause()
        assert not isinstance(app.screen, SplashScreen)

        # Further retry ticks in the same reconnect cycle must not re-push it.
        app.handle_ha_message({"type": "ha_reconnecting", "attempt": 1, "delay": 5})
        await pilot.pause()
        assert not isinstance(app.screen, SplashScreen)
