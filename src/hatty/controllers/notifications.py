# hatty — MIT License. See LICENSE file for details.
"""Entity change alerts, extracted from HACLI (issue #224).

Watched entities are the union of the members of every list named in
`notify_lists` (issue #24) — any user list can be designated a notification
source, toggled from the list popup (`ListSelectionPopup`'s `n` binding) rather
than through membership in one reserved list. `notify_lists` is a plain name
set, persisted like `manual_lists`; `ListController` carries a list's
designation across rename and drops it on delete.

The `enabled` preference is a pure global mute — it doesn't affect which lists
are designated or what's in them, just whether `handle_state_change` fires.

Preferences (`app_config["notifications"]`) are read fresh on every alert rather
than cached, so toggling a channel in ConfigScreen takes effect immediately.
"""

import asyncio
import subprocess

import aiohttp

from hatty.const import CONFIG_KEY_NOTIFICATIONS, DEFAULT_NOTIFICATIONS
from hatty.types import Entity
from hatty.ui.entity_table import get_display_name

# How long a changed entity stays highlighted in the table/dashboard before the
# transient marker clears itself.
HIGHLIGHT_SECONDS = 5.0


def build_ntfy_request(prefs: dict, title: str, body: str) -> tuple[str, bytes, dict] | None:
    """(post_url, data, headers) for an ntfy POST built from `prefs`, or `None`
    when no topic is configured. Shared by the silent live-alert path
    (`NotificationController._ntfy`) and the config-screen test button
    (`send_test_ntfy`) so both send an identical request."""
    topic = (prefs.get("ntfy_topic") or "").strip()
    if not topic:
        return None
    url = (prefs.get("ntfy_url") or "").rstrip("/")
    username = (prefs.get("ntfy_username") or "").strip()
    password = prefs.get("ntfy_password") or ""
    headers = {"Title": title}
    if username and password:
        headers["Authorization"] = aiohttp.encode_basic_auth(username, password)
    return f"{url}/{topic}", body.encode(), headers


async def send_test_ntfy(prefs: dict, title: str, body: str, timeout: float = 5.0) -> tuple[bool, str]:
    """One-shot ntfy POST for the config screen's "Send test notification"
    button (issue #248). Returns (ok, message); never raises — mirrors
    `client.probe_connection`'s shape so ConfigScreen can reuse the same
    status-label pattern."""
    request = build_ntfy_request(prefs, title, body)
    if request is None:
        return (False, "Enter an ntfy topic first.")
    url, data, headers = request
    topic = (prefs.get("ntfy_topic") or "").strip()
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.post(url, data=data, headers=headers) as resp:
                if resp.status in (401, 403):
                    return (False, f"ntfy rejected the credentials ({resp.status}).")
                if resp.status < 200 or resp.status >= 300:
                    return (False, f"ntfy server returned HTTP {resp.status}.")
        return (True, f"Test notification sent to {topic}.")
    except aiohttp.ClientConnectorError as e:
        return (False, f"Could not reach the ntfy server ({e}). Check the URL.")
    except asyncio.TimeoutError:
        return (False, "Timed out contacting the ntfy server. Check the URL.")
    except Exception as e:
        return (False, f"Test notification failed: {e}")


class NotificationController:
    """Owns which lists are designated as notification sources and dispatches
    change alerts."""

    def __init__(self, app) -> None:
        self._app = app
        self.notify_lists: set[str] = set()
        # entity_ids currently in their transient post-change highlight window.
        self.alerted: set[str] = set()
        self._timers: dict = {}

    def _prefs(self) -> dict:
        prefs = self._app.app_config.get(CONFIG_KEY_NOTIFICATIONS) or {}
        return {**DEFAULT_NOTIFICATIONS, **prefs}

    def toggle_list(self, list_name: str) -> bool:
        """Flip `list_name`'s designation and persist. Returns the new state."""
        if list_name in self.notify_lists:
            self.notify_lists.discard(list_name)
            now_on = False
        else:
            self.notify_lists.add(list_name)
            now_on = True
        self._app.persist("notify_lists")
        return now_on

    def is_watched(self, entity_id: str) -> bool:
        entity_lists = self._app.entity_lists
        return any(entity_id in (entity_lists.get(name) or []) for name in self.notify_lists)

    def watched_entities(self) -> set[str]:
        """The de-duplicated union of every designated list's members."""
        entity_lists = self._app.entity_lists
        result: set[str] = set()
        for name in self.notify_lists:
            result.update(entity_lists.get(name) or [])
        return result

    def is_alerted(self, entity_id: str) -> bool:
        return entity_id in self.alerted

    def handle_state_change(self, entity_id: str, old_state: Entity | None, new_state: Entity) -> None:
        """Fire the configured alert channels when a watched entity's state
        *value* changes (attribute-only updates and first-seen states are not
        alerts — issue #224 scope)."""
        prefs = self._prefs()
        if not prefs["enabled"] or not self.is_watched(entity_id):
            return
        old = old_state.get("state") if old_state else None
        new = new_state.get("state")
        if old is None or old == new:
            return

        app = self._app
        title = get_display_name(new_state)
        body = f"{old} → {new}"

        if prefs["toast"]:
            app.notify(f"{title}: {body}", title="Entity Alert")
        if prefs["beep"]:
            app.bell()
        if prefs["desktop"]:
            app.spawn(self._desktop(title, body))
        if prefs["ntfy"]:
            app.spawn(self._ntfy(prefs, title, body))
        if prefs["highlight"]:
            self._highlight(entity_id)

    async def _desktop(self, title: str, body: str) -> None:
        try:
            await asyncio.to_thread(
                subprocess.run, ["notify-send", title, body], capture_output=True, timeout=5
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            pass  # No libnotify (or it failed) — desktop alerts are best-effort.

    async def _ntfy(self, prefs: dict, title: str, body: str) -> None:
        request = build_ntfy_request(prefs, title, body)
        if request is None:
            return
        url, data, headers = request
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(url, data=data, headers=headers)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass  # Unreachable ntfy server must not break the app.

    def _highlight(self, entity_id: str) -> None:
        app = self._app
        self.alerted.add(entity_id)
        app._update_entities_display()
        app._refresh_dashboard_widgets(entity_id)

        existing = self._timers.pop(entity_id, None)
        if existing:
            existing.stop()
        self._timers[entity_id] = app.set_timer(HIGHLIGHT_SECONDS, lambda: self._clear(entity_id))

    def _clear(self, entity_id: str) -> None:
        self._timers.pop(entity_id, None)
        self.alerted.discard(entity_id)
        self._app._update_entities_display()
        self._app._refresh_dashboard_widgets(entity_id)

    def stop_watching_all(self) -> None:
        """Undesignate every notifying list (the config-page "Stop watching all
        lists" button). Lists and their contents are untouched — only the
        notify_lists designation is cleared."""
        self.notify_lists.clear()
        self._app.persist("notify_lists")
