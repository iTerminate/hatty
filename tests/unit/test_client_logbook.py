# hatty — MIT License. See LICENSE file for details.
"""`HAClient.fetch_logbook`'s time-window plumbing (issue #2): an explicit
`end` anchors the request instead of always meaning "now", so paging an
activity log back in time asks Home Assistant for the right window."""

from datetime import datetime, timedelta, timezone

from hatty.client import HAClient


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
