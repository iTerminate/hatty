# hatty — MIT License. See LICENSE file for details.
from textual.widgets import Select

from hatty.ui.dashboard.screen import DashboardScreen
from hatty.ui.dashboard.slot_popup import DashboardSlotPopup
from hatty.ui.dashboard.widgets.fan import FanSlotWidget
from hatty.ui.entity_table import EntitiesTable
from tests.conftest import make_config

_HA = make_config(lists={})

_PCT_FAN = {
    "entity_id": "fan.living_room",
    "state": "on",
    "attributes": {"friendly_name": "Living Room Fan", "percentage": 40, "percentage_step": 20},
    "last_changed": "",
}

_PRESET_FAN = {
    "entity_id": "fan.bedroom",
    "state": "on",
    "attributes": {"friendly_name": "Bedroom Fan", "preset_modes": ["low", "medium", "high"], "preset_mode": "low"},
    "last_changed": "",
}


def _cfg(entity_id):
    return {
        **_HA,
        "dashboards": {
            "Main": {
                "rows": 1,
                "cols": 1,
                "slots": [{"row": 0, "col": 0, "widget_type": "fan", "entity_id": entity_id}],
            }
        },
    }


async def _open(pilot, app) -> DashboardScreen:
    await pilot.press("d")
    await pilot.pause()
    assert isinstance(app.screen, DashboardScreen)
    return app.screen


async def test_fan_tile_renders_name_and_speed(make_app):
    app = make_app(entities=[_PCT_FAN], config_data=_cfg("fan.living_room"))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        fan = screen.query_one(FanSlotWidget)
        assert str(fan.query_one("#slot_name").content) == "Living Room Fan"
        # Percentage shows next to on/off (issue #211) so it survives a pane too
        # small for the bar row; the bar row itself has no duplicate percentage.
        glyph_text = str(fan.query_one("#slot_glyph").content)
        assert "on" in glyph_text
        assert "40%" in glyph_text
        assert "%" not in str(fan.query_one("#fan_speed").content)


async def test_fan_glyph_shows_no_detail_when_off(make_app):
    off_fan = {**_PCT_FAN, "state": "off"}
    app = make_app(entities=[off_fan], config_data=_cfg("fan.living_room"))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        fan = screen.query_one(FanSlotWidget)
        assert str(fan.query_one("#slot_glyph").content) == "❋ off"


async def test_fan_glyph_shows_preset_when_no_percentage(make_app):
    app = make_app(entities=[_PRESET_FAN], config_data=_cfg("fan.bedroom"))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        fan = screen.query_one(FanSlotWidget)
        assert str(fan.query_one("#slot_glyph").content) == "❋ on   low"


async def test_up_increases_percentage_in_widget_mode(make_app):
    app = make_app(entities=[_PCT_FAN], config_data=_cfg("fan.living_room"))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("enter")  # enter widget mode
        await pilot.press("up")
        await pilot.pause()
        call = ("fan", "set_percentage", {"entity_id": "fan.living_room", "percentage": 60})
        assert call in app.client.call_service_calls


async def test_down_decreases_percentage_in_widget_mode(make_app):
    app = make_app(entities=[_PCT_FAN], config_data=_cfg("fan.living_room"))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("enter")
        await pilot.press("down")
        await pilot.pause()
        call = ("fan", "set_percentage", {"entity_id": "fan.living_room", "percentage": 20})
        assert call in app.client.call_service_calls


async def test_up_cycles_preset_when_no_percentage(make_app):
    app = make_app(entities=[_PRESET_FAN], config_data=_cfg("fan.bedroom"))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        assert "low" in str(screen.query_one(FanSlotWidget).query_one("#fan_speed").content)
        await pilot.press("enter")
        await pilot.press("up")
        await pilot.pause()
        call = ("fan", "set_preset_mode", {"entity_id": "fan.bedroom", "preset_mode": "medium"})
        assert call in app.client.call_service_calls


async def test_slot_popup_fan_picker_lists_only_fan_entities(make_app, sample_entities, open_dashboard):
    app = make_app(entities=[*sample_entities, _PCT_FAN, _PRESET_FAN])
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # edit mode
        await pilot.press("a")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)

        popup.query_one("#widget_type_select", Select).value = "fan"
        await pilot.pause()
        popup.query_one("#btn_next_step").press()
        await pilot.pause()

        table = popup.query_one("#entity_picker_table", EntitiesTable)
        row_keys = {key.value for key in table.rows}
        assert row_keys == {"", "fan.living_room", "fan.bedroom"}


async def test_enter_in_widget_mode_toggles_power(make_app):
    app = make_app(entities=[_PCT_FAN], config_data=_cfg("fan.living_room"))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("enter")  # enter widget mode
        await pilot.press("enter")  # toggle power (fan is on -> turn_off)
        await pilot.pause()
        call = ("fan", "turn_off", {"entity_id": "fan.living_room"})
        assert call in app.client.call_service_calls
