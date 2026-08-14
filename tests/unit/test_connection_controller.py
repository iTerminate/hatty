# hatty — MIT License. See LICENSE file for details.
"""Unit tests for ConnectionController: the HA message pump in isolation (issue #166)."""

from hatty.controllers.connection import ConnectionController


class _StubGraphCtl:
    def __init__(self):
        self.recorded = []
        self.preview_refreshes = []

    def record_state(self, entity):
        self.recorded.append(entity)

    def refresh_graph_preview(self, entity_id):
        self.preview_refreshes.append(entity_id)

    def refresh_detail_panel(self):
        pass


class _StubNotifyCtl:
    def __init__(self):
        self.handled = []

    def handle_state_change(self, entity_id, old_state, new_state):
        self.handled.append((entity_id, old_state, new_state))


class _StubClient:
    def __init__(self):
        self.pending_requests = {}
        self.logbook_subscription_id = None

    # The registry fetchers are spawned as coroutines by the real app; the stub
    # just needs callables whose return value spawn can swallow.
    def fetch_entity_registry(self):
        return None

    def fetch_device_registry(self):
        return None

    def fetch_area_registry(self):
        return None

    def subscribe_logbook(self, entity_ids, device_ids=None):
        return None


class _StubLogCtl:
    """Records the LogbookController calls ConnectionController drives —
    no session is ever open in this pump-only test file, so these are just
    call recorders, not a functioning controller."""

    def __init__(self):
        self.reconnect_resubscribes = 0
        self.state_changes = []
        self.stream_frames = []

    def resubscribe_after_reconnect(self):
        self.reconnect_resubscribes += 1

    def handle_state_change(self, entity_id, new_state, old_state=None):
        self.state_changes.append((entity_id, new_state, old_state))

    def handle_stream_frame(self, raw_entries):
        self.stream_frames.append(raw_entries)


class _StubApp:
    """Records the interactions ConnectionController drives, so the pump can be
    exercised without booting the Textual app."""

    def __init__(self, ha_url=""):
        self.ha_url = ha_url
        self.client = _StubClient()
        self.graph_ctl = _StubGraphCtl()
        self.notify_ctl = _StubNotifyCtl()
        self.log_ctl = _StubLogCtl()
        self.all_entities = []
        self.entity_registry = []
        self.device_registry = []
        self.area_registry = []
        self.entity_names = {}
        self.sub_title = ""
        self._detail_entity_id = None
        self.notifications = []
        self.spawned = []
        self.cleared_pending = []
        self.refreshed_widgets = []
        self.refreshed_tree_entities = []
        self.display_updates = 0
        self.title_updates = 0
        self.bindings_refreshes = 0
        self.device_tree_refreshes = 0
        self.splash_dismissals = 0
        self.splash_shows = 0
        self.splash_statuses = []

    # ── plumbing the pump reaches back into ──────────────────────────────────
    def notify(self, message, **kwargs):
        self.notifications.append((message, kwargs))

    def spawn(self, coro):
        self.spawned.append(coro)

    def set_title_based_on_focused_ui(self):
        self.title_updates += 1

    def _splash_screen(self):
        return None

    def _dismiss_splash(self):
        self.splash_dismissals += 1

    def _show_splash(self, status=None):
        self.splash_shows += 1
        self.splash_statuses.append(status)

    def _apply_name_override(self, entity):
        entity["_local_name_override"] = self.entity_names.get(entity.get("entity_id"))

    def _schedule_display_update(self):
        self.display_updates += 1

    def _update_entities_display(self):
        self.display_updates += 1

    def refresh_bindings(self):
        self.bindings_refreshes += 1

    def _refresh_device_tree(self):
        self.device_tree_refreshes += 1

    def _refresh_device_tree_entity(self, entity_id):
        self.refreshed_tree_entities.append(entity_id)

    def _clear_pending_call(self, entity_id):
        self.cleared_pending.append(entity_id)

    def _refresh_dashboard_widgets(self, entity_id):
        self.refreshed_widgets.append(entity_id)

    def call_later(self, fn, *args):
        fn(*args)


def _ctl(app=None) -> ConnectionController:
    return ConnectionController(app or _StubApp())


def test_unknown_message_type_is_ignored():
    ctl = _ctl()
    ctl.handle_ha_message({"type": "does_not_exist"})  # no handler, no crash


def test_connect_failed_sets_sub_title_and_notifies_first_time():
    app = _StubApp()
    ctl = _ctl(app)
    ctl.handle_ha_message({"type": "ha_connect_failed", "error": "refused", "attempt": 1})
    assert "retry 1 pending" in app.sub_title
    assert len(app.notifications) == 1


def test_reconnecting_sets_sub_title_without_notify():
    app = _StubApp()
    ctl = _ctl(app)
    ctl.handle_ha_message({"type": "ha_reconnecting", "attempt": 2, "delay": 10})
    assert "Reconnecting in 10s" in app.sub_title
    assert app.notifications == []


def test_connected_marks_connected():
    app = _StubApp()
    ctl = _ctl(app)
    assert ctl._connected is False
    ctl.handle_ha_message({"type": "ha_connected", "attempt": 0})
    assert ctl._connected is True


def test_disconnect_after_connect_shows_splash():
    # The connected→disconnected edge (issue #243) re-shows the splash exactly once.
    app = _StubApp()
    ctl = _ctl(app)
    ctl.handle_ha_message({"type": "ha_connected", "attempt": 0})
    ctl.handle_ha_message({"type": "ha_disconnect"})
    assert app.splash_shows == 1
    assert ctl._connected is False
    assert "reconnect" in app.sub_title.lower()
    disconnect_toasts = [n for n in app.notifications if n[1].get("title") == "Disconnected"]
    assert len(disconnect_toasts) == 1


def test_disconnect_without_prior_connect_does_not_show_splash():
    # No preceding ha_connected — e.g. still on the boot splash mid-retry — so this
    # falls through to the ordinary status mirror, not a fresh splash push.
    app = _StubApp()
    ctl = _ctl(app)
    ctl.handle_ha_message({"type": "ha_disconnect"})
    assert app.splash_shows == 0


def test_connect_failed_edge_shows_splash_once():
    app = _StubApp()
    ctl = _ctl(app)
    ctl.handle_ha_message({"type": "ha_connected", "attempt": 0})
    ctl.handle_ha_message({"type": "ha_connect_failed", "error": "refused", "attempt": 1})
    ctl.handle_ha_message({"type": "ha_connect_failed", "error": "refused", "attempt": 2})
    assert app.splash_shows == 1
    assert ctl._connected is False


def test_auth_failed_dismisses_splash_and_sets_sub_title():
    app = _StubApp()
    ctl = _ctl(app)
    ctl.handle_ha_message({"type": "ha_auth_failed", "error": "invalid"})
    assert app.splash_dismissals == 1
    assert "Authentication failed" in app.sub_title
    assert len(app.notifications) == 1


def test_connected_fetches_registries():
    app = _StubApp()
    ctl = _ctl(app)
    ctl.handle_ha_message({"type": "ha_connected", "attempt": 0})
    assert app.title_updates == 1
    # entity + device + area registry fetches spawned.
    assert len(app.spawned) == 3


def test_connected_asks_log_ctl_to_resubscribe():
    app = _StubApp()
    ctl = _ctl(app)
    ctl.handle_ha_message({"type": "ha_connected", "attempt": 1})
    assert app.log_ctl.reconnect_resubscribes == 1


def test_cleartext_http_warning_fires_once():
    app = _StubApp(ha_url="http://homeassistant.local:8123")
    ctl = _ctl(app)
    ctl.handle_ha_message({"type": "ha_connected", "attempt": 0})
    ctl.handle_ha_message({"type": "ha_connected", "attempt": 1})
    warnings = [n for n in app.notifications if n[1].get("title") == "Insecure connection"]
    assert len(warnings) == 1
    assert ctl.http_warned is True


def test_https_url_does_not_warn():
    app = _StubApp(ha_url="https://homeassistant.local:8123")
    ctl = _ctl(app)
    ctl.handle_ha_message({"type": "ha_connected", "attempt": 0})
    warnings = [n for n in app.notifications if n[1].get("title") == "Insecure connection"]
    assert warnings == []
    assert ctl.http_warned is False


def test_get_states_result_populates_entities():
    app = _StubApp()
    ctl = _ctl(app)
    app.client.pending_requests[1] = "get_states"
    entity = {"entity_id": "light.kitchen", "state": "on", "attributes": {}}
    ctl.handle_ha_message({"type": "result", "success": True, "id": 1, "result": [entity]})
    assert app.all_entities == [entity]
    assert app.graph_ctl.recorded == [entity]
    assert entity["_local_name_override"] is None  # name override applied
    assert app.display_updates == 1
    assert app.bindings_refreshes == 1
    assert app.splash_dismissals == 1


def test_registry_results_refresh_device_tree():
    app = _StubApp()
    ctl = _ctl(app)
    app.client.pending_requests[7] = "get_device_registry"
    ctl.handle_ha_message({"type": "result", "success": True, "id": 7, "result": [{"id": "d1"}]})
    assert app.device_registry == [{"id": "d1"}]
    assert app.device_tree_refreshes == 1


def test_failed_call_service_clears_pending():
    app = _StubApp()
    ctl = _ctl(app)
    app.client.pending_requests[9] = "call_service:light.kitchen"
    ctl.handle_ha_message(
        {"type": "result", "success": False, "id": 9, "error": {"message": "boom"}}
    )
    assert app.cleared_pending == ["light.kitchen"]
    assert app.refreshed_widgets == ["light.kitchen"]


def test_event_upserts_entity_and_clears_pending():
    app = _StubApp()
    app.all_entities = [{"entity_id": "switch.fan", "state": "off", "attributes": {}}]
    ctl = _ctl(app)
    new_state = {"entity_id": "switch.fan", "state": "on", "attributes": {}}
    ctl.handle_ha_message(
        {"type": "event", "event": {"data": {"entity_id": "switch.fan", "new_state": new_state}}}
    )
    assert app.all_entities == [new_state]  # replaced in place
    assert app.cleared_pending == ["switch.fan"]
    assert app.graph_ctl.recorded == [new_state]
    assert app.refreshed_tree_entities == ["switch.fan"]
    assert app.log_ctl.state_changes == [("switch.fan", new_state, None)]


def test_logbook_stream_event_routes_to_log_ctl():
    app = _StubApp()
    ctl = _ctl(app)
    entries = [{"when": "2024-01-15T10:30:00+00:00", "state": "on", "entity_id": "light.kitchen"}]
    ctl.handle_ha_message({"type": "event", "event": {"events": entries}})
    assert app.log_ctl.stream_frames == [entries]


def test_event_without_new_state_is_ignored():
    app = _StubApp()
    app.all_entities = [{"entity_id": "switch.fan", "state": "off"}]
    ctl = _ctl(app)
    ctl.handle_ha_message(
        {"type": "event", "event": {"data": {"entity_id": "switch.fan", "new_state": None}}}
    )
    assert app.cleared_pending == []
    assert app.all_entities == [{"entity_id": "switch.fan", "state": "off"}]
