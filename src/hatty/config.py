# hatty — MIT License. See LICENSE file for details.
import os
from pathlib import Path

import yaml

from hatty.const import (
    CONFIG_KEY_BACKUP,
    CONFIG_KEY_COLUMNS,
    CONFIG_KEY_DASHBOARDS,
    CONFIG_KEY_DEFAULT_DASHBOARD,
    CONFIG_KEY_DEFAULT_LIST,
    CONFIG_KEY_ENTITY_NAMES,
    CONFIG_KEY_GRAPH_HOURS,
    CONFIG_KEY_GRAPH_TYPE,
    CONFIG_KEY_HOME_ASSISTANT,
    CONFIG_KEY_KEYBINDINGS,
    CONFIG_KEY_LISTS,
    CONFIG_KEY_LOG_HOURS,
    CONFIG_KEY_MANUAL_LISTS,
    CONFIG_KEY_NOTIFICATIONS,
    CONFIG_KEY_SAVED_GRAPHS,
    CONFIG_KEY_TERMINAL_TITLE,
    CONFIG_KEY_TERMINAL_TITLE_ENABLED,
    CONFIG_KEY_THEME,
    CONFIG_KEY_TOKEN,
    CONFIG_KEY_URL,
    DEFAULT_BACKUP,
    DEFAULT_COLUMNS,
    DEFAULT_GRAPH_HOURS,
    DEFAULT_LOG_HOURS,
    DEFAULT_NOTIFICATIONS,
    DEFAULT_TERMINAL_TITLE,
)

APP_NAME = "hatty"

# The placeholder token shipped in config.example.yaml; treated as "unconfigured"
# so a copied-but-unedited example still triggers the onboarding wizard.
PLACEHOLDER_TOKEN = "YOUR_LONG_LIVED_ACCESS_TOKEN"


def _config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME


def get_config_path() -> Path | None:
    xdg_path = _config_dir() / "config.yaml"
    if xdg_path.exists():
        return xdg_path

    cwd_path = Path.cwd() / "config.yaml"
    if cwd_path.exists():
        return cwd_path

    return None


def default_config_path() -> Path:
    """Where a fresh config is written when none exists yet (the XDG location)."""
    return _config_dir() / "config.yaml"


def default_config() -> dict:
    """The documented config skeleton, used to seed a brand-new config file."""
    return {
        CONFIG_KEY_HOME_ASSISTANT: {
            CONFIG_KEY_URL: "http://homeassistant.local:8123",
            CONFIG_KEY_TOKEN: "",
        },
        CONFIG_KEY_LISTS: {},
        CONFIG_KEY_MANUAL_LISTS: [],
        CONFIG_KEY_DEFAULT_LIST: None,
        CONFIG_KEY_COLUMNS: list(DEFAULT_COLUMNS),
        CONFIG_KEY_THEME: None,
        CONFIG_KEY_GRAPH_TYPE: "line",
        CONFIG_KEY_ENTITY_NAMES: {},
        CONFIG_KEY_DASHBOARDS: {},
        CONFIG_KEY_DEFAULT_DASHBOARD: None,
        CONFIG_KEY_GRAPH_HOURS: DEFAULT_GRAPH_HOURS,
        CONFIG_KEY_LOG_HOURS: DEFAULT_LOG_HOURS,
        CONFIG_KEY_SAVED_GRAPHS: {},
        CONFIG_KEY_NOTIFICATIONS: dict(DEFAULT_NOTIFICATIONS),
        CONFIG_KEY_TERMINAL_TITLE_ENABLED: True,
        CONFIG_KEY_TERMINAL_TITLE: DEFAULT_TERMINAL_TITLE,
        CONFIG_KEY_KEYBINDINGS: {},
        CONFIG_KEY_BACKUP: dict(DEFAULT_BACKUP),
    }


def needs_onboarding(config: dict) -> bool:
    """True when the app can't connect yet because the config is missing or has no
    usable URL/token — the trigger for the first-run onboarding wizard. A config
    that merely failed to *parse* (an 'error' key other than 'not found') is left
    alone so the wizard never silently overwrites a file the user hand-edited."""
    error = config.get("error")
    if error:
        return error == "Configuration file not found."
    ha = config.get(CONFIG_KEY_HOME_ASSISTANT) or {}
    url = (ha.get(CONFIG_KEY_URL) or "").strip()
    token = (ha.get(CONFIG_KEY_TOKEN) or "").strip()
    return not url or not token or token == PLACEHOLDER_TOKEN


def load_config(config_path: str | None = None) -> dict:
    path = Path(config_path) if config_path else get_config_path()

    if not path or not path.exists():
        return {"error": "Configuration file not found."}

    try:
        with open(path, "r") as f:
            config = yaml.safe_load(f) or {}
    except (IOError, yaml.YAMLError) as e:
        return {"error": f"Error loading configuration: {e}"}

    _migrate_legacy(config)

    for key, default in default_config().items():
        if key == CONFIG_KEY_HOME_ASSISTANT:
            # Absence of a usable url/token drives the onboarding wizard;
            # don't fabricate connection defaults here.
            continue
        config.setdefault(key, default)

    return config


def _migrate_legacy(config: dict) -> None:
    """Rewrite pre-'lists' config shapes in place: the legacy 'favorites' key
    and a bare-list 'lists' value both become the {name: [entity_ids]} dict."""
    if "favorites" in config:
        config[CONFIG_KEY_LISTS] = config.pop("favorites")

    lists = config.get(CONFIG_KEY_LISTS)
    if isinstance(lists, list):
        lists = {"default": lists}
    config[CONFIG_KEY_LISTS] = lists if isinstance(lists, dict) else {}


def save_config(config: dict, config_path: str | None = None) -> None:
    path = Path(config_path) if config_path else (get_config_path() or default_config_path())

    if not path:
        raise ValueError("Configuration file path not found, cannot save config.")

    # The config holds the long-lived HA token in cleartext, so keep the dir and
    # file private (issue #156). mkdir's mode= is masked by umask, so chmod it
    # explicitly; write the file via os.open with 0o600 (no world-readable window
    # for a fresh file) and chmod afterward to tighten any pre-existing config.
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        yaml.safe_dump(config, f)
    os.chmod(path, 0o600)
