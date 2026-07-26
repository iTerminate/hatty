# hatty — MIT License. See LICENSE file for details.
from textual.color import Color
from textual.widgets import Button, Input, Static, TabbedContent, Tabs

from hatty.ui.controls.kelvin_slider import KelvinSlider
from hatty.ui.controls.light_screen import LightControlScreen, hsv_to_rgb
from hatty.ui.controls.percentage_slider import PercentageSlider
from hatty.ui.help_popup import HelpPopup
from tests.conftest import make_config

_CONFIG = {
    **make_config(),
    "lists": {},
}

_WHITE_LIGHT = [
    {
        "entity_id": "light.desk",
        "state": "on",
        "attributes": {
            "friendly_name": "Desk Light",
            "brightness": 128,
            "supported_color_modes": ["color_temp"],
            "color_temp_kelvin": 4200,
            "min_color_temp_kelvin": 2200,
            "max_color_temp_kelvin": 6500,
        },
        "last_changed": "",
    }
]

_COLOR_LIGHT = [
    {
        "entity_id": "light.color_bulb",
        "state": "on",
        "attributes": {
            "friendly_name": "Color Bulb",
            "brightness": 200,
            "supported_color_modes": ["hs"],
            "hs_color": [120.0, 80.0],
        },
        "last_changed": "",
    }
]

_DUAL_MODE_LIGHT = [
    {
        "entity_id": "light.studio",
        "state": "on",
        "attributes": {
            "friendly_name": "Studio Light",
            "brightness": 200,
            "supported_color_modes": ["color_temp", "hs"],
            "color_mode": "color_temp",
            "color_temp_kelvin": 3000,
            "min_color_temp_kelvin": 2000,
            "max_color_temp_kelvin": 6500,
        },
        "last_changed": "",
    }
]

_ONOFF_LIGHT = [
    {
        "entity_id": "light.porch",
        "state": "on",
        "attributes": {"friendly_name": "Porch Light", "supported_color_modes": ["onoff"]},
        "last_changed": "",
    }
]

_MIREDS_LIGHT = [
    {
        "entity_id": "light.legacy",
        "state": "on",
        "attributes": {
            "friendly_name": "Legacy Light",
            "supported_color_modes": ["color_temp"],
            "color_temp": 250,  # mireds → 4000 K
            "min_mireds": 153,
            "max_mireds": 500,
        },
        "last_changed": "",
    }
]

_EFFECTS_LIGHT = [
    {
        "entity_id": "light.disco",
        "state": "on",
        "attributes": {
            "friendly_name": "Disco Light",
            "brightness": 200,
            "effect_list": ["Rainbow", "Strobe", "Solid", "Sparkle"],
            "effect": "Rainbow",
        },
        "last_changed": "",
    }
]

_FULL_LIGHT = [
    {
        "entity_id": "light.everything",
        "state": "on",
        "attributes": {
            "friendly_name": "Everything Light",
            "brightness": 200,
            "supported_color_modes": ["color_temp", "hs"],
            "color_mode": "color_temp",
            "color_temp_kelvin": 3000,
            "min_color_temp_kelvin": 2000,
            "max_color_temp_kelvin": 6500,
            "effect_list": ["Rainbow", "Strobe"],
            "effect": "Rainbow",
        },
        "last_changed": "",
    }
]


async def _open(pilot, app) -> LightControlScreen:
    await pilot.press("e")
    await pilot.pause()
    assert isinstance(app.screen, LightControlScreen)
    return app.screen


async def test_e_opens_light_control_screen_focused_and_prefilled(make_app):
    """e opening the screen (with its initial focus and brightness/kelvin
    prefill for a white-mode light) is read-only, so one boot covers it —
    `_open`'s own assert already confirms the screen opens for any light."""
    app = make_app(entities=_WHITE_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        assert app.focused is screen.query_one("#field_brightness", PercentageSlider)
        assert screen.query_one("#field_brightness", PercentageSlider).value == 50  # round(128/255*100)
        assert len(screen.query("#field_kelvin")) == 1
        assert len(screen.query("#btn_pick_color")) == 0

        slider = screen.query_one("#field_kelvin", KelvinSlider)
        assert slider.value == 4200
        assert slider.min_value == 2200
        assert slider.max_value == 6500


async def test_onoff_light_has_no_brightness_or_tabs(make_app):
    app = make_app(entities=_ONOFF_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        assert len(screen.query("#field_brightness")) == 0
        assert len(screen.query(TabbedContent)) == 0


async def test_color_only_light_has_color_tab_but_no_kelvin(make_app):
    app = make_app(entities=_COLOR_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        assert len(screen.query("#field_kelvin")) == 0
        assert len(screen.query("#btn_pick_color")) == 1
        r, g, b = hsv_to_rgb(120.0, 80.0, 100)
        assert screen._light_color == Color(r, g, b)


async def test_dual_mode_light_has_both_tabs_and_starts_on_white(make_app):
    app = make_app(entities=_DUAL_MODE_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        assert len(screen.query("#field_kelvin")) == 1
        assert len(screen.query("#btn_pick_color")) == 1
        assert screen.query_one(TabbedContent).active == "tab_white"


async def test_kelvin_slider_prefilled_from_mireds(make_app):
    app = make_app(entities=_MIREDS_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        slider = screen.query_one("#field_kelvin", KelvinSlider)
        assert slider.value == round(1_000_000 / 250)  # 4000
        assert slider.min_value == round(1_000_000 / 500)  # 2000
        assert slider.max_value == round(1_000_000 / 153)  # 6536


async def test_brightness_change_live_dispatches_after_debounce(make_app):
    app = make_app(entities=_WHITE_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        slider = screen.query_one("#field_brightness", PercentageSlider)
        slider.focus()
        slider.value = 80
        await pilot.pause(delay=0.5)  # let the 0.3s debounce fire

        calls = [c for c in app.client.call_service_calls if c[1] == "turn_on"]
        assert any(c[2].get("brightness") == round(80 / 100 * 255) for c in calls)


async def test_down_from_brightness_slider_navigates_instead_of_adjusting(make_app):
    app = make_app(entities=_FULL_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        slider = screen.query_one("#field_brightness", PercentageSlider)
        assert app.focused is slider

        await pilot.press("down")
        await pilot.pause()

        assert slider.value == round(200 / 255 * 100)  # unchanged
        assert isinstance(app.focused, Tabs)


async def test_left_right_still_adjust_brightness_slider_value(make_app):
    app = make_app(entities=_FULL_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        slider = screen.query_one("#field_brightness", PercentageSlider)
        start = slider.value

        await pilot.press("right")
        await pilot.pause()

        assert slider.value == start + 1
        assert app.focused is slider  # left/right never move focus off a slider


async def test_effects_option_list_keeps_its_own_up_down_navigation(make_app):
    app = make_app(entities=_FULL_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        tc = screen.query_one(TabbedContent)
        tc.active = "tab_effects"
        options = screen.query_one("#effect_options")
        options.focus()
        await pilot.pause()

        assert options.highlighted == 0
        await pilot.press("down")
        await pilot.pause()

        assert options.highlighted == 1  # cursor moved within the list
        assert app.focused is options  # focus never left the OptionList


async def test_white_preset_key_dispatches_kelvin(make_app):
    app = make_app(entities=_WHITE_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        await pilot.press("1")  # warm preset
        await pilot.pause(delay=0.5)

        assert screen.query_one("#field_kelvin", KelvinSlider).value == 2700
        calls = [c for c in app.client.call_service_calls if c[1] == "turn_on"]
        assert any(c[2].get("color_temp_kelvin") == 2700 for c in calls)
        assert all("kelvin" not in c[2] for c in calls)
        assert all("rgb_color" not in c[2] for c in calls)


async def test_white_preset_button_sets_kelvin(make_app):
    app = make_app(entities=_WHITE_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        screen.query_one("#btn_preset_cool", Button).press()
        await pilot.pause()
        assert screen.query_one("#field_kelvin", KelvinSlider).value == 6500


async def test_color_swatch_sets_color_and_dispatches_rgb(make_app):
    app = make_app(entities=_COLOR_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        screen.query_one("#btn_swatch_blue", Button).press()
        await pilot.pause(delay=0.5)

        assert screen._light_color == Color.parse("#0000ff")
        assert "0000ff" in str(screen.query_one("#color_hex_display", Static).render()).lower()
        calls = [c for c in app.client.call_service_calls if c[1] == "turn_on"]
        assert any(c[2].get("rgb_color") == [0, 0, 255] for c in calls)
        assert all("kelvin" not in c[2] and "color_temp_kelvin" not in c[2] for c in calls)


async def test_color_swatches_have_no_visible_label_but_keep_tooltip(make_app):
    app = make_app(entities=_COLOR_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        swatch = screen.query_one("#btn_swatch_blue", Button)
        assert str(swatch.label) == ""
        assert swatch.tooltip == "Blue"


async def test_effects_filter_and_select_dispatches_effect(make_app):
    app = make_app(entities=_EFFECTS_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        effect_filter = screen.query_one("#effect_filter", Input)
        effect_filter.focus()
        effect_filter.value = "str"
        await pilot.pause()

        option_list = screen.query_one("#effect_options")
        visible = [option_list.get_option_at_index(i).id for i in range(option_list.option_count)]
        assert visible == ["Strobe"]

        await pilot.press("enter")  # submit filter -> focus list
        await pilot.pause()
        await pilot.press("enter")  # select highlighted effect
        await pilot.pause(delay=0.5)

        calls = [c for c in app.client.call_service_calls if c[1] == "turn_on"]
        assert any(c[2].get("effect") == "Strobe" for c in calls)


async def test_space_toggles_power(make_app):
    app = make_app(entities=_WHITE_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)

        await pilot.press("space")
        await pilot.pause()

        assert ("light", "turn_off", {"entity_id": "light.desk"}) in app.client.call_service_calls


async def test_space_types_normally_in_effect_filter(make_app):
    app = make_app(entities=_EFFECTS_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        effect_filter = screen.query_one("#effect_filter", Input)
        effect_filter.focus()
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()

        assert effect_filter.value == " "
        assert all(c[1] != "turn_off" for c in app.client.call_service_calls)


async def test_escape_closes_without_extra_dispatch(make_app):
    app = make_app(entities=_WHITE_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, LightControlScreen)
        assert app.client.call_service_calls == []


async def test_t_cycles_through_tabs_with_wraparound(make_app):
    app = make_app(entities=_FULL_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        tc = screen.query_one(TabbedContent)
        assert tc.active == "tab_white"  # color_mode is color_temp

        await pilot.press("t")
        await pilot.pause()
        assert tc.active == "tab_color"
        await pilot.press("t")
        await pilot.pause()
        assert tc.active == "tab_effects"
        # Landing on Effects must not focus the filter — the next `t` cycles on.
        assert not screen.query_one("#effect_filter", Input).has_focus
        await pilot.press("t")
        await pilot.pause()
        assert tc.active == "tab_white"

        # The old ctrl-chord tab jumps are gone (issue #88).
        await pilot.press("ctrl+f")
        await pilot.pause()
        assert tc.active == "tab_white"


async def test_t_types_in_effect_filter_without_switching_tab(make_app):
    app = make_app(entities=_FULL_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        tc = screen.query_one(TabbedContent)
        tc.active = "tab_effects"
        effect_filter = screen.query_one("#effect_filter", Input)
        effect_filter.focus()
        await pilot.pause()

        await pilot.press("t")
        await pilot.pause()
        assert effect_filter.value == "t"
        assert tc.active == "tab_effects"


async def test_cycle_tab_gated_without_a_second_pane(make_app):
    # A white-only light has a single pane — nothing to cycle through.
    app = make_app(entities=_WHITE_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        assert screen.check_action("cycle_tab", ()) is False
        await pilot.press("t")
        await pilot.pause()
        assert screen.query_one(TabbedContent).active == "tab_white"


async def test_up_down_leave_the_color_swatch_row(make_app):
    app = make_app(entities=_COLOR_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        screen.query_one("#btn_swatch_green", Button).focus()
        await pilot.pause()
        await pilot.press("up")
        await pilot.pause()
        assert screen._enclosing_row(app.focused) is None
        assert isinstance(app.focused, Tabs)

        screen.query_one("#btn_swatch_green", Button).focus()
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        assert app.focused is screen.query_one("#btn_pick_color", Button)


async def test_left_right_cycle_within_swatch_row_and_wrap(make_app):
    app = make_app(entities=_COLOR_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        screen.query_one("#btn_swatch_white", Button).focus()  # last swatch
        await pilot.pause()
        await pilot.press("right")
        await pilot.pause()
        assert app.focused is screen.query_one("#btn_swatch_red", Button)  # wraps to first

        await pilot.press("left")
        await pilot.pause()
        assert app.focused is screen.query_one("#btn_swatch_white", Button)  # back to last


async def test_up_leaves_white_preset_row_to_kelvin_slider(make_app):
    app = make_app(entities=_WHITE_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        screen.query_one("#btn_preset_neutral", Button).focus()
        await pilot.pause()
        await pilot.press("up")
        await pilot.pause()
        assert app.focused is screen.query_one("#field_kelvin", KelvinSlider)


async def test_arrow_keys_switch_tabs_when_tab_bar_focused(make_app):
    app = make_app(entities=_FULL_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        tc = screen.query_one(TabbedContent)
        screen.query_one(Tabs).focus()
        await pilot.pause()

        await pilot.press("right")
        await pilot.pause()
        assert tc.active == "tab_color"
        await pilot.press("left")
        await pilot.pause()
        assert tc.active == "tab_white"


async def test_question_mark_opens_help_on_light_control_screen(make_app):
    """Issue #7: LightControlScreen is a ModalScreen, so the app-level `?`
    binding never reached it — it needed its own question_mark binding."""
    app = make_app(entities=_FULL_LIGHT, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpPopup)
        titles = [title for title, _ in app.screen._pages]
        assert app.screen._pages[app.screen._active_index][0] == "Light Control"
        assert "Light Control" in titles
        descriptions = [desc for _, desc in app.screen._binding_rows]
        assert "Close" in descriptions
        assert "On/Off" in descriptions


async def test_hsv_to_rgb_pure_red():
    assert hsv_to_rgb(0, 100, 100) == (255, 0, 0)


async def test_hsv_to_rgb_pure_green():
    assert hsv_to_rgb(120, 100, 100) == (0, 255, 0)


async def test_hsv_to_rgb_gray():
    assert hsv_to_rgb(0, 0, 50) == (128, 128, 128)
