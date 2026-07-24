# hatty — MIT License. See LICENSE file for details.
"""``DemoHAClient`` — the offline stand-in that powers ``uv run hatty --demo``.

A production-side sibling of the test suite's ``FakeHAClient``: it feeds the
curated snapshot from ``demo_data`` through the same ``on_message`` envelopes the
real ``HAClient`` emits, so nothing in ``main.py``/``client.py`` needs to change.
Injected at the ``HACLI._client_factory`` seam (see ``main.py``).

Beyond serving reads it is *interactive*: ``call_service`` mutates the in-memory
entity and echoes a synthetic ``state_changed`` event, so toggling a switch or
nudging a thermostat visibly updates the UI. Method signatures mirror
``HAClient`` exactly (enforced by ``tests/test_fake_client_parity.py``).
"""

from datetime import datetime, timezone
from typing import Any

from hatty.client import _UNSET
from hatty.demo import demo_data


class DemoHAClient:
    def __init__(self, url: str, token: str, on_message, logger):
        self.url = url
        self.token = token
        self.on_message = on_message
        self.log = logger
        self.pending_requests: dict[int, str] = {}
        self.message_id = 0
        self._entities: dict[str, dict] = {e["entity_id"]: e for e in demo_data.demo_entities()}
        self._registry = demo_data.demo_registry()
        self._devices = demo_data.demo_devices()
        self._areas = demo_data.demo_areas()
        self._closing = False

    def _next_id(self) -> int:
        self.message_id += 1
        return self.message_id

    def _result(self, label: str, result) -> None:
        request_id = self._next_id()
        self.pending_requests[request_id] = label
        self.on_message({"id": request_id, "type": "result", "success": True, "result": result})

    def _emit_state(self, entity: dict, old_state: dict | None = None) -> None:
        entity["last_changed"] = datetime.now(timezone.utc).isoformat()
        self.on_message(
            {
                "type": "event",
                "event": {
                    "event_type": "state_changed",
                    "data": {"entity_id": entity["entity_id"], "new_state": entity, "old_state": old_state},
                },
            }
        )

    async def listen(self):
        # Mirror the real connect handshake: states, subscribe ack, ha_connected.
        self._result("get_states", list(self._entities.values()))
        self._result("subscribe_events_state_changed", None)
        self.on_message({"type": "ha_connected", "attempt": 0})

    async def fetch_entity_registry(self):
        self._result("get_entity_registry", list(self._registry))

    async def fetch_device_registry(self):
        self._result("get_device_registry", list(self._devices))

    async def fetch_area_registry(self):
        self._result("get_area_registry", list(self._areas))

    async def close(self):
        self._closing = True

    async def call_service(self, domain: str, service: str, service_data: dict[str, Any], entity_id: str = ""):
        entity = self._entities.get(entity_id)
        if entity is None:
            return
        # Snapshot the pre-mutation state (a shallow copy would still share the
        # nested `attributes` dict `_apply_service` mutates in place) so the
        # echoed event carries a real old_state — issue #224's change alerts
        # need one to tell "state changed" from "first seen".
        old_state = {**entity, "attributes": dict(entity.get("attributes", {}))}
        _apply_service(entity, domain, service, service_data)
        self._emit_state(entity, old_state)

    async def update_entity_registry(self, entity_id: str, name: str | None):
        entity = self._entities.get(entity_id)
        if entity is None:
            return
        entity.setdefault("attributes", {})["friendly_name"] = name or entity_id
        self._emit_state(entity)

    async def update_device_registry(self, device_id: str, area_id=_UNSET, name_by_user=_UNSET):
        # Mutate the in-memory device, then ack like the real client — main.py's
        # handler re-fetches the device registry (served above with the new area
        # or name) and rebuilds the tree, so the move/rename is interactive in demo.
        for device in self._devices:
            if device.get("id") == device_id:
                if area_id is not _UNSET:
                    device["area_id"] = area_id
                if name_by_user is not _UNSET:
                    device["name_by_user"] = name_by_user
                break
        self._result("rename_device" if name_by_user is not _UNSET else "update_device_registry", None)

    async def create_area(self, name: str):
        # Append to the in-memory areas, then ack like the real client — main.py's
        # handler re-fetches the area registry (served with the new area), so the
        # create is interactive in demo.
        area_id = "area_" + "_".join(name.lower().split())
        self._areas.append({"area_id": area_id, "name": name})
        self._result("create_area", None)

    async def rename_area(self, area_id: str, name: str):
        for area in self._areas:
            if area.get("area_id") == area_id:
                area["name"] = name
                break
        self._result("update_area", None)

    async def fetch_history(
        self, entity_id: str, hours: float = 4, end: datetime | None = None
    ) -> list[tuple[str, float]] | None:
        return demo_data.demo_numeric_history(entity_id, hours, end)

    async def fetch_binary_history(
        self, entity_id: str, hours: float = 4, end: datetime | None = None
    ) -> list[tuple[str, float]] | None:
        return demo_data.demo_binary_history(entity_id, hours, end)

    async def fetch_climate_history(
        self, entity_id: str, hours: float = 4, end: datetime | None = None
    ) -> list[dict] | None:
        return demo_data.demo_climate_history(entity_id, hours, end)

    async def fetch_logbook(self, entity_ids: list[str], hours: int = 24) -> list[dict] | None:
        return demo_data.demo_logbook(entity_ids, hours)

    async def fetch_forecast(self, entity_id: str, forecast_type: str = "daily") -> list[dict] | None:
        return demo_data.demo_forecast(entity_id, forecast_type)


def _apply_service(entity: dict, domain: str, service: str, service_data: dict[str, Any]) -> None:
    """Mutate a demo entity in place to reflect a service call, so the echoed
    state_changed event looks like a real optimistic update."""
    attrs = entity.setdefault("attributes", {})

    if service == "turn_on":
        entity["state"] = "heat" if domain == "climate" else "on"
    elif service == "turn_off":
        entity["state"] = "off"
    elif service == "toggle":
        entity["state"] = "off" if entity["state"] not in ("off", "closed") else "on"
    elif service == "lock":
        entity["state"] = "locked"
    elif service == "unlock":
        entity["state"] = "unlocked"
    elif service == "media_play_pause":
        entity["state"] = "paused" if entity.get("state") == "playing" else "playing"
    elif service == "media_stop":
        entity["state"] = "idle"
    elif service == "volume_up":
        volume = attrs.get("volume_level") or 0.5
        attrs["volume_level"] = min(1.0, round(volume + 0.05, 2))
    elif service == "volume_down":
        volume = attrs.get("volume_level") or 0.5
        attrs["volume_level"] = max(0.0, round(volume - 0.05, 2))

    # Merge any attribute-bearing fields the service carried (brightness, rgb_color,
    # color_temp_kelvin, effect, percentage, preset_mode, …).
    for key, value in service_data.items():
        if key in ("entity_id",):
            continue
        if key == "temperature":  # climate setpoint
            attrs["temperature"] = value
        elif key == "position":  # cover
            attrs["current_position"] = value
            entity["state"] = "open" if value else "closed"
        elif key == "hvac_mode":
            entity["state"] = value
        elif key == "value":  # input_number
            entity["state"] = str(value)
        else:
            attrs[key] = value
            if key in ("brightness", "rgb_color", "color_temp_kelvin", "effect") and domain == "light":
                entity["state"] = "on"


def demo_client_factory():
    """A ``HACLI._client_factory`` producing ``DemoHAClient`` instances — the
    same seam ``tests/conftest.py`` uses to inject ``FakeHAClient``."""

    def factory(url, token, on_message, logger):
        return DemoHAClient(url, token, on_message, logger)

    return factory
