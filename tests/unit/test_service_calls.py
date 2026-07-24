# hatty — MIT License. See LICENSE file for details.
"""Unit tests for the pure per-domain service-call payload builders (issue #169)."""

import pytest

from hatty.const import media_supports
from hatty.service_calls import (
    _CONTROL_SERVICE_BUILDERS,
    _climate_control_calls,
    _cover_control_calls,
    _fan_control_calls,
    _input_number_control_calls,
    _light_control_calls,
    _lock_control_calls,
    _media_player_control_calls,
)

# ── Light ────────────────────────────────────────────────────────────────────


def test_light_kelvin_maps_to_color_temp_kelvin():
    calls = _light_control_calls("light.lamp", {"kelvin": "3000"})
    assert calls == [("light", "turn_on", {"entity_id": "light.lamp", "color_temp_kelvin": 3000})]
    # The legacy "kelvin" service param must never leak into the payload.
    assert "kelvin" not in calls[0][2]


def test_light_brightness_is_int():
    calls = _light_control_calls("light.lamp", {"brightness": "128"})
    assert calls[0][2] == {"entity_id": "light.lamp", "brightness": 128}


def test_light_effect_passthrough():
    calls = _light_control_calls("light.lamp", {"effect": "rainbow"})
    assert calls[0][2]["effect"] == "rainbow"


def test_light_rgb_hex_parsed_stripping_hash_and_whitespace():
    calls = _light_control_calls("light.lamp", {"rgb_hex": "  #FF8000 "})
    assert calls[0][2]["rgb_color"] == [255, 128, 0]


def test_light_rgb_hex_wrong_length_ignored():
    calls = _light_control_calls("light.lamp", {"rgb_hex": "abc"})
    # Nothing usable -> no call at all (only entity_id would remain).
    assert calls == []


def test_light_folds_multiple_fields_into_one_turn_on():
    calls = _light_control_calls("light.lamp", {"brightness": "10", "kelvin": "4000", "effect": "none"})
    assert len(calls) == 1
    domain, service, data = calls[0]
    assert (domain, service) == ("light", "turn_on")
    assert data == {
        "entity_id": "light.lamp",
        "brightness": 10,
        "color_temp_kelvin": 4000,
        "effect": "none",
    }


def test_light_no_usable_fields_returns_empty():
    assert _light_control_calls("light.lamp", {}) == []


def test_light_non_hex_rgb_raises_value_error():
    with pytest.raises(ValueError):
        _light_control_calls("light.lamp", {"rgb_hex": "zzzzzz"})


# ── Fan ──────────────────────────────────────────────────────────────────────


def test_fan_percentage_only():
    calls = _fan_control_calls("fan.f", {"percentage": "40"})
    assert calls == [("fan", "set_percentage", {"entity_id": "fan.f", "percentage": 40})]


def test_fan_preset_only():
    calls = _fan_control_calls("fan.f", {"preset_mode": "auto"})
    assert calls == [("fan", "set_preset_mode", {"entity_id": "fan.f", "preset_mode": "auto"})]


def test_fan_both_fields_two_calls():
    calls = _fan_control_calls("fan.f", {"percentage": "40", "preset_mode": "auto"})
    assert [c[1] for c in calls] == ["set_percentage", "set_preset_mode"]


def test_fan_no_fields_empty():
    assert _fan_control_calls("fan.f", {}) == []


# ── Climate ──────────────────────────────────────────────────────────────────


def test_climate_temperature_is_float():
    calls = _climate_control_calls("climate.c", {"temperature": "21.5"})
    assert calls == [("climate", "set_temperature", {"entity_id": "climate.c", "temperature": 21.5})]


def test_climate_hvac_mode_passthrough():
    calls = _climate_control_calls("climate.c", {"hvac_mode": "heat"})
    assert calls == [("climate", "set_hvac_mode", {"entity_id": "climate.c", "hvac_mode": "heat"})]


def test_climate_fan_mode_passthrough():
    calls = _climate_control_calls("climate.c", {"fan_mode": "high"})
    assert calls == [("climate", "set_fan_mode", {"entity_id": "climate.c", "fan_mode": "high"})]


def test_climate_both_fields_two_calls():
    calls = _climate_control_calls("climate.c", {"temperature": "20", "hvac_mode": "cool"})
    assert [c[1] for c in calls] == ["set_temperature", "set_hvac_mode"]


def test_climate_no_fields_empty():
    assert _climate_control_calls("climate.c", {}) == []


# ── Cover ────────────────────────────────────────────────────────────────────


def test_cover_position_present():
    calls = _cover_control_calls("cover.c", {"position": "75"})
    assert calls == [("cover", "set_cover_position", {"entity_id": "cover.c", "position": 75})]


def test_cover_position_absent_empty():
    assert _cover_control_calls("cover.c", {}) == []


# ── input_number ─────────────────────────────────────────────────────────────


def test_input_number_value_is_float():
    calls = _input_number_control_calls("input_number.n", {"value": "3.5"})
    assert calls == [("input_number", "set_value", {"entity_id": "input_number.n", "value": 3.5})]


def test_input_number_value_absent_empty():
    assert _input_number_control_calls("input_number.n", {}) == []


# ── Lock ─────────────────────────────────────────────────────────────────────


def test_lock_locked_dispatches_lock():
    calls = _lock_control_calls("lock.l", {"locked": "locked"})
    assert calls == [("lock", "lock", {"entity_id": "lock.l"})]


def test_lock_unlocked_dispatches_unlock():
    calls = _lock_control_calls("lock.l", {"locked": "unlocked"})
    assert calls == [("lock", "unlock", {"entity_id": "lock.l"})]


def test_lock_absent_empty():
    assert _lock_control_calls("lock.l", {}) == []


# ── Media player ─────────────────────────────────────────────────────────────


def test_media_player_volume_level_is_float():
    calls = _media_player_control_calls("media_player.m", {"volume_level": "0.5"})
    assert calls == [("media_player", "volume_set", {"entity_id": "media_player.m", "volume_level": 0.5})]


def test_media_player_muted_bool():
    calls = _media_player_control_calls("media_player.m", {"is_volume_muted": True})
    assert calls == [("media_player", "volume_mute", {"entity_id": "media_player.m", "is_volume_muted": True})]


def test_media_player_source_passthrough():
    calls = _media_player_control_calls("media_player.m", {"source": "Spotify"})
    assert calls == [("media_player", "select_source", {"entity_id": "media_player.m", "source": "Spotify"})]


def test_media_player_sound_mode_passthrough():
    calls = _media_player_control_calls("media_player.m", {"sound_mode": "Movie"})
    assert calls == [("media_player", "select_sound_mode", {"entity_id": "media_player.m", "sound_mode": "Movie"})]


def test_media_player_shuffle_bool():
    calls = _media_player_control_calls("media_player.m", {"shuffle": True})
    assert calls == [("media_player", "shuffle_set", {"entity_id": "media_player.m", "shuffle": True})]


def test_media_player_repeat_passthrough():
    calls = _media_player_control_calls("media_player.m", {"repeat": "all"})
    assert calls == [("media_player", "repeat_set", {"entity_id": "media_player.m", "repeat": "all"})]


def test_media_player_multiple_fields_multiple_calls():
    calls = _media_player_control_calls("media_player.m", {"volume_level": "0.2", "shuffle": False})
    assert [c[1] for c in calls] == ["volume_set", "shuffle_set"]


def test_media_player_no_fields_empty():
    assert _media_player_control_calls("media_player.m", {}) == []


# ── media_supports (MediaPlayerEntityFeature bitmask helper) ─────────────────


def test_media_supports_flag_set():
    assert media_supports(4, "volume_set") is True


def test_media_supports_flag_not_set():
    assert media_supports(4, "select_source") is False


def test_media_supports_none_features():
    assert media_supports(None, "volume_set") is False


def test_media_supports_combined_bitmask():
    features = 4 | 2048  # volume_set | select_source
    assert media_supports(features, "volume_set") is True
    assert media_supports(features, "select_source") is True
    assert media_supports(features, "shuffle_set") is False


# ── Registry + conversion errors ─────────────────────────────────────────────


def test_registry_maps_every_controllable_domain():
    assert set(_CONTROL_SERVICE_BUILDERS) == {
        "light",
        "fan",
        "climate",
        "cover",
        "input_number",
        "lock",
        "media_player",
    }


def test_bad_numeric_string_raises_value_error():
    with pytest.raises(ValueError):
        _fan_control_calls("fan.f", {"percentage": "fast"})
