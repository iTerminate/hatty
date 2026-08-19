# hatty — MIT License. See LICENSE file for details.
"""Unit tests for GraphController: classification, saved-graph CRUD, live
record_state (issue #169).

`_trim_history` is covered by test_history_trim.py; the `open` branch of
handle_saved_graphs_popup_action is UI-heavy and covered end-to-end by
tests/test_saved_graphs.py, so it's not re-tested here.
"""

from collections import deque

from hatty.controllers.graphs import GraphController


class _StubApp:
    def __init__(self):
        self.persist_calls = []
        self.notifications = []
        self.graph_hours = 24

    def persist(self, *keys):
        self.persist_calls.append(keys)

    def notify(self, message, **kwargs):
        self.notifications.append((message, kwargs))


def _controller() -> GraphController:
    return GraphController(_StubApp())


# ── Classification ────────────────────────────────────────────────────────────


def test_is_climate_entity():
    assert GraphController.is_climate_entity("climate.living") is True
    assert GraphController.is_climate_entity("sensor.temp") is False


def test_is_binary_entity():
    assert GraphController.is_binary_entity("binary_sensor.door") is True
    assert GraphController.is_binary_entity("switch.fan") is False


def test_is_graphable_numeric():
    ctl = _controller()
    assert ctl.is_graphable({"entity_id": "sensor.temp", "state": "21.5"}) is True


def test_is_graphable_climate_and_binary():
    ctl = _controller()
    assert ctl.is_graphable({"entity_id": "climate.living", "state": "heat"}) is True
    assert ctl.is_graphable({"entity_id": "binary_sensor.door", "state": "on"}) is True


def test_is_graphable_false_for_non_numeric_light():
    ctl = _controller()
    assert ctl.is_graphable({"entity_id": "light.lamp", "state": "on"}) is False


# ── save_graph ────────────────────────────────────────────────────────────────


def test_save_graph_builds_entry_and_persists():
    ctl = _controller()
    ctl.save_graph("Temps", ["sensor.a", "sensor.b"], "line", 4.0)
    assert ctl.saved_graphs["Temps"] == {
        "entity_ids": ["sensor.a", "sensor.b"],
        "graph_type": "line",
        "hours": 4.0,
    }
    assert ("saved_graphs",) in ctl._app.persist_calls


def test_save_graph_includes_colors_when_truthy():
    ctl = _controller()
    ctl.save_graph("Temps", ["sensor.a"], "line", 4.0, colors={"sensor.a": "red"})
    assert ctl.saved_graphs["Temps"]["colors"] == {"sensor.a": "red"}


def test_save_graph_omits_empty_colors():
    ctl = _controller()
    ctl.save_graph("Temps", ["sensor.a"], "line", 4.0, colors={})
    assert "colors" not in ctl.saved_graphs["Temps"]


# ── handle_saved_graphs_popup_action: rename / delete ─────────────────────────


def test_saved_graphs_rename_happy_path():
    ctl = _controller()
    ctl.saved_graphs = {"Old": {"entity_ids": ["sensor.a"], "graph_type": "line", "hours": 4.0}}
    ctl.handle_saved_graphs_popup_action({"action": "rename", "old_name": "Old", "new_name": "New"})
    assert "Old" not in ctl.saved_graphs and "New" in ctl.saved_graphs
    assert ("saved_graphs",) in ctl._app.persist_calls


def test_saved_graphs_rename_missing_source_noop():
    ctl = _controller()
    ctl.saved_graphs = {"A": {}}
    ctl.handle_saved_graphs_popup_action({"action": "rename", "old_name": "Ghost", "new_name": "New"})
    assert set(ctl.saved_graphs) == {"A"}


def test_saved_graphs_rename_empty_new_name_noop():
    ctl = _controller()
    ctl.saved_graphs = {"A": {}}
    ctl.handle_saved_graphs_popup_action({"action": "rename", "old_name": "A", "new_name": ""})
    assert set(ctl.saved_graphs) == {"A"}


def test_saved_graphs_rename_collision_noop():
    ctl = _controller()
    ctl.saved_graphs = {"A": {}, "B": {}}
    ctl.handle_saved_graphs_popup_action({"action": "rename", "old_name": "A", "new_name": "B"})
    assert set(ctl.saved_graphs) == {"A", "B"}


def test_saved_graphs_delete_removes_and_persists():
    ctl = _controller()
    ctl.saved_graphs = {"A": {}}
    ctl.handle_saved_graphs_popup_action({"action": "delete", "name": "A"})
    assert ctl.saved_graphs == {}
    assert ("saved_graphs",) in ctl._app.persist_calls


def test_saved_graphs_delete_missing_noop():
    ctl = _controller()
    ctl.saved_graphs = {"A": {}}
    ctl.handle_saved_graphs_popup_action({"action": "delete", "name": "Ghost"})
    assert set(ctl.saved_graphs) == {"A"}


# ── record_state ──────────────────────────────────────────────────────────────


def test_record_state_appends_numeric_to_loaded_buffer():
    ctl = _controller()
    ctl.entity_history["sensor.temp"] = deque([("2026-07-07T10:00:00", 20.0)])
    ctl.record_state({"entity_id": "sensor.temp", "state": "21.5", "last_changed": "2026-07-07T10:05:00"})
    assert ctl.entity_history["sensor.temp"][-1] == ("2026-07-07T10:05:00", 21.5)


def test_record_state_maps_binary_via_state_map():
    ctl = _controller()
    ctl.entity_history["binary_sensor.door"] = deque([("2026-07-07T10:00:00", 0.0)])
    ctl.record_state(
        {"entity_id": "binary_sensor.door", "state": "on", "last_changed": "2026-07-07T10:05:00"}
    )
    assert ctl.entity_history["binary_sensor.door"][-1] == ("2026-07-07T10:05:00", 1.0)


def test_record_state_skips_when_not_loaded():
    ctl = _controller()
    ctl.record_state({"entity_id": "sensor.temp", "state": "21.5"})
    assert "sensor.temp" not in ctl.entity_history


def test_record_state_skips_non_numeric_state():
    ctl = _controller()
    ctl.entity_history["sensor.temp"] = deque([("2026-07-07T10:00:00", 20.0)])
    ctl.record_state({"entity_id": "sensor.temp", "state": "unavailable"})
    assert list(ctl.entity_history["sensor.temp"]) == [("2026-07-07T10:00:00", 20.0)]


def test_record_state_skips_unmapped_binary_state():
    ctl = _controller()
    ctl.entity_history["binary_sensor.door"] = deque([("2026-07-07T10:00:00", 0.0)])
    ctl.record_state({"entity_id": "binary_sensor.door", "state": "unknown"})
    assert list(ctl.entity_history["binary_sensor.door"]) == [("2026-07-07T10:00:00", 0.0)]


def test_record_state_missing_entity_id_is_noop():
    ctl = _controller()
    ctl.record_state({"state": "21.5"})  # no entity_id -> early return, no error


# ── export / import ──────────────────────────────────────────────────────────


def test_export_payload_shape():
    ctl = _controller()
    ctl.saved_graphs = {"Temps": {"entity_ids": ["sensor.a"], "graph_type": "line", "hours": 4.0}}
    payload = ctl.to_export_payload("Temps")
    assert payload["hatty_graph"] == 1
    assert payload["name"] == "Temps"
    assert payload["graph"] == ctl.saved_graphs["Temps"]
    # A deep copy, not a live reference.
    assert payload["graph"] is not ctl.saved_graphs["Temps"]


def test_import_round_trip_creates_matching_graph():
    ctl = _controller()
    ctl.saved_graphs = {"Temps": {"entity_ids": ["sensor.a"], "graph_type": "line", "hours": 4.0}}
    payload = ctl.to_export_payload("Temps")

    ctl2 = _controller()
    final = ctl2.import_from_payload(payload)
    assert final == "Temps"
    assert ctl2.saved_graphs["Temps"] == ctl.saved_graphs["Temps"]
    assert ("saved_graphs",) in ctl2._app.persist_calls


def test_import_dedupes_name_on_collision():
    ctl = _controller()
    ctl.saved_graphs = {"Temps": {"entity_ids": ["sensor.a"], "graph_type": "line", "hours": 4.0}}
    payload = ctl.to_export_payload("Temps")
    final = ctl.import_from_payload(payload)
    assert final == "Temps (2)"
    assert "Temps" in ctl.saved_graphs and "Temps (2)" in ctl.saved_graphs


def test_import_rejects_wrong_version():
    ctl = _controller()
    for bad in ({"hatty_graph": 2, "name": "A", "graph": {"entity_ids": []}}, {}, "not a dict"):
        try:
            ctl.import_from_payload(bad)
            assert False, "expected ValueError"
        except ValueError:
            pass


def test_import_rejects_missing_entity_ids():
    ctl = _controller()
    for bad_graph in (None, "nope", {}, {"graph_type": "line"}):
        payload = {"hatty_graph": 1, "name": "A", "graph": bad_graph}
        try:
            ctl.import_from_payload(payload)
            assert False, "expected ValueError"
        except ValueError:
            pass
