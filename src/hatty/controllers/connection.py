# hatty — MIT License. See LICENSE file for details.
"""HA websocket message pump, extracted from HACLI.

Owns the inbound-message dispatch: ``handle_ha_message`` (the callback the client
invokes for every frame) routes ``result``/``event``/connection-state messages to
the ``_on_ha_*`` handlers, which fold the result into app state (entities, the
registries), drive connection-status UI, and resolve pending service calls. All
app state (``all_entities``, the registries, the pending-call machine) still lives
on ``HACLI``; this controller reaches it through the app reference.
"""

from datetime import datetime

from hatty.ui.activity_log_panel import ActivityLogPanel
from hatty.ui.entity_table import get_display_name


class ConnectionController:
    """Owns the HA websocket message pump. UI plumbing (notify, sub_title,
    splash), entity/registry state, and the pending-call machine live on the
    app and are reached through the app reference."""

    def __init__(self, app) -> None:
        self._app = app
        self.http_warned = False  # one-shot guard for the cleartext-http warning (#158)
        self._connected = False  # tracks the connected→disconnected edge (#243)

    def handle_ha_message(self, msg: dict) -> None:
        handler = self._HA_MESSAGE_HANDLERS.get(msg.get("type", ""))
        if handler is not None:
            handler(self, msg)

    def _set_connection_status(self, sub_title: str, splash_status: str | None = None) -> None:
        """Show a connection-state line in the sub_title and mirror it onto the
        splash screen if that is still up."""
        app = self._app
        app.sub_title = sub_title
        splash = app._splash_screen()
        if splash is not None:
            splash.update_status(splash_status if splash_status is not None else sub_title)

    def _on_ha_result(self, msg: dict) -> None:
        if msg.get("success"):
            self._handle_result_message(msg)
        else:
            self._handle_failed_result_message(msg)

    def _on_ha_event(self, msg: dict) -> None:
        self._handle_event_message(msg)

    def _on_ha_connected(self, msg: dict) -> None:
        app = self._app
        self._connected = True
        app.set_title_based_on_focused_ui()
        # (Re)load the entity/device/area registries on every (re)connect — they
        # aren't part of the state stream, so a reconnect would otherwise keep
        # stale names/areas.
        app.spawn(app.client.fetch_entity_registry())
        app.spawn(app.client.fetch_device_registry())
        app.spawn(app.client.fetch_area_registry())
        if msg.get("attempt", 0) > 0:
            app.notify("Reconnected to Home Assistant.", title="Reconnected", severity="information")
        # Warn once per run when the token travels over cleartext http:// (issue #158).
        if not self.http_warned and (app.ha_url or "").lower().startswith("http://"):
            self.http_warned = True
            app.notify(
                "Connected over http:// — your access token is sent unencrypted. Prefer https://.",
                title="Insecure connection",
                severity="warning",
            )

    def _on_ha_connect_failed(self, msg: dict) -> None:
        attempt = msg.get("attempt", 1)
        sub_title = f"Home Assistant unreachable — retry {attempt} pending…"
        splash_status = f"Unreachable — retry {attempt} pending…"
        if self._connected:
            # The connected→disconnected edge (issue #243): a drop that surfaces as an
            # exception rather than a clean close. Re-show the splash (over whatever
            # screen is up) with its status baked in via the constructor — it isn't
            # mounted yet, so update_status() can't be used here.
            self._connected = False
            self._app._show_splash(splash_status)
            self._app.sub_title = sub_title
        else:
            self._set_connection_status(sub_title, splash_status)
        # A toast on the first failure and then occasionally; not every retry.
        if attempt == 1 or attempt % 5 == 0:
            self._app.notify(
                f"Could not connect to Home Assistant: {msg.get('error', '')}. Retrying…",
                title="Connection Failed",
                severity="error",
            )

    def _on_ha_disconnect(self, msg: dict) -> None:
        app = self._app
        sub_title = "Disconnected from Home Assistant — reconnecting…"
        splash_status = "Disconnected — reconnecting…"
        if self._connected:
            # Connected→disconnected edge (issue #243): a clean server-initiated close.
            self._connected = False
            app._show_splash(splash_status)
            app.sub_title = sub_title
        else:
            self._set_connection_status(sub_title, splash_status)
        app.notify(
            "Disconnected from Home Assistant. Reconnecting…", title="Disconnected", severity="warning"
        )

    def _on_ha_reconnecting(self, msg: dict) -> None:
        delay = msg.get("delay", 0)
        self._set_connection_status(f"Reconnecting in {round(delay)}s (attempt {msg.get('attempt', 1)})…")

    def _on_ha_auth_failed(self, msg: dict) -> None:
        # Retrying can't fix a bad token; drop the splash so the sub_title
        # guidance and the toast are visible.
        app = self._app
        app._dismiss_splash()
        app.sub_title = "Authentication failed — check your access token"
        app.notify(
            f"Home Assistant rejected the access token: {msg.get('error', '')}. "
            "Update your token in the config to reconnect.",
            title="Authentication Failed",
            severity="error",
            timeout=30,
        )

    _HA_MESSAGE_HANDLERS = {
        "result": _on_ha_result,
        "event": _on_ha_event,
        "ha_connected": _on_ha_connected,
        "ha_connect_failed": _on_ha_connect_failed,
        "ha_disconnect": _on_ha_disconnect,
        "ha_reconnecting": _on_ha_reconnecting,
        "ha_auth_failed": _on_ha_auth_failed,
    }

    def _handle_result_message(self, msg: dict) -> None:
        app = self._app
        request_type = app.client.pending_requests.pop(msg.get("id"), None)

        if request_type == "get_states":
            app.all_entities = msg.get("result") or []
            for entity in app.all_entities:
                app.graph_ctl.record_state(entity)
                app._apply_name_override(entity)
            app._schedule_display_update()
            app.refresh_bindings()
            app._dismiss_splash()
        elif request_type == "get_entity_registry":
            app.entity_registry = msg.get("result") or []
        elif request_type == "get_device_registry":
            app.device_registry = msg.get("result") or []
            app._refresh_device_tree()
        elif request_type == "get_area_registry":
            app.area_registry = msg.get("result") or []
            app._refresh_device_tree()
        elif request_type == "update_entity_registry":
            app.notify("Renamed entity in Home Assistant.", title="Renamed")
        elif request_type == "update_device_registry":
            app.notify("Moved device in Home Assistant.", title="Moved")
            app.spawn(app.client.fetch_device_registry())
        elif request_type == "rename_device":
            app.notify("Renamed device in Home Assistant.", title="Renamed")
            app.spawn(app.client.fetch_device_registry())
        elif request_type == "create_area":
            app.notify("Created area in Home Assistant.", title="Area Created")
            app.spawn(app.client.fetch_area_registry())
        elif request_type == "update_area":
            app.notify("Renamed area in Home Assistant.", title="Area Renamed")
            app.spawn(app.client.fetch_area_registry())

    def _handle_failed_result_message(self, msg: dict) -> None:
        app = self._app
        request_type = app.client.pending_requests.pop(msg.get("id"), None)
        if request_type == "update_entity_registry":
            app.notify("Failed to rename entity in Home Assistant.", title="Rename Error", severity="error")
        elif request_type == "update_device_registry":
            app.notify("Failed to move device in Home Assistant.", title="Move Error", severity="error")
        elif request_type == "rename_device":
            app.notify("Failed to rename device in Home Assistant.", title="Rename Error", severity="error")
        elif request_type == "create_area":
            app.notify("Failed to create area in Home Assistant.", title="Area Error", severity="error")
        elif request_type == "update_area":
            app.notify("Failed to rename area in Home Assistant.", title="Area Error", severity="error")
        elif request_type and request_type.startswith("call_service:"):
            entity_id = request_type.removeprefix("call_service:")
            error_msg = msg.get("error", {}).get("message", "Unknown error")
            app.notify(f"Command failed: {error_msg}", title="Service Error", severity="error")
            if entity_id:
                app._clear_pending_call(entity_id)
                app._update_entities_display()
                app._refresh_dashboard_widgets(entity_id)

    def _handle_event_message(self, msg: dict) -> None:
        app = self._app
        event_data = msg.get("event", {}).get("data", {})
        new_state = event_data.get("new_state")
        if not event_data.get("entity_id") or new_state is None:
            return

        old_state = event_data.get("old_state")
        entity_id = new_state["entity_id"]
        app._apply_name_override(new_state)
        for i, entity in enumerate(app.all_entities):
            if entity["entity_id"] == entity_id:
                app.all_entities[i] = new_state
                break
        else:
            app.all_entities.append(new_state)

        app.graph_ctl.record_state(new_state)
        app.notify_ctl.handle_state_change(entity_id, old_state, new_state)
        if app._log_entity_ids and entity_id in app._log_entity_ids:
            log_panel = app.query_one("#activity_log_panel", ActivityLogPanel)
            if log_panel.has_class("-visible"):
                app.call_later(
                    log_panel.add_entry,
                    get_display_name(new_state),
                    new_state.get("state", ""),
                    datetime.now().strftime("%H:%M:%S"),
                )
        app._clear_pending_call(entity_id)
        if app._detail_entity_id == entity_id:
            app.call_later(app.graph_ctl.refresh_detail_panel)
        app._refresh_dashboard_widgets(entity_id)
        app._refresh_device_tree_entity(entity_id)
        app.graph_ctl.refresh_graph_preview(entity_id)
        app._schedule_display_update()
