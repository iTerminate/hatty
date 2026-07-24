# hatty — MIT License. See LICENSE file for details.
from hatty.const import supported_forecast_types, weather_supports


def test_weather_supports_checks_bitmask_flag():
    assert weather_supports(1, "forecast_daily") is True
    assert weather_supports(1, "forecast_hourly") is False
    assert weather_supports(None, "forecast_daily") is False


def test_supported_forecast_types_decodes_bitmask_in_preferred_order():
    assert supported_forecast_types(7) == ["daily", "twice_daily", "hourly"]
    assert supported_forecast_types(1) == ["daily"]
    # National Weather Service style: twice_daily + hourly, no daily (issue #283).
    assert supported_forecast_types(6) == ["twice_daily", "hourly"]


def test_supported_forecast_types_empty_for_no_features():
    assert supported_forecast_types(None) == []
    assert supported_forecast_types(0) == []
