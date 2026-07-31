# hatty — MIT License. See LICENSE file for details.
"""`HAClient.fetch_logbook`'s time-window plumbing (issue #2): an explicit
`end` anchors the request instead of always meaning "now", so paging an
activity log back in time asks Home Assistant for the right window.

Also its WS-first / REST-fallback split (issue #17): `logbook/get_events` is
the only HA API that accepts `device_ids`, so a connected client tries it
first and only falls back to the REST endpoint (entity-only) when the
websocket is unavailable or HA rejects the command. The four REST-path tests
below run against a bare client with `ws is None`, which is exactly the
"WS unavailable" case — they must keep passing unmodified as proof the
fallback still behaves like the old entity-only fetch_logbook."""

import asyncio
from datetime import datetime, timedelta, timezone

from hatty.client import HAClient, HARequestError


class _Log:
    def warning(self, *a, **k):
        pass


def _make_client():
    return HAClient("http://x:8123", "tok", lambda m: None, _Log())


async def test_fetch_logbook_defaults_to_now(monkeypatch):
    client = _make_client()
    captured = {}

    async def fake_get_json(url, params, label):
        captured["url"] = url
        captured["params"] = params
        return []

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    before = datetime.now(timezone.utc)
    await client.fetch_logbook(["light.x"], hours=1)
    after = datetime.now(timezone.utc)

    end_time = datetime.fromisoformat(captured["params"]["end_time"])
    assert before <= end_time <= after


async def test_fetch_logbook_uses_explicit_end(monkeypatch):
    client = _make_client()
    captured = {}

    async def fake_get_json(url, params, label):
        captured["url"] = url
        captured["params"] = params
        return []

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    end = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
    await client.fetch_logbook(["light.x"], hours=4, end=end)

    assert captured["params"]["end_time"] == end.isoformat()
    start = end - timedelta(hours=4)
    assert start.isoformat() in captured["url"]


async def test_fetch_logbook_filters_on_entity_param(monkeypatch):
    """HA's logbook REST endpoint reads the filter from `entity`, not `entity_id`
    (issue #13) — `entity_id` is silently ignored and returns the whole instance."""
    client = _make_client()
    captured = {}

    async def fake_get_json(url, params, label):
        captured["params"] = params
        return []

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    await client.fetch_logbook(["light.x", "switch.y"], hours=1)

    assert captured["params"]["entity"] == "light.x,switch.y"
    assert "entity_id" not in captured["params"]


async def test_fetch_logbook_omits_filter_when_no_entities(monkeypatch):
    client = _make_client()
    captured = {}

    async def fake_get_json(url, params, label):
        captured["params"] = params
        return []

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    await client.fetch_logbook([], hours=1)

    assert "entity" not in captured["params"]


async def test_fetch_logbook_ws_first_builds_get_events_payload(monkeypatch):
    client = _make_client()
    client.ws = object()  # truthy: WS path is attempted
    captured = {}

    async def fake_request(payload, **kwargs):
        captured["payload"] = payload
        return []

    monkeypatch.setattr(client, "_request", fake_request)
    end = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
    await client.fetch_logbook(["light.x"], hours=4, end=end, device_ids=["dev_1"])

    payload = captured["payload"]
    assert payload["type"] == "logbook/get_events"
    assert payload["start_time"] == (end - timedelta(hours=4)).isoformat()
    assert payload["end_time"] == end.isoformat()
    assert payload["entity_ids"] == ["light.x"]
    assert payload["device_ids"] == ["dev_1"]


async def test_fetch_logbook_ws_omits_empty_filters(monkeypatch):
    client = _make_client()
    client.ws = object()
    captured = {}

    async def fake_request(payload, **kwargs):
        captured["payload"] = payload
        return []

    monkeypatch.setattr(client, "_request", fake_request)
    await client.fetch_logbook([], hours=1)

    assert "entity_ids" not in captured["payload"]
    assert "device_ids" not in captured["payload"]


async def test_fetch_logbook_unknown_command_latches_off_and_falls_back(monkeypatch):
    client = _make_client()
    client.ws = object()
    rest_calls = []

    async def fake_request(payload, **kwargs):
        raise HARequestError("unknown_command", "no such command")

    async def fake_rest(entity_ids, start, end):
        rest_calls.append(entity_ids)
        return [{"when": "2024-01-15T12:00:00+00:00"}]

    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(client, "_rest_fetch_logbook", fake_rest)

    result = await client.fetch_logbook(["light.x"], hours=1)

    assert rest_calls == [["light.x"]]
    assert result == [{"when": "2024-01-15T12:00:00+00:00"}]
    assert client._logbook_ws_supported is False

    # Latched off: the next call skips WS entirely, going straight to REST.
    ws_attempted = {"hit": False}

    async def fake_request_again(payload, **kwargs):
        ws_attempted["hit"] = True
        return []

    monkeypatch.setattr(client, "_request", fake_request_again)
    await client.fetch_logbook(["light.x"], hours=1)
    assert ws_attempted["hit"] is False


async def test_fetch_logbook_invalid_format_also_latches_off(monkeypatch):
    """HA can have logbook/get_events before it gains device_ids on it — the
    command exists but the schema rejects the request, not `unknown_command`."""
    client = _make_client()
    client.ws = object()

    async def fake_request(payload, **kwargs):
        raise HARequestError("invalid_format", "extra keys not allowed")

    async def fake_rest(entity_ids, start, end):
        return []

    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(client, "_rest_fetch_logbook", fake_rest)

    await client.fetch_logbook(["light.x"], hours=1, device_ids=["dev_1"])

    assert client._logbook_ws_supported is False


async def test_fetch_logbook_timeout_falls_back_without_latching(monkeypatch):
    client = _make_client()
    client.ws = object()

    async def fake_request(payload, **kwargs):
        raise asyncio.TimeoutError()

    async def fake_rest(entity_ids, start, end):
        return []

    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(client, "_rest_fetch_logbook", fake_rest)

    await client.fetch_logbook(["light.x"], hours=1)

    assert client._logbook_ws_supported is True  # transient failure, not latched
