# hatty — MIT License. See LICENSE file for details.
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import aiohttp

from hatty.const import BINARY_STATE_MAP

RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 60
# WS ping keepalive interval (seconds). Without this, a silently-dropped
# network (e.g. WiFi turned off, no TCP FIN/RST) leaves `ws.receive()`
# blocked forever — neither `ha_disconnect` nor `ha_connect_failed` is ever
# emitted, so the UI shows stale state indefinitely (issue #250). With a
# heartbeat, aiohttp pings the server and raises a timeout when pongs stop
# arriving, which flows through listen()'s except-Exception path instead.
WS_HEARTBEAT = 30

# How long an awaited WS request (`_request`) waits for its `result` frame
# before giving up — see fetch_logbook's WS-first/REST-fallback split (issue #17).
WS_REQUEST_TIMEOUT = 10

# Sentinel distinguishing "argument omitted" from an explicit None (which is a
# meaningful value — clearing a device's area or reverting its user-set name).
# Shared so the stand-in clients import the *same* object: the parity test in
# tests/test_fake_client_parity.py compares parameter defaults by identity.
_UNSET = object()


class AuthenticationError(Exception):
    """Home Assistant rejected the access token. Retrying won't help, so the
    reconnect loop stops and surfaces this distinctly from an unreachable host."""


class HARequestError(Exception):
    """An awaited WS request (`_request`) came back `success: false`. Carries
    HA's error `code` so callers can distinguish "old HA, command doesn't
    exist" (`unknown_command`) from a transient failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


async def probe_connection(url: str, token: str, timeout: float = 5.0) -> tuple[bool, str]:
    """One-shot REST reachability/auth check for the onboarding wizard.

    Returns (ok, message): a friendly success line with the HA version, or a
    human-readable reason (bad URL vs. rejected token vs. HTTP error). Never
    raises — the wizard shows the message inline."""
    base = url.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(f"{base}/api/config", headers=headers) as resp:
                if resp.status == 401:
                    return (False, "Access token was rejected (401). Check the token.")
                if resp.status != 200:
                    return (False, f"Home Assistant returned HTTP {resp.status}.")
                data = await resp.json()
        version = data.get("version", "?") if isinstance(data, dict) else "?"
        message = f"Connected to Home Assistant {version}."
        if base.lower().startswith("http://"):
            # The token is sent in cleartext over http:// — warn but don't refuse,
            # since plain-HTTP HA on a trusted LAN is a common setup (issue #158).
            message += " ⚠ Using http:// — your token is sent unencrypted; prefer https://."
        return (True, message)
    except aiohttp.ClientConnectorError as e:
        return (False, f"Could not reach {base} ({e}). Check the URL.")
    except asyncio.TimeoutError:
        return (False, f"Timed out connecting to {base}. Check the URL.")
    except Exception as e:
        return (False, f"Connection failed: {e}")


class HAClient:
    def __init__(self, url: str, token: str, on_message: Callable, logger):
        self.base_url = url
        self.url = url.replace("http://", "ws://", 1).replace("https://", "wss://", 1) + "/api/websocket"
        self.token = token
        self.on_message = on_message
        self.log = logger
        self.session: aiohttp.ClientSession | None = None
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.message_id = 1
        self.pending_requests: dict[int, str] = {}
        self._pending_futures: dict[int, asyncio.Future] = {}
        self._closing = False
        # Latched off if HA rejects logbook/get_events (old HA or missing
        # device_ids support) so fetch_logbook stops retrying WS every call.
        self._logbook_ws_supported = True
        # The active logbook/event_stream subscription id, if any — dies with
        # the socket, so it's reset on every fresh connect() (issue #19).
        self.logbook_subscription_id: int | None = None

    def _next_message_id(self) -> int:
        self.message_id += 1
        return self.message_id

    async def connect(self):
        # A fresh connection might be to an upgraded HA, so give logbook/get_events
        # another chance even after a previous connection latched it off.
        self._logbook_ws_supported = True
        # Any prior subscription id is meaningless on a new socket — the caller
        # (HACLI, via ha_connected) re-subscribes if the log is open and live.
        self.logbook_subscription_id = None
        self.session = aiohttp.ClientSession()
        self.ws = await self.session.ws_connect(self.url, heartbeat=WS_HEARTBEAT)

        msg = await self.ws.receive_json()
        if msg.get("type") != "auth_required":
            self.log.warning(f"Unexpected first message from HA: {msg}")
            return

        await self.ws.send_json({"type": "auth", "access_token": self.token})

        auth_result = await self.ws.receive_json()
        if auth_result.get("type") != "auth_ok":
            await self.session.close()
            self.session = None
            self.ws = None
            raise AuthenticationError(f"Authentication failed: {auth_result.get('message')}")

    async def _send(self, payload: dict[str, Any], label: str) -> int:
        """Send a WS request with the next message id and record it in
        pending_requests under `label` so the response can be routed. Returns
        the message id (used by subscribe-style callers that need it later to
        unsubscribe)."""
        if self.ws is None:
            raise ConnectionError("Cannot send: the WebSocket is not connected")
        message_id = self._next_message_id()
        await self.ws.send_json({"id": message_id, **payload})
        self.pending_requests[message_id] = label
        return message_id

    async def _request(self, payload: dict[str, Any], *, timeout: float = WS_REQUEST_TIMEOUT) -> Any:
        """Send a WS request and await its `result` frame directly, instead of
        going through the label-based `pending_requests` demux that
        ConnectionController handles later/out of band. Raises ConnectionError
        (not connected, or disconnects before a response arrives),
        asyncio.TimeoutError, or HARequestError (`success: false`)."""
        if self.ws is None:
            raise ConnectionError("Cannot send: the WebSocket is not connected")
        message_id = self._next_message_id()
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        # Register before sending — a fast HA can otherwise land the result
        # frame in _read_loop before this entry exists, and it would be
        # forwarded to on_message instead of resolving this future.
        self._pending_futures[message_id] = future
        try:
            await self.ws.send_json({"id": message_id, **payload})
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending_futures.pop(message_id, None)

    def _resolve_pending_future(self, data: dict) -> bool:
        """If `data` is a `result` frame for one of our awaited `_request`
        calls, resolve it and return True (consumed — do not forward to
        on_message). Otherwise return False."""
        if data.get("type") != "result":
            return False
        message_id = data.get("id")
        if message_id is None:
            return False
        future = self._pending_futures.get(message_id)
        if future is None:
            return False
        if not future.done():
            if data.get("success"):
                future.set_result(data.get("result"))
            else:
                error = data.get("error") or {}
                future.set_exception(HARequestError(error.get("code", ""), error.get("message", "")))
        return True

    def _fail_pending_futures(self, error: BaseException) -> None:
        """Unblock every outstanding `_request` waiter (e.g. on disconnect)
        instead of leaving it to time out. set_exception rather than cancel():
        a CancelledError out of wait_for would look like caller-task
        cancellation, whereas callers already handle ConnectionError."""
        for future in self._pending_futures.values():
            if not future.done():
                future.set_exception(error)
        self._pending_futures.clear()

    async def fetch_states(self):
        await self._send({"type": "get_states"}, "get_states")

    async def fetch_entity_registry(self):
        await self._send({"type": "config/entity_registry/list"}, "get_entity_registry")

    async def fetch_device_registry(self):
        await self._send({"type": "config/device_registry/list"}, "get_device_registry")

    async def fetch_area_registry(self):
        await self._send({"type": "config/area_registry/list"}, "get_area_registry")

    async def update_entity_registry(self, entity_id: str, name: str | None):
        await self._send(
            {"type": "config/entity_registry/update", "entity_id": entity_id, "name": name},
            "update_entity_registry",
        )

    async def update_device_registry(self, device_id: str, area_id=_UNSET, name_by_user=_UNSET):
        """Update a device registry entry. Send only the fields provided, so a
        pure rename never resets the area and a move never touches the name.
        `name_by_user` routes to a distinct `rename_device` label so main.py can
        surface the right notification."""
        payload: dict[str, Any] = {"type": "config/device_registry/update", "device_id": device_id}
        if area_id is not _UNSET:
            payload["area_id"] = area_id
        label = "update_device_registry"
        if name_by_user is not _UNSET:
            payload["name_by_user"] = name_by_user
            label = "rename_device"
        await self._send(payload, label)

    async def create_area(self, name: str):
        await self._send({"type": "config/area_registry/create", "name": name}, "create_area")

    async def rename_area(self, area_id: str, name: str):
        await self._send(
            {"type": "config/area_registry/update", "area_id": area_id, "name": name},
            "update_area",
        )

    async def subscribe_to_events(self, event_type: str = "state_changed"):
        await self._send({"type": "subscribe_events", "event_type": event_type}, f"subscribe_events_{event_type}")

    async def subscribe_logbook(self, entity_ids: list[str], device_ids: list[str] | None = None) -> int | None:
        """Live logbook events (issue #19) — device-scoped events never fire a
        state_changed WS event, so this is the only way they can appear in the
        log without reloading it. Anchored at "now" rather than the fetched
        window's start, so the historical replay batch HA sends is empty/near-
        empty and this is effectively a pure live-append channel; fetch_logbook
        still serves the loaded window. Returns the subscription id (needed by
        unsubscribe_logbook), or None if the request couldn't be sent (e.g.
        mid-reconnect) — never raises, matching the REST fetchers' contract."""
        payload: dict[str, Any] = {
            "type": "logbook/event_stream",
            "start_time": datetime.now(timezone.utc).isoformat(),
        }
        if entity_ids:
            payload["entity_ids"] = list(entity_ids)
        if device_ids:
            payload["device_ids"] = list(device_ids)
        try:
            message_id = await self._send(payload, "logbook_stream")
        except ConnectionError:
            return None
        self.logbook_subscription_id = message_id
        return message_id

    async def unsubscribe_logbook(self) -> None:
        """No-op when nothing is subscribed. Never raises — a disconnect
        between subscribing and unsubscribing just means there's nothing left
        on the server to tell; the subscription already died with the socket."""
        subscription_id = self.logbook_subscription_id
        if subscription_id is None:
            return
        self.logbook_subscription_id = None
        try:
            await self._send({"type": "unsubscribe_events", "subscription": subscription_id}, "unsubscribe_logbook")
        except ConnectionError:
            pass

    async def call_service(self, domain: str, service: str, service_data: dict[str, Any], entity_id: str = ""):
        await self._send(
            {"type": "call_service", "domain": domain, "service": service, "service_data": service_data},
            f"call_service:{entity_id}",
        )

    async def _read_loop(self) -> None:
        ws = self.ws
        if ws is None:
            return
        while not ws.closed:
            msg = await ws.receive()
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if not self._resolve_pending_future(data):
                    self.on_message(data)
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff from RECONNECT_DELAY, capped at MAX_RECONNECT_DELAY:
        5, 10, 20, 40, 60, 60… so a down host isn't hammered but recovery is quick."""
        return min(RECONNECT_DELAY * (2 ** min(attempt - 1, 4)), MAX_RECONNECT_DELAY)

    async def listen(self):
        """Connect and stay connected, retrying forever — including the very first
        connection, so the app survives being started while HA is unreachable. Only
        a rejected token (AuthenticationError) stops the loop, since retrying that
        can't succeed."""
        attempt = 0
        while not self._closing:
            try:
                if not self.ws:
                    await self.connect()
                    await self.fetch_states()
                    await self.subscribe_to_events()
                    self.on_message({"type": "ha_connected", "attempt": attempt})
                    attempt = 0
                await self._read_loop()
                # Clean close (server closed the socket) — fall through to reconnect.
                self.on_message({"type": "ha_disconnect"})
            except AuthenticationError as e:
                self.log.warning(f"Authentication failed: {e}")
                self.on_message({"type": "ha_auth_failed", "error": str(e)})
                return
            except Exception as e:
                self.log.warning(f"Connection attempt {attempt + 1} failed: {e}")
                self.on_message({"type": "ha_connect_failed", "error": str(e), "attempt": attempt + 1})
            finally:
                # Unblock any in-flight _request() waiters immediately rather than
                # leaving them to hit WS_REQUEST_TIMEOUT during a reconnect.
                self._fail_pending_futures(ConnectionError("WebSocket disconnected"))
                if self.session:
                    await self.session.close()
                    self.session = None
                    self.ws = None

            if self._closing:
                return
            attempt += 1
            delay = self._backoff_delay(attempt)
            self.on_message({"type": "ha_reconnecting", "attempt": attempt, "delay": delay})
            await asyncio.sleep(delay)

    async def close(self):
        self._closing = True
        self._fail_pending_futures(ConnectionError("Client closed"))
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()

    async def _get_json(self, url: str, params: dict, warn_label: str) -> Any | None:
        """GET a REST endpoint with the bearer token; parsed JSON, or None on
        any failure (non-200, network error, bad JSON) — logged, never raised."""
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as resp:
                    if resp.status != 200:
                        self.log.warning(f"{warn_label} HTTP {resp.status}")
                        return None
                    return await resp.json()
        except Exception as e:
            self.log.warning(f"{warn_label} failed: {e}")
            return None

    async def _post_json(self, url: str, params: dict, json_body: dict, warn_label: str) -> Any | None:
        """POST a REST endpoint with the bearer token; parsed JSON, or None on
        any failure (non-200, network error, bad JSON) — logged, never raised."""
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params, json=json_body, headers=headers) as resp:
                    if resp.status != 200:
                        self.log.warning(f"{warn_label} HTTP {resp.status}")
                        return None
                    return await resp.json()
        except Exception as e:
            self.log.warning(f"{warn_label} failed: {e}")
            return None

    async def fetch_forecast(self, entity_id: str, forecast_type: str = "daily") -> list[dict] | None:
        """Fetch a weather entity's forecast via the weather.get_forecasts
        service (issue #283) — modern HA no longer exposes forecast as an
        inline entity attribute, so this is a REST service call with
        `return_response` rather than a websocket call_service (which has no
        response-awaiting path here). Returns None on any failure; callers
        should fall back to the legacy `forecast` attribute in that case."""
        url = f"{self.base_url}/api/services/weather/get_forecasts"
        data = await self._post_json(
            url,
            {"return_response": "true"},
            {"entity_id": entity_id, "type": forecast_type},
            f"fetch_forecast for {entity_id}",
        )
        if not isinstance(data, dict):
            return None
        forecast = data.get("service_response", {}).get(entity_id, {}).get("forecast")
        return forecast if isinstance(forecast, list) else None

    async def _rest_fetch_logbook(
        self, entity_ids: list[str], start: datetime, end: datetime
    ) -> list[dict] | None:
        """The REST `/api/logbook` fallback. Entity-only — HA's REST logbook view
        has no device filter at all, so device-scoped events (e.g. zha_event)
        never come back through this path (issue #17)."""
        url = f"{self.base_url}/api/logbook/{start.isoformat()}"
        params: dict = {"end_time": end.isoformat()}
        if entity_ids:
            # HA's logbook endpoint reads the filter from `entity` (comma-separated) —
            # `entity_id` is silently ignored and returns the whole instance (issue #13).
            params["entity"] = ",".join(entity_ids)
        data = await self._get_json(url, params, "fetch_logbook")
        if data is None:
            return None
        return data if isinstance(data, list) else []

    async def _ws_fetch_logbook(
        self, entity_ids: list[str], device_ids: list[str], start: datetime, end: datetime
    ) -> list[dict] | None:
        """`logbook/get_events` — the only HA API that accepts `device_ids`, so
        it's the one path that can surface device-scoped events like zha_event
        (issue #17). Entries differ in shape from the REST endpoint (epoch
        `when`, no `name` on state entries) — see `hatty.logbook.normalize_entries`.
        Returns None on any failure so the caller falls back to REST; latches
        `_logbook_ws_supported` off on a command/schema HA doesn't recognize so
        later calls skip straight to REST instead of retrying every time."""
        payload: dict[str, Any] = {
            "type": "logbook/get_events",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }
        if entity_ids:
            payload["entity_ids"] = list(entity_ids)
        if device_ids:
            payload["device_ids"] = list(device_ids)
        try:
            result = await self._request(payload)
        except HARequestError as e:
            if e.code in ("unknown_command", "invalid_format"):
                # `invalid_format` covers HA versions that have logbook/get_events
                # but not yet its device_ids param — the command exists, only the
                # schema rejects us, so latch off the same way.
                self._logbook_ws_supported = False
            self.log.warning(f"fetch_logbook (WS) failed: {e}")
            return None
        except (ConnectionError, asyncio.TimeoutError) as e:
            self.log.warning(f"fetch_logbook (WS) failed: {e}")
            return None
        return result if isinstance(result, list) else []

    async def fetch_logbook(
        self,
        entity_ids: list[str],
        hours: float = 24,
        end: datetime | None = None,
        device_ids: list[str] | None = None,
    ) -> list[dict] | None:
        end = end or datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        if self._logbook_ws_supported and self.ws is not None:
            entries = await self._ws_fetch_logbook(entity_ids, device_ids or [], start, end)
            if entries is not None:
                return entries
        return await self._rest_fetch_logbook(entity_ids, start, end)

    async def _fetch_raw_history(
        self, entity_id: str, hours: float, end: datetime | None, minimal: bool = True
    ) -> list[dict] | None:
        """State history rows for one entity, or None on failure. `minimal`
        strips attributes server-side; climate history needs them kept."""
        end = end or datetime.now(timezone.utc)
        start = (end - timedelta(hours=hours)).isoformat()
        url = f"{self.base_url}/api/history/period/{start}"
        params = {
            "filter_entity_id": entity_id,
            "end_time": end.isoformat(),
        }
        if minimal:
            params["minimal_response"] = "true"
            params["no_attributes"] = "true"
        data = await self._get_json(url, params, f"fetch_history for {entity_id}")
        if data is None:
            return None
        return data[0] if data else []

    async def fetch_history(
        self, entity_id: str, hours: float = 4, end: datetime | None = None
    ) -> list[tuple[str, float]] | None:
        items = await self._fetch_raw_history(entity_id, hours, end)
        if items is None:
            return None
        values = []
        for item in items:
            try:
                values.append((item.get("last_changed", ""), float(item["state"])))
            except (ValueError, KeyError, TypeError):
                continue
        return values

    async def fetch_binary_history(
        self, entity_id: str, hours: float = 4, end: datetime | None = None
    ) -> list[tuple[str, float]] | None:
        """Like fetch_history, but maps on/off states to 1.0/0.0 (skipping
        unavailable/unknown) so binary entities fit the numeric history shape."""
        items = await self._fetch_raw_history(entity_id, hours, end)
        if items is None:
            return None
        values = []
        for item in items:
            mapped = BINARY_STATE_MAP.get(item.get("state", ""))
            if mapped is not None:
                values.append((item.get("last_changed", ""), mapped))
        return values

    async def fetch_climate_history(
        self, entity_id: str, hours: float = 4, end: datetime | None = None
    ) -> list[dict] | None:
        """Like fetch_history, but keeps attributes (current_temperature, temperature,
        hvac_action) instead of just the numeric state, since a climate entity's state
        is its hvac_mode, not a graphable number."""
        items = await self._fetch_raw_history(entity_id, hours, end, minimal=False)
        if items is None:
            return None
        values = []
        for item in items:
            ts = item.get("last_changed", "")
            if not ts:
                continue
            attrs = item.get("attributes", {})
            values.append(
                {
                    "ts": ts,
                    "current_temperature": attrs.get("current_temperature"),
                    "target_temperature": attrs.get("temperature"),
                    "hvac_action": attrs.get("hvac_action"),
                }
            )
        return values
