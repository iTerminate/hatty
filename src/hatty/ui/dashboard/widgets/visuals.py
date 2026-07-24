# hatty — MIT License. See LICENSE file for details.
"""Pure rendering helpers shared by the dashboard slot widgets."""

from datetime import datetime
from typing import NamedTuple

from hatty.types import Entity
from hatty.ui.graph.plot_time import ts_to_hhmm

GAUGE_WIDTH = 14


def gauge_position(value: float, min_v: float, max_v: float, width: int = GAUGE_WIDTH) -> int:
    """Map value onto a 0..width-1 column index within [min_v, max_v], clamped."""
    if max_v <= min_v:
        return 0
    frac = (value - min_v) / (max_v - min_v)
    frac = max(0.0, min(1.0, frac))
    return round(frac * (width - 1))


def render_gauge(current: float, setpoint: float | None, min_v: float, max_v: float, width: int = GAUGE_WIDTH) -> str:
    """Render a min->max bar filled to `current`, with a caret marking `setpoint` below it."""
    fill = gauge_position(current, min_v, max_v, width) + 1
    bar = "█" * fill + "·" * (width - fill)
    if setpoint is None:
        return bar
    caret_pos = gauge_position(setpoint, min_v, max_v, width)
    caret_line = " " * caret_pos + "▲"
    return f"{bar}\n{caret_line}"


def render_bar(value: float, min_v: float, max_v: float, width: int = GAUGE_WIDTH) -> str:
    """A plain min->max bar filled to `value` (a caret-less gauge)."""
    return render_gauge(value, None, min_v, max_v, width)


def empty_bar(width: int = GAUGE_WIDTH) -> str:
    return "·" * width


def trend_arrow(history: list[tuple[str, float]]) -> str:
    """Direction of the last change in a numeric history: ▲ rising, ▼ falling, → flat."""
    if len(history) < 2:
        return ""
    prev, last = history[-2][1], history[-1][1]
    if last > prev:
        return "▲"
    if last < prev:
        return "▼"
    return "→"


# hvac_action -> icon/word/CSS class for climate widgets. "idle" carries no
# class, staying the default muted color; unmapped actions (off, fan, drying,
# unreported) fall back to showing the plain HVAC mode instead.
HVAC_ACTION_ICONS = {"heating": "🔥", "cooling": "❄", "idle": "•"}
HVAC_ACTION_WORDS = {"heating": "Heating", "cooling": "Cooling", "idle": "Idle"}
HVAC_ACTION_CLASSES = {"heating": "-heating", "cooling": "-cooling"}


# device_class -> icon for numeric sensor widgets.
SENSOR_CLASS_ICONS = {
    "temperature": "🌡",
    "humidity": "💧",
    "power": "⚡",
    "energy": "⚡",
    "battery": "🔋",
    "illuminance": "☀",
    "signal_strength": "📶",
    "pressure": "◎",
    "carbon_dioxide": "☁",
}


# domain -> representative glyph for the entity table's opt-in "Icon" column
# (#217). "lock" matches the padlock-with-key glyph used for the locked state
# elsewhere (dashboard/widgets/lock.py, dashboard/widgets/binary_sensor.py,
# controls/control_popup.py) so the domain icon and the locked-state icon agree.
DOMAIN_GLYPHS = {
    "light": "💡",
    "switch": "🔌",
    "fan": "🌀",
    "climate": "🌡",
    "cover": "🪟",
    "lock": "🔐",
    "media_player": "🔊",
    "sensor": "📊",
    "binary_sensor": "◉",
    "person": "👤",
    "device_tracker": "📍",
    "camera": "📷",
    "vacuum": "🧹",
    "scene": "🎬",
    "script": "📜",
    "automation": "⚙",
    "input_boolean": "🔘",
    "input_number": "🔢",
    "number": "🔢",
    "button": "⏺",
    "sun": "☀",
    "weather": "☁",
    "update": "⬆",
    "alarm_control_panel": "🛡",
    "siren": "📢",
    "humidifier": "💧",
    "select": "▾",
}


# HA weather.* condition -> multi-line ASCII art (wego/wttr.in idiom). Near-identical
# conditions deliberately share one block (both lightning variants, both windy variants,
# both "rainy" flavors) rather than drawing 15 distinct scenes.
_ART_SUNNY = """\
   \\   /
    .-.
 ― (   ) ―
    `-'
   /   \\"""

_ART_CLEAR_NIGHT = """\
    .   *
  *  .-.
    (   )
     `-'  .
  .    *"""

_ART_PARTLY_CLOUDY = """\
   \\  /
 _ /"".-.
  \\_(   ).
  /(___(__)"""

_ART_CLOUDY = """\
    .--.
 .-(    ).
(___.__)__)"""

_ART_FOG = """\
 _ - _ - _ -
  _ - _ - _
 _ - _ - _ -"""

_ART_RAINY = """\
    .-.
   (   ).
  (___(__)
  ‚'‚'‚'‚'
  ‚'‚'‚'‚'"""

_ART_POURING = """\
    .-.
   (   ).
  (___(__)
 ‚'‚'‚'‚'‚'
 ‚'‚'‚'‚'‚'"""

_ART_HAIL = """\
    .-.
   (   ).
  (___(__)
  *  *  *
  *  *  *"""

_ART_SNOWY = """\
    .-.
   (   ).
  (___(__)
  *  *  *
 *  *  *"""

_ART_SNOWY_RAINY = """\
    .-.
   (   ).
  (___(__)
  *‚'*‚'*
  ‚'* ‚'*"""

_ART_LIGHTNING = """\
    .-.
   (   ).
  (___(__)
    ⚡ ⚡
   ⚡ ⚡"""

_ART_WINDY = """\
  ~~ ~~~
 ~~~ ~~
  ~~~~ ~"""

_ART_EXCEPTIONAL = """\
   /!\\
  / ! \\
 /_____\\"""

WEATHER_ART: dict[str, str] = {
    "sunny": _ART_SUNNY,
    "clear-night": _ART_CLEAR_NIGHT,
    "partlycloudy": _ART_PARTLY_CLOUDY,
    "cloudy": _ART_CLOUDY,
    "fog": _ART_FOG,
    "rainy": _ART_RAINY,
    "pouring": _ART_POURING,
    "hail": _ART_HAIL,
    "snowy": _ART_SNOWY,
    "snowy-rainy": _ART_SNOWY_RAINY,
    "lightning": _ART_LIGHTNING,
    "lightning-rainy": _ART_LIGHTNING,
    "windy": _ART_WINDY,
    "windy-variant": _ART_WINDY,
    "exceptional": _ART_EXCEPTIONAL,
}

WEATHER_WORDS: dict[str, str] = {
    "clear-night": "Clear",
    "cloudy": "Cloudy",
    "exceptional": "Exceptional",
    "fog": "Fog",
    "hail": "Hail",
    "lightning": "Lightning",
    "lightning-rainy": "Thunderstorms",
    "partlycloudy": "Partly Cloudy",
    "pouring": "Pouring",
    "rainy": "Rainy",
    "snowy": "Snowy",
    "snowy-rainy": "Snow / Rain",
    "sunny": "Sunny",
    "windy": "Windy",
    "windy-variant": "Windy",
}

# condition -> CSS modifier class for the art/temp coloring on WeatherSlotWidget.
WEATHER_CLASSES: dict[str, str] = {
    "sunny": "-sunny",
    "clear-night": "-night",
    "partlycloudy": "-cloudy",
    "cloudy": "-cloudy",
    "fog": "-cloudy",
    "rainy": "-rainy",
    "pouring": "-rainy",
    "hail": "-rainy",
    "snowy": "-snowy",
    "snowy-rainy": "-snowy",
    "lightning": "-storm",
    "lightning-rainy": "-storm",
    "windy": "-cloudy",
    "windy-variant": "-cloudy",
    "exceptional": "-storm",
}


def weather_art(condition: str) -> str:
    """ASCII art for a weather condition; unknown conditions fall back to cloudy
    rather than rendering blank."""
    return WEATHER_ART.get(condition, _ART_CLOUDY)


_MAX_ART_HEIGHT = max(art.count("\n") + 1 for art in WEATHER_ART.values())


def pad_forecast_art(art: str, height: int = _MAX_ART_HEIGHT) -> str:
    """Pad an art block with trailing blank lines to a fixed height. The
    blocks in `WEATHER_ART` range 3-5 lines tall; without padding, the
    forecast screen's per-day columns (which stack art above condition/temp
    labels) would leave those labels at different rows depending on which
    condition's art is shorter, making the day columns look ragged."""
    lines = art.split("\n")
    lines += [""] * (height - len(lines))
    return "\n".join(lines)


def weather_label(condition: str) -> str:
    """Display word for a weather condition, title-casing unknown conditions
    instead of showing the raw HA slug."""
    return WEATHER_WORDS.get(condition) or condition.replace("-", " ").title()


def forecast_day_label(
    datetime_str: str | None, index: int, forecast_type: str = "daily", is_daytime: bool | None = None
) -> str:
    """Per-entry label for one `forecast` item (issue #283), format depending on
    `forecast_type`:
    - "hourly": the entry's local time ("14:32"), via the same `ts_to_hhmm`
      the graph screens use — a weekday label would be meaningless when every
      entry falls on today (or spills into tomorrow near midnight).
    - "twice_daily": weekday + "Day"/"Night" from `is_daytime`, since each day
      contributes two entries and a bare weekday would be ambiguous between them.
    - "daily" (default, legacy shape): weekday, with the first entry always
      "Today" regardless of its date (the convention HA's forecast list
      follows). Every variant falls back to a positional "+N" label when the
      datetime string can't be parsed.
    """
    if forecast_type == "hourly":
        return ts_to_hhmm(datetime_str) if datetime_str else f"+{index}h"
    if forecast_type == "twice_daily":
        period = "" if is_daytime is None else (" Day" if is_daytime else " Night")
        if datetime_str:
            try:
                day = datetime.fromisoformat(datetime_str)
            except ValueError:
                pass
            else:
                return f"{day.strftime('%a')}{period}"
        return f"+{index}{period}"
    if index == 0:
        return "Today"
    if datetime_str:
        try:
            day = datetime.fromisoformat(datetime_str)
        except ValueError:
            pass
        else:
            return day.strftime("%a")
    return f"+{index}"


def forecast_temp_range(item: dict, temp_unit: str) -> str:
    """ "high/low" string for one `forecast` entry, "—" for whichever bound
    (`temperature`/`templow`) is missing rather than omitting it entirely."""
    high = item.get("temperature")
    low = item.get("templow")
    high_text = str(high) if high is not None else "—"
    low_text = str(low) if low is not None else "—"
    return f"{high_text}/{low_text}{temp_unit}"


class ForecastColumn(NamedTuple):
    """One rendered day of `build_forecast_columns`, consumed by
    `weather_forecast_screen.py`."""

    label: str
    art: str
    condition_label: str
    css_class: str
    temp_range: str
    extra: str


def build_forecast_columns(
    forecast: list[dict] | None, temp_unit: str, *, forecast_type: str = "daily", limit: int = 7
) -> list[ForecastColumn]:
    """Map a weather entity's raw forecast list (issue #283: from
    `HAClient.fetch_forecast`, or the legacy inline `forecast` attribute) into
    display-ready columns, reusing the same art/label/class tables as the
    compact `WeatherSlotWidget`. `forecast_type` ("daily"/"twice_daily"/"hourly")
    picks the label format via `forecast_day_label` — each entry's `is_daytime`
    flag (present on twice_daily entries) is passed through. Caps at `limit`
    entries; a missing/empty forecast returns an empty list rather than
    raising, so the screen can render its own "no forecast data" placeholder."""
    if not forecast:
        return []
    columns = []
    for index, item in enumerate(forecast[:limit]):
        condition = item.get("condition", "")
        precip_prob = item.get("precipitation_probability")
        precip = item.get("precipitation")
        if precip_prob is not None:
            extra = f"☔ {precip_prob}%"
        elif precip is not None:
            extra = f"☔ {precip}mm"
        else:
            extra = ""
        columns.append(
            ForecastColumn(
                label=forecast_day_label(item.get("datetime"), index, forecast_type, item.get("is_daytime")),
                art=pad_forecast_art(weather_art(condition)),
                condition_label=weather_label(condition),
                css_class=WEATHER_CLASSES.get(condition, ""),
                temp_range=forecast_temp_range(item, temp_unit),
                extra=extra,
            )
        )
    return columns


def entity_glyph(entity: Entity) -> str:
    """A representative glyph for the entity's domain, for the entity table's
    opt-in "Icon" column. Sensors refine by device_class (reusing
    SENSOR_CLASS_ICONS) when one is mapped; anything unmapped falls back to
    "◆" (matching the generic fallback used elsewhere, e.g. the lock widget)."""
    domain = entity.get("entity_id", "").split(".")[0]
    if domain == "sensor":
        device_class = entity.get("attributes", {}).get("device_class") or ""
        if device_class in SENSOR_CLASS_ICONS:
            return SENSOR_CLASS_ICONS[device_class]
    return DOMAIN_GLYPHS.get(domain, "◆")
