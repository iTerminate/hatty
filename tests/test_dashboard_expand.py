# hatty — MIT License. See LICENSE file for details.
from textual.widgets import Tabs

from hatty.ui.controls.control_popup import EntityControlPopup
from hatty.ui.controls.light_screen import LightControlScreen
from hatty.ui.dashboard.screen import DashboardScreen
from hatty.ui.device_tree_screen import DeviceTreeScreen
from hatty.ui.weather_forecast_screen import WeatherForecastScreen
from tests.conftest import make_config

_HA = make_config(lists={})

_CLIMATE = {
    "entity_id": "climate.thermostat",
    "state": "heat",
    "attributes": {
        "friendly_name": "Hallway Thermostat",
        "current_temperature": 68.0,
        "temperature": 70.0,
        "target_temp_step": 0.5,
        "min_temp": 60.0,
        "max_temp": 80.0,
        "hvac_modes": ["heat", "off"],
    },
    "last_changed": "",
}


_WEATHER = {
    "entity_id": "weather.home",
    "state": "partlycloudy",
    "attributes": {
        "friendly_name": "Home Weather",
        "temperature": 18.4,
        "temperature_unit": "°C",
        "forecast": [
            {"datetime": "2024-01-16T12:00:00+00:00", "condition": "sunny", "temperature": 20.0, "templow": 12.0},
        ],
    },
    "last_changed": "",
}

_WEATHER_NO_FORECAST = {
    "entity_id": "weather.away",
    "state": "cloudy",
    "attributes": {"friendly_name": "Away Weather", "temperature": 10.0, "temperature_unit": "°C"},
    "last_changed": "",
}


def _cfg(slots):
    return {**_HA, "dashboards": {"Main": {"rows": 1, "cols": 1, "slots": slots}}}


async def _open(pilot, app) -> DashboardScreen:
    await pilot.press("d")
    await pilot.pause()
    assert isinstance(app.screen, DashboardScreen)
    return app.screen


async def test_e_on_light_slot_opens_light_control(make_app, sample_entities):
    cfg = _cfg([{"row": 0, "col": 0, "widget_type": "light", "entity_id": "light.kitchen_light"}])
    app = make_app(entities=sample_entities, config_data=cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, LightControlScreen)


async def test_e_on_climate_slot_opens_control_popup(make_app, sample_entities):
    cfg = _cfg([{"row": 0, "col": 0, "widget_type": "thermostat", "entity_id": "climate.thermostat"}])
    app = make_app(entities=[*sample_entities, _CLIMATE], config_data=cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, EntityControlPopup)


async def test_e_on_weather_slot_opens_forecast_screen(make_app, sample_entities):
    # No supported_features on this fixture, so the screen requests "daily"
    # (its no-features guess) from fetch_forecast; the fake has no canned
    # response for it, so the screen falls back to the legacy inline
    # "forecast" attribute (issue #283) — the same content the old
    # attribute-only screen rendered.
    cfg = _cfg([{"row": 0, "col": 0, "widget_type": "weather", "entity_id": "weather.home"}])
    app = make_app(entities=[*sample_entities, _WEATHER], config_data=cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("e")
        await pilot.pause()
        await pilot.pause()  # let the fetch_forecast worker resolve and render
        assert isinstance(app.screen, WeatherForecastScreen)
        assert str(app.screen.query_one("#forecast_title").content) == "Home Weather Forecast"
        # A single supported type (the no-features guess) means no tab bar.
        assert not app.screen.query("#forecast_tabs")
        assert str(app.screen.query_one(".forecast_condition").content) == "Sunny"
        assert str(app.screen.query_one(".forecast_temp").content) == "20.0/12.0°C"

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)


async def test_e_on_weather_slot_without_forecast_shows_placeholder(make_app, sample_entities):
    cfg = _cfg([{"row": 0, "col": 0, "widget_type": "weather", "entity_id": "weather.away"}])
    app = make_app(entities=[*sample_entities, _WEATHER_NO_FORECAST], config_data=cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("e")
        await pilot.pause()
        await pilot.pause()  # let the fetch_forecast worker resolve and render
        assert isinstance(app.screen, WeatherForecastScreen)
        assert str(app.screen.query_one("#forecast_status").content) == "No forecast data available"


async def test_e_on_weather_slot_fetches_forecast_via_service(make_app, sample_entities):
    """A weather entity whose supported_features advertises twice_daily +
    hourly (e.g. a National Weather Service entity — issue #283) fetches via
    weather.get_forecasts rather than the legacy attribute, defaults to the
    first supported type, and `t` cycles to the next one."""
    entity = {
        "entity_id": "weather.nws",
        "state": "sunny",
        "attributes": {
            "friendly_name": "NWS Forecast",
            "temperature_unit": "°F",
            "supported_features": 6,  # twice_daily(4) | hourly(2), no daily
        },
        "last_changed": "",
    }
    cfg = _cfg([{"row": 0, "col": 0, "widget_type": "weather", "entity_id": "weather.nws"}])
    app = make_app(entities=[*sample_entities, entity], config_data=cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        app.client._forecast_data["weather.nws"] = {
            "twice_daily": [{"datetime": "2024-01-15T06:00:00+00:00", "condition": "sunny", "temperature": 75.0}],
            "hourly": [{"datetime": "2024-01-15T12:00:00+00:00", "condition": "cloudy", "temperature": 70.0}],
        }
        await pilot.press("e")
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, WeatherForecastScreen)
        assert app.client.forecast_calls[-1] == ("weather.nws", "twice_daily")
        assert str(app.screen.query_one("#forecast_title").content) == "NWS Forecast Forecast"
        assert app.screen.query_one("#forecast_tabs", Tabs).active == "type_twice_daily"
        assert str(app.screen.query_one(".forecast_condition").content) == "Sunny"

        await pilot.press("t")
        await pilot.pause()
        await pilot.pause()
        assert app.client.forecast_calls[-1] == ("weather.nws", "hourly")
        assert app.screen.query_one("#forecast_tabs", Tabs).active == "type_hourly"
        assert str(app.screen.query_one(".forecast_condition").content) == "Cloudy"


async def test_e_on_panel_opens_control_for_highlighted_row(make_app, sample_entities):
    cfg = _cfg(
        [
            {
                "row": 0,
                "col": 0,
                "widget_type": "panel",
                "entity_id": None,
                "entity_ids": ["switch.fan", "light.kitchen_light"],
            }
        ]
    )
    app = make_app(entities=sample_entities, config_data=cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        panel = screen._content_widget_at_cursor()
        panel.cursor_index = 1  # light.kitchen_light row
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, LightControlScreen)


async def test_e_is_use_mode_only(make_app, sample_entities):
    cfg = _cfg([{"row": 0, "col": 0, "widget_type": "light", "entity_id": "light.kitchen_light"}])
    app = make_app(entities=sample_entities, config_data=cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        await pilot.press("E")  # enter edit mode
        await pilot.pause()
        assert screen.edit_mode
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)  # nothing pushed over it


async def test_shift_d_on_dashboard_opens_device_tree(make_app, sample_entities):
    cfg = _cfg([{"row": 0, "col": 0, "widget_type": "light", "entity_id": "light.kitchen_light"}])
    app = make_app(entities=sample_entities, config_data=cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("D")
        await pilot.pause()
        assert isinstance(app.screen, DeviceTreeScreen)
