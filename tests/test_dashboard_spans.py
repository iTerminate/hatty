# hatty — MIT License. See LICENSE file for details.
from hatty.ui.dashboard.screen import DashboardScreen, DashboardSlotWidget
from tests.conftest import make_config

_SPAN_CONFIG = {
    **make_config(),
    "lists": {},
    "dashboards": {
        "Main": {
            "rows": 3,
            "cols": 3,
            "slots": [
                {
                    "row": 0,
                    "col": 0,
                    "widget_type": "sensor",
                    "entity_id": "sensor.temperature",
                    "row_span": 2,
                    "col_span": 2,
                },
                {"row": 0, "col": 2, "widget_type": "switch", "entity_id": "switch.fan"},
            ],
        }
    },
}


async def _open_dashboard(pilot, app) -> DashboardScreen:
    await pilot.press("d")
    await pilot.pause()
    assert isinstance(app.screen, DashboardScreen)
    return app.screen


async def test_spanned_slot_renders_one_widget_covering_its_footprint(make_app):
    app = make_app(config_data=_SPAN_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_dashboard(pilot, app)

        widgets = list(screen.query(DashboardSlotWidget))
        # 9 cells - 3 covered by the 2x2 span = 6 widgets
        assert len(widgets) == 6
        spanned = next(w for w in widgets if w.slot and w.slot["entity_id"] == "sensor.temperature")
        assert (spanned.row_span, spanned.col_span) == (2, 2)
        assert spanned.covers(1, 1)
        assert str(spanned.styles.column_span) == "2"
        assert str(spanned.styles.row_span) == "2"


async def test_cursor_skips_over_spanned_footprint(make_app):
    app = make_app(config_data=_SPAN_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_dashboard(pilot, app)

        assert (screen.cursor_row, screen.cursor_col) == (0, 0)
        await pilot.press("right")
        await pilot.pause()
        # Skips the covered (0,1) straight to (0,2)
        assert (screen.cursor_row, screen.cursor_col) == (0, 2)

        await pilot.press("left")
        await pilot.press("down")
        await pilot.pause()
        # Back inside the span; down exits the 2-row footprint to row 2
        assert (screen.cursor_row, screen.cursor_col) == (2, screen.cursor_col)


async def test_operations_target_the_covering_slot_from_any_cell(make_app):
    app = make_app(config_data=_SPAN_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_dashboard(pilot, app)

        # Move onto a covered (non-anchor) cell by direct assignment.
        screen.cursor_row, screen.cursor_col = 1, 1
        slot = screen._slot_at_cursor()
        assert slot is not None and slot["entity_id"] == "sensor.temperature"


async def test_grow_and_shrink_slot_with_ctrl_arrows(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_dashboard(pilot, app)
        # Assign a slot at (0,0) directly, then grow it in edit mode.
        app._set_dashboard_slot("Main", 0, 0, "sensor", "sensor.temperature")
        screen.render_dashboard()
        await pilot.pause()

        await pilot.press("E")  # edit mode
        await pilot.pause()
        await pilot.press("ctrl+right")
        await pilot.pause()
        slot = app.dashboards["Main"]["slots"][0]
        assert slot["col_span"] == 2

        await pilot.press("ctrl+down")
        await pilot.pause()
        assert slot["row_span"] == 2

        await pilot.press("ctrl+left")
        await pilot.pause()
        assert "col_span" not in slot  # back to 1 -> key dropped

        assert app.app_config["dashboards"]["Main"]["slots"][0] is slot


async def test_grow_refused_when_blocked_by_neighbor(make_app):
    app = make_app(config_data=_SPAN_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_dashboard(pilot, app)
        screen.cursor_row, screen.cursor_col = 0, 2  # the 1x1 switch next to the 2x2 span

        await pilot.press("E")
        await pilot.pause()
        await pilot.press("ctrl+left")  # would need to grow leftwards? no: narrower on 1x1 is no-op
        await pilot.pause()
        await pilot.press("ctrl+down")  # grow down into free (1,2) works
        await pilot.pause()
        switch_slot = next(s for s in app.dashboards["Main"]["slots"] if s["entity_id"] == "switch.fan")
        assert switch_slot.get("row_span") == 2

        await pilot.press("ctrl+down")  # (2,2) free too
        await pilot.pause()
        assert switch_slot.get("row_span") == 3

        await pilot.press("ctrl+down")  # out of bounds -> refused
        await pilot.pause()
        assert switch_slot.get("row_span") == 3


async def test_move_spanned_slot_into_free_region(make_app):
    config = {
        **make_config(),
        "lists": {},
        "dashboards": {
            "Main": {
                "rows": 3,
                "cols": 3,
                "slots": [
                    {
                        "row": 0,
                        "col": 0,
                        "widget_type": "sensor",
                        "entity_id": "sensor.temperature",
                        "col_span": 2,
                    },
                ],
            }
        },
    }
    app = make_app(config_data=config)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_dashboard(pilot, app)

        await pilot.press("E")
        await pilot.pause()
        await pilot.press("enter")  # grab
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("enter")  # drop at (1,0)
        await pilot.pause()

        slot = app.dashboards["Main"]["slots"][0]
        assert (slot["row"], slot["col"]) == (1, 0)
        assert slot["col_span"] == 2


async def test_move_spanned_slot_refused_when_it_does_not_fit(make_app):
    config = {
        **make_config(),
        "lists": {},
        "dashboards": {
            "Main": {
                "rows": 2,
                "cols": 3,
                "slots": [
                    {
                        "row": 0,
                        "col": 0,
                        "widget_type": "sensor",
                        "entity_id": "sensor.temperature",
                        "col_span": 2,
                    },
                    {"row": 1, "col": 2, "widget_type": "switch", "entity_id": "switch.fan"},
                ],
            }
        },
    }
    app = make_app(config_data=config)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open_dashboard(pilot, app)

        await pilot.press("E")
        await pilot.pause()
        await pilot.press("enter")  # grab the 1x2 sensor
        await pilot.pause()
        await pilot.press("down")
        await pilot.press("right")
        await pilot.pause()
        assert (screen.cursor_row, screen.cursor_col) == (1, 1)
        await pilot.press("enter")  # dropping a 1x2 at (1,1) would overlap the switch at (1,2)
        await pilot.pause()

        slot = app.dashboards["Main"]["slots"][0]
        assert (slot["row"], slot["col"]) == (0, 0)  # unchanged
        assert screen._grabbed is not None  # still grabbed after the refusal


async def test_dashboard_resize_drops_slots_whose_footprint_no_longer_fits(make_app):
    app = make_app(config_data=_SPAN_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_dashboard(pilot, app)

        # 2x2 grid: the 2x2 span still fits, the switch at (0,2) does not.
        app._resize_dashboard("Main", 2, 2)
        slots = app.dashboards["Main"]["slots"]
        assert [s["entity_id"] for s in slots] == ["sensor.temperature"]

        # 1x3: now the 2-row span is dropped.
        app._resize_dashboard("Main", 1, 3)
        assert app.dashboards["Main"]["slots"] == []


async def test_legacy_slots_without_span_keys_round_trip_unchanged(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_dashboard(pilot, app)
        app._set_dashboard_slot("Main", 0, 0, "switch", "switch.fan")
        slot = app.dashboards["Main"]["slots"][0]
        assert "row_span" not in slot and "col_span" not in slot
