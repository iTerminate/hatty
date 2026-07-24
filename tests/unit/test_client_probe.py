# hatty — MIT License. See LICENSE file for details.
"""probe_connection warns about cleartext http:// token transport (issue #158)."""

import aiohttp
import pytest

from hatty.client import probe_connection


class _FakeResp:
    status = 200

    async def json(self):
        return {"version": "2024.7.0"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def get(self, url, headers=None):
        return _FakeResp()


@pytest.fixture
def _fake_session(monkeypatch):
    monkeypatch.setattr(aiohttp, "ClientSession", _FakeSession)


async def test_probe_warns_on_http(_fake_session):
    ok, message = await probe_connection("http://homeassistant.local:8123", "tok")
    assert ok is True
    assert "2024.7.0" in message
    assert "http://" in message and "unencrypted" in message


async def test_probe_does_not_warn_on_https(_fake_session):
    ok, message = await probe_connection("https://homeassistant.local:8123", "tok")
    assert ok is True
    assert "unencrypted" not in message
