# hatty — MIT License. See LICENSE file for details.
from hatty.ui.dashboard.widgets.binary_sensor import binary_sensor_icon, binary_sensor_severity
from hatty.ui.dashboard.widgets.visuals import (
    WEATHER_ART,
    build_forecast_columns,
    empty_bar,
    entity_glyph,
    forecast_day_label,
    forecast_temp_range,
    pad_forecast_art,
    render_bar,
    trend_arrow,
    weather_art,
    weather_label,
)
from hatty.ui.graph.plot_time import ts_to_hhmm


def test_render_bar_full_and_empty():
    assert render_bar(100, 0, 100, width=10) == "█" * 10
    assert render_bar(0, 0, 100, width=10) == "█" + "·" * 9


def test_render_bar_clamps_out_of_range():
    assert render_bar(150, 0, 100, width=10) == "█" * 10
    assert render_bar(-5, 0, 100, width=10) == "█" + "·" * 9


def test_empty_bar():
    assert empty_bar(width=5) == "·····"


def test_trend_arrow_directions():
    assert trend_arrow([("t1", 1.0), ("t2", 2.0)]) == "▲"
    assert trend_arrow([("t1", 2.0), ("t2", 1.0)]) == "▼"
    assert trend_arrow([("t1", 1.0), ("t2", 1.0)]) == "→"
    assert trend_arrow([("t1", 1.0)]) == ""
    assert trend_arrow([]) == ""


def _binary(state: str, device_class: str | None = None) -> dict:
    attrs = {"device_class": device_class} if device_class else {}
    return {"entity_id": "binary_sensor.x", "state": state, "attributes": attrs}


def test_binary_severity_alert_classes_color_on_as_error():
    assert binary_sensor_severity(_binary("on", "smoke")) == "-alert"
    assert binary_sensor_severity(_binary("off", "smoke")) == "-off"


def test_binary_severity_benign_classes_color_on_as_success():
    assert binary_sensor_severity(_binary("on", "motion")) == "-on"
    assert binary_sensor_severity(_binary("on")) == "-on"
    assert binary_sensor_severity(_binary("unavailable")) == ""


def test_binary_icon_follows_device_class_and_state():
    assert binary_sensor_icon(_binary("on", "lock")) == "🔓"
    assert binary_sensor_icon(_binary("off", "lock")) == "🔐"
    assert binary_sensor_icon(_binary("on")) == "●"
    assert binary_sensor_icon(_binary("off")) == "○"


def _entity(entity_id: str, device_class: str | None = None) -> dict:
    attrs = {"device_class": device_class} if device_class else {}
    return {"entity_id": entity_id, "state": "on", "attributes": attrs}


def test_entity_glyph_by_domain():
    assert entity_glyph(_entity("light.lamp")) == "💡"
    assert entity_glyph(_entity("lock.front_door")) == "🔐"
    assert entity_glyph(_entity("fan.office")) == "🌀"


def test_entity_glyph_sensor_refines_by_device_class():
    assert entity_glyph(_entity("sensor.temp", "temperature")) == "🌡"
    assert entity_glyph(_entity("sensor.mystery", "unmapped_class")) == "📊"


def test_entity_glyph_unmapped_domain_falls_back():
    assert entity_glyph(_entity("zwave_js.something")) == "◆"


def test_weather_art_known_condition():
    assert weather_art("sunny") == WEATHER_ART["sunny"]
    assert weather_art("rainy") == WEATHER_ART["rainy"]


def test_weather_art_unknown_condition_falls_back_to_cloudy():
    assert weather_art("some-future-condition") == WEATHER_ART["cloudy"]


def test_weather_label_known_condition():
    assert weather_label("partlycloudy") == "Partly Cloudy"
    assert weather_label("clear-night") == "Clear"


def test_weather_label_unknown_condition_title_cases_the_slug():
    assert weather_label("super-storm") == "Super Storm"


def test_pad_forecast_art_appends_blank_lines_to_target_height():
    assert pad_forecast_art("a\nb", height=4) == "a\nb\n\n"


def test_pad_forecast_art_leaves_already_tall_art_unchanged():
    assert pad_forecast_art("a\nb\nc", height=3) == "a\nb\nc"


def test_forecast_day_label_first_entry_is_today_regardless_of_date():
    assert forecast_day_label("2024-01-16T12:00:00+00:00", 0) == "Today"
    assert forecast_day_label(None, 0) == "Today"


def test_forecast_day_label_later_entries_use_weekday():
    assert forecast_day_label("2024-01-16T12:00:00+00:00", 1) == "Tue"


def test_forecast_day_label_falls_back_to_positional_label():
    assert forecast_day_label(None, 2) == "+2"
    assert forecast_day_label("not-a-date", 3) == "+3"


def test_forecast_day_label_hourly_uses_local_time():
    # Compared against ts_to_hhmm directly (rather than a hardcoded "HH:MM")
    # since it converts to the local timezone the test happens to run in.
    ts = "2024-01-15T14:32:00+00:00"
    assert forecast_day_label(ts, 0, "hourly") == ts_to_hhmm(ts)


def test_forecast_day_label_hourly_falls_back_to_positional_label():
    assert forecast_day_label(None, 2, "hourly") == "+2h"


def test_forecast_day_label_twice_daily_adds_day_night():
    assert forecast_day_label("2024-01-16T06:00:00+00:00", 0, "twice_daily", is_daytime=True) == "Tue Day"
    assert forecast_day_label("2024-01-16T18:00:00+00:00", 1, "twice_daily", is_daytime=False) == "Tue Night"


def test_forecast_day_label_twice_daily_falls_back_to_positional_label():
    assert forecast_day_label(None, 2, "twice_daily", is_daytime=True) == "+2 Day"


def test_forecast_temp_range_both_bounds():
    assert forecast_temp_range({"temperature": 20.0, "templow": 12.0}, "°C") == "20.0/12.0°C"


def test_forecast_temp_range_missing_bound_falls_back_to_dash():
    assert forecast_temp_range({"temperature": 20.0}, "°C") == "20.0/—°C"
    assert forecast_temp_range({}, "°C") == "—/—°C"


def test_build_forecast_columns_empty_or_missing_returns_empty_list():
    assert build_forecast_columns(None, "°C") == []
    assert build_forecast_columns([], "°C") == []


def test_build_forecast_columns_maps_fields_and_caps_at_limit():
    forecast = [
        {
            "datetime": "2024-01-15T12:00:00+00:00",
            "condition": "sunny",
            "temperature": 20.0,
            "templow": 12.0,
            "precipitation_probability": 10,
        },
        {
            "datetime": "2024-01-16T12:00:00+00:00",
            "condition": "rainy",
            "temperature": 15.0,
            "templow": 9.0,
            "precipitation": 3,
        },
        {"datetime": "2024-01-17T12:00:00+00:00", "condition": "cloudy", "temperature": 16.0},
    ]
    columns = build_forecast_columns(forecast, "°C", limit=2)

    assert len(columns) == 2
    assert columns[0].label == "Today"
    assert columns[0].art == pad_forecast_art(WEATHER_ART["sunny"])
    assert columns[0].condition_label == "Sunny"
    assert columns[0].css_class == "-sunny"
    assert columns[0].temp_range == "20.0/12.0°C"
    assert columns[0].extra == "☔ 10%"

    assert columns[1].condition_label == "Rainy"
    assert columns[1].extra == "☔ 3mm"


def test_build_forecast_columns_hourly_type_labels_by_time():
    ts = "2024-01-15T14:00:00+00:00"
    forecast = [{"datetime": ts, "condition": "sunny", "temperature": 19.0}]
    columns = build_forecast_columns(forecast, "°C", forecast_type="hourly")
    assert columns[0].label == ts_to_hhmm(ts)


def test_build_forecast_columns_twice_daily_type_labels_with_day_night():
    forecast = [
        {"datetime": "2024-01-15T06:00:00+00:00", "condition": "sunny", "temperature": 19.0, "is_daytime": True},
        {"datetime": "2024-01-15T18:00:00+00:00", "condition": "clear-night", "temperature": 11.0, "is_daytime": False},
    ]
    columns = build_forecast_columns(forecast, "°C", forecast_type="twice_daily")
    assert columns[0].label == "Mon Day"
    assert columns[1].label == "Mon Night"
