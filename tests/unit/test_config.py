# hatty — MIT License. See LICENSE file for details.
import os
import stat

import yaml

from hatty.config import (
    PLACEHOLDER_TOKEN,
    default_config,
    load_config,
    needs_onboarding,
    save_config,
)


def test_missing_file_returns_error(tmp_path):
    missing = tmp_path / "does_not_exist.yaml"
    result = load_config(str(missing))
    assert "error" in result


def test_empty_file_gets_defaults(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("")
    result = load_config(str(path))
    assert result["lists"] == {}
    assert result["default_list"] is None
    assert result["columns"] == ["name", "value", "last_changed", "in_list"]
    assert result["theme"] is None
    assert result["entity_names"] == {}
    assert result["dashboards"] == {}
    assert result["default_dashboard"] is None
    assert result["saved_graphs"] == {}
    assert result["terminal_title_enabled"] is True
    assert result["terminal_title"] == "hatty"


def test_missing_keys_get_defaults(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"home_assistant": {"url": "http://x", "token": "y"}}))
    result = load_config(str(path))
    assert result["lists"] == {}
    assert result["default_list"] is None
    assert result["columns"] == ["name", "value", "last_changed", "in_list"]
    assert result["home_assistant"]["url"] == "http://x"
    assert result["entity_names"] == {}
    assert result["dashboards"] == {}
    assert result["default_dashboard"] is None
    assert result["saved_graphs"] == {}
    assert result["terminal_title_enabled"] is True
    assert result["terminal_title"] == "hatty"


def test_legacy_favorites_key_migrates_to_lists(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"favorites": {"default": ["light.kitchen"]}}))
    result = load_config(str(path))
    assert "favorites" not in result
    assert result["lists"] == {"default": ["light.kitchen"]}


def test_bare_list_lists_value_is_wrapped(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"lists": ["light.kitchen", "switch.fan"]}))
    result = load_config(str(path))
    assert result["lists"] == {"default": ["light.kitchen", "switch.fan"]}


def test_unparseable_yaml_returns_error(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("home_assistant: [unclosed")
    result = load_config(str(path))
    assert "error" in result


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "config.yaml"
    config = {
        "home_assistant": {"url": "http://x", "token": "y"},
        "lists": {"default": ["light.kitchen"]},
        "default_list": "default",
        "columns": ["name", "state"],
        "theme": "nord",
        "entity_names": {"light.kitchen": "Main Light"},
        "dashboards": {
            "Main": {
                "rows": 3,
                "cols": 3,
                "slots": [{"row": 0, "col": 0, "widget_type": "graph", "entity_id": "sensor.temp"}],
            }
        },
        "default_dashboard": "Main",
        "saved_graphs": {
            "Living Room Trend": {"entity_ids": ["sensor.temp"], "graph_type": "line", "hours": 24},
        },
    }
    save_config(config, str(path))
    reloaded = load_config(str(path))
    assert reloaded["lists"] == {"default": ["light.kitchen"]}
    assert reloaded["default_list"] == "default"
    assert reloaded["columns"] == ["name", "state"]
    assert reloaded["theme"] == "nord"
    assert reloaded["entity_names"] == {"light.kitchen": "Main Light"}
    assert reloaded["dashboards"] == {
        "Main": {
            "rows": 3,
            "cols": 3,
            "slots": [{"row": 0, "col": 0, "widget_type": "graph", "entity_id": "sensor.temp"}],
        }
    }
    assert reloaded["default_dashboard"] == "Main"
    assert reloaded["saved_graphs"] == {
        "Living Room Trend": {"entity_ids": ["sensor.temp"], "graph_type": "line", "hours": 24},
    }


def test_save_without_path_falls_back_to_default_location(tmp_path, monkeypatch):
    # With no existing config and no explicit path, save_config writes to the
    # default XDG location (creating parent dirs) so the onboarding wizard can
    # create a config from scratch.
    default = tmp_path / "fresh" / "config.yaml"
    monkeypatch.setattr("hatty.config.get_config_path", lambda: None)
    monkeypatch.setattr("hatty.config.default_config_path", lambda: default)
    save_config({"lists": {"x": []}})
    assert default.exists()
    assert load_config(str(default))["lists"] == {"x": []}


def test_default_config_has_full_skeleton():
    cfg = default_config()
    for key in (
        "home_assistant",
        "lists",
        "columns",
        "dashboards",
        "saved_graphs",
        "graph_hours",
        "notifications",
    ):
        assert key in cfg
    assert cfg["home_assistant"] == {"url": "http://homeassistant.local:8123", "token": ""}


def test_default_config_notifications_block(tmp_path):
    # issue #224: notifications default to enabled with toast/beep/highlight on
    # and desktop/ntfy off, so a fresh install alerts without extra setup.
    prefs = default_config()["notifications"]
    assert prefs["enabled"] is True
    assert prefs["toast"] is True
    assert prefs["beep"] is True
    assert prefs["highlight"] is True
    assert prefs["desktop"] is False
    assert prefs["ntfy"] is False
    # issue #246: optional ntfy Basic auth defaults to unset (anonymous publish).
    assert prefs["ntfy_username"] == ""
    assert prefs["ntfy_password"] == ""

    # An empty file setdefaults the same block (load_config's default-fill loop).
    path = tmp_path / "config.yaml"
    path.write_text("")
    assert load_config(str(path))["notifications"] == prefs


def test_save_config_writes_private_permissions(tmp_path):
    # The config holds the plaintext HA token, so it must not be world-readable (#156).
    cfg_dir = tmp_path / "hatty"
    path = cfg_dir / "config.yaml"
    save_config({"lists": {}}, str(path))
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(cfg_dir).st_mode) == 0o700


def test_save_config_tightens_existing_world_readable_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("lists: {}\n")
    os.chmod(path, 0o644)
    save_config({"lists": {}}, str(path))
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_needs_onboarding_truth_table():
    # Missing file -> yes.
    assert needs_onboarding({"error": "Configuration file not found."}) is True
    # A parse error (hand-edited, broken) -> no, don't clobber it.
    assert needs_onboarding({"error": "Error loading configuration: bad yaml"}) is False
    # Empty / placeholder credentials -> yes.
    assert needs_onboarding({"home_assistant": {"url": "", "token": ""}}) is True
    assert needs_onboarding({"home_assistant": {"url": "http://h:8123", "token": ""}}) is True
    assert needs_onboarding({"home_assistant": {"url": "http://h:8123", "token": PLACEHOLDER_TOKEN}}) is True
    # Fully configured -> no.
    assert needs_onboarding({"home_assistant": {"url": "http://h:8123", "token": "abc"}}) is False
