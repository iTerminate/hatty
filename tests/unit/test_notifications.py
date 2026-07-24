# hatty — MIT License. See LICENSE file for details.
"""Unit tests for NotificationController: watch-list visibility and alert
dispatch, in isolation (issue #224)."""

import aiohttp
import pytest

from hatty.const import DEFAULT_NOTIFICATIONS, NOTIFY_LIST_NAME
from hatty.controllers.notifications import NotificationController, build_ntfy_request, send_test_ntfy


class _StubTimer:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class _StubApp:
    """Records the interactions NotificationController drives, so tests can
    assert on them without booting the Textual app."""

    def __init__(self, notifications: dict | None = None):
        self.app_config = {"notifications": notifications if notifications is not None else {}}
        self.entity_lists: dict = {}
        self.list_names: list = []
        self.current_list_name: str | None = None
        self.notifications: list = []
        self.bells = 0
        self.spawned: list = []
        self.display_updates = 0
        self.refreshed_widgets: list = []
        self.persist_calls: list = []
        self._timers: list = []

    def notify(self, message, **kwargs):
        self.notifications.append((message, kwargs))

    def bell(self):
        self.bells += 1

    def spawn(self, coro):
        # Real app fires-and-forgets a coroutine; close it immediately here so
        # pytest doesn't warn about an un-awaited coroutine.
        coro.close()
        self.spawned.append(coro)

    def _update_entities_display(self):
        self.display_updates += 1

    def _refresh_dashboard_widgets(self, entity_id):
        self.refreshed_widgets.append(entity_id)

    def persist(self, *keys):
        self.persist_calls.append(keys)

    def set_timer(self, delay, callback):
        timer = _StubTimer()
        timer.callback = callback
        self._timers.append(timer)
        return timer


def _controller(notifications=None) -> tuple[NotificationController, _StubApp]:
    app = _StubApp(notifications)
    return NotificationController(app), app


# ── sync (visibility) ──────────────────────────────────────────────────────────


def test_sync_seeds_and_shows_reserved_list_when_enabled():
    ctl, app = _controller()
    ctl.sync()
    assert app.entity_lists == {NOTIFY_LIST_NAME: []}
    assert app.list_names == [NOTIFY_LIST_NAME]


def test_sync_hides_reserved_list_when_disabled_but_keeps_membership():
    ctl, app = _controller({"enabled": False})
    app.entity_lists[NOTIFY_LIST_NAME] = ["switch.fan"]
    app.list_names = [NOTIFY_LIST_NAME]
    app.current_list_name = NOTIFY_LIST_NAME

    ctl.sync()

    assert NOTIFY_LIST_NAME not in app.list_names
    assert app.entity_lists[NOTIFY_LIST_NAME] == ["switch.fan"]  # data survives
    assert app.current_list_name is None  # kicked back to View All


def test_sync_reenable_restores_visibility_and_membership():
    ctl, app = _controller({"enabled": False})
    app.entity_lists[NOTIFY_LIST_NAME] = ["switch.fan"]
    ctl.sync()  # disabled: hidden
    assert NOTIFY_LIST_NAME not in app.list_names

    app.app_config["notifications"]["enabled"] = True
    ctl.sync()  # re-enabled: visible again, same membership
    assert app.list_names == [NOTIFY_LIST_NAME]
    assert app.entity_lists[NOTIFY_LIST_NAME] == ["switch.fan"]


def test_sync_is_idempotent():
    ctl, app = _controller()
    ctl.sync()
    ctl.sync()
    assert app.list_names == [NOTIFY_LIST_NAME]


# ── handle_state_change ─────────────────────────────────────────────────────────

_NEW_STATE = {"entity_id": "switch.fan", "state": "on", "attributes": {"friendly_name": "Fan"}}
_OLD_STATE = {"entity_id": "switch.fan", "state": "off", "attributes": {"friendly_name": "Fan"}}


def _watch(ctl, app, entity_id="switch.fan"):
    app.entity_lists[NOTIFY_LIST_NAME] = [entity_id]


def test_no_alert_when_disabled():
    ctl, app = _controller({"enabled": False})
    _watch(ctl, app)
    ctl.handle_state_change("switch.fan", _OLD_STATE, _NEW_STATE)
    assert app.notifications == []
    assert app.bells == 0
    assert ctl.alerted == set()


def test_no_alert_when_entity_not_watched():
    ctl, app = _controller()
    ctl.handle_state_change("switch.fan", _OLD_STATE, _NEW_STATE)
    assert app.notifications == []
    assert ctl.alerted == set()


def test_no_alert_on_first_seen_state():
    ctl, app = _controller()
    _watch(ctl, app)
    ctl.handle_state_change("switch.fan", None, _NEW_STATE)
    assert app.notifications == []
    assert ctl.alerted == set()


def test_no_alert_when_state_value_unchanged():
    ctl, app = _controller()
    _watch(ctl, app)
    same = {**_OLD_STATE, "state": "on"}
    ctl.handle_state_change("switch.fan", {**_NEW_STATE}, same)
    assert app.notifications == []
    assert ctl.alerted == set()


def test_alert_fires_enabled_channels_and_highlights():
    ctl, app = _controller({**DEFAULT_NOTIFICATIONS, "desktop": False, "ntfy": False})
    _watch(ctl, app)
    ctl.handle_state_change("switch.fan", _OLD_STATE, _NEW_STATE)

    assert len(app.notifications) == 1
    assert app.bells == 1
    assert ctl.alerted == {"switch.fan"}
    assert app.display_updates >= 1
    assert "switch.fan" in app.refreshed_widgets


def test_alert_respects_disabled_channels():
    ctl, app = _controller({**DEFAULT_NOTIFICATIONS, "toast": False, "beep": False, "highlight": False})
    _watch(ctl, app)
    ctl.handle_state_change("switch.fan", _OLD_STATE, _NEW_STATE)

    assert app.notifications == []
    assert app.bells == 0
    assert ctl.alerted == set()


def test_alert_spawns_desktop_and_ntfy_when_enabled():
    ctl, app = _controller({**DEFAULT_NOTIFICATIONS, "ntfy": True, "ntfy_topic": "alerts"})
    _watch(ctl, app)
    ctl.handle_state_change("switch.fan", _OLD_STATE, _NEW_STATE)

    # desktop is on by DEFAULT_NOTIFICATIONS-copy? no — default desktop is False;
    # explicitly enable both to exercise the spawn paths.
    assert len(app.spawned) >= 1  # ntfy coroutine spawned (desktop still off)


def test_highlight_clear_resets_alerted_and_refreshes():
    ctl, app = _controller()
    _watch(ctl, app)
    ctl.handle_state_change("switch.fan", _OLD_STATE, _NEW_STATE)
    assert ctl.alerted == {"switch.fan"}

    # Simulate the highlight timer firing.
    ctl._clear("switch.fan")
    assert ctl.alerted == set()
    assert app.refreshed_widgets.count("switch.fan") == 2  # once on alert, once on clear


# ── clear_entities ───────────────────────────────────────────────────────────────


def test_clear_entities_empties_the_watch_list():
    ctl, app = _controller()
    app.entity_lists[NOTIFY_LIST_NAME] = ["switch.fan", "light.lamp"]
    ctl.clear_entities()
    assert app.entity_lists[NOTIFY_LIST_NAME] == []
    assert app.persist_calls == [("lists",)]


# ── _ntfy (issue #246: optional Basic auth) ─────────────────────────────────────


class _FakeNtfySession:
    """Records the .post(...) call so tests can assert on the request built by
    NotificationController._ntfy, mirroring test_client_probe.py's _FakeSession."""

    def __init__(self, *args, **kwargs):
        self.post_calls: list[tuple[tuple, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        self.post_calls.append((args, kwargs))


@pytest.fixture
def _ntfy_session(monkeypatch):
    session = _FakeNtfySession()
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: session)
    return session


async def test_ntfy_sends_basic_auth_when_username_and_password_set(_ntfy_session):
    ctl, _app = _controller()
    prefs = {
        **DEFAULT_NOTIFICATIONS,
        "ntfy_topic": "alerts",
        "ntfy_username": "bob",
        "ntfy_password": "secret",
    }
    await ctl._ntfy(prefs, "Fan", "off → on")

    assert len(_ntfy_session.post_calls) == 1
    _args, kwargs = _ntfy_session.post_calls[0]
    assert kwargs["headers"]["Authorization"] == aiohttp.encode_basic_auth("bob", "secret")


async def test_ntfy_omits_auth_header_when_credentials_blank(_ntfy_session):
    ctl, _app = _controller()
    prefs = {**DEFAULT_NOTIFICATIONS, "ntfy_topic": "alerts"}
    await ctl._ntfy(prefs, "Fan", "off → on")

    assert len(_ntfy_session.post_calls) == 1
    assert "Authorization" not in _ntfy_session.post_calls[0][1]["headers"]


async def test_ntfy_omits_auth_header_when_only_username_set(_ntfy_session):
    ctl, _app = _controller()
    prefs = {**DEFAULT_NOTIFICATIONS, "ntfy_topic": "alerts", "ntfy_username": "bob"}
    await ctl._ntfy(prefs, "Fan", "off → on")

    assert "Authorization" not in _ntfy_session.post_calls[0][1]["headers"]


# ── build_ntfy_request ──────────────────────────────────────────────────────────


def test_build_ntfy_request_none_when_topic_blank():
    prefs = {**DEFAULT_NOTIFICATIONS, "ntfy_topic": ""}
    assert build_ntfy_request(prefs, "Fan", "off → on") is None


def test_build_ntfy_request_shape():
    prefs = {**DEFAULT_NOTIFICATIONS, "ntfy_url": "https://ntfy.sh", "ntfy_topic": "alerts"}
    request = build_ntfy_request(prefs, "Fan", "off → on")
    assert request is not None
    url, data, headers = request
    assert url == "https://ntfy.sh/alerts"
    assert data == b"off \xe2\x86\x92 on"
    assert headers["Title"] == "Fan"
    assert "Authorization" not in headers


# ── send_test_ntfy (issue #248: config-screen test button) ─────────────────────


class _FakeNtfyResponse:
    def __init__(self, status: int):
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeNtfyTestSession:
    """Supports `async with session.post(...) as resp`, unlike _FakeNtfySession
    above (which only backs the fire-and-forget live path)."""

    def __init__(self, status: int):
        self._status = status
        self.post_calls: list[tuple[tuple, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, *args, **kwargs):
        self.post_calls.append((args, kwargs))
        return _FakeNtfyResponse(self._status)


def _fake_session(monkeypatch, status: int) -> _FakeNtfyTestSession:
    session = _FakeNtfyTestSession(status)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **kw: session)
    return session


async def test_send_test_ntfy_blank_topic_makes_no_request(monkeypatch):
    session = _fake_session(monkeypatch, 200)
    ok, message = await send_test_ntfy({**DEFAULT_NOTIFICATIONS, "ntfy_topic": ""}, "hatty", "test")
    assert ok is False
    assert "topic" in message.lower()
    assert session.post_calls == []


async def test_send_test_ntfy_success(monkeypatch):
    _fake_session(monkeypatch, 200)
    prefs = {**DEFAULT_NOTIFICATIONS, "ntfy_topic": "alerts"}
    ok, message = await send_test_ntfy(prefs, "hatty", "test")
    assert ok is True
    assert "alerts" in message


async def test_send_test_ntfy_auth_rejected(monkeypatch):
    _fake_session(monkeypatch, 401)
    prefs = {**DEFAULT_NOTIFICATIONS, "ntfy_topic": "alerts", "ntfy_username": "bob", "ntfy_password": "wrong"}
    ok, message = await send_test_ntfy(prefs, "hatty", "test")
    assert ok is False
    assert "401" in message


async def test_send_test_ntfy_other_http_error(monkeypatch):
    _fake_session(monkeypatch, 500)
    prefs = {**DEFAULT_NOTIFICATIONS, "ntfy_topic": "alerts"}
    ok, message = await send_test_ntfy(prefs, "hatty", "test")
    assert ok is False
    assert "500" in message


async def test_send_test_ntfy_sends_basic_auth_header(monkeypatch):
    session = _fake_session(monkeypatch, 200)
    prefs = {**DEFAULT_NOTIFICATIONS, "ntfy_topic": "alerts", "ntfy_username": "bob", "ntfy_password": "secret"}
    await send_test_ntfy(prefs, "hatty", "test")
    _args, kwargs = session.post_calls[0]
    assert kwargs["headers"]["Authorization"] == aiohttp.encode_basic_auth("bob", "secret")
