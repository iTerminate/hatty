# hatty — MIT License. See LICENSE file for details.
"""HAClient's awaited WS request/response path (`_request`), added so a caller
can `await` a command's own `result` frame instead of relying on the
label-based `pending_requests` demux ConnectionController handles later
(issue #16) — needed for fetch_logbook's WS-first `logbook/get_events`."""

import asyncio
import json

import aiohttp
import pytest

from hatty.client import HAClient, HARequestError


class _Log:
    def warning(self, *a, **k):
        pass


def _make_client(on_message=lambda m: None):
    return HAClient("http://x:8123", "tok", on_message, _Log())


class _Msg:
    def __init__(self, type_, data):
        self.type = type_
        self.data = data


class _FakeWS:
    """Records sent frames; `push`/`push_close` feed `_read_loop` via `receive()`."""

    def __init__(self):
        self.sent: list[dict] = []
        self.closed = False
        self._queue: asyncio.Queue = asyncio.Queue()

    async def send_json(self, data):
        self.sent.append(data)

    def push(self, data: dict) -> None:
        self._queue.put_nowait(_Msg(aiohttp.WSMsgType.TEXT, json.dumps(data)))

    def push_close(self) -> None:
        self._queue.put_nowait(_Msg(aiohttp.WSMsgType.CLOSED, None))

    async def receive(self):
        return await self._queue.get()


async def test_request_resolves_on_success():
    client = _make_client()
    client.ws = _FakeWS()

    task = asyncio.ensure_future(client._request({"type": "foo"}))
    await asyncio.sleep(0)  # let _request send before we reply
    sent_id = client.ws.sent[0]["id"]

    client._resolve_pending_future({"id": sent_id, "type": "result", "success": True, "result": {"a": 1}})

    assert await task == {"a": 1}


async def test_request_raises_ha_request_error_with_code_on_failure():
    client = _make_client()
    client.ws = _FakeWS()

    task = asyncio.ensure_future(client._request({"type": "foo"}))
    await asyncio.sleep(0)
    sent_id = client.ws.sent[0]["id"]

    client._resolve_pending_future(
        {"id": sent_id, "type": "result", "success": False, "error": {"code": "unknown_command", "message": "nope"}}
    )

    with pytest.raises(HARequestError) as exc_info:
        await task
    assert exc_info.value.code == "unknown_command"


async def test_request_times_out_when_no_response_arrives():
    client = _make_client()
    client.ws = _FakeWS()

    with pytest.raises(asyncio.TimeoutError):
        await client._request({"type": "foo"}, timeout=0.01)


async def test_request_raises_connection_error_when_not_connected():
    client = _make_client()
    with pytest.raises(ConnectionError):
        await client._request({"type": "foo"})


async def test_awaited_result_frame_is_not_forwarded_to_on_message():
    messages = []
    client = _make_client(messages.append)
    ws = _FakeWS()
    client.ws = ws

    task = asyncio.ensure_future(client._request({"type": "foo"}))
    await asyncio.sleep(0)
    sent_id = ws.sent[0]["id"]

    ws.push({"id": sent_id, "type": "result", "success": True, "result": "ok"})
    ws.push_close()
    await client._read_loop()

    assert await task == "ok"
    assert messages == []  # consumed by the future, never forwarded


async def test_label_routed_frame_is_still_forwarded_to_on_message():
    """Regression guard: get_states-style responses (no matching _request)
    must keep reaching ConnectionController's pending_requests demux."""
    messages = []
    client = _make_client(messages.append)
    ws = _FakeWS()
    client.ws = ws

    ws.push({"id": 99, "type": "result", "success": True, "result": []})
    ws.push_close()
    await client._read_loop()

    assert messages == [{"id": 99, "type": "result", "success": True, "result": []}]


async def test_fail_pending_futures_unblocks_a_waiter():
    client = _make_client()
    client.ws = _FakeWS()

    task = asyncio.ensure_future(client._request({"type": "foo"}))
    await asyncio.sleep(0)

    client._fail_pending_futures(ConnectionError("disconnected"))

    with pytest.raises(ConnectionError):
        await task


async def test_late_frame_for_a_timed_out_request_is_forwarded_harmlessly():
    """The future is popped from _pending_futures on timeout, so a slow reply
    that arrives afterward falls through to on_message like an unmatched
    frame — dropped downstream, but never crashes the read loop."""
    messages = []
    client = _make_client(messages.append)
    ws = _FakeWS()
    client.ws = ws

    with pytest.raises(asyncio.TimeoutError):
        await client._request({"type": "foo"}, timeout=0.01)
    sent_id = ws.sent[0]["id"]

    late = {"id": sent_id, "type": "result", "success": True, "result": "late"}
    ws.push(late)
    ws.push_close()
    await client._read_loop()

    assert messages == [late]
