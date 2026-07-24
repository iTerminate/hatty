# hatty — MIT License. See LICENSE file for details.
"""The dashboard split key (s in edit mode) — nested sub-grid splits (issue #81)."""

from hatty.ui.dashboard.screen import DashboardScreen
from hatty.ui.dashboard.split_slot_popup import SplitSlotPopup
from tests.conftest import make_config

_HA = make_config(lists={})

_CONFIG = {
    **_HA,
    "dashboards": {
        "Main": {
            "rows": 2,
            "cols": 2,
            "slots": [{"row": 0, "col": 1, "widget_type": "switch", "entity_id": "switch.fan"}],
        }
    },
}


async def _open(pilot, app) -> DashboardScreen:
    await pilot.press("d")
    await pilot.pause()
    assert isinstance(app.screen, DashboardScreen)
    return app.screen


async def test_split_quarters_creates_local_nested_grid(make_app):
    app = make_app(config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        await pilot.press("E")  # edit mode
        await pilot.pause()
        await pilot.press("s")  # open split popup
        await pilot.pause()
        assert isinstance(app.screen, SplitSlotPopup)
        await pilot.press("q")  # quarters
        await pilot.pause()

        dashboard = app.dashboards["Main"]
        # The grid itself is untouched — the split is local to the pane.
        assert (dashboard["rows"], dashboard["cols"]) == (2, 2)
        fan = next(s for s in dashboard["slots"] if s["entity_id"] == "switch.fan")
        assert (fan["row"], fan["col"]) == (0, 1)
        assert "row_span" not in fan and "col_span" not in fan

        split = next(s for s in dashboard["slots"] if s["widget_type"] == "split")
        assert (split["row"], split["col"]) == (0, 0)
        assert split["children"] == {"rows": 2, "cols": 2, "slots": []}
        assert (screen.cursor_row, screen.cursor_col) == (0, 0)


async def test_split_vertical_makes_one_row_two_col_children(make_app):
    app = make_app(config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("E")
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("v")  # left/right
        await pilot.pause()

        dashboard = app.dashboards["Main"]
        assert (dashboard["rows"], dashboard["cols"]) == (2, 2)
        split = next(s for s in dashboard["slots"] if s["widget_type"] == "split")
        assert (split["children"]["rows"], split["children"]["cols"]) == (1, 2)


async def test_splitting_occupied_slot_moves_widget_into_first_child(make_app):
    app = make_app(config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        await pilot.press("E")
        await pilot.pause()
        await pilot.press("right")  # onto switch.fan at (0, 1)
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("h")  # top/bottom
        await pilot.pause()

        split = next(s for s in app.dashboards["Main"]["slots"] if s["widget_type"] == "split")
        assert (split["row"], split["col"]) == (0, 1)
        assert split["children"]["slots"] == [{"row": 0, "col": 0, "widget_type": "switch", "entity_id": "switch.fan"}]
        assert screen._cursor_path == [(0, 1)]


async def test_splitting_a_split_is_refused(make_app):
    app = make_app(config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("E")
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()

        await pilot.press("s")  # split the same (now split) slot again
        await pilot.pause()
        assert not isinstance(app.screen, SplitSlotPopup)
        split = next(s for s in app.dashboards["Main"]["slots"] if s["widget_type"] == "split")
        assert split["children"]["rows"] == 2  # unchanged


async def test_unsplit_collapses_single_survivor_back_into_slot(make_app):
    app = make_app(config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("E")
        await pilot.pause()
        await pilot.press("right")  # onto switch.fan
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("q")  # split it: fan moves into child (0, 0)
        await pilot.pause()

        await pilot.press("u")  # unsplit: single occupant collapses back
        await pilot.pause()

        dashboard = app.dashboards["Main"]
        assert all(s["widget_type"] != "split" for s in dashboard["slots"])
        fan = next(s for s in dashboard["slots"] if s["entity_id"] == "switch.fan")
        assert (fan["row"], fan["col"]) == (0, 1)


async def test_unsplit_refused_with_multiple_children(make_app, sample_entities):
    config = {
        **_HA,
        "dashboards": {
            "Main": {
                "rows": 1,
                "cols": 1,
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
                    }
                ],
            }
        },
    }
    app = make_app(entities=sample_entities, config_data=config)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("E")
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()

        split = app.dashboards["Main"]["slots"][0]
        assert split["widget_type"] == "split"
        assert len(split["children"]["slots"]) == 2


async def test_split_is_edit_mode_only(make_app):
    # In Use mode `s` is the app-level saved-graphs key, not split; the split
    # popup must only open from Edit mode.
    app = make_app(config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        assert screen.check_action("split_slot", ()) is False
        await pilot.press("s")
        await pilot.pause()
        assert not isinstance(app.screen, SplitSlotPopup)
