# hatty — MIT License. See LICENSE file for details.
from textual.coordinate import Coordinate
from textual.widgets import Button, Input, Select

from hatty.ui.controls.control_popup import EntityControlPopup
from hatty.ui.controls.percentage_slider import PercentageSlider
from hatty.ui.entity_table import EntitiesTable
from hatty.ui.help_popup import HelpPopup
from hatty.ui.weather_forecast_screen import WeatherForecastScreen
from tests.conftest import make_config

_CONTROL_ENTITIES = [
    {
        "entity_id": "climate.thermostat",
        "state": "heat",
        "attributes": {
            "friendly_name": "Thermostat",
            "temperature": 21.0,
            "hvac_modes": ["heat", "off"],
        },
        "last_changed": "",
    },
    {
        "entity_id": "sensor.temperature",
        "state": "21.5",
        "attributes": {"friendly_name": "Temperature Sensor"},
        "last_changed": "",
    },
    {
        "entity_id": "fan.bedroom",
        "state": "on",
        "attributes": {"friendly_name": "Bedroom Fan", "percentage": 40},
        "last_changed": "",
    },
    {
        "entity_id": "cover.garage",
        "state": "open",
        "attributes": {"friendly_name": "Garage Door", "current_position": 60},
        "last_changed": "",
    },
]

_CONFIG = {
    **make_config(),
    "lists": {},
}

# Alphabetical order: Bedroom Fan(0), Garage Door(1), Temperature Sensor(2), Thermostat(3)


async def test_e_opens_forecast_screen_for_weather_on_main_table(make_app):
    """Regression test for issue #283: weather is neither in CONTROLLABLE_DOMAINS
    nor graphable, so HACLI.check_action's expand_entity branch used to hide the
    `e` binding entirely on the main table (it only worked via the dashboard/device
    tree, which gate "e" through their own screen-local check_action)."""
    entities = [
        *_CONTROL_ENTITIES,
        {
            "entity_id": "weather.home",
            "state": "sunny",
            "attributes": {"friendly_name": "Home Weather", "temperature_unit": "°C"},
            "last_changed": "",
        },
    ]
    app = make_app(entities=entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        # Alphabetical: Bedroom Fan(0), Garage Door(1), Home Weather(2), Temperature Sensor(3), Thermostat(4)
        table.cursor_coordinate = Coordinate(2, 0)
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        await pilot.pause()  # let the fetch_forecast worker resolve
        assert isinstance(app.screen, WeatherForecastScreen)

        # Issue #7: WeatherForecastScreen isn't one of HACLI.action_show_help's
        # six known pages, so "?" used to silently show the unrelated Main page.
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpPopup)
        assert app.screen._pages[0][0] == "Weather Forecast"
        assert app.screen._active_index == 0
        descriptions = [desc for _, desc in app.screen._binding_rows]
        assert "Back" in descriptions


async def test_e_opens_control_popup_for_fan_focused_on_first_field(make_app):
    app = make_app(entities=_CONTROL_ENTITIES, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)  # Bedroom Fan
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, EntityControlPopup)
        assert app.focused is popup.query_one("#field_percentage", PercentageSlider)


async def test_e_does_nothing_for_uncontrollable_domain(make_app):
    app = make_app(entities=_CONTROL_ENTITIES, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(2, 0)  # sensor.temperature
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert not isinstance(app.screen, EntityControlPopup)


async def test_fan_speed_slider_dispatches_set_percentage(make_app):
    app = make_app(entities=_CONTROL_ENTITIES, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)  # Bedroom Fan
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        speed_slider = app.screen.query_one("#field_percentage", PercentageSlider)
        assert speed_slider.value == 40
        speed_slider.value = 75
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        calls = app.client.call_service_calls
        assert ("fan", "set_percentage", {"entity_id": "fan.bedroom", "percentage": 75}) in calls


async def test_cover_position_slider_dispatches_set_cover_position(make_app):
    app = make_app(entities=_CONTROL_ENTITIES, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(1, 0)  # Garage Door
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        position_slider = app.screen.query_one("#field_position", PercentageSlider)
        assert position_slider.value == 60
        position_slider.value = 25
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        calls = app.client.call_service_calls
        assert ("cover", "set_cover_position", {"entity_id": "cover.garage", "position": 25}) in calls


async def test_escape_cancels_without_dispatching(make_app):
    app = make_app(entities=_CONTROL_ENTITIES, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)  # Bedroom Fan
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.client.call_service_calls == []


async def test_climate_dispatches_set_temperature_and_hvac_mode(make_app):
    app = make_app(entities=_CONTROL_ENTITIES, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # Thermostat
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        temp_input = app.screen.query_one("#field_temperature", Input)
        temp_input.value = "22.5"
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        calls = app.client.call_service_calls
        assert ("climate", "set_temperature", {"entity_id": "climate.thermostat", "temperature": 22.5}) in calls


def _climate_entity(**extra_attrs) -> dict:
    return {
        "entity_id": "climate.thermostat",
        "state": "heat",
        "attributes": {
            "friendly_name": "Thermostat",
            "temperature": 21.0,
            "hvac_modes": ["heat", "off"],
            **extra_attrs,
        },
        "last_changed": "",
    }


async def test_climate_status_label_shows_heating(make_app):
    app = make_app(entities=[_climate_entity(hvac_action="heating")], config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        status = app.screen.query_one(".climate-status")
        assert "Heating" in str(status.content)
        assert status.has_class("-heating")


async def test_climate_status_label_shows_idle(make_app):
    app = make_app(entities=[_climate_entity(hvac_action="idle")], config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        status = app.screen.query_one(".climate-status")
        assert "Idle" in str(status.content)
        assert not status.has_class("-heating")
        assert not status.has_class("-cooling")


async def test_climate_status_label_hidden_without_hvac_action(make_app):
    app = make_app(entities=[_climate_entity()], config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        assert not app.screen.query(".climate-status")


async def test_climate_fan_mode_field_shown_when_fan_modes_present(make_app):
    entity = _climate_entity(fan_modes=["auto", "low", "high"], fan_mode="auto")
    app = make_app(entities=[entity], config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        select = app.screen.query_one("#field_fan_mode", Select)
        assert select.value == "auto"


async def test_climate_fan_mode_field_absent_without_fan_modes(make_app):
    app = make_app(entities=[_climate_entity()], config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        assert not app.screen.query("#field_fan_mode")


async def test_climate_fan_mode_dispatches_set_fan_mode(make_app):
    entity = _climate_entity(fan_modes=["auto", "low", "high"], fan_mode="auto")
    app = make_app(entities=[entity], config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        app.screen.query_one("#field_fan_mode", Select).value = "high"
        await pilot.pause()
        app.screen.query_one("#btn_save", Button).press()
        await pilot.pause()

        calls = app.client.call_service_calls
        assert ("climate", "set_fan_mode", {"entity_id": "climate.thermostat", "fan_mode": "high"}) in calls


async def test_enter_saves_with_text_input_focused(make_app):
    app = make_app(entities=_CONTROL_ENTITIES, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # Thermostat
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        temp_input = app.screen.query_one("#field_temperature", Input)
        temp_input.focus()
        temp_input.value = "22.5"
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        calls = app.client.call_service_calls
        assert ("climate", "set_temperature", {"entity_id": "climate.thermostat", "temperature": 22.5}) in calls
        assert not isinstance(app.screen, EntityControlPopup)


async def test_up_down_nudges_focused_numeric_input(make_app):
    app = make_app(entities=_CONTROL_ENTITIES, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # Thermostat (numeric temp Input)
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        temp_input = app.screen.query_one("#field_temperature", Input)
        temp_input.focus()
        await pilot.pause()

        await pilot.press("up")
        await pilot.pause()
        assert temp_input.value == "22.0"

        await pilot.press("down")
        await pilot.press("down")
        await pilot.pause()
        assert temp_input.value == "20.0"


async def test_left_right_moves_focus_between_save_and_cancel(make_app):
    app = make_app(entities=_CONTROL_ENTITIES, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)  # Bedroom Fan
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        save_button = app.screen.query_one("#btn_save", Button)
        cancel_button = app.screen.query_one("#btn_cancel", Button)
        save_button.focus()
        await pilot.pause()

        await pilot.press("right")
        await pilot.pause()
        assert app.screen.focused is cancel_button

        await pilot.press("left")
        await pilot.pause()
        assert app.screen.focused is save_button


# ── Fan speed steps ──────────────────────────────────────────────────────────

_THREE_SPEED_FAN = [
    {
        "entity_id": "fan.ceiling",
        "state": "on",
        "attributes": {
            "friendly_name": "Ceiling Fan",
            "percentage": 67,
            "percentage_step": 33.33,
        },
        "last_changed": "",
    }
]


async def test_fan_with_percentage_step_sets_slider_step_and_level_count_label(make_app):
    app = make_app(entities=_THREE_SPEED_FAN, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        popup = app.screen
        assert isinstance(popup, EntityControlPopup)
        slider = popup.query_one("#field_percentage", PercentageSlider)
        assert slider.step == 33
        labels = [lbl.content for lbl in popup.query("Label.field-label")]
        assert any("3 levels" in str(lbl) for lbl in labels)


async def test_fan_without_percentage_step_defaults_to_step_1(make_app):
    app = make_app(entities=_CONTROL_ENTITIES, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)  # Bedroom Fan (no percentage_step)
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        slider = app.screen.query_one("#field_percentage", PercentageSlider)
        assert slider.step == 1


# ── input_number ─────────────────────────────────────────────────────────────

_INPUT_NUMBER_ENTITY = [
    {
        "entity_id": "input_number.target_humidity",
        "state": "45",
        "attributes": {
            "friendly_name": "Target Humidity",
            "min": 20,
            "max": 80,
            "step": 5,
            "unit_of_measurement": "%",
        },
        "last_changed": "",
    },
]


async def test_e_opens_control_popup_for_input_number(make_app):
    app = make_app(entities=_INPUT_NUMBER_ENTITY, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, EntityControlPopup)
        value_input = app.screen.query_one("#field_value", Input)
        assert value_input.value == "45"


async def test_input_number_dispatches_set_value(make_app):
    app = make_app(entities=_INPUT_NUMBER_ENTITY, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        value_input = app.screen.query_one("#field_value", Input)
        value_input.value = "60"
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        calls = app.client.call_service_calls
        assert ("input_number", "set_value", {"entity_id": "input_number.target_humidity", "value": 60.0}) in calls


# ── Lock ─────────────────────────────────────────────────────────────────────

_LOCKED_ENTITY = [
    {
        "entity_id": "lock.front_door",
        "state": "locked",
        "attributes": {"friendly_name": "Front Door Lock"},
        "last_changed": "",
    },
]

_UNLOCKED_ENTITY = [
    {
        "entity_id": "lock.front_door",
        "state": "unlocked",
        "attributes": {"friendly_name": "Front Door Lock"},
        "last_changed": "",
    },
]


async def test_enter_on_lock_row_opens_controls_instead_of_toggling(make_app):
    # Safety guarantee for issue #215: since "lock" is controllable but not
    # togglable, `enter` on the entities table falls back to opening the
    # control popup (existing toggle_or_open_controls behavior, issue #150)
    # rather than dispatching lock/unlock immediately.
    app = make_app(entities=_LOCKED_ENTITY, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.client.call_service_calls == []
        assert isinstance(app.screen, EntityControlPopup)


async def test_locked_lock_disables_lock_button_and_unlocking_dispatches(make_app):
    app = make_app(entities=_LOCKED_ENTITY, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        assert isinstance(app.screen, EntityControlPopup)
        lock_button = app.screen.query_one("#field_lock_lock", Button)
        unlock_button = app.screen.query_one("#field_lock_unlock", Button)
        assert lock_button.disabled
        assert not unlock_button.disabled

        unlock_button.press()
        await pilot.pause()

        calls = app.client.call_service_calls
        assert ("lock", "unlock", {"entity_id": "lock.front_door"}) in calls


async def test_unlocked_lock_disables_unlock_button_and_locking_dispatches(make_app):
    app = make_app(entities=_UNLOCKED_ENTITY, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        lock_button = app.screen.query_one("#field_lock_lock", Button)
        unlock_button = app.screen.query_one("#field_lock_unlock", Button)
        assert not lock_button.disabled
        assert unlock_button.disabled

        lock_button.press()
        await pilot.pause()

        calls = app.client.call_service_calls
        assert ("lock", "lock", {"entity_id": "lock.front_door"}) in calls


# ── Media player ─────────────────────────────────────────────────────────────

_MEDIA_PLAYER_ENTITY = [
    {
        "entity_id": "media_player.living_room",
        "state": "playing",
        "attributes": {"friendly_name": "Living Room Speaker", "supported_features": 16384 | 1},
        "last_changed": "",
    },
]


async def test_enter_on_media_player_row_dispatches_play_pause(make_app):
    # media_player is togglable, but enter's "toggle" is media_play_pause rather
    # than turn_on/turn_off (its state is playing/paused, not on/off).
    app = make_app(entities=_MEDIA_PLAYER_ENTITY, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert ("media_player", "media_play_pause", {"entity_id": "media_player.living_room"}) in (
            app.client.call_service_calls
        )


async def test_input_number_nudge_uses_entity_step(make_app):
    app = make_app(entities=_INPUT_NUMBER_ENTITY, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        value_input = app.screen.query_one("#field_value", Input)
        value_input.focus()
        await pilot.pause()

        await pilot.press("up")
        await pilot.pause()
        assert value_input.value == "50.0"

        await pilot.press("down")
        await pilot.press("down")
        await pilot.pause()
        assert value_input.value == "40.0"
