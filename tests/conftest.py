# hatty — MIT License. See LICENSE file for details.
from datetime import datetime
from typing import Any

import pytest
import yaml

from hatty.client import _UNSET

# Shared fake connection settings used by nearly every acceptance test.
FAKE_URL = "http://fake.ha.local:8123"
FAKE_TOKEN = "fake_token"


def make_config(url=FAKE_URL, token=FAKE_TOKEN, **overrides):
    """The single source of truth for a test config dict: the shared
    home_assistant stanza (url/token overridable) plus any top-level overrides
    (lists, dashboards, saved_graphs, …). Importable
    (`from tests.conftest import make_config`) for module-level constants."""
    return {"home_assistant": {"url": url, "token": token}, **overrides}


# The ubiquitous "connected but no lists" config, shared by every module that
# used to define its own identical `_NO_LIST_CONFIG = make_config(lists={})`.
NO_LIST_CONFIG = make_config(lists={})


@pytest.fixture(autouse=True)
def _no_terminal_title_side_effects(monkeypatch):
    """Acceptance tests boot the real HACLI app, which by default sets the
    terminal/tmux title (issue: set tmux title to hatty or pref). Stub it out so
    a test run never renames the developer's real tmux window (relevant whenever
    pytest itself happens to run inside tmux) or writes an OSC escape to stdout."""
    monkeypatch.setattr("hatty.terminal_title.apply", lambda title: None)
    monkeypatch.setattr("hatty.terminal_title.restore", lambda prev: None)


def notified(app, *, title=None, message_contains=None):
    """True if a currently-live notification matches the given title and/or
    message substring. Prefer this over `len(app._notifications) > before`
    count-delta checks, which are flaky: Textual expires notifications on a
    timer, so an unrelated expiry can offset a freshly posted one (#201)."""
    for n in app._notifications:
        if title is not None and n.title != title:
            continue
        if message_contains is not None and message_contains not in n.message:
            continue
        return True
    return False


class FakeHAClient:
    """Stand-in for HAClient that feeds canned responses without a real websocket.

    Method signatures must match HAClient's — tests/test_fake_client_parity.py
    fails on drift. Setting a `_history_data`/`_climate_history_data` entry to
    None simulates a failed fetch (the real client returns None on failure)."""

    def __init__(self, url, token, on_message, logger):
        self.url = url
        self.token = token
        self.on_message = on_message
        self.log = logger
        self.pending_requests: dict[int, str] = {}
        self.message_id = 0
        self.call_service_calls: list[tuple] = []
        self.update_entity_registry_calls: list[tuple] = []
        self.update_device_registry_calls: list[tuple] = []
        self.rename_device_calls: list[tuple] = []
        self.create_area_calls: list[str] = []
        self.rename_area_calls: list[tuple] = []
        self._initial_entities: list = []
        self._initial_registry: list = []
        self._initial_devices: list = []
        self._initial_areas: list = []
        self._history_data: dict = {}
        self._climate_history_data: dict = {}
        self._logbook_data: list[dict] = []
        self._logbook_device_data: list[dict] = []
        self.logbook_calls: list[tuple[list[str], float, "datetime | None", list[str]]] = []
        self._forecast_data: dict[str, dict[str, list[dict]]] = {}
        self.forecast_calls: list[tuple[str, str]] = []
        self._closing = False

    def _next_id(self) -> int:
        self.message_id += 1
        return self.message_id

    async def listen(self):
        states_id = self._next_id()
        self.pending_requests[states_id] = "get_states"
        self.on_message({"id": states_id, "type": "result", "success": True, "result": list(self._initial_entities)})

        sub_id = self._next_id()
        self.pending_requests[sub_id] = "subscribe_events_state_changed"
        self.on_message({"id": sub_id, "type": "result", "success": True, "result": None})

        # Mirror the real client: signal a successful connect so the app fetches
        # the entity registry through the same ha_connected path as production.
        self.on_message({"type": "ha_connected", "attempt": 0})

    async def fetch_entity_registry(self):
        registry_id = self._next_id()
        self.pending_requests[registry_id] = "get_entity_registry"
        self.on_message({"id": registry_id, "type": "result", "success": True, "result": list(self._initial_registry)})

    async def fetch_device_registry(self):
        registry_id = self._next_id()
        self.pending_requests[registry_id] = "get_device_registry"
        self.on_message({"id": registry_id, "type": "result", "success": True, "result": list(self._initial_devices)})

    async def fetch_area_registry(self):
        registry_id = self._next_id()
        self.pending_requests[registry_id] = "get_area_registry"
        self.on_message({"id": registry_id, "type": "result", "success": True, "result": list(self._initial_areas)})

    async def close(self):
        self._closing = True

    async def call_service(self, domain: str, service: str, service_data: dict[str, Any], entity_id: str = ""):
        self.call_service_calls.append((domain, service, service_data))

    async def update_entity_registry(self, entity_id: str, name: str | None):
        self.update_entity_registry_calls.append((entity_id, name))

    async def update_device_registry(self, device_id: str, area_id=_UNSET, name_by_user=_UNSET):
        if area_id is not _UNSET:
            self.update_device_registry_calls.append((device_id, area_id))
        if name_by_user is not _UNSET:
            self.rename_device_calls.append((device_id, name_by_user))

    async def create_area(self, name: str):
        self.create_area_calls.append(name)

    async def rename_area(self, area_id: str, name: str):
        self.rename_area_calls.append((area_id, name))

    async def fetch_history(
        self, entity_id: str, hours: float = 4, end: datetime | None = None
    ) -> list[tuple[str, float]] | None:
        return self._history_data.get(entity_id, [])

    async def fetch_binary_history(
        self, entity_id: str, hours: float = 4, end: datetime | None = None
    ) -> list[tuple[str, float]] | None:
        return self._history_data.get(entity_id, [])

    async def fetch_climate_history(
        self, entity_id: str, hours: float = 4, end: datetime | None = None
    ) -> list[dict] | None:
        return self._climate_history_data.get(entity_id, [])

    async def fetch_logbook(
        self,
        entity_ids: list[str],
        hours: float = 24,
        end: datetime | None = None,
        device_ids: list[str] | None = None,
    ) -> list[dict] | None:
        self.logbook_calls.append((list(entity_ids), hours, end, list(device_ids or [])))
        entries = list(self._logbook_data)
        if device_ids:
            entries += list(self._logbook_device_data)
        return entries

    async def fetch_forecast(self, entity_id: str, forecast_type: str = "daily") -> list[dict] | None:
        self.forecast_calls.append((entity_id, forecast_type))
        return self._forecast_data.get(entity_id, {}).get(forecast_type)

    def inject_failed_result(self, label: str, error: dict | None = None) -> None:
        request_id = self._next_id()
        self.pending_requests[request_id] = label
        self.on_message({"id": request_id, "type": "result", "success": False, "error": error or {}})

    def inject_state_change(self, new_state: dict, old_state: dict | None = None) -> None:
        self.on_message(
            {
                "type": "event",
                "event": {
                    "event_type": "state_changed",
                    "data": {"entity_id": new_state["entity_id"], "new_state": new_state, "old_state": old_state},
                },
            }
        )


@pytest.fixture
def fake_client_class():
    """The FakeHAClient class itself (conftest isn't importable as a module),
    for tests that inspect it rather than instantiate it."""
    return FakeHAClient


@pytest.fixture
def sample_entities():
    return [
        {
            "entity_id": "light.living_room_lamp",
            "state": "on",
            "attributes": {"friendly_name": "Living Room Lamp"},
            "last_changed": "2024-01-15T10:30:00.000000+00:00",
        },
        {
            "entity_id": "switch.fan",
            "state": "off",
            "attributes": {"friendly_name": "Fan Switch"},
            "last_changed": "2024-01-15T10:30:00.000000+00:00",
        },
        {
            "entity_id": "sensor.temperature",
            "state": "21.5",
            "attributes": {"friendly_name": "Temperature Sensor", "unit_of_measurement": "°C"},
            "last_changed": "2024-01-15T10:30:00.000000+00:00",
        },
        {
            "entity_id": "light.kitchen_light",
            "state": "off",
            "attributes": {"friendly_name": "Kitchen Light"},
            "last_changed": "2024-01-15T10:30:00.000000+00:00",
        },
    ]


def _build_client_factory(entities, registry, devices=None, areas=None):
    """A HACLI._client_factory seam producing FakeHAClients preloaded with
    the given entities/registry/devices/areas (shared by make_app and
    fake_client_factory)."""

    def client_factory(url, token, on_message, logger):
        fake = FakeHAClient(url, token, on_message, logger)
        fake._initial_entities = list(entities)
        fake._initial_registry = list(registry) if registry is not None else []
        fake._initial_devices = list(devices) if devices is not None else []
        fake._initial_areas = list(areas) if areas is not None else []
        return fake

    return client_factory


@pytest.fixture
def sample_registry():
    """Shared entity->device registry fixture (device log tests)."""
    return [
        {"entity_id": "light.living_room_lamp", "device_id": "dev_abc"},
        {"entity_id": "light.kitchen_light", "device_id": "dev_abc"},
        {"entity_id": "sensor.temperature", "device_id": "dev_xyz"},
        {"entity_id": "switch.fan", "device_id": None},
    ]


@pytest.fixture
def make_app(tmp_path, sample_entities):
    from hatty.main import HACLI

    def factory(entities=None, config_data=None, registry=None, devices=None, areas=None):
        entities_to_use = entities if entities is not None else sample_entities

        if config_data is None:
            config_data = {
                "home_assistant": {"url": "http://fake.ha.local:8123", "token": "fake_token_abc"},
                "default_list": "my_list",
                "lists": {"my_list": ["light.living_room_lamp"]},
            }

        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.safe_dump(config_data))

        app = HACLI(config_path=str(config_path))
        app._client_factory = _build_client_factory(entities_to_use, registry, devices, areas)
        return app

    return factory


@pytest.fixture
def fake_client_factory(sample_entities):
    """Builds a FakeHAClient factory for tests that construct HACLI directly
    (e.g. onboarding, which needs control over whether a config file exists)."""

    def build(entities=None, registry=None, devices=None, areas=None):
        entities_to_use = entities if entities is not None else sample_entities
        return _build_client_factory(entities_to_use, registry, devices, areas)

    return build


@pytest.fixture
def open_dashboard():
    """The near-universal dashboard-test preamble as an awaitable helper:
    settle the app, press d, settle the pushed DashboardScreen."""

    async def _open(pilot):
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()

    return _open
