# hatty — MIT License. See LICENSE file for details.
"""Shared application constants.

Single home for the HA-domain/state knowledge and display defaults that were
previously scattered across whichever module first needed them. This module
must not import anything from the app so it stays cycle-safe.
"""

# Domains flippable with a plain turn_on/turn_off pair (enter on the entities
# table). "media_player" is here too, but its enter behavior is media_play_pause
# — see the carve-out at the top of HACLI.toggle_entity.
TOGGLABLE_DOMAINS = {"switch", "light", "fan", "media_player"}

# Domains with an attribute-editing UI. "light"/"media_player" route to their own
# live-apply screens (ui/controls/); EntityControlPopup handles the rest.
CONTROLLABLE_DOMAINS = {"light", "fan", "climate", "cover", "input_number", "lock", "media_player"}

# Home Assistant MediaPlayerEntityFeature bitmask (only the flags we gate on).
MEDIA_FEAT = {
    "pause": 1,
    "seek": 2,
    "volume_set": 4,
    "volume_mute": 8,
    "previous_track": 16,
    "next_track": 32,
    "turn_on": 128,
    "turn_off": 256,
    "volume_step": 1024,
    "select_source": 2048,
    "stop": 4096,
    "play": 16384,
    "shuffle_set": 32768,
    "select_sound_mode": 65536,
    "repeat_set": 262144,
}


def media_supports(features: int | None, flag: str) -> bool:
    """Whether a media_player's supported_features bitmask has `flag` set."""
    return bool((features or 0) & MEDIA_FEAT[flag])


# Home Assistant WeatherEntityFeature bitmask — which weather.get_forecasts
# `type` values an entity supports; order doubles as the preferred default.
WEATHER_FEAT = {
    "forecast_daily": 1,
    "forecast_hourly": 2,
    "forecast_twice_daily": 4,
}


def weather_supports(features: int | None, flag: str) -> bool:
    """Whether a weather entity's supported_features bitmask has `flag` set."""
    return bool((features or 0) & WEATHER_FEAT[flag])


def supported_forecast_types(features: int | None) -> list[str]:
    """The weather.get_forecasts `type` strings this entity's supported_features
    bitmask advertises, in preferred-default order (daily, twice_daily, hourly).
    Empty when the entity advertises no forecast support at all."""
    types = []
    if weather_supports(features, "forecast_daily"):
        types.append("daily")
    if weather_supports(features, "forecast_twice_daily"):
        types.append("twice_daily")
    if weather_supports(features, "forecast_hourly"):
        types.append("hourly")
    return types


NUMERIC_INPUT_TYPES = {"integer", "number"}

# Binary entity states -> graphable values; anything else
# (unavailable/unknown) is dropped.
BINARY_STATE_MAP = {"on": 1.0, "off": 0.0}

# device_class -> (on label, off label), per Home Assistant's binary_sensor conventions.
# Shared by the dashboard binary_sensor slot widget and the activity log (issue #25).
DEVICE_CLASS_LABELS = {
    "battery": ("Low", "Normal"),
    "battery_charging": ("Charging", "Not Charging"),
    "cold": ("Cold", "Normal"),
    "connectivity": ("Connected", "Disconnected"),
    "door": ("Open", "Closed"),
    "garage_door": ("Open", "Closed"),
    "gas": ("Detected", "Clear"),
    "heat": ("Hot", "Normal"),
    "light": ("Detected", "No Light"),
    "lock": ("Unlocked", "Locked"),
    "moisture": ("Wet", "Dry"),
    "motion": ("Detected", "Clear"),
    "moving": ("Moving", "Not Moving"),
    "occupancy": ("Detected", "Clear"),
    "opening": ("Open", "Closed"),
    "plug": ("Plugged In", "Unplugged"),
    "power": ("Detected", "No Power"),
    "presence": ("Home", "Away"),
    "problem": ("Problem", "OK"),
    "running": ("Running", "Not Running"),
    "safety": ("Unsafe", "Safe"),
    "smoke": ("Detected", "Clear"),
    "sound": ("Detected", "Clear"),
    "tamper": ("Tampering", "Clear"),
    "update": ("Update Available", "Up-to-date"),
    "vibration": ("Detected", "Clear"),
    "window": ("Open", "Closed"),
}


def binary_state_label(state: str, device_class: str) -> str:
    """Human label for a binary_sensor's on/off state, per device_class
    (e.g. door: Open/Closed). Any other state passes through unchanged."""
    on_label, off_label = DEVICE_CLASS_LABELS.get(device_class, ("On", "Off"))
    if state == "on":
        return on_label
    if state == "off":
        return off_label
    return state


# Dashboard slot widget types offered by DashboardSlotPopup ("split" is not
# assignable — split slots are created via SplitSlotPopup).
WIDGET_TYPES = [
    "graph",
    "gauge",
    "switch",
    "light",
    "fan",
    "thermostat",
    "cover",
    "lock",
    "media_player",
    "sensor",
    "binary_sensor",
    "weather",
    "panel",
]

# widget_type -> domain its entity picker restricts to; absent = unrestricted (panel).
# "graph"/"gauge" filter by numeric state instead, so they're not mapped here. Every
# new WIDGET_TYPES entry needs a mapping here or an explicit carve-out above.
WIDGET_TYPE_DOMAINS = {
    "switch": "switch",
    "light": "light",
    "fan": "fan",
    "thermostat": "climate",
    "cover": "cover",
    "lock": "lock",
    "media_player": "media_player",
    "sensor": "sensor",
    "binary_sensor": "binary_sensor",
    "weather": "weather",
}

# Widget types that can carry "show_last_changed": every single-entity widget.
# "graph" plots its own time axis; "panel"/"split" hold many entities, no single one.
LAST_CHANGED_WIDGET_TYPES = frozenset(WIDGET_TYPES) - {"graph", "panel"}

# Entity table columns shown when the config carries no "columns" key.
DEFAULT_COLUMNS = ["name", "value", "last_changed", "in_list"]

# Fallback for the global "graph_hours" config value.
DEFAULT_GRAPH_HOURS = 4

# Fallback for the global "log_hours" config value (the activity log's window size).
DEFAULT_LOG_HOURS = 24

# GraphPreviewScreen's shift+left/right "fast page" multiplier. Lives here (not
# preview_screen.py) so the keybinding registry can reference it without a cycle.
FAST_PAGE_MULTIPLIER = 6

# Canonical names for the top-level app_config keys, so a rename is one edit and a
# typo is a NameError instead of a silent None (config.default_config() and
# storage.PERSISTED reference these). NOTE: "graph_type"/"hours" also appear as
# keys *inside* saved-graph entry dicts (a different namespace) — don't reuse
# CONFIG_KEY_GRAPH_TYPE there.
CONFIG_KEY_HOME_ASSISTANT = "home_assistant"
CONFIG_KEY_URL = "url"
CONFIG_KEY_TOKEN = "token"
CONFIG_KEY_COLUMNS = "columns"
CONFIG_KEY_THEME = "theme"
CONFIG_KEY_GRAPH_TYPE = "graph_type"
CONFIG_KEY_GRAPH_HOURS = "graph_hours"
CONFIG_KEY_LOG_HOURS = "log_hours"
CONFIG_KEY_LISTS = "lists"
CONFIG_KEY_DEFAULT_LIST = "default_list"
CONFIG_KEY_DASHBOARDS = "dashboards"
CONFIG_KEY_DEFAULT_DASHBOARD = "default_dashboard"
CONFIG_KEY_SAVED_GRAPHS = "saved_graphs"
CONFIG_KEY_ENTITY_NAMES = "entity_names"
CONFIG_KEY_MANUAL_LISTS = "manual_lists"
CONFIG_KEY_NOTIFICATIONS = "notifications"
CONFIG_KEY_NOTIFY_LISTS = "notify_lists"
CONFIG_KEY_TERMINAL_TITLE_ENABLED = "terminal_title_enabled"
CONFIG_KEY_TERMINAL_TITLE = "terminal_title"
CONFIG_KEY_KEYBINDINGS = "keybindings"
CONFIG_KEY_BACKUP = "backup"

# Fallback for the "terminal_title" config key.
DEFAULT_TERMINAL_TITLE = "hatty"

# Legacy reserved list name (#224). No longer special — any list can be a
# notification source via `notify_lists` (#24); kept only for migration lookup.
NOTIFY_LIST_NAME = "\U0001f514 Notifications"

# Default notification preferences (config key "notifications"), merged over by
# NotificationController whenever a config predates a given key.
DEFAULT_NOTIFICATIONS = {
    "enabled": True,
    "toast": True,
    "beep": True,
    "desktop": False,
    "ntfy": False,
    "highlight": True,
    "ntfy_url": "https://ntfy.sh",
    "ntfy_topic": "",
    "ntfy_username": "",
    "ntfy_password": "",
}

# Default Backup & Sync preferences (config key "backup"), merged over by
# BackupController for a config that predates a key. "sections" is spelled out
# literally (matching backup.SECTIONS) so const.py stays import-free.
DEFAULT_BACKUP = {
    "path": "",  # export directory; "" = feature idle
    "sections": ["lists", "dashboards", "saved_graphs", "entity_names", "settings", "keybindings"],
    "git_enabled": False,
    "pull_on_start": False,  # pull + import at boot
    "import_on_pull": True,  # after a successful pull, load the files back in
    "commit_on_exit": False,  # export + commit at quit
    "push_on_exit": False,  # ...and push (implies commit)
    "pull_rebase": False,
}
