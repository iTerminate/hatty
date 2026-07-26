# hatty — MIT License. See LICENSE file for details.
from hatty.const import WIDGET_TYPES
from hatty.ui.dashboard.widget_match import compatible_widget_types, entity_matches_widget_type


def _entity(entity_id: str, state: str = "on") -> dict:
    return {"entity_id": entity_id, "state": state, "attributes": {}}


def test_numeric_sensor_matches_graph_gauge_and_sensor():
    # "panel" always qualifies too (it's a multi-entity container that accepts
    # anything) — callers that want to exclude it filter it out themselves.
    sensor = _entity("sensor.temperature", state="21.5")
    assert compatible_widget_types(sensor) == ["sensor", "graph", "gauge", "panel"]


def test_non_numeric_sensor_only_matches_sensor():
    sensor = _entity("sensor.mode", state="cool")
    assert compatible_widget_types(sensor) == ["sensor", "panel"]


def test_binary_sensor_matches_graph_as_step_timeline():
    entity = _entity("binary_sensor.door", state="off")
    types = compatible_widget_types(entity)
    assert types[0] == "binary_sensor"
    assert "graph" in types
    assert "gauge" not in types  # not numeric


def test_light_matches_only_light():
    light = _entity("light.living_room_lamp")
    assert compatible_widget_types(light) == ["light", "panel"]


def test_domain_with_no_widget_type_still_matches_panel():
    # "person" has no WIDGET_TYPE_DOMAINS entry and no numeric state, so only
    # the always-compatible "panel" carve-out applies.
    person = _entity("person.someone")
    assert compatible_widget_types(person) == ["panel"]


def test_compatible_types_round_trip_with_entity_matches_widget_type():
    for entity in (_entity("sensor.temperature", state="21.5"), _entity("light.lamp"), _entity("fan.bedroom")):
        for widget_type in WIDGET_TYPES:
            expected = entity_matches_widget_type(entity, widget_type)
            assert (widget_type in compatible_widget_types(entity)) == expected
