# hatty — MIT License. See LICENSE file for details.
"""Unit tests for DashboardController CRUD and slot/span/split math (issue #169).

`create_populated` / `domain_to_widget_type` / grid math are covered by
test_dashboard_create_populated.py; the pure layout helpers by
test_dashboard_layout.py. These target the remaining untested mutations.
"""

from hatty.controllers.dashboards import DashboardController


class _StubApp:
    def __init__(self):
        self.persist_calls = []
        self.notifications = []
        self.entity_lists = {}

    def persist(self, *keys):
        self.persist_calls.append(keys)

    def notify(self, message, **kwargs):
        self.notifications.append((message, kwargs))


def _controller() -> DashboardController:
    return DashboardController(_StubApp())


def _slot(row, col, **extra):
    return {"row": row, "col": col, "widget_type": "sensor", "entity_id": f"sensor.{row}{col}", **extra}


# ── rename ────────────────────────────────────────────────────────────────────


def test_rename_happy_path_rewrites_everything():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.default_dashboard_name = "A"
    ctl.rename("A", "B")
    assert "A" not in ctl.dashboards and "B" in ctl.dashboards
    assert ctl.dashboard_names == ["B"]
    assert ctl.current_dashboard_name == "B"
    assert ctl.default_dashboard_name == "B"


def test_rename_missing_source_is_noop():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.rename("Ghost", "B")
    assert ctl.dashboard_names == ["A"]


def test_rename_to_same_name_is_noop():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.rename("A", "A")
    assert ctl.dashboard_names == ["A"]


def test_rename_to_existing_name_refused():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.create("B", 2, 2)
    ctl.rename("A", "B")
    assert "A" in ctl.dashboards and "B" in ctl.dashboards
    assert ctl._app.notifications[-1][1].get("severity") == "error"


# ── resize ────────────────────────────────────────────────────────────────────


def test_resize_prunes_out_of_bounds_slots():
    ctl = _controller()
    ctl.create("A", 3, 3)
    ctl.dashboards["A"]["slots"] = [_slot(0, 0), _slot(2, 2)]
    ctl.resize("A", 2, 2)
    coords = [(s["row"], s["col"]) for s in ctl.dashboards["A"]["slots"]]
    assert coords == [(0, 0)]
    assert ctl.dashboards["A"]["rows"] == 2 and ctl.dashboards["A"]["cols"] == 2


# ── row_height (#223) ────────────────────────────────────────────────────────


def test_create_without_row_height_omits_key():
    ctl = _controller()
    ctl.create("A", 2, 2)
    assert "row_height" not in ctl.dashboards["A"]


def test_create_with_row_height_sets_key():
    ctl = _controller()
    ctl.create("A", 2, 2, row_height=12)
    assert ctl.dashboards["A"]["row_height"] == 12


def test_set_row_height_sets_and_clears():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.set_row_height("A", 10)
    assert ctl.dashboards["A"]["row_height"] == 10
    ctl.set_row_height("A", None)
    assert "row_height" not in ctl.dashboards["A"]


# ── switch / set_default ──────────────────────────────────────────────────────


def test_switch_only_to_known_dashboard():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.switch("Ghost")
    assert ctl.current_dashboard_name == "A"
    ctl.create("B", 2, 2)
    ctl.switch("A")
    assert ctl.current_dashboard_name == "A"


def test_set_default_guarded_by_membership():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.set_default("Ghost")
    assert ctl.default_dashboard_name is None
    ctl.set_default("A")
    assert ctl.default_dashboard_name == "A"


# ── delete ────────────────────────────────────────────────────────────────────


def test_delete_reassigns_current_and_clears_default():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.create("B", 2, 2)
    ctl.default_dashboard_name = "B"
    ctl.current_dashboard_name = "B"
    ctl.delete("B")
    assert "B" not in ctl.dashboards
    assert ctl.current_dashboard_name == "A"
    assert ctl.default_dashboard_name is None


def test_delete_refuses_last_remaining():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.delete("A")
    assert "A" in ctl.dashboards
    assert ctl._app.notifications[-1][1].get("severity") == "warning"


def test_delete_missing_is_noop():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.create("B", 2, 2)
    ctl.delete("Ghost")
    assert set(ctl.dashboards) == {"A", "B"}


# ── resize_slot ───────────────────────────────────────────────────────────────


def test_resize_slot_missing_returns_false():
    ctl = _controller()
    ctl.create("A", 3, 3)
    assert ctl.resize_slot("A", 0, 0, 2, 2) is False


def test_resize_slot_out_of_bounds_returns_false():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.dashboards["A"]["slots"] = [_slot(1, 1)]
    assert ctl.resize_slot("A", 1, 1, 2, 2) is False


def test_resize_slot_overlap_returns_false():
    ctl = _controller()
    ctl.create("A", 3, 3)
    ctl.dashboards["A"]["slots"] = [_slot(0, 0), _slot(0, 1)]
    assert ctl.resize_slot("A", 0, 0, 1, 2) is False


def test_resize_slot_success_sets_spans_and_drops_ones():
    ctl = _controller()
    ctl.create("A", 3, 3)
    ctl.dashboards["A"]["slots"] = [_slot(0, 0)]
    assert ctl.resize_slot("A", 0, 0, 2, 2) is True
    slot = ctl.dashboards["A"]["slots"][0]
    assert slot["row_span"] == 2 and slot["col_span"] == 2
    # Shrinking back to 1 removes the keys (legacy shape).
    assert ctl.resize_slot("A", 0, 0, 1, 1) is True
    assert "row_span" not in slot and "col_span" not in slot


# ── swap_slots ────────────────────────────────────────────────────────────────


def test_swap_slots_move_into_empty():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.dashboards["A"]["slots"] = [_slot(0, 0)]
    assert ctl.swap_slots("A", 0, 0, 1, 1) is True
    slot = ctl.dashboards["A"]["slots"][0]
    assert (slot["row"], slot["col"]) == (1, 1)


def test_swap_slots_swaps_two_occupied():
    ctl = _controller()
    ctl.create("A", 2, 2)
    a, b = _slot(0, 0), _slot(1, 1)
    ctl.dashboards["A"]["slots"] = [a, b]
    assert ctl.swap_slots("A", 0, 0, 1, 1) is True
    assert (a["row"], a["col"]) == (1, 1)
    assert (b["row"], b["col"]) == (0, 0)


def test_swap_slots_refuses_span_misfit():
    ctl = _controller()
    ctl.create("A", 2, 2)
    # A 1x2 slot at (0,0) can't move to (0,1) — it would run off the grid.
    wide = _slot(0, 0, col_span=2)
    ctl.dashboards["A"]["slots"] = [wide]
    assert ctl.swap_slots("A", 0, 0, 0, 1) is False
    assert (wide["row"], wide["col"]) == (0, 0)


# ── split_slot / unsplit_slot ─────────────────────────────────────────────────


def test_split_slot_directions_produce_child_grid():
    for direction, dims in (("h", (2, 1)), ("v", (1, 2)), ("quad", (2, 2))):
        ctl = _controller()
        ctl.create("A", 2, 2)
        assert ctl.split_slot("A", 0, 0, direction) is True
        split = ctl.dashboards["A"]["slots"][0]
        assert split["widget_type"] == "split"
        assert (split["children"]["rows"], split["children"]["cols"]) == dims


def test_split_slot_moves_existing_widget_into_child_00():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.dashboards["A"]["slots"] = [_slot(0, 0, row_span=2)]
    assert ctl.split_slot("A", 0, 0, "v") is True
    split = ctl.dashboards["A"]["slots"][0]
    # Top-level span preserved on the container.
    assert split["row_span"] == 2
    child = split["children"]["slots"][0]
    assert (child["row"], child["col"]) == (0, 0)
    assert child["widget_type"] == "sensor"


def test_split_slot_already_split_refused():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.split_slot("A", 0, 0, "v")
    assert ctl.split_slot("A", 0, 0, "v") is False


def test_unsplit_single_child_collapses_back():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.dashboards["A"]["slots"] = [_slot(0, 0)]
    ctl.split_slot("A", 0, 0, "v")
    assert ctl.unsplit_slot("A", 0, 0) is True
    slot = ctl.dashboards["A"]["slots"][0]
    assert slot["widget_type"] == "sensor"
    assert (slot["row"], slot["col"]) == (0, 0)


def test_unsplit_multiple_children_refused():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.split_slot("A", 0, 0, "quad")
    split = ctl.dashboards["A"]["slots"][0]
    split["children"]["slots"] = [
        {"row": 0, "col": 0, "widget_type": "sensor", "entity_id": "sensor.a"},
        {"row": 1, "col": 1, "widget_type": "sensor", "entity_id": "sensor.b"},
    ]
    assert ctl.unsplit_slot("A", 0, 0) is False


def test_unsplit_non_split_refused():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.dashboards["A"]["slots"] = [_slot(0, 0)]
    assert ctl.unsplit_slot("A", 0, 0) is False


# ── fill_split (issue #218) ─────────────────────────────────────────────────────


def test_pack_grid_dimensions():
    from hatty.controllers.dashboards import DashboardController as DC

    assert DC._pack_grid(1) == (1, 1)
    assert DC._pack_grid(2) == (2, 1)
    assert DC._pack_grid(4) == (2, 2)
    assert DC._pack_grid(6) == (3, 2)


def test_fill_split_empty_pane_creates_sized_split():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ids = ["switch.a", "switch.b", "switch.c", "switch.d"]
    assert ctl.fill_split("A", 0, 0, "switch", ids) is True
    split = ctl.dashboards["A"]["slots"][0]
    assert split["widget_type"] == "split"
    assert split["entity_id"] is None
    children = split["children"]
    assert (children["rows"], children["cols"]) == (2, 2)
    assert [c["entity_id"] for c in children["slots"]] == ids
    assert all(c["widget_type"] == "switch" for c in children["slots"])
    # Row-major placement.
    assert [(c["row"], c["col"]) for c in children["slots"]] == [(0, 0), (0, 1), (1, 0), (1, 1)]


def test_fill_split_replaces_existing_widget_preserving_span():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.dashboards["A"]["slots"] = [_slot(0, 0, row_span=2)]
    assert ctl.fill_split("A", 0, 0, "sensor", ["sensor.a", "sensor.b"]) is True
    slots = ctl.dashboards["A"]["slots"]
    assert len(slots) == 1
    split = slots[0]
    assert split["widget_type"] == "split"
    assert split["row_span"] == 2
    assert len(split["children"]["slots"]) == 2


def test_fill_split_replaces_existing_split():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.split_slot("A", 0, 0, "v")
    assert ctl.fill_split("A", 0, 0, "light", ["light.a", "light.b", "light.c"]) is True
    slots = ctl.dashboards["A"]["slots"]
    assert len(slots) == 1
    assert len(slots[0]["children"]["slots"]) == 3


def test_fill_split_blank_ids_dropped():
    ctl = _controller()
    ctl.create("A", 2, 2)
    assert ctl.fill_split("A", 0, 0, "switch", ["switch.a", "", "switch.b"]) is True
    children = ctl.dashboards["A"]["slots"][0]["children"]
    assert [c["entity_id"] for c in children["slots"]] == ["switch.a", "switch.b"]


def test_fill_split_all_blank_is_noop():
    ctl = _controller()
    ctl.create("A", 2, 2)
    assert ctl.fill_split("A", 0, 0, "switch", ["", None]) is False
    assert ctl.dashboards["A"]["slots"] == []


def test_fill_split_persists():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl._app.persist_calls.clear()
    ctl.fill_split("A", 0, 0, "switch", ["switch.a"])
    assert ("dashboards",) in ctl._app.persist_calls


# ── grid_ctx ──────────────────────────────────────────────────────────────────


def test_grid_ctx_no_parent_returns_dashboard_grid():
    ctl = _controller()
    ctl.create("A", 3, 2)
    slots, rows, cols = ctl.grid_ctx("A", None)
    assert slots is ctl.dashboards["A"]["slots"]
    assert (rows, cols) == (3, 2)


def test_grid_ctx_split_parent_returns_child_grid():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.split_slot("A", 0, 0, "quad")
    slots, rows, cols = ctl.grid_ctx("A", (0, 0))
    split = ctl.dashboards["A"]["slots"][0]
    assert slots is split["children"]["slots"]
    assert (rows, cols) == (2, 2)


def test_grid_ctx_non_split_parent_returns_none():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.dashboards["A"]["slots"] = [_slot(0, 0)]
    assert ctl.grid_ctx("A", (0, 0)) is None


# ── export / import (issue #219) ─────────────────────────────────────────────


def test_export_payload_shape():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.set_slot("A", 0, 0, "sensor", "sensor.temp")
    payload = ctl.to_export_payload("A")
    assert payload["hatty_dashboard"] == 1
    assert payload["name"] == "A"
    assert payload["dashboard"] == ctl.dashboards["A"]
    # A deep copy, not a live reference.
    assert payload["dashboard"] is not ctl.dashboards["A"]


def test_import_round_trip_creates_matching_dashboard():
    ctl = _controller()
    ctl.create("A", 2, 2)
    ctl.set_slot("A", 0, 0, "sensor", "sensor.temp")
    ctl.split_slot("A", 1, 1, "quad")
    payload = ctl.to_export_payload("A")

    ctl2 = _controller()
    final = ctl2.import_from_payload(payload)
    assert final == "A"
    assert ctl2.dashboards["A"] == ctl.dashboards["A"]
    assert ctl2.current_dashboard_name == "A"
    assert ("dashboards",) in ctl2._app.persist_calls


def test_import_dedupes_name_on_collision():
    ctl = _controller()
    ctl.create("A", 2, 2)
    payload = ctl.to_export_payload("A")
    final = ctl.import_from_payload(payload)
    assert final == "A (2)"
    assert "A" in ctl.dashboards and "A (2)" in ctl.dashboards


def test_import_rejects_wrong_version():
    ctl = _controller()
    for bad in ({"hatty_dashboard": 2, "name": "A", "dashboard": {"rows": 1, "cols": 1}}, {}, "not a dict"):
        try:
            ctl.import_from_payload(bad)
            assert False, "expected ValueError"
        except ValueError:
            pass


def test_import_rejects_missing_dashboard_data():
    ctl = _controller()
    for bad_dashboard in (None, {"rows": 1}, {"cols": 1}, "nope"):
        payload = {"hatty_dashboard": 1, "name": "A", "dashboard": bad_dashboard}
        try:
            ctl.import_from_payload(payload)
            assert False, "expected ValueError"
        except ValueError:
            pass


def test_import_defaults_slots_when_missing():
    ctl = _controller()
    payload = {"hatty_dashboard": 1, "name": "A", "dashboard": {"rows": 2, "cols": 2}}
    final = ctl.import_from_payload(payload)
    assert ctl.dashboards[final]["slots"] == []


# ── dashboard_entity_ids ─────────────────────────────────────────────────────


def test_dashboard_entity_ids_collects_single_and_panel_slots_deduped():
    ctl = _controller()
    ctl.create("A", 1, 3)
    ctl.dashboards["A"]["slots"] = [
        {"row": 0, "col": 0, "widget_type": "switch", "entity_id": "switch.fan"},
        {"row": 0, "col": 1, "widget_type": "panel", "entity_id": None, "entity_ids": ["light.a", "light.b"]},
        # A duplicate of switch.fan (e.g. also panel-listed elsewhere) shouldn't repeat.
        {"row": 0, "col": 2, "widget_type": "switch", "entity_id": "switch.fan"},
    ]
    assert ctl.dashboard_entity_ids("A") == ["switch.fan", "light.a", "light.b"]


def test_dashboard_entity_ids_recurses_into_split_children():
    ctl = _controller()
    ctl.create("A", 1, 1)
    ctl.dashboards["A"]["slots"] = [
        {
            "row": 0,
            "col": 0,
            "widget_type": "split",
            "entity_id": None,
            "children": {
                "rows": 1,
                "cols": 2,
                "slots": [
                    {"row": 0, "col": 0, "widget_type": "switch", "entity_id": "switch.fan"},
                    {"row": 0, "col": 1, "widget_type": "panel", "entity_id": None, "entity_ids": ["light.a"]},
                ],
            },
        }
    ]
    assert ctl.dashboard_entity_ids("A") == ["switch.fan", "light.a"]


def test_dashboard_entity_ids_skips_empty_slots():
    ctl = _controller()
    ctl.create("A", 1, 1)
    ctl.dashboards["A"]["slots"] = [{"row": 0, "col": 0, "widget_type": "panel", "entity_id": None}]
    assert ctl.dashboard_entity_ids("A") == []
