# hatty — MIT License. See LICENSE file for details.
"""Pure per-domain builders that turn entity-control popup fields into the
``(domain, service, service_data)`` tuples ``HACLI.dispatch_entity_control``
sends to Home Assistant. No app state — just field-shape conversion.
``int()``/``float()`` conversions raise ``ValueError`` for the dispatcher to surface.
"""


def _light_control_calls(entity_id: str, fields: dict) -> list[tuple[str, str, dict]]:
    service_data: dict = {"entity_id": entity_id}
    if "brightness" in fields:
        service_data["brightness"] = int(fields["brightness"])
    if "kelvin" in fields:
        # HA removed the legacy "kelvin" service param; the modern key is color_temp_kelvin.
        service_data["color_temp_kelvin"] = int(fields["kelvin"])
    if "effect" in fields:
        service_data["effect"] = fields["effect"]
    if "rgb_hex" in fields:
        hex_str = fields["rgb_hex"].strip().lstrip("#")
        if len(hex_str) == 6:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            service_data["rgb_color"] = [r, g, b]
    if len(service_data) > 1:
        return [("light", "turn_on", service_data)]
    return []


def _fan_control_calls(entity_id: str, fields: dict) -> list[tuple[str, str, dict]]:
    calls = []
    if "percentage" in fields:
        calls.append(("fan", "set_percentage", {"entity_id": entity_id, "percentage": int(fields["percentage"])}))
    if "preset_mode" in fields:
        calls.append(("fan", "set_preset_mode", {"entity_id": entity_id, "preset_mode": fields["preset_mode"]}))
    return calls


def _climate_control_calls(entity_id: str, fields: dict) -> list[tuple[str, str, dict]]:
    calls = []
    if "temperature" in fields:
        calls.append(
            ("climate", "set_temperature", {"entity_id": entity_id, "temperature": float(fields["temperature"])})
        )
    if "hvac_mode" in fields:
        calls.append(("climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": fields["hvac_mode"]}))
    if "fan_mode" in fields:
        calls.append(("climate", "set_fan_mode", {"entity_id": entity_id, "fan_mode": fields["fan_mode"]}))
    return calls


def _cover_control_calls(entity_id: str, fields: dict) -> list[tuple[str, str, dict]]:
    if "position" in fields:
        return [("cover", "set_cover_position", {"entity_id": entity_id, "position": int(fields["position"])})]
    return []


def _input_number_control_calls(entity_id: str, fields: dict) -> list[tuple[str, str, dict]]:
    if "value" in fields:
        return [("input_number", "set_value", {"entity_id": entity_id, "value": float(fields["value"])})]
    return []


def _lock_control_calls(entity_id: str, fields: dict) -> list[tuple[str, str, dict]]:
    if "locked" in fields:
        service = "lock" if fields["locked"] == "locked" else "unlock"
        return [("lock", service, {"entity_id": entity_id})]
    return []


def _media_player_control_calls(entity_id: str, fields: dict) -> list[tuple[str, str, dict]]:
    """Continuous/selection media_player fields; discrete transport commands
    (play/pause/stop/next/previous) are dispatched directly by the control
    screen/dashboard widget via dispatch_service_call, not built here."""
    calls = []
    if "volume_level" in fields:
        calls.append(
            ("media_player", "volume_set", {"entity_id": entity_id, "volume_level": float(fields["volume_level"])})
        )
    if "is_volume_muted" in fields:
        muted = bool(fields["is_volume_muted"])
        calls.append(("media_player", "volume_mute", {"entity_id": entity_id, "is_volume_muted": muted}))
    if "source" in fields:
        calls.append(("media_player", "select_source", {"entity_id": entity_id, "source": fields["source"]}))
    if "sound_mode" in fields:
        calls.append(
            ("media_player", "select_sound_mode", {"entity_id": entity_id, "sound_mode": fields["sound_mode"]})
        )
    if "shuffle" in fields:
        calls.append(("media_player", "shuffle_set", {"entity_id": entity_id, "shuffle": bool(fields["shuffle"])}))
    if "repeat" in fields:
        calls.append(("media_player", "repeat_set", {"entity_id": entity_id, "repeat": fields["repeat"]}))
    return calls


# Domain -> pure (entity_id, fields) -> [(domain, service, service_data)] builder.
_CONTROL_SERVICE_BUILDERS = {
    "light": _light_control_calls,
    "fan": _fan_control_calls,
    "climate": _climate_control_calls,
    "cover": _cover_control_calls,
    "input_number": _input_number_control_calls,
    "lock": _lock_control_calls,
    "media_player": _media_player_control_calls,
}
