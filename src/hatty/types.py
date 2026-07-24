# hatty — MIT License. See LICENSE file for details.
"""Typed shapes for the Home Assistant entity dict (issue #170).

`find_entity` and the widgets/table extractors pass around the raw dict HA sends
for each entity. These TypedDicts document that unwritten contract so a checker
can catch key typos, without changing anything at runtime — a `TypedDict` is a
plain `dict` when the code runs.

Both are `total=False`: HA entity payloads are partial (a dead/unavailable
entity may carry no `attributes`), and the code already guards every read with
`.get(...)`. This module imports only `typing`, so — like `const.py` — it stays
at the bottom of the dependency graph and can never introduce an import cycle.
"""

from typing import TypedDict


class EntityAttributes(TypedDict, total=False):
    """The `attributes` sub-dict. Only the keys the app actually reads are listed;
    HA sends many more, and `total=False` means any of these may be absent."""

    friendly_name: str
    device_class: str
    unit_of_measurement: str
    # climate
    temperature: float
    current_temperature: float
    target_temp_step: float
    min_temp: float
    max_temp: float
    hvac_action: str
    hvac_modes: list[str]
    preset_mode: str
    preset_modes: list[str]
    # light
    brightness: int
    color_mode: str
    color_temp: int
    color_temp_kelvin: int
    min_color_temp_kelvin: int
    max_color_temp_kelvin: int
    min_mireds: int
    max_mireds: int
    rgb_color: list[int]
    hs_color: list[float]
    effect: str
    effect_list: list[str]
    supported_color_modes: list[str]
    # cover / fan
    current_position: int
    percentage: int
    percentage_step: float
    # media_player
    supported_features: int
    volume_level: float
    is_volume_muted: bool
    media_title: str
    media_artist: str
    source: str
    source_list: list[str]
    sound_mode: str
    sound_mode_list: list[str]
    shuffle: bool
    repeat: str
    # gauge / numeric bounds + step
    min: float
    max: float
    step: float
    # weather
    temperature_unit: str
    humidity: float
    wind_speed: float
    wind_speed_unit: str
    forecast: list[dict]


class Entity(TypedDict, total=False):
    """One Home Assistant entity as delivered over the websocket / REST state API.

    `_local_name_override` is *not* from HA — it's injected locally by the rename
    path (`main.py`) and read by `get_display_name` (`ui/entity_table.py`)."""

    entity_id: str
    state: str
    attributes: EntityAttributes
    last_changed: str
    last_updated: str
    _local_name_override: str
