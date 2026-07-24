# hatty — MIT License. See LICENSE file for details.
"""Reconnect loop for HAClient, including retrying the initial connect (issue #71)."""

import asyncio

import aiohttp

from hatty.client import MAX_RECONNECT_DELAY, RECONNECT_DELAY, WS_HEARTBEAT, AuthenticationError, HAClient


class _Log:
    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


def _make_client(on_message):
    return HAClient("http://x:8123", "tok", on_message, _Log())


def test_backoff_grows_then_caps():
    client = _make_client(lambda m: None)
    delays = [client._backoff_delay(a) for a in range(1, 7)]
    assert delays == [5, 10, 20, 40, 60, 60]
    assert delays[0] == RECONNECT_DELAY
    assert max(delays) == MAX_RECONNECT_DELAY


async def test_retries_initial_connection_until_success(monkeypatch):
    messages = []
    client = _make_client(messages.append)
    delays = []

    async def fake_sleep(d):
        delays.append(d)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    attempts = {"n": 0}

    async def fake_connect():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionRefusedError("host down")
        client.ws = object()  # success

    async def noop():
        pass

    async def fake_read_loop():
        client._closing = True  # end after the first live session

    monkeypatch.setattr(client, "connect", fake_connect)
    monkeypatch.setattr(client, "fetch_states", noop)
    monkeypatch.setattr(client, "subscribe_to_events", noop)
    monkeypatch.setattr(client, "_read_loop", fake_read_loop)

    await client.listen()

    types = [m["type"] for m in messages]
    assert types.count("ha_connect_failed") == 2
    assert "ha_connected" in types
    # Backoff after the two failures, no sleep after the eventual success.
    assert delays == [5, 10]
    connected = next(m for m in messages if m["type"] == "ha_connected")
    assert connected["attempt"] == 2  # succeeded on the third try


async def test_auth_failure_stops_the_loop(monkeypatch):
    messages = []
    client = _make_client(messages.append)
    delays = []

    async def fake_sleep(d):
        delays.append(d)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def fake_connect():
        raise AuthenticationError("bad token")

    monkeypatch.setattr(client, "connect", fake_connect)

    await client.listen()

    types = [m["type"] for m in messages]
    assert types == ["ha_auth_failed"]
    assert delays == []  # never retried


async def test_close_during_backoff_ends_loop(monkeypatch):
    messages = []
    client = _make_client(messages.append)
    delays = []

    async def fake_sleep(d):
        delays.append(d)
        if len(delays) == 2:
            client._closing = True  # simulate the app quitting mid-backoff

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def always_fail():
        raise ConnectionRefusedError("still down")

    monkeypatch.setattr(client, "connect", always_fail)

    await client.listen()

    assert len(delays) == 2  # stopped retrying once closing was set


async def test_attempt_counter_resets_after_success(monkeypatch):
    messages = []
    client = _make_client(messages.append)
    delays = []

    async def fake_sleep(d):
        delays.append(d)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    class _FakeSession:
        async def close(self):
            pass

    # Fail once, connect (a real session so a drop clears ws like production),
    # let the session drop, connect again, then stop.
    script = {"connect": 0, "read": 0}

    async def fake_connect():
        script["connect"] += 1
        if script["connect"] == 1:
            raise ConnectionRefusedError("flap")
        client.ws = object()
        client.session = _FakeSession()

    async def noop():
        pass

    async def fake_read_loop():
        script["read"] += 1
        if script["read"] >= 2:
            client._closing = True
        # First session ends cleanly (a drop); return to trigger reconnect.

    monkeypatch.setattr(client, "connect", fake_connect)
    monkeypatch.setattr(client, "fetch_states", noop)
    monkeypatch.setattr(client, "subscribe_to_events", noop)
    monkeypatch.setattr(client, "_read_loop", fake_read_loop)

    await client.listen()

    # Sequence: fail(5) -> connect(session, drop) -> backoff(5) -> connect(session, close).
    # The backoff after the drop is 5 again, not 10+, proving the attempt counter reset.
    assert delays == [5, 5]
    connects = [m for m in messages if m["type"] == "ha_connected"]
    assert [m["attempt"] for m in connects] == [1, 1]


async def test_connect_passes_ws_heartbeat(monkeypatch):
    """issue #250: a WS ping keepalive must be configured, or a silently-dropped
    network (WiFi off, no TCP close) leaves ws.receive() blocked forever with no
    ha_disconnect/ha_connect_failed ever emitted."""
    captured = {}
    auth_msgs = iter([{"type": "auth_required"}, {"type": "auth_ok"}])

    class FakeWS:
        async def receive_json(self):
            return next(auth_msgs)

        async def send_json(self, data):
            pass

    class FakeSession:
        async def ws_connect(self, url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return FakeWS()

        async def close(self):
            pass

    monkeypatch.setattr(aiohttp, "ClientSession", lambda: FakeSession())

    client = _make_client(lambda m: None)
    await client.connect()

    assert captured["kwargs"].get("heartbeat") == WS_HEARTBEAT
