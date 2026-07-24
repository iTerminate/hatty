# hatty — MIT License. See LICENSE file for details.
"""Unit tests for the pure device-tree search filters (issue #129)."""

from hatty.ui.device_tree_screen import (
    NO_INTEGRATION_LABEL,
    build_device_groups,
    build_integration_groups,
    filter_area_groups,
    filter_device_groups,
    filter_integration_groups,
)

DEVICE_GROUPS = [
    {"device_id": "dev_lamp", "label": "Lamp", "area_id": "lr", "entity_ids": ["light.lamp", "sensor.temp"]},
    {"device_id": "dev_fan", "label": "Fan", "area_id": None, "entity_ids": ["switch.fan"]},
]


def _matcher(*matching_ids):
    return lambda entity_id: entity_id in matching_ids


def test_entity_match_prunes_group_to_matches():
    result = filter_device_groups(DEVICE_GROUPS, "temp", _matcher("sensor.temp"))
    assert [g["label"] for g in result] == ["Lamp"]
    assert result[0]["entity_ids"] == ["sensor.temp"]
    # The original group is untouched (a pruned copy is returned).
    assert DEVICE_GROUPS[0]["entity_ids"] == ["light.lamp", "sensor.temp"]


def test_device_label_match_keeps_all_entities():
    result = filter_device_groups(DEVICE_GROUPS, "lamp", _matcher())
    assert [g["label"] for g in result] == ["Lamp"]
    assert result[0]["entity_ids"] == ["light.lamp", "sensor.temp"]


def test_no_match_drops_all_groups():
    assert filter_device_groups(DEVICE_GROUPS, "zzz", _matcher()) == []


def test_area_label_match_keeps_whole_subtree():
    areas = [{"area_id": "lr", "label": "Living Room", "devices": DEVICE_GROUPS}]
    result = filter_area_groups(areas, "living", _matcher())
    assert result == areas


def test_area_label_multi_word_skips_words():
    areas = [{"area_id": "lr", "label": "Living Room Downstairs", "devices": DEVICE_GROUPS}]
    # "downstairs" skips over "room" in between.
    result = filter_area_groups(areas, "living downstairs", _matcher())
    assert result == areas
    # order-independent
    result = filter_area_groups(areas, "downstairs living", _matcher())
    assert result == areas
    # every word must still be present
    assert filter_area_groups(areas, "living kitchen", _matcher()) == []


def test_device_label_multi_word_skips_words():
    groups = [{**DEVICE_GROUPS[0], "label": "Living Room Lamp"}, DEVICE_GROUPS[1]]
    result = filter_device_groups(groups, "living lamp", _matcher())
    assert [g["label"] for g in result] == ["Living Room Lamp"]


def test_area_survives_via_matching_device():
    areas = [
        {"area_id": "lr", "label": "Living Room", "devices": [DEVICE_GROUPS[0]]},
        {"area_id": "kt", "label": "Kitchen", "devices": [DEVICE_GROUPS[1]]},
    ]
    result = filter_area_groups(areas, "temp", _matcher("sensor.temp"))
    assert [a["label"] for a in result] == ["Living Room"]
    assert result[0]["devices"][0]["entity_ids"] == ["sensor.temp"]


# ── search scopes (issue #140) ────────────────────────────────────────────────

AREAS = [
    {"area_id": "lr", "label": "Living Room", "devices": [DEVICE_GROUPS[0]]},
    {"area_id": "kt", "label": "Kitchen", "devices": [DEVICE_GROUPS[1]]},
]


def test_device_scope_ignores_entity_and_area_matches():
    # "temp" matches sensor.temp only via entity — device scope must ignore it.
    assert filter_device_groups(DEVICE_GROUPS, "temp", _matcher("sensor.temp"), "device") == []
    # A device-label match still keeps all entities.
    result = filter_device_groups(DEVICE_GROUPS, "lamp", _matcher(), "device")
    assert [g["label"] for g in result] == ["Lamp"]
    assert result[0]["entity_ids"] == ["light.lamp", "sensor.temp"]


def test_entity_scope_ignores_device_labels():
    # "lamp" is a device label — entity scope must not keep the device on it.
    assert filter_device_groups(DEVICE_GROUPS, "lamp", _matcher(), "entity") == []
    result = filter_device_groups(DEVICE_GROUPS, "temp", _matcher("sensor.temp"), "entity")
    assert result[0]["entity_ids"] == ["sensor.temp"]


def test_area_scope_keeps_only_label_matches():
    # Whole subtree kept on an area-label hit.
    result = filter_area_groups(AREAS, "living", _matcher("sensor.temp"), "area")
    assert [a["label"] for a in result] == ["Living Room"]
    assert result[0]["devices"] == [DEVICE_GROUPS[0]]
    # An entity/device match must NOT keep an area under area scope.
    assert filter_area_groups(AREAS, "temp", _matcher("sensor.temp"), "area") == []


def test_device_scope_at_area_level_ignores_area_labels():
    # "living" is an area label; device scope ignores it and finds no device match.
    assert filter_area_groups(AREAS, "living", _matcher(), "device") == []
    # A device-label match keeps its area.
    result = filter_area_groups(AREAS, "fan", _matcher(), "device")
    assert [a["label"] for a in result] == ["Kitchen"]


def test_entity_scope_at_area_level_prunes_to_matches():
    result = filter_area_groups(AREAS, "temp", _matcher("sensor.temp"), "entity")
    assert [a["label"] for a in result] == ["Living Room"]
    assert result[0]["devices"][0]["entity_ids"] == ["sensor.temp"]


# ── integration grouping (issue #147) ─────────────────────────────────────────

INT_REGISTRY = [
    {"entity_id": "light.lamp", "device_id": "dev_lamp", "platform": "hue"},
    {"entity_id": "sensor.temp", "device_id": "dev_multi", "platform": "zha"},
    {"entity_id": "binary_sensor.motion", "device_id": "dev_multi", "platform": "zha"},
    {"entity_id": "input_number.offset", "device_id": None},  # no platform
]
INT_DEVICES = [
    {"id": "dev_lamp", "name": "Lamp", "area_id": "lr"},
    {"id": "dev_multi", "name": "Multisensor", "area_id": "lr"},
]


def test_build_integration_groups_partitions_by_platform():
    groups = build_integration_groups(INT_REGISTRY, INT_DEVICES)
    # Named platforms sorted alphabetically, no-integration bucket last.
    assert [g["label"] for g in groups] == ["hue", "zha", NO_INTEGRATION_LABEL]
    hue, zha, none = groups
    assert [d["label"] for d in hue["devices"]] == ["Lamp"]
    # Both zha entities share one device.
    assert zha["devices"][0]["entity_ids"] == ["sensor.temp", "binary_sensor.motion"]
    # The platformless helper falls into the no-integration / no-device bucket.
    assert none["devices"][0]["entity_ids"] == ["input_number.offset"]


def test_filter_integration_label_match_keeps_subtree():
    groups = build_integration_groups(INT_REGISTRY, INT_DEVICES)
    result = filter_integration_groups(groups, "zha", _matcher())
    assert [g["label"] for g in result] == ["zha"]
    assert result[0]["devices"][0]["entity_ids"] == ["sensor.temp", "binary_sensor.motion"]


def test_filter_integration_label_multi_word_skips_words():
    groups = build_integration_groups(INT_REGISTRY, INT_DEVICES)
    groups = [{**g, "label": "Zigbee Home Automation"} if g["label"] == "zha" else g for g in groups]
    result = filter_integration_groups(groups, "zigbee automation", _matcher())
    assert [g["label"] for g in result] == ["Zigbee Home Automation"]


def test_filter_integration_entity_scope_prunes_to_matches():
    groups = build_integration_groups(INT_REGISTRY, INT_DEVICES)
    result = filter_integration_groups(groups, "temp", _matcher("sensor.temp"), "entity")
    assert [g["label"] for g in result] == ["zha"]
    assert result[0]["devices"][0]["entity_ids"] == ["sensor.temp"]


def test_filter_integration_area_scope_matches_nothing():
    groups = build_integration_groups(INT_REGISTRY, INT_DEVICES)
    assert filter_integration_groups(groups, "zha", _matcher("sensor.temp"), "area") == []


def test_filter_integration_scope_keeps_only_label_matches():
    # issue #180: the "integration" scope restricts the term to integration
    # (platform) labels — a label match keeps the whole subtree...
    groups = build_integration_groups(INT_REGISTRY, INT_DEVICES)
    result = filter_integration_groups(groups, "zha", _matcher(), "integration")
    assert [g["label"] for g in result] == ["zha"]
    assert result[0]["devices"][0]["entity_ids"] == ["sensor.temp", "binary_sensor.motion"]
    # ...but an entity-only term matches nothing under integration scope.
    assert filter_integration_groups(groups, "temp", _matcher("sensor.temp"), "integration") == []


def test_filter_integration_scope_in_area_mode_matches_nothing():
    # The scope is shared across view modes; "integration" has no node level in
    # area grouping, so it prunes everything (issue #180).
    areas = [{"area_id": "lr", "label": "Living Room", "devices": DEVICE_GROUPS}]
    assert filter_area_groups(areas, "living", _matcher(), "integration") == []


# ── disabled-entity filtering (issue #139) ────────────────────────────────────


def test_build_device_groups_skips_disabled_entities():
    registry = [
        {"entity_id": "light.lamp", "device_id": "dev_lamp", "platform": "hue"},
        {"entity_id": "sensor.battery", "device_id": "dev_lamp", "platform": "hue", "disabled_by": "user"},
    ]
    devices = [{"id": "dev_lamp", "name": "Lamp", "area_id": "lr"}]
    groups = build_device_groups(registry, devices)
    # The disabled entity is dropped; its device still shows its enabled sibling.
    assert [g["label"] for g in groups] == ["Lamp"]
    assert groups[0]["entity_ids"] == ["light.lamp"]


def test_build_device_groups_drops_all_disabled_device():
    registry = [
        {"entity_id": "sensor.battery", "device_id": "dev_lamp", "disabled_by": "integration"},
    ]
    devices = [{"id": "dev_lamp", "name": "Lamp", "area_id": "lr"}]
    # A device whose only entity is disabled produces no group at all.
    assert build_device_groups(registry, devices) == []


def test_build_integration_groups_drops_all_disabled_platform():
    registry = [
        {"entity_id": "light.lamp", "device_id": "dev_lamp", "platform": "hue"},
        {"entity_id": "sensor.temp", "device_id": "dev_multi", "platform": "zha", "disabled_by": "user"},
    ]
    devices = [
        {"id": "dev_lamp", "name": "Lamp", "area_id": "lr"},
        {"id": "dev_multi", "name": "Multisensor", "area_id": "lr"},
    ]
    groups = build_integration_groups(registry, devices)
    # The all-disabled `zha` platform yields no (empty) integration node.
    assert [g["label"] for g in groups] == ["hue"]
