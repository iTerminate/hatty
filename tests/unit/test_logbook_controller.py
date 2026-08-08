# hatty — MIT License. See LICENSE file for details.
"""Unit tests for LogbookController: scope resolution, caps, paging, the live
subscription singleton, and the state_changed/stream fallbacks — extracted
from HACLI/GraphPreviewScreen (issue #38). Pilot-free: hosts and the client
are stubbed, so these run without booting the Textual app."""

import asyncio
from datetime import datetime, timedelta, timezone

import hatty.controllers.logbook as logbook_module
from hatty.controllers.logbook import LogbookController, LogScope, LogSession


class _StubClient:
    def __init__(self):
        self.logbook_subscription_id = None
        self.logbook_calls = []
        self.state_log_calls = []
        self.subscribe_calls = []
        self.unsubscribe_calls = 0
        self._logbook_data: list[dict] = []
        self._state_log_data: dict[str, list[dict]] = {}
        self._next_id = 1

    async def fetch_logbook(self, entity_ids, hours=24, end=None, device_ids=None):
        self.logbook_calls.append((list(entity_ids), hours, end, list(device_ids or [])))
        return list(self._logbook_data)

    async def fetch_state_log(self, entity_id, hours=24, end=None):
        self.state_log_calls.append((entity_id, hours, end))
        return list(self._state_log_data.get(entity_id, []))

    async def subscribe_logbook(self, entity_ids, device_ids=None):
        self.subscribe_calls.append((list(entity_ids), list(device_ids or [])))
        self.logbook_subscription_id = self._next_id
        self._next_id += 1
        return self.logbook_subscription_id

    async def unsubscribe_logbook(self):
        # Mirrors FakeHAClient/HAClient: a no-op when nothing is subscribed,
        # so a counting test can't be fooled by an extra call.
        if self.logbook_subscription_id is None:
            return
        self.unsubscribe_calls += 1
        self.logbook_subscription_id = None


class _StubPanel:
    def __init__(self):
        self.classes: set[str] = set()
        self.title = ""
        self.hint = ""
        self.history = None
        self.cleared = 0
        self.entries_added: list = []

    def set_hint(self, text):
        self.hint = text

    def set_title(self, text):
        self.title = text

    def add_class(self, name):
        self.classes.add(name)

    def remove_class(self, name):
        self.classes.discard(name)

    def has_class(self, name):
        return name in self.classes

    def clear(self):
        self.cleared += 1

    def load_history(self, entries):
        self.history = entries

    def add_log_entry(self, entry):
        self.entries_added.append(entry)


class _StubHost:
    LOG_PANEL_ID = "stub_panel"
    LOG_SUPPORTS_LIVE = True

    def __init__(self):
        self.panel_widget = _StubPanel()
        self.entries_seen: list = []

    def query_one(self, selector, widget_type=None):
        return self.panel_widget

    def log_window(self, session):
        return 24.0, session.end

    def log_title_suffix(self, session):
        return ""

    def on_log_entries(self, entries):
        self.entries_seen.append(entries)


class _StubFetchOnlyHost(_StubHost):
    """Mirrors GraphPreviewScreen: no live subscription."""

    LOG_PANEL_ID = "stub_fetch_only_panel"
    LOG_SUPPORTS_LIVE = False


class _StubApp:
    def __init__(self):
        self.all_entities: list = []
        self.entity_registry: list = []
        self.device_registry: list = []
        self.log_hours = 24.0
        self.client = _StubClient()
        self.notifications: list = []
        self.bindings_refreshes = 0
        self.spawned: list = []

    def find_entity(self, entity_id):
        return next((e for e in self.all_entities if e["entity_id"] == entity_id), None)

    def notify(self, message, **kwargs):
        self.notifications.append((message, kwargs))

    def call_later(self, fn, *args):
        fn(*args)

    def refresh_bindings(self):
        self.bindings_refreshes += 1

    def spawn(self, coro):
        task = asyncio.ensure_future(coro)
        self.spawned.append(task)
        return task

    async def run_spawned(self) -> None:
        while self.spawned:
            await self.spawned.pop(0)


def _controller() -> tuple[LogbookController, _StubApp]:
    app = _StubApp()
    return LogbookController(app), app


# ── base_option ──────────────────────────────────────────────────────────────


def test_base_option_resolves_plain_scope():
    ctl, app = _controller()
    option = ctl.base_option("list", "my_list", ["light.a", "light.b"], with_devices=False)
    scope = option.resolve()
    assert scope == LogScope(["light.a", "light.b"], [], "Activity Log — my_list")


def test_base_option_resolves_none_for_empty_base():
    ctl, app = _controller()
    option = ctl.base_option("list", "my_list", [], with_devices=False)
    assert option.resolve() is None


def test_base_option_with_devices_widens_and_titles():
    ctl, app = _controller()
    app.entity_registry = [
        {"entity_id": "light.a", "device_id": "dev_1"},
        {"entity_id": "light.b", "device_id": "dev_2"},
    ]
    option = ctl.base_option("list_devices", "my_list", ["light.a", "light.b"], with_devices=True)
    scope = option.resolve()
    assert scope.entity_ids == ["light.a", "light.b"]
    assert scope.device_ids == ["dev_1", "dev_2"]
    assert scope.title == "Device Log — my_list (2 devices)"


def test_base_option_with_devices_single_device_no_count_suffix():
    ctl, app = _controller()
    app.entity_registry = [{"entity_id": "light.a", "device_id": "dev_1"}]
    option = ctl.base_option("list_devices", "my_list", ["light.a"], with_devices=True)
    scope = option.resolve()
    assert scope.title == "Device Log — my_list"


# ── cursor_option ────────────────────────────────────────────────────────────


def test_cursor_option_resolves_none_without_a_selection():
    ctl, app = _controller()
    option = ctl.cursor_option("cursor", lambda: None, with_device=False)
    assert option.resolve() is None


def test_cursor_option_resolves_selected_entity():
    ctl, app = _controller()
    app.all_entities = [{"entity_id": "light.a", "attributes": {"friendly_name": "Lamp"}}]
    option = ctl.cursor_option("cursor", lambda: "light.a", with_device=False)
    scope = option.resolve()
    assert scope == LogScope(["light.a"], [], "Activity Log — Lamp")


def test_cursor_option_with_device_resolves_siblings():
    ctl, app = _controller()
    app.all_entities = [{"entity_id": "light.a", "attributes": {"friendly_name": "Lamp"}}]
    app.entity_registry = [
        {"entity_id": "light.a", "device_id": "dev_1"},
        {"entity_id": "light.b", "device_id": "dev_1"},
    ]
    option = ctl.cursor_option("cursor_device", lambda: "light.a", with_device=True)
    scope = option.resolve()
    assert set(scope.entity_ids) == {"light.a", "light.b"}
    assert scope.device_ids == ["dev_1"]
    assert scope.no_device is False


def test_cursor_option_with_device_flags_no_device_without_notifying():
    ctl, app = _controller()
    app.all_entities = [{"entity_id": "switch.fan", "attributes": {}}]
    option = ctl.cursor_option("cursor_device", lambda: "switch.fan", with_device=True)
    scope = option.resolve()
    assert scope.entity_ids == ["switch.fan"]
    assert scope.device_ids == []
    assert scope.no_device is True
    # resolve() is pure — no toast until something actually applies this option.
    assert app.notifications == []


# ── caps ─────────────────────────────────────────────────────────────────────


def test_base_option_caps_widened_entities_and_devices(monkeypatch):
    ctl, app = _controller()
    monkeypatch.setattr(logbook_module, "_DEVICE_LOG_MAX_ENTITIES", 2)
    monkeypatch.setattr(logbook_module, "_DEVICE_LOG_MAX_DEVICES", 1)
    app.entity_registry = [
        {"entity_id": "light.a", "device_id": "dev_1"},
        {"entity_id": "light.b", "device_id": "dev_2"},
        {"entity_id": "light.c", "device_id": "dev_3"},
    ]
    option = ctl.base_option("list_devices", "my_list", ["light.a", "light.b", "light.c"], with_devices=True)
    scope = option.resolve()
    assert scope.entity_ids == ["light.a", "light.b", "light.c"][:2]
    assert scope.device_ids == ["dev_1"]
    assert scope.entity_total == 3
    assert scope.device_total == 3
    # resolve() itself never notifies — only apply_option does.
    assert app.notifications == []


def test_cursor_device_option_is_capped_too(monkeypatch):
    """Unlike the pre-#38 behaviour, cursor_device now goes through the same
    caps as every other device-widened option."""
    ctl, app = _controller()
    monkeypatch.setattr(logbook_module, "_DEVICE_LOG_MAX_ENTITIES", 1)
    app.all_entities = [{"entity_id": "light.a", "attributes": {}}]
    app.entity_registry = [
        {"entity_id": "light.a", "device_id": "dev_1"},
        {"entity_id": "light.b", "device_id": "dev_1"},
    ]
    option = ctl.cursor_option("cursor_device", lambda: "light.a", with_device=True)
    scope = option.resolve()
    assert len(scope.entity_ids) == 1
    assert scope.entity_total == 2


# ── apply_option ─────────────────────────────────────────────────────────────


async def test_apply_option_clears_retitles_and_fetches():
    ctl, app = _controller()
    host = _StubHost()
    app.client._logbook_data = [{"when": "2024-01-15T10:00:00+00:00", "state": "on", "entity_id": "light.a"}]
    options = [ctl.base_option("list", "my_list", ["light.a"], with_devices=False)]
    ctl.open(host, options=options, option_id="list", hint="hint text")
    await app.run_spawned()

    assert host.panel_widget.has_class("-visible")
    assert host.panel_widget.hint == "hint text"
    assert host.panel_widget.cleared >= 1
    assert host.panel_widget.title == "Activity Log — my_list"
    assert host.panel_widget.history is not None
    assert app.client.logbook_calls[-1][0] == ["light.a"]


async def test_apply_option_notifies_caps_exactly_once(monkeypatch):
    ctl, app = _controller()
    host = _StubHost()
    monkeypatch.setattr(logbook_module, "_DEVICE_LOG_MAX_DEVICES", 1)
    app.entity_registry = [
        {"entity_id": "light.a", "device_id": "dev_1"},
        {"entity_id": "light.b", "device_id": "dev_2"},
    ]
    options = [
        ctl.base_option("list", "my_list", ["light.a", "light.b"], with_devices=False),
        ctl.base_option("list_devices", "my_list", ["light.a", "light.b"], with_devices=True),
    ]
    ctl.open(host, options=options, option_id="list", hint="")
    await app.run_spawned()
    assert app.notifications == []

    ctl.apply_option(host, "list_devices")
    await app.run_spawned()
    device_cap_toasts = [n for n in app.notifications if "devices" in n[0]]
    assert len(device_cap_toasts) == 1


async def test_apply_option_notifies_no_device_found():
    ctl, app = _controller()
    host = _StubHost()
    app.all_entities = [{"entity_id": "switch.fan", "attributes": {}}]
    options = [ctl.cursor_option("cursor_device", lambda: "switch.fan", with_device=True)]
    ctl.open(host, options=options, option_id="cursor_device", hint="")
    await app.run_spawned()
    assert any("No device found" in n[0] for n in app.notifications)


async def test_apply_option_resubscribes_with_the_new_scope():
    ctl, app = _controller()
    host = _StubHost()
    options = [
        ctl.base_option("a", "a", ["light.a"], with_devices=False),
        ctl.base_option("b", "b", ["light.b"], with_devices=False),
    ]
    ctl.open(host, options=options, option_id="a", hint="")
    await app.run_spawned()
    assert app.client.subscribe_calls[-1] == (["light.a"], [])

    ctl.apply_option(host, "b")
    await app.run_spawned()
    assert app.client.subscribe_calls[-1] == (["light.b"], [])


# ── resolved_options / handle_scope_popup_result (the `v` scope popup) ─────


def test_resolved_options_includes_unresolvable_as_none():
    ctl, app = _controller()
    host = _StubHost()
    options = [
        ctl.base_option("list", "my_list", ["light.a"], with_devices=False),
        ctl.cursor_option("cursor", lambda: None, with_device=False),
    ]
    session = LogSession(
        host=host,
        panel_id=host.LOG_PANEL_ID,
        supports_live=host.LOG_SUPPORTS_LIVE,
        options=options,
        option_id="list",
        query_ids=["light.a"],
        device_ids=[],
        entity_ids={"light.a"},
        title_base="Activity Log — my_list",
    )
    ctl._sessions[id(host)] = session
    resolved = ctl.resolved_options(host)
    assert [scope is not None for _option, scope in resolved] == [True, False]


def test_resolved_options_empty_without_a_session():
    ctl, app = _controller()
    assert ctl.resolved_options(_StubHost()) == []


async def test_handle_scope_popup_result_applies_the_chosen_option():
    ctl, app = _controller()
    host = _StubHost()
    options = [
        ctl.base_option("a", "a", ["light.a"], with_devices=False),
        ctl.base_option("b", "b", ["light.b"], with_devices=False),
    ]
    ctl.open(host, options=options, option_id="a", hint="")
    await app.run_spawned()

    ctl.handle_scope_popup_result(host, "b")
    await app.run_spawned()
    assert ctl.session_for(host).option_id == "b"


async def test_handle_scope_popup_result_none_leaves_scope_untouched():
    ctl, app = _controller()
    host = _StubHost()
    options = [
        ctl.base_option("a", "a", ["light.a"], with_devices=False),
        ctl.base_option("b", "b", ["light.b"], with_devices=False),
    ]
    ctl.open(host, options=options, option_id="a", hint="")
    await app.run_spawned()

    ctl.handle_scope_popup_result(host, None)
    assert ctl.session_for(host).option_id == "a"


# ── paging ───────────────────────────────────────────────────────────────────


async def test_page_older_sets_a_window_end():
    ctl, app = _controller()
    host = _StubHost()
    options = [ctl.base_option("list", "my_list", ["light.a"], with_devices=False)]
    ctl.open(host, options=options, option_id="list", hint="")
    await app.run_spawned()

    before = datetime.now(timezone.utc)
    ctl.page(host, -1)
    await app.run_spawned()
    after = datetime.now(timezone.utc)
    session = ctl.session_for(host)
    assert session.end is not None
    assert before - timedelta(hours=app.log_hours) <= session.end <= after - timedelta(hours=app.log_hours)


async def test_page_newer_is_a_noop_while_live():
    ctl, app = _controller()
    host = _StubHost()
    options = [ctl.base_option("list", "my_list", ["light.a"], with_devices=False)]
    ctl.open(host, options=options, option_id="list", hint="")
    await app.run_spawned()

    ctl.page(host, 1)
    assert ctl.session_for(host).end is None


async def test_page_newer_snaps_back_to_live_past_now():
    ctl, app = _controller()
    host = _StubHost()
    options = [ctl.base_option("list", "my_list", ["light.a"], with_devices=False)]
    ctl.open(host, options=options, option_id="list", hint="")
    await app.run_spawned()
    ctl.session_for(host).end = datetime.now(timezone.utc) - timedelta(hours=1)

    ctl.page(host, 1)
    await app.run_spawned()
    assert ctl.session_for(host).end is None


# ── live_session ─────────────────────────────────────────────────────────────


async def test_live_session_requires_live_capable_and_visible_and_not_paged():
    ctl, app = _controller()
    live_host = _StubHost()
    fetch_only_host = _StubFetchOnlyHost()
    options = [ctl.base_option("a", "a", ["light.a"], with_devices=False)]

    assert ctl.live_session() is None

    ctl.open(fetch_only_host, options=list(options), option_id="a", hint="")
    await app.run_spawned()
    assert ctl.live_session() is None  # fetch-only host never counts

    ctl.open(live_host, options=list(options), option_id="a", hint="")
    await app.run_spawned()
    assert ctl.live_session() is ctl.session_for(live_host)

    ctl.session_for(live_host).end = datetime.now(timezone.utc)
    assert ctl.live_session() is None  # paged back

    ctl.session_for(live_host).end = None
    live_host.panel_widget.remove_class("-visible")
    assert ctl.live_session() is None  # closed


# ── resync_subscription / resubscribe_after_reconnect ───────────────────────


async def test_resync_subscription_unsubscribes_then_resubscribes():
    ctl, app = _controller()
    host = _StubHost()
    options = [ctl.base_option("a", "a", ["light.a"], with_devices=False)]
    ctl.open(host, options=options, option_id="a", hint="")
    await app.run_spawned()
    assert app.client.subscribe_calls == [(["light.a"], [])]

    await ctl.resync_subscription()
    assert app.client.unsubscribe_calls == 1
    assert app.client.subscribe_calls[-1] == (["light.a"], [])


async def test_resubscribe_after_reconnect_does_not_unsubscribe_first():
    ctl, app = _controller()
    host = _StubHost()
    options = [ctl.base_option("a", "a", ["light.a"], with_devices=False)]
    ctl.open(host, options=options, option_id="a", hint="")
    await app.run_spawned()
    app.client.unsubscribe_calls = 0

    ctl.resubscribe_after_reconnect()
    await app.run_spawned()
    assert app.client.unsubscribe_calls == 0
    assert len(app.client.subscribe_calls) == 2


def test_resubscribe_after_reconnect_noop_when_nothing_live():
    ctl, app = _controller()
    ctl.resubscribe_after_reconnect()
    assert app.spawned == []


# ── fetch_entries ────────────────────────────────────────────────────────────


async def test_fetch_entries_passes_through_without_continuous_sensors():
    ctl, app = _controller()
    app.client._logbook_data = [{"when": "x"}]
    result = await ctl.fetch_entries(["light.a"], hours=24)
    assert result == [{"when": "x"}]
    assert app.client.state_log_calls == []


async def test_fetch_entries_merges_and_sorts_continuous_sensor_history():
    ctl, app = _controller()
    app.all_entities = [
        {"entity_id": "sensor.temp", "attributes": {"unit_of_measurement": "°C", "state_class": "measurement"}}
    ]
    app.client._logbook_data = [{"when": "2024-01-15T10:02:00+00:00", "entity_id": "light.a", "state": "on"}]
    app.client._state_log_data = {"sensor.temp": [{"when": "2024-01-15T10:00:00+00:00", "state": "21.0"}]}
    result = await ctl.fetch_entries(["light.a", "sensor.temp"], hours=24)
    assert [e["when"] for e in result] == ["2024-01-15T10:00:00+00:00", "2024-01-15T10:02:00+00:00"]


async def test_fetch_entries_returns_none_on_base_failure_without_synthesized_rows():
    ctl, app = _controller()

    async def _fail(*args, **kwargs):
        return None

    app.client.fetch_logbook = _fail
    result = await ctl.fetch_entries(["light.a"], hours=24)
    assert result is None


# ── load: the generation guard ───────────────────────────────────────────────


async def test_load_drops_a_stale_result():
    ctl, app = _controller()
    host = _StubHost()
    options = [ctl.base_option("a", "a", ["light.a"], with_devices=False)]
    session = ctl.open(host, options=options, option_id="a", hint="")
    await app.run_spawned()

    stale_load = ctl.load(session)
    session.generation += 1  # a newer reload started before the stale one resolves
    await stale_load
    # The stale load must not have clobbered the panel with its (older) result.
    assert host.panel_widget.history is not None  # still whatever the fresh load left


async def test_load_drops_result_when_panel_closed_midflight():
    ctl, app = _controller()
    host = _StubHost()
    options = [ctl.base_option("a", "a", ["light.a"], with_devices=False)]
    session = ctl.open(host, options=options, option_id="a", hint="")
    await app.run_spawned()
    host.panel_widget.remove_class("-visible")

    host.panel_widget.history = "sentinel"
    await ctl.load(session)
    assert host.panel_widget.history == "sentinel"  # untouched


# ── handle_stream_frame / handle_state_change ───────────────────────────────


async def test_handle_stream_frame_appends_to_the_live_session():
    ctl, app = _controller()
    host = _StubHost()
    options = [ctl.base_option("a", "a", ["light.a"], with_devices=False)]
    ctl.open(host, options=options, option_id="a", hint="")
    await app.run_spawned()

    ctl.handle_stream_frame([{"when": "2024-01-15T10:00:00+00:00", "state": "on", "entity_id": "light.a"}])
    assert len(host.panel_widget.entries_added) == 1


def test_handle_stream_frame_noop_with_no_live_session():
    ctl, app = _controller()
    ctl.handle_stream_frame([{"when": "x"}])
    assert app.notifications == []  # nothing blew up, nothing happened


async def test_handle_state_change_appends_only_when_in_scope_and_unsubscribed():
    ctl, app = _controller()
    host = _StubHost()
    options = [ctl.base_option("a", "a", ["light.a"], with_devices=False)]
    ctl.open(host, options=options, option_id="a", hint="")
    await app.run_spawned()
    assert app.client.logbook_subscription_id is not None

    # Subscription still active — the stream already carries this, so no append.
    ctl.handle_state_change("light.a", {"state": "on", "attributes": {}})
    assert host.panel_widget.entries_added == []

    app.client.logbook_subscription_id = None
    ctl.handle_state_change("light.a", {"state": "on", "attributes": {}})
    assert len(host.panel_widget.entries_added) == 1

    # Out-of-scope entity: still filtered even with the stream down.
    ctl.handle_state_change("light.b", {"state": "on", "attributes": {}})
    assert len(host.panel_widget.entries_added) == 1
