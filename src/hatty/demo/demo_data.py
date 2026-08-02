# hatty — MIT License. See LICENSE file for details.
"""Curated fake data for demo mode (``uv run hatty --demo``).

Pure data + deterministic history generators — no Textual or HA imports. The
entity dicts follow the exact shape the app reads from a real ``get_states``
response; the history helpers return the same store shapes the REST fetchers in
``client.py`` produce, so the UI can't tell it's synthetic.

Everything here is a *snapshot*: states are fixed, history is generated anchored
to "now" so timestamps look current on any run, and there's no background ticker.
Interactivity (a toggled switch visibly flipping) comes from ``DemoHAClient``
echoing ``call_service`` back as a ``state_changed`` event, not from this module.
"""

import math
import random
from datetime import datetime, timedelta, timezone

from hatty.logbook import is_continuous_sensor


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ── Live entity snapshot ─────────────────────────────────────────────────────


def demo_entities() -> list[dict]:
    """The curated entity set, exercising every domain with UI surface: sensor,
    light, climate, switch, binary_sensor, cover, lock, media_player, fan,
    input_number."""
    now = _iso(_now())

    def e(entity_id: str, state: str, attributes: dict) -> dict:
        return {"entity_id": entity_id, "state": state, "attributes": attributes, "last_changed": now}

    return [
        # ── Sensors (numeric) ──
        e("sensor.living_room_temperature", "21.5",
          {"friendly_name": "Living Room Temperature", "unit_of_measurement": "°C", "device_class": "temperature"}),
        e("sensor.living_room_humidity", "48",
          {"friendly_name": "Living Room Humidity", "unit_of_measurement": "%", "device_class": "humidity"}),
        e("sensor.outdoor_temperature", "12.3",
          {"friendly_name": "Outdoor Temperature", "unit_of_measurement": "°C", "device_class": "temperature"}),
        e("sensor.power_consumption", "342",
          {"friendly_name": "Power Consumption", "unit_of_measurement": "W", "device_class": "power",
           "min": 0, "max": 3000}),
        e("sensor.solar_production", "1240",
          {"friendly_name": "Solar Production", "unit_of_measurement": "W", "device_class": "power",
           "min": 0, "max": 5000}),
        e("sensor.internet_speed", "94.2",
          {"friendly_name": "Internet Speed", "unit_of_measurement": "Mbit/s"}),
        # ── Lights ──
        e("light.living_room_lamp", "on",
          {"friendly_name": "Living Room Lamp", "brightness": 180, "color_mode": "rgb",
           "supported_color_modes": ["color_temp", "rgb"], "rgb_color": [255, 147, 41],
           "color_temp_kelvin": 2700, "min_color_temp_kelvin": 2000, "max_color_temp_kelvin": 6500,
           "effect": "None", "effect_list": ["None", "Colorloop", "Random"]}),
        e("light.kitchen_spots", "on",
          {"friendly_name": "Kitchen Spots", "brightness": 220, "color_mode": "color_temp",
           "supported_color_modes": ["color_temp"], "color_temp_kelvin": 4000,
           "min_color_temp_kelvin": 2200, "max_color_temp_kelvin": 6500}),
        e("light.bedroom", "off",
          {"friendly_name": "Bedroom Light", "color_mode": "brightness",
           "supported_color_modes": ["brightness"]}),
        # ── Switches ──
        e("switch.coffee_maker", "off", {"friendly_name": "Coffee Maker"}),
        e("switch.living_room_tv", "on", {"friendly_name": "Living Room TV"}),
        # ── Climate ──
        e("climate.living_room", "heat",
          {"friendly_name": "Living Room Thermostat", "current_temperature": 20.5, "temperature": 21.5,
           "hvac_action": "heating", "hvac_modes": ["heat", "cool", "off", "auto"],
           "fan_mode": "auto", "fan_modes": ["auto", "low", "high"],
           "min_temp": 7, "max_temp": 35, "target_temp_step": 0.5, "unit_of_measurement": "°C"}),
        e("climate.bedroom", "off",
          {"friendly_name": "Bedroom Thermostat", "current_temperature": 19.0, "temperature": 18.0,
           "hvac_action": "idle", "hvac_modes": ["heat", "cool", "off"],
           "min_temp": 7, "max_temp": 35, "target_temp_step": 0.5, "unit_of_measurement": "°C"}),
        # ── Binary sensors ──
        e("binary_sensor.front_door", "off", {"friendly_name": "Front Door", "device_class": "door"}),
        e("binary_sensor.living_room_motion", "off",
          {"friendly_name": "Living Room Motion", "device_class": "motion"}),
        e("binary_sensor.smoke_detector", "off", {"friendly_name": "Smoke Detector", "device_class": "smoke"}),
        e("binary_sensor.washing_machine", "on", {"friendly_name": "Washing Machine", "device_class": "running"}),
        # A Zigbee button has no meaningful state beyond its battery — but the
        # device log (`i` then `v`) is reached from an entity row, so it needs
        # one to be reachable at all. Its interest is its device events (issue #17):
        # button presses never show up as a state change.
        e("sensor.living_room_button_battery", "87",
          {"friendly_name": "Living Room Button Battery", "unit_of_measurement": "%", "device_class": "battery"}),
        # ── Covers ──
        e("cover.living_room_blinds", "open", {"friendly_name": "Living Room Blinds", "current_position": 70}),
        e("cover.garage_door", "closed", {"friendly_name": "Garage Door", "current_position": 0}),
        # ── Lock ──
        e("lock.front_door", "locked", {"friendly_name": "Front Door Lock"}),
        # ── Media player ──
        # supported_features 384447 = every MediaPlayerEntityFeature bit this app
        # controls (const.MEDIA_FEAT's values summed); not imported here to keep
        # this module free of app imports.
        e("media_player.living_room_speaker", "playing",
          {"friendly_name": "Living Room Speaker", "supported_features": 384447,
           "volume_level": 0.4, "is_volume_muted": False,
           "media_title": "Random Access Memories", "media_artist": "Daft Punk",
           "source": "Spotify", "source_list": ["Spotify", "TV", "Radio"],
           "sound_mode": "Movie", "sound_mode_list": ["Movie", "Music", "Night"],
           "shuffle": False, "repeat": "off"}),
        # ── Fan ──
        e("fan.bedroom_fan", "on",
          {"friendly_name": "Bedroom Fan", "percentage": 66, "percentage_step": 33,
           "preset_mode": "auto", "preset_modes": ["auto", "sleep", "turbo"]}),
        # ── input_number ──
        e("input_number.thermostat_offset", "1.5",
          {"friendly_name": "Thermostat Offset", "min": -5, "max": 5, "step": 0.5, "unit_of_measurement": "°C"}),
        # ── Weather ──
        # supported_features 7 = FORECAST_DAILY(1) | FORECAST_HOURLY(2) | FORECAST_TWICE_DAILY(4),
        # so the demo entity exercises all three weather.get_forecasts types (issue #283) —
        # see demo_forecast() below for the per-type payloads; the inline "forecast" attribute
        # here is the legacy daily shape, kept as the fallback path's demo data.
        e("weather.home", "partlycloudy",
          {"friendly_name": "Home Weather", "supported_features": 7,
           "temperature": 18.4, "temperature_unit": "°C",
           "humidity": 61, "pressure": 1014, "wind_speed": 12, "wind_speed_unit": "km/h",
           "forecast": [
               {"datetime": "2024-01-15T12:00:00+00:00", "condition": "partlycloudy",
                "temperature": 18.4, "templow": 11.0, "precipitation_probability": 10},
               {"datetime": "2024-01-16T12:00:00+00:00", "condition": "sunny",
                "temperature": 21.0, "templow": 12.5, "precipitation_probability": 0},
               {"datetime": "2024-01-17T12:00:00+00:00", "condition": "cloudy",
                "temperature": 17.0, "templow": 10.0, "precipitation_probability": 20},
               {"datetime": "2024-01-18T12:00:00+00:00", "condition": "rainy",
                "temperature": 14.5, "templow": 9.0, "precipitation_probability": 70},
               {"datetime": "2024-01-19T12:00:00+00:00", "condition": "sunny",
                "temperature": 20.0, "templow": 11.5, "precipitation_probability": 5},
           ]}),
    ]


# Per-type weather.get_forecasts payloads (issue #283), keyed by entity_id then
# forecast type — served by DemoHAClient.fetch_forecast so --demo exercises the
# same fetch-and-switch path a real HA instance does, rather than only ever
# reading the legacy inline "forecast" attribute.
_WEATHER_FORECASTS: dict[str, dict[str, list[dict]]] = {
    "weather.home": {
        "daily": [
            {"datetime": "2024-01-15T12:00:00+00:00", "condition": "partlycloudy",
             "temperature": 18.4, "templow": 11.0, "precipitation_probability": 10},
            {"datetime": "2024-01-16T12:00:00+00:00", "condition": "sunny",
             "temperature": 21.0, "templow": 12.5, "precipitation_probability": 0},
            {"datetime": "2024-01-17T12:00:00+00:00", "condition": "cloudy",
             "temperature": 17.0, "templow": 10.0, "precipitation_probability": 20},
            {"datetime": "2024-01-18T12:00:00+00:00", "condition": "rainy",
             "temperature": 14.5, "templow": 9.0, "precipitation_probability": 70},
            {"datetime": "2024-01-19T12:00:00+00:00", "condition": "sunny",
             "temperature": 20.0, "templow": 11.5, "precipitation_probability": 5},
        ],
        "twice_daily": [
            {"datetime": "2024-01-15T06:00:00+00:00", "condition": "partlycloudy",
             "temperature": 18.4, "is_daytime": True, "precipitation_probability": 10},
            {"datetime": "2024-01-15T18:00:00+00:00", "condition": "clear-night",
             "temperature": 11.0, "is_daytime": False, "precipitation_probability": 5},
            {"datetime": "2024-01-16T06:00:00+00:00", "condition": "sunny",
             "temperature": 21.0, "is_daytime": True, "precipitation_probability": 0},
            {"datetime": "2024-01-16T18:00:00+00:00", "condition": "clear-night",
             "temperature": 12.5, "is_daytime": False, "precipitation_probability": 0},
        ],
        "hourly": [
            {"datetime": "2024-01-15T12:00:00+00:00", "condition": "partlycloudy",
             "temperature": 18.4, "precipitation_probability": 10},
            {"datetime": "2024-01-15T13:00:00+00:00", "condition": "partlycloudy",
             "temperature": 18.9, "precipitation_probability": 8},
            {"datetime": "2024-01-15T14:00:00+00:00", "condition": "sunny",
             "temperature": 19.5, "precipitation_probability": 5},
            {"datetime": "2024-01-15T15:00:00+00:00", "condition": "sunny",
             "temperature": 19.2, "precipitation_probability": 5},
            {"datetime": "2024-01-15T16:00:00+00:00", "condition": "cloudy",
             "temperature": 18.0, "precipitation_probability": 15},
            {"datetime": "2024-01-15T17:00:00+00:00", "condition": "cloudy",
             "temperature": 16.8, "precipitation_probability": 20},
        ],
    },
}


def demo_forecast(entity_id: str, forecast_type: str) -> list[dict] | None:
    """weather.get_forecasts stand-in (issue #283): the per-type payload for a
    demo weather entity, or None when the entity/type isn't in the fixture
    (DemoHAClient.fetch_forecast falls back to the legacy inline attribute)."""
    return _WEATHER_FORECASTS.get(entity_id, {}).get(forecast_type)


def demo_registry() -> list[dict]:
    """``config/entity_registry/list`` rows — every demo entity mapped to a
    device from ``demo_devices()`` (the entity→device source of truth shared by
    the Device Log's `v` views and the device tree ``D``) and to a ``platform`` (the
    integration, backing the tree's integration grouping mode). ``input_number``
    is a helper with no backing device and no platform, populating the tree's
    "No device" and "No integration" buckets. One row carries ``disabled_by`` to
    exercise the device tree's disabled-entity filter (issue #139) — it shares a
    device and platform with enabled entities, so it's simply dropped from the
    tree while its device/integration still render their siblings."""

    def r(
        entity_id: str,
        device_id: str | None,
        platform: str | None,
        disabled_by: str | None = None,
    ) -> dict:
        row = {"entity_id": entity_id, "device_id": device_id, "platform": platform}
        if disabled_by:
            row["disabled_by"] = disabled_by
        return row

    return [
        # ── Living Room ──
        r("light.living_room_lamp", "dev_lr_lamp", "hue"),
        r("switch.living_room_tv", "dev_lr_tv", "mqtt"),
        r("climate.living_room", "dev_lr_thermostat", "nest"),
        r("sensor.living_room_temperature", "dev_lr_multisensor", "zha"),
        r("sensor.living_room_humidity", "dev_lr_multisensor", "zha"),
        r("binary_sensor.living_room_motion", "dev_lr_multisensor", "zha"),
        # Disabled by the user — hidden from the device tree (issue #139).
        r("sensor.living_room_battery", "dev_lr_multisensor", "zha", disabled_by="user"),
        r("sensor.living_room_button_battery", "dev_lr_button", "zha"),
        r("cover.living_room_blinds", "dev_lr_blinds", "zha"),
        r("media_player.living_room_speaker", "dev_lr_speaker", "sonos"),
        # ── Kitchen ──
        r("light.kitchen_spots", "dev_kitchen_spots", "hue"),
        r("switch.coffee_maker", "dev_coffee_maker", "mqtt"),
        # ── Bedroom ──
        r("light.bedroom", "dev_bedroom_light", "hue"),
        r("climate.bedroom", "dev_bedroom_thermostat", "nest"),
        r("fan.bedroom_fan", "dev_bedroom_fan", "mqtt"),
        r("binary_sensor.smoke_detector", "dev_smoke", "nest"),
        # ── Garage / Utility ──
        r("cover.garage_door", "dev_garage_door", "myq"),
        r("binary_sensor.washing_machine", "dev_washer", "mqtt"),
        r("sensor.power_consumption", "dev_energy_meter", "shelly"),
        r("sensor.solar_production", "dev_energy_meter", "shelly"),
        # ── Outdoor ──
        r("sensor.outdoor_temperature", "dev_weather", "netatmo"),
        r("binary_sensor.front_door", "dev_front_door", "zha"),
        r("lock.front_door", "dev_front_door_lock", "zwave_js"),
        # ── Unassigned device (no area) ──
        r("sensor.internet_speed", "dev_router", "unifi"),
        # ── No backing device / no integration (helper) ──
        r("input_number.thermostat_offset", None, None),
    ]


def demo_areas() -> list[dict]:
    """``config/area_registry/list`` rows for the demo home."""
    return [
        {"area_id": "area_living_room", "name": "Living Room"},
        {"area_id": "area_kitchen", "name": "Kitchen"},
        {"area_id": "area_bedroom", "name": "Bedroom"},
        {"area_id": "area_garage", "name": "Garage"},
        {"area_id": "area_outdoor", "name": "Outdoor"},
    ]


def demo_devices() -> list[dict]:
    """``config/device_registry/list`` rows. Each backs one or more entities (see
    ``demo_registry()``); ``dev_router`` has ``area_id=None`` to populate the
    device tree's "Unassigned" bucket."""

    def d(device_id: str, name: str, area_id: str | None, manufacturer: str, model: str) -> dict:
        return {"id": device_id, "name": name, "area_id": area_id,
                "manufacturer": manufacturer, "model": model}

    return [
        # ── Living Room ──
        d("dev_lr_lamp", "Living Room Lamp", "area_living_room", "Philips Hue", "Hue Color"),
        d("dev_lr_tv", "Living Room TV", "area_living_room", "Sony", "Bravia XR"),
        d("dev_lr_thermostat", "Living Room Thermostat", "area_living_room", "Nest", "Learning"),
        d("dev_lr_multisensor", "Living Room Multisensor", "area_living_room", "Aqara", "FP2"),
        d("dev_lr_button", "Living Room Button", "area_living_room", "Aqara", "Wireless Mini Switch"),
        d("dev_lr_blinds", "Living Room Blinds", "area_living_room", "IKEA", "Fyrtur"),
        d("dev_lr_speaker", "Living Room Speaker", "area_living_room", "Sonos", "One"),
        # ── Kitchen ──
        d("dev_kitchen_spots", "Kitchen Spotlights", "area_kitchen", "Philips Hue", "Hue White"),
        d("dev_coffee_maker", "Coffee Maker", "area_kitchen", "Smarter", "iKettle 3.0"),
        # ── Bedroom ──
        d("dev_bedroom_light", "Bedroom Light", "area_bedroom", "Philips Hue", "Hue White"),
        d("dev_bedroom_thermostat", "Bedroom Thermostat", "area_bedroom", "Nest", "Learning"),
        d("dev_bedroom_fan", "Bedroom Fan", "area_bedroom", "Dyson", "Cool AM07"),
        d("dev_smoke", "Smoke Detector", "area_bedroom", "Nest", "Protect"),
        # ── Garage / Utility ──
        d("dev_garage_door", "Garage Door", "area_garage", "Chamberlain", "MyQ"),
        d("dev_washer", "Washing Machine", "area_garage", "Bosch", "Serie 6"),
        d("dev_energy_meter", "Energy Meter", "area_garage", "Shelly", "Pro EM"),
        # ── Outdoor ──
        d("dev_weather", "Weather Station", "area_outdoor", "Netatmo", "Smart Weather"),
        d("dev_front_door", "Front Door Sensor", "area_outdoor", "Aqara", "Door Sensor"),
        d("dev_front_door_lock", "Front Door Lock", "area_outdoor", "Schlage", "Connect Smart Deadbolt"),
        # ── Unassigned (no area) ──
        d("dev_router", "Internet Router", None, "Ubiquiti", "Dream Machine"),
    ]


# ── History generation ───────────────────────────────────────────────────────

# entity_id -> generation params for a diurnal-ish numeric walk.
_NUMERIC = {
    "sensor.living_room_temperature": {"base": 21.0, "amp": 1.5, "round": 1, "floor": None},
    "sensor.living_room_humidity": {"base": 48.0, "amp": 6.0, "round": 0, "floor": 0.0},
    "sensor.outdoor_temperature": {"base": 12.0, "amp": 5.0, "round": 1, "floor": None},
    "sensor.power_consumption": {"base": 400.0, "amp": 250.0, "round": 0, "floor": 0.0},
    "sensor.solar_production": {"base": 1200.0, "amp": 900.0, "round": 0, "floor": 0.0},
    "sensor.internet_speed": {"base": 92.0, "amp": 6.0, "round": 1, "floor": 0.0},
}

# entity_id -> probability of being "on" at any flip (biased toward off).
_BINARY = {
    "binary_sensor.front_door": 0.25,
    "binary_sensor.living_room_motion": 0.4,
    "binary_sensor.smoke_detector": 0.03,
    "binary_sensor.washing_machine": 0.6,
}

# entity_id -> climate generation params.
_CLIMATE = {
    "climate.living_room": {"target": 21.5, "start": 19.5, "cool": False},
    "climate.bedroom": {"target": 18.0, "start": 19.5, "cool": False},
}


def _rng(entity_id: str) -> random.Random:
    return random.Random(hash(entity_id) & 0xFFFFFFFF)


def _timestamps(hours: float, end: datetime | None, n: int) -> list[datetime]:
    end = end or _now()
    step = (hours * 3600) / (n - 1)
    return [end - timedelta(seconds=step * (n - 1 - i)) for i in range(n)]


def demo_numeric_history(
    entity_id: str, hours: float = 4, end: datetime | None = None, n: int = 80
) -> list[tuple[str, float]]:
    cfg = _NUMERIC.get(entity_id)
    if cfg is None:
        return []
    rng = _rng(entity_id)
    base, amp = cfg["base"], cfg["amp"]
    pts: list[tuple[str, float]] = []
    for t in _timestamps(hours, end, n):
        hod = t.hour + t.minute / 60
        val = base + amp * math.sin(2 * math.pi * hod / 24) + rng.uniform(-amp * 0.12, amp * 0.12)
        if cfg["floor"] is not None:
            val = max(cfg["floor"], val)
        pts.append((_iso(t), round(val, cfg["round"])))
    return pts


def demo_state_log(entity_id: str, hours: float = 24, end: datetime | None = None) -> list[dict]:
    """Logbook-shaped entries synthesized from demo_numeric_history — the
    demo-mode counterpart of ``HAClient.fetch_state_log`` (issue #29), which
    fills the gap real HA's logbook leaves for continuous sensors. Thinned
    to 8 samples so it reads like discrete state changes, not the raw
    ~80-point plot feed."""
    return [
        {"when": when, "entity_id": entity_id, "state": str(value)}
        for when, value in demo_numeric_history(entity_id, hours, end, n=8)
    ]


def demo_binary_history(
    entity_id: str, hours: float = 4, end: datetime | None = None, n: int = 60
) -> list[tuple[str, float]]:
    p_on = _BINARY.get(entity_id)
    if p_on is None:
        return []
    rng = _rng(entity_id)
    state = 1.0 if rng.random() < p_on else 0.0
    pts: list[tuple[str, float]] = []
    for t in _timestamps(hours, end, n):
        if rng.random() < 0.15:
            state = 1.0 if rng.random() < p_on else 0.0
        pts.append((_iso(t), state))
    return pts


def demo_climate_history(
    entity_id: str, hours: float = 4, end: datetime | None = None, n: int = 80
) -> list[dict]:
    cfg = _CLIMATE.get(entity_id)
    if cfg is None:
        return []
    rng = _rng(entity_id)
    target = cfg["target"]
    cur = cfg["start"]
    pts: list[dict] = []
    for t in _timestamps(hours, end, n):
        cur += (target - cur) * 0.08 + rng.uniform(-0.15, 0.15)
        if cur < target - 0.2:
            action = "heating"
        elif cfg["cool"] and cur > target + 0.2:
            action = "cooling"
        else:
            action = "idle"
        pts.append(
            {
                "ts": _iso(t),
                "current_temperature": round(cur, 1),
                "target_temperature": target,
                "hvac_action": action,
            }
        )
    return pts


# device_id -> plausible zha_event types (issue #17) — a button's presses and
# a door sensor's connectivity pings never show up as a state change, so these
# are the demo's proof that the device log (`v`) surfaces more than entities do.
_DEMO_DEVICE_EVENTS: dict[str, list[str]] = {
    "dev_lr_button": ["remote_button_short_press", "remote_button_double_press", "remote_button_long_press"],
    "dev_front_door": ["device_offline", "device_online"],
}


def demo_device_events(device_ids: list[str], hours: float = 24, end: datetime | None = None) -> list[dict]:
    """Fake device-scoped logbook entries for the given device_ids. WS-shaped
    (epoch `when`, no `entity_id`) — same as a real logbook/get_events
    response — so --demo exercises the normalizer's WS branch end to end."""
    end = end or _now()
    device_names = {d["id"]: d["name"] for d in demo_devices()}
    entries: list[dict] = []
    for device_id in device_ids:
        event_types = _DEMO_DEVICE_EVENTS.get(device_id)
        if not event_types:
            continue
        rng = _rng(device_id)
        name = device_names.get(device_id, device_id)
        for _ in range(rng.randint(1, 3)):
            when = end - timedelta(minutes=rng.randint(1, max(1, int(hours * 60))))
            event_type = rng.choice(event_types)
            params = "{'device_ieee': '00:15:8d:00:02:f1:9a:1c'}"
            entries.append(
                {
                    "when": when.timestamp(),
                    "name": name,
                    "message": f"{event_type} event was fired with parameters: {params}",
                    "domain": "zha",
                }
            )
    return entries


def _when_key(entry: dict) -> float:
    """demo_logbook mixes ISO-string `when` (state entries) with epoch-float
    `when` (demo_device_events, WS-shaped) — normalize both to an epoch float
    so sort() doesn't raise TypeError comparing str to float."""
    when = entry["when"]
    if isinstance(when, (int, float)):
        return float(when)
    return datetime.fromisoformat(when).timestamp()


def demo_logbook(
    entity_ids: list[str], hours: float = 24, end: datetime | None = None, device_ids: list[str] | None = None
) -> list[dict]:
    """A handful of plausible activity entries for the given entities, plus
    device-scoped events (issue #17) when device_ids is given. Continuous
    sensors are skipped here, same as a real HA logbook (issue #29) —
    demo_state_log fills that gap the same way fetch_state_log does."""
    entity_attrs = {e["entity_id"]: e["attributes"] for e in demo_entities()}
    names = {eid: attrs.get("friendly_name", eid) for eid, attrs in entity_attrs.items()}
    targets = entity_ids or list(names)
    targets = [eid for eid in targets if not is_continuous_sensor(eid, entity_attrs.get(eid, {}))]
    rng = random.Random(1234)
    end = end or _now()
    entries: list[dict] = []
    for entity_id in targets:
        name = names.get(entity_id, entity_id)
        for _ in range(rng.randint(1, 3)):
            when = end - timedelta(minutes=rng.randint(1, max(1, int(hours * 60))))
            state = rng.choice(["on", "off", "open", "closed"])
            entries.append({"when": _iso(when), "name": name, "state": state})
    if device_ids:
        entries += demo_device_events(device_ids, hours, end)
    entries.sort(key=_when_key, reverse=True)
    return entries


# ── Seed user-data collections ───────────────────────────────────────────────


def demo_collections() -> dict:
    """Pre-built lists, dashboards, and saved graphs so the app looks lived-in
    and its newer features (manual sort, split panes, media_player/panel/light/
    cover/lock/fan widgets, row spans, gauge overrides, graph colors) are
    already populated rather than only reachable by building them by hand.
    Shapes match ``storage.COLLECTION_KEYS`` / the in-memory dicts the app holds."""
    return {
        "lists": {
            "Living Room": [
                "light.living_room_lamp",
                "switch.living_room_tv",
                "sensor.living_room_temperature",
                "sensor.living_room_humidity",
                "binary_sensor.living_room_motion",
                "cover.living_room_blinds",
            ],
            "Climate": [
                "climate.living_room",
                "climate.bedroom",
                "sensor.outdoor_temperature",
            ],
            # Deliberately non-alphabetical curated order (issue #213) so manual
            # sort visibly differs from the default alphabetical display.
            "Favorites": [
                "media_player.living_room_speaker",
                "light.living_room_lamp",
                "climate.living_room",
                "cover.living_room_blinds",
                "lock.front_door",
            ],
            # Pre-designated as a notify list below (issue #24) so change alerts
            # show up already in use.
            "Security": [
                "binary_sensor.smoke_detector",
                "binary_sensor.front_door",
                "lock.front_door",
            ],
        },
        "manual_lists": ["Favorites"],
        "notify_lists": ["Security"],
        "default_list": "Living Room",
        "entity_names": {"sensor.internet_speed": "WAN Speed"},
        "dashboards": {
            "Home": {
                "rows": 3,
                "cols": 4,
                "slots": [
                    {"row": 0, "col": 0, "widget_type": "thermostat", "entity_id": "climate.living_room",
                     "row_span": 2},
                    {"row": 0, "col": 1, "widget_type": "gauge", "entity_id": "sensor.power_consumption"},
                    {"row": 0, "col": 2, "widget_type": "gauge", "entity_id": "sensor.solar_production",
                     "gauge_min": 0, "gauge_max": 3000},
                    {"row": 0, "col": 3, "widget_type": "weather", "entity_id": "weather.home",
                     "row_span": 2},
                    {"row": 1, "col": 1, "widget_type": "switch", "entity_id": "switch.coffee_maker"},
                    {"row": 1, "col": 2, "widget_type": "sensor", "entity_id": "sensor.living_room_humidity"},
                    {"row": 2, "col": 0, "widget_type": "graph", "entity_id": "sensor.living_room_temperature",
                     "col_span": 2},
                    {"row": 2, "col": 2, "widget_type": "binary_sensor", "entity_id": "binary_sensor.front_door"},
                ],
            },
            "Living Room": {
                "rows": 3,
                "cols": 3,
                "slots": [
                    {"row": 0, "col": 0, "widget_type": "light", "entity_id": "light.living_room_lamp"},
                    {"row": 0, "col": 1, "widget_type": "media_player",
                     "entity_id": "media_player.living_room_speaker", "col_span": 2},
                    {
                        "row": 1, "col": 0, "widget_type": "split", "entity_id": None,
                        "children": {
                            "rows": 2,
                            "cols": 1,
                            "slots": [
                                {"row": 0, "col": 0, "widget_type": "switch",
                                 "entity_id": "switch.living_room_tv"},
                                {"row": 1, "col": 0, "widget_type": "switch",
                                 "entity_id": "switch.coffee_maker"},
                            ],
                        },
                    },
                    {"row": 1, "col": 1, "widget_type": "cover", "entity_id": "cover.living_room_blinds"},
                    {"row": 1, "col": 2, "widget_type": "lock", "entity_id": "lock.front_door"},
                    {
                        "row": 2, "col": 0, "widget_type": "panel", "entity_id": None,
                        "entity_ids": [
                            "sensor.living_room_temperature",
                            "sensor.living_room_humidity",
                            "binary_sensor.living_room_motion",
                            "binary_sensor.washing_machine",
                        ],
                        "col_span": 2,
                    },
                    {"row": 2, "col": 2, "widget_type": "fan", "entity_id": "fan.bedroom_fan"},
                ],
            },
        },
        "default_dashboard": "Home",
        "saved_graphs": {
            "Temperatures": {
                "entity_ids": ["sensor.living_room_temperature", "sensor.outdoor_temperature"],
                "graph_type": "line",
                "hours": 12,
                "colors": {"sensor.living_room_temperature": "orange", "sensor.outdoor_temperature": "cyan"},
            },
            "Energy": {
                "entity_ids": ["sensor.power_consumption", "sensor.solar_production"],
                "graph_type": "line",
                "hours": 24,
                "colors": {"sensor.power_consumption": "red", "sensor.solar_production": "green"},
            },
            "Internet Speed": {
                "entity_ids": ["sensor.internet_speed"],
                "graph_type": "scatter",
                "hours": 6,
            },
        },
    }
