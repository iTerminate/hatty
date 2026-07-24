# hatty — MIT License. See LICENSE file for details.
"""`HAClient.update_device_registry` payload shaping (issue #152).

A move sends only `area_id`; a rename sends only `name_by_user` under a distinct
`rename_device` label — never both, so a rename can't stomp the device's area."""

from hatty.client import HAClient


class _Log:
    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


class _FakeWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload):
        self.sent.append(payload)


def _make_client():
    client = HAClient("http://x:8123", "tok", lambda m: None, _Log())
    client.ws = _FakeWS()
    return client


async def test_move_sends_only_area_id():
    client = _make_client()
    await client.update_device_registry("dev_1", "kitchen")
    payload = client.ws.sent[-1]
    assert payload["type"] == "config/device_registry/update"
    assert payload["area_id"] == "kitchen"
    assert "name_by_user" not in payload
    assert client.pending_requests[payload["id"]] == "update_device_registry"


async def test_rename_sends_only_name_by_user():
    client = _make_client()
    await client.update_device_registry("dev_1", name_by_user="Reading Lamp")
    payload = client.ws.sent[-1]
    assert payload["name_by_user"] == "Reading Lamp"
    assert "area_id" not in payload
    assert client.pending_requests[payload["id"]] == "rename_device"


async def test_clearing_area_still_sends_explicit_none():
    client = _make_client()
    await client.update_device_registry("dev_1", None)
    payload = client.ws.sent[-1]
    assert payload["area_id"] is None
    assert client.pending_requests[payload["id"]] == "update_device_registry"
