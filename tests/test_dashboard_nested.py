# hatty — MIT License. See LICENSE file for details.
"""Nested split-pane dashboard slots (issue #81, Approach B)."""

from textual.widgets import Button, Label, Select

from hatty.ui.dashboard.screen import DashboardScreen
from hatty.ui.dashboard.widgets.split import SplitSlotWidget, normalized_children
from hatty.ui.dashboard.widgets.switch import SwitchSlotWidget
from hatty.ui.dashboard.widgets.text import TextSlotWidget
from tests.conftest import make_config

_HA = make_config(lists={})

_SPLIT_CONFIG = {
    **_HA,
    "dashboards": {
        "Main": {
            "rows": 2,
            "cols": 2,
            "slots": [
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
                            {"row": 0, "col": 1, "widget_type": "sensor", "entity_id": "sensor.temperature"},
                        ],
                    },
                },
                {"row": 1, "col": 1, "widget_type": "light", "entity_id": "light.kitchen_light"},
            ],
        }
    },
}


async def _open(pilot, app) -> DashboardScreen:
    await pilot.press("d")
    await pilot.pause()
    assert isinstance(app.screen, DashboardScreen)
    return app.screen


async def test_split_slot_renders_child_widgets(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_SPLIT_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        split = screen.query_one(SplitSlotWidget)
        switch = split.query_one(SwitchSlotWidget)
        assert switch.entity_id == "switch.fan"
        assert str(switch.query_one("#slot_name", Label).content) == "Fan Switch"
        sensor = split.query_one(TextSlotWidget)
        assert sensor.entity_id == "sensor.temperature"


async def test_live_state_change_reaches_child_widget(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_SPLIT_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        switch = screen.query_one(SplitSlotWidget).query_one(SwitchSlotWidget)
        assert "▱" in str(switch.query_one("#slot_glyph", Label).content)  # off

        app.client.inject_state_change(
            {
                "entity_id": "switch.fan",
                "state": "on",
                "attributes": {"friendly_name": "Fan Switch"},
                "last_changed": "2024-01-15T11:00:00.000000+00:00",
            }
        )
        await pilot.pause()
        assert "▰" in str(switch.query_one("#slot_glyph", Label).content)  # on


async def test_malformed_children_are_normalized_not_crashed(make_app, sample_entities):
    config = {
        **_HA,
        "dashboards": {
            "Main": {
                "rows": 1,
                "cols": 2,
                "slots": [
                    {
                        "row": 0,
                        "col": 0,
                        "widget_type": "split",
                        "entity_id": None,
                        "children": {
                            "rows": 1,
                            "cols": 2,
                            "slots": [
                                # nested split and spans are ignored, out-of-bounds dropped
                                {"row": 0, "col": 0, "widget_type": "split", "entity_id": None},
                                {
                                    "row": 0,
                                    "col": 1,
                                    "widget_type": "switch",
                                    "entity_id": "switch.fan",
                                    "row_span": 3,
                                    "col_span": 3,
                                },
                                {"row": 5, "col": 5, "widget_type": "sensor", "entity_id": "sensor.temperature"},
                            ],
                        },
                    },
                ],
            }
        },
    }
    app = make_app(entities=sample_entities, config_data=config)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        split = screen.query_one(SplitSlotWidget)
        assert split.child_slots == [{"row": 0, "col": 1, "widget_type": "switch", "entity_id": "switch.fan"}]
        assert split.query_one(SwitchSlotWidget).entity_id == "switch.fan"


def test_normalized_children_defaults():
    rows, cols, slots = normalized_children({"widget_type": "split", "children": {}})
    assert (rows, cols, slots) == (1, 1, [])


async def test_enter_descends_into_split_and_escape_ascends(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_SPLIT_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        assert screen._cursor_path == [(0, 0)]

        await pilot.press("enter")  # descend into the split
        await pilot.pause()
        assert screen._cursor_path == [(0, 0), (0, 0)]

        # The split container shows the descended style; the child cell is selected.
        split = screen.query_one(SplitSlotWidget)
        assert split.parent.has_class("-descended")
        assert not split.parent.has_class("-selected")
        child_cells = {(w.row, w.col): w for w in split.query("DashboardSlotWidget")}
        assert child_cells[(0, 0)].has_class("-selected")

        await pilot.press("escape")  # ascend, still on the dashboard
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
        assert screen._cursor_path == [(0, 0)]
        assert split.parent.has_class("-selected")
        assert not child_cells[(0, 0)].has_class("-selected")


async def test_arrows_move_within_child_grid_bounds(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_SPLIT_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        await pilot.press("enter")  # descend
        await pilot.pause()

        await pilot.press("right")
        await pilot.pause()
        assert screen._cursor_path == [(0, 0), (0, 1)]

        # Moving past the child grid's edge never auto-ascends.
        await pilot.press("right")
        await pilot.press("down")
        await pilot.pause()
        assert screen._cursor_path == [(0, 0), (0, 1)]

        await pilot.press("left")
        await pilot.pause()
        assert screen._cursor_path == [(0, 0), (0, 0)]


async def test_enter_toggles_child_slot_entity(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_SPLIT_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("enter")  # descend to child (0, 0): switch.fan, currently off
        await pilot.press("enter")  # toggle it
        await pilot.pause()
        assert ("switch", "turn_on", {"entity_id": "switch.fan"}) in app.client.call_service_calls


async def test_split_and_span_are_refused_inside_split(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_SPLIT_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        await pilot.press("enter")  # descend
        await pilot.press("E")  # edit mode
        await pilot.pause()
        before = repr(app.dashboards)

        await pilot.press("s")  # split (refused: one level max)
        await pilot.pause()
        await pilot.press("ctrl+right")  # resize (refused: children can't span)
        await pilot.pause()
        assert repr(app.dashboards) == before
        assert screen._cursor_path == [(0, 0), (0, 0)]


_ONE_CHILD_CONFIG = {
    **_HA,
    "dashboards": {
        "Main": {
            "rows": 2,
            "cols": 2,
            "slots": [
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
                        ],
                    },
                },
            ],
        }
    },
}


async def test_assign_widget_into_empty_child_cell(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_ONE_CHILD_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("enter")  # descend
        await pilot.press("E")  # edit mode
        await pilot.press("right")  # empty child (0, 1)
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()

        popup = app.screen
        popup.query_one("#widget_type_select", Select).value = "light"
        await pilot.pause()
        popup.query_one("#btn_next_step", Button).press()
        await pilot.pause()
        table = popup.query_one("#entity_picker_table")
        table.jump_cursor_to_row_key("light.kitchen_light")
        table.focus()
        await pilot.press("enter")
        await pilot.pause()

        children = app.dashboards["Main"]["slots"][0]["children"]
        assert {"row": 0, "col": 1, "widget_type": "light", "entity_id": "light.kitchen_light"} in children["slots"]
        # The dashboard's own grid was never touched.
        assert (app.dashboards["Main"]["rows"], app.dashboards["Main"]["cols"]) == (2, 2)


async def test_clear_child_cell(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_ONE_CHILD_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("enter")  # descend to child (0, 0)
        await pilot.press("E")
        await pilot.pause()
        await pilot.press("delete")
        await pilot.pause()

        children = app.dashboards["Main"]["slots"][0]["children"]
        assert children["slots"] == []


async def test_grab_move_swaps_cells_within_a_split(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_SPLIT_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("enter")  # descend to (0, 0): switch.fan
        await pilot.press("E")
        await pilot.pause()
        await pilot.press("enter")  # grab child (0, 0)
        await pilot.press("right")
        await pilot.press("enter")  # drop on child (0, 1): sensor.temperature
        await pilot.pause()

        children = app.dashboards["Main"]["slots"][0]["children"]
        by_cell = {(s["row"], s["col"]): s["entity_id"] for s in children["slots"]}
        assert by_cell == {(0, 0): "sensor.temperature", (0, 1): "switch.fan"}


async def test_edit_mode_assign_on_split_descends_instead_of_crashing(make_app, sample_entities):
    # `a` on a split pane used to open the popup with widget_type "split",
    # which isn't a legal Select value (issue #89). It should descend instead.
    app = make_app(entities=sample_entities, config_data=_ONE_CHILD_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        await pilot.press("E")  # edit mode, cursor on the split at (0, 0)
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)  # no popup, no crash
        assert screen._cursor_path == [(0, 0), (0, 0)]

        await pilot.press("right")  # empty child (0, 1)
        await pilot.press("a")  # now the popup opens, for the child cell
        await pilot.pause()
        assert not isinstance(app.screen, DashboardScreen)
        assert app.screen.query_one("#widget_type_select", Select).value == "graph"


async def test_slot_popup_tolerates_unassignable_widget_type(make_app, sample_entities):
    # Belt and braces: a slot dict whose widget_type the popup can't assign
    # (split, or anything unrecognized) falls back to the default selection.
    from hatty.ui.dashboard.slot_popup import DashboardSlotPopup

    app = make_app(entities=sample_entities, config_data=_SPLIT_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        split_slot = app.dashboards["Main"]["slots"][0]
        app.push_screen(DashboardSlotPopup(split_slot))
        await pilot.pause()
        assert app.screen.query_one("#widget_type_select", Select).value == "graph"


# ── Cross-grid grab-move (issue #220) ───────────────────────────────────────

_PARTIAL_SPLIT_CONFIG = {
    **_HA,
    "dashboards": {
        "Main": {
            "rows": 2,
            "cols": 2,
            "slots": [
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
                        ],
                    },
                },
                {"row": 1, "col": 1, "widget_type": "light", "entity_id": "light.kitchen_light"},
            ],
        }
    },
}


async def test_grab_move_out_of_split_into_empty_top_level_cell(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_PARTIAL_SPLIT_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        await pilot.press("enter")  # descend to child (0, 0): switch.fan
        await pilot.press("E")  # edit mode
        await pilot.pause()
        await pilot.press("enter")  # grab child (0, 0)

        await pilot.press("escape")  # ascend, carrying the grab
        await pilot.pause()
        assert screen._cursor_path == [(0, 0)]
        assert screen._grabbed is not None

        await pilot.press("right")  # empty top-level cell (0, 1)
        await pilot.press("enter")  # drop -> moves out of the split
        await pilot.pause()

        top_slots = app.dashboards["Main"]["slots"]
        by_cell = {(s["row"], s["col"]): s["entity_id"] for s in top_slots if s["widget_type"] != "split"}
        assert by_cell == {(0, 1): "switch.fan", (1, 1): "light.kitchen_light"}
        children = top_slots[0]["children"]
        assert children["slots"] == []
        assert screen._grabbed is None


async def test_grab_move_into_empty_child_cell_from_top_level(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_PARTIAL_SPLIT_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        await pilot.press("E")  # edit mode, cursor still on the split at (0, 0)
        await pilot.pause()
        await pilot.press("right")
        await pilot.press("down")  # (1, 1): light.kitchen_light
        await pilot.press("enter")  # grab it
        await pilot.press("up")
        await pilot.press("left")  # back to the split at (0, 0)

        await pilot.press("a")  # descend into the split, carrying the grab
        await pilot.pause()
        assert screen._cursor_path == [(0, 0), (0, 0)]
        assert screen._grabbed is not None

        await pilot.press("right")  # empty child cell (0, 1)
        await pilot.press("enter")  # drop -> moves into the split
        await pilot.pause()

        top_slots = app.dashboards["Main"]["slots"]
        assert [s for s in top_slots if s["widget_type"] != "split"] == []
        children = top_slots[0]["children"]
        by_cell = {(s["row"], s["col"]): s["entity_id"] for s in children["slots"]}
        assert by_cell == {(0, 0): "switch.fan", (0, 1): "light.kitchen_light"}


async def test_grab_move_swap_across_grids_onto_occupied_cell(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_SPLIT_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        await pilot.press("E")  # edit mode, cursor on the split at (0, 0)
        await pilot.pause()
        await pilot.press("right")
        await pilot.press("down")  # (1, 1): light.kitchen_light
        await pilot.press("enter")  # grab it
        await pilot.press("up")
        await pilot.press("left")  # back to the split at (0, 0)

        await pilot.press("a")  # descend into the split, carrying the grab
        await pilot.pause()
        assert screen._cursor_path == [(0, 0), (0, 0)]  # occupied: switch.fan

        await pilot.press("enter")  # drop -> cross-grid swap
        await pilot.pause()

        top_slots = app.dashboards["Main"]["slots"]
        by_cell = {(s["row"], s["col"]): s["entity_id"] for s in top_slots if s["widget_type"] != "split"}
        assert by_cell == {(1, 1): "switch.fan"}
        children = next(s for s in top_slots if s["widget_type"] == "split")["children"]
        by_child_cell = {(s["row"], s["col"]): s["entity_id"] for s in children["slots"]}
        assert by_child_cell == {(0, 0): "light.kitchen_light", (0, 1): "sensor.temperature"}


_TWO_SPLITS_CONFIG = {
    **_HA,
    "dashboards": {
        "Main": {
            "rows": 1,
            "cols": 2,
            "slots": [
                {
                    "row": 0,
                    "col": 0,
                    "widget_type": "split",
                    "entity_id": None,
                    "children": {
                        "rows": 1,
                        "cols": 1,
                        "slots": [{"row": 0, "col": 0, "widget_type": "switch", "entity_id": "switch.fan"}],
                    },
                },
                {
                    "row": 0,
                    "col": 1,
                    "widget_type": "split",
                    "entity_id": None,
                    "children": {
                        "rows": 1,
                        "cols": 1,
                        "slots": [{"row": 0, "col": 0, "widget_type": "sensor", "entity_id": "sensor.temperature"}],
                    },
                },
            ],
        }
    },
}


async def test_grab_move_refuses_nesting_a_split(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_TWO_SPLITS_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        await pilot.press("E")  # edit mode, cursor on split A at (0, 0)
        await pilot.pause()
        before = repr(app.dashboards)

        await pilot.press("enter")  # grab split A itself
        assert screen._grabbed == (0, 0)
        await pilot.press("right")  # split B at (0, 1)
        await pilot.press("a")  # descend into split B, carrying the grab
        await pilot.pause()
        assert screen._cursor_path == [(0, 1), (0, 0)]

        await pilot.press("enter")  # drop -> refused, a split can't nest
        await pilot.pause()

        assert repr(app.dashboards) == before
        assert screen._grabbed == (0, 0)  # grab still held


_SPAN_CONFIG = {
    **_HA,
    "dashboards": {
        "Main": {
            "rows": 2,
            "cols": 2,
            "slots": [
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
                        ],
                    },
                },
                {
                    "row": 0,
                    "col": 1,
                    "widget_type": "light",
                    "entity_id": "light.kitchen_light",
                    "row_span": 2,
                },
            ],
        }
    },
}


async def test_grab_move_drops_spans_entering_a_split(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_SPAN_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("E")  # edit mode, cursor on the split at (0, 0)
        await pilot.pause()
        await pilot.press("right")  # (0, 1): light.kitchen_light (spans 2 rows)
        await pilot.press("enter")  # grab it
        await pilot.press("left")  # back to the split at (0, 0)

        await pilot.press("a")  # descend, carrying the grab
        await pilot.pause()
        await pilot.press("right")  # empty child cell (0, 1)
        await pilot.press("enter")  # drop -> moves into the split
        await pilot.pause()

        top_slots = app.dashboards["Main"]["slots"]
        assert [s for s in top_slots if s["widget_type"] != "split"] == []
        children = top_slots[0]["children"]
        landed = next(s for s in children["slots"] if s["entity_id"] == "light.kitchen_light")
        assert landed["row"] == 0 and landed["col"] == 1
        assert "row_span" not in landed and "col_span" not in landed


async def test_escape_ascends_before_releasing_a_held_grab(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_SPLIT_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        await pilot.press("enter")  # descend to child (0, 0): switch.fan
        await pilot.press("E")  # edit mode
        await pilot.pause()
        before = repr(app.dashboards)
        await pilot.press("enter")  # grab child (0, 0)
        assert screen._grabbed is not None

        await pilot.press("escape")  # ascends, keeps the grab
        await pilot.pause()
        assert screen._cursor_path == [(0, 0)]
        assert screen._grabbed is not None

        await pilot.press("escape")  # now at top level -> releases the grab
        await pilot.pause()
        assert screen._grabbed is None
        assert repr(app.dashboards) == before  # nothing was ever dropped/mutated
