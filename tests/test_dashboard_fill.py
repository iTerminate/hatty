# hatty — MIT License. See LICENSE file for details.
"""The dashboard fill key (f in edit mode) — quick-fill a pane with several
same-type widgets by auto-splitting it (issue #218)."""

from textual.widgets import Button, ListView, Select

from hatty.ui.dashboard.screen import DashboardScreen
from hatty.ui.dashboard.slot_popup import DashboardSlotPopup


async def _pick_entity(pilot, popup, search_term: str) -> None:
    await pilot.click("#entity_search_input")
    await pilot.press(*search_term)
    await pilot.pause()
    await pilot.press("enter")  # submit search -> focuses entity table
    await pilot.press("enter")  # select highlighted (only) match
    await pilot.pause()
    assert isinstance(popup.app.screen, DashboardSlotPopup)  # stays open, multi-add


def _panel_list_labels(popup) -> list[str]:
    list_view = popup.query_one("#panel_added_list", ListView)
    return [str(item.children[0].content) for item in list_view.children]


async def _fill_two_lights(pilot, popup) -> None:
    popup.query_one("#widget_type_select", Select).value = "light"
    await pilot.pause()
    popup.query_one("#btn_next_step", Button).press()
    await pilot.pause()

    await _pick_entity(pilot, popup, "living")
    await pilot.press("escape")  # clear the filter, stay in the entity step
    await pilot.pause()
    await _pick_entity(pilot, popup, "kitchen")


async def test_fill_creates_split_sized_to_picked_entities(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # enter edit mode
        await pilot.press("f")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)
        assert popup._fill_mode is True

        popup.query_one("#widget_type_select", Select).value = "light"
        await pilot.pause()
        popup.query_one("#btn_next_step", Button).press()
        await pilot.pause()

        await _pick_entity(pilot, popup, "living")
        await pilot.press("escape")  # clear the filter, stay in the entity step
        await pilot.pause()
        await _pick_entity(pilot, popup, "kitchen")

        popup.query_one("#btn_panel_done", Button).press()
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)
        slots = app.dashboards["Main"]["slots"]
        assert len(slots) == 1
        split = slots[0]
        assert (split["row"], split["col"]) == (0, 0)
        assert split["widget_type"] == "split"
        children = split["children"]
        assert (children["rows"], children["cols"]) == (2, 1)
        assert [c["widget_type"] for c in children["slots"]] == ["light", "light"]
        assert [c["entity_id"] for c in children["slots"]] == [
            "light.living_room_lamp",
            "light.kitchen_light",
        ]


async def test_fill_type_choices_exclude_panel(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")
        await pilot.press("f")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)
        assert "panel" not in popup._type_choices()


async def test_fill_replaces_existing_widget_in_pane(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        app.dashboards["Main"]["slots"] = [{"row": 0, "col": 0, "widget_type": "switch", "entity_id": "switch.fan"}]
        app.screen.render_dashboard()
        await pilot.pause()

        await pilot.press("E")
        await pilot.press("f")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)

        popup.query_one("#widget_type_select", Select).value = "light"
        await pilot.pause()
        popup.query_one("#btn_next_step", Button).press()
        await pilot.pause()

        await _pick_entity(pilot, popup, "living")
        popup.query_one("#btn_panel_done", Button).press()
        await pilot.pause()

        slots = app.dashboards["Main"]["slots"]
        assert len(slots) == 1
        assert slots[0]["widget_type"] == "split"
        assert slots[0]["children"]["slots"] == [
            {"row": 0, "col": 0, "widget_type": "light", "entity_id": "light.living_room_lamp"}
        ]


async def test_fill_cancel_leaves_pane_untouched(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")
        await pilot.press("f")
        await pilot.pause()
        assert isinstance(app.screen, DashboardSlotPopup)
        await pilot.press("escape")  # step 1 -> cancels the whole popup
        await pilot.pause()

        assert isinstance(app.screen, DashboardScreen)
        assert app.dashboards["Main"]["slots"] == []


async def test_panel_added_box_reorders_with_shift_down(make_app, open_dashboard):
    """The accumulated-entities scroll box (issue #254) is shared by panel and
    fill; exercising it via fill covers both since they funnel through the same
    _is_multi_add() code path."""
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")
        await pilot.press("f")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)

        await _fill_two_lights(pilot, popup)
        assert popup._panel_entity_ids == ["light.living_room_lamp", "light.kitchen_light"]
        assert _panel_list_labels(popup) == ["Living Room Lamp", "Kitchen Light"]

        list_view = popup.query_one("#panel_added_list", ListView)
        list_view.focus()
        list_view.index = 0
        await pilot.pause()
        await pilot.press("shift+down")
        await pilot.pause()

        assert popup._panel_entity_ids == ["light.kitchen_light", "light.living_room_lamp"]
        assert _panel_list_labels(popup) == ["Kitchen Light", "Living Room Lamp"]
        assert list_view.index == 1

        # Reordering only applies while the box itself is focused — moving focus
        # elsewhere makes shift+up a no-op rather than reordering blind.
        popup.query_one("#entity_search_input").focus()
        await pilot.pause()
        await pilot.press("shift+up")
        await pilot.pause()
        assert popup._panel_entity_ids == ["light.kitchen_light", "light.living_room_lamp"]


async def test_panel_added_box_removes_with_delete(make_app, open_dashboard):
    app = make_app()
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")
        await pilot.press("f")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)

        await _fill_two_lights(pilot, popup)

        list_view = popup.query_one("#panel_added_list", ListView)
        list_view.focus()
        list_view.index = 0
        await pilot.pause()
        await pilot.press("delete")
        await pilot.pause()

        assert popup._panel_entity_ids == ["light.kitchen_light"]
        assert _panel_list_labels(popup) == ["Kitchen Light"]

        await pilot.press("delete")
        await pilot.pause()
        assert popup._panel_entity_ids == []
        assert _panel_list_labels(popup) == ["(none yet)"]
