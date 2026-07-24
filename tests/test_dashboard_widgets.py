# hatty — MIT License. See LICENSE file for details.
from hatty.ui.dashboard.screen import DashboardScreen
from hatty.ui.dashboard.widgets.graph import GraphSlotWidget
from hatty.ui.dashboard.widgets.lock import LockSlotWidget
from hatty.ui.dashboard.widgets.panel import PanelSlotWidget
from hatty.ui.dashboard.widgets.switch import SwitchSlotWidget
from hatty.ui.dashboard.widgets.text import TextSlotWidget
from hatty.ui.dashboard.widgets.thermostat import ThermostatSlotWidget
from hatty.ui.dashboard.widgets.weather import WeatherSlotWidget
from tests.conftest import make_config

_SWITCH_DASHBOARD_CONFIG = {
    **make_config(),
    "lists": {},
    "dashboards": {
        "Main": {
            "rows": 1,
            "cols": 1,
            "slots": [{"row": 0, "col": 0, "widget_type": "switch", "entity_id": "switch.fan"}],
        }
    },
}

_LOCK_ENTITY = {
    "entity_id": "lock.front_door",
    "state": "locked",
    "attributes": {"friendly_name": "Front Door Lock"},
    "last_changed": "2024-01-15T10:30:00.000000+00:00",
}

_LOCK_DASHBOARD_CONFIG = {
    **make_config(),
    "lists": {},
    "dashboards": {
        "Main": {
            "rows": 1,
            "cols": 1,
            "slots": [{"row": 0, "col": 0, "widget_type": "lock", "entity_id": "lock.front_door"}],
        }
    },
}

_SENSOR_DASHBOARD_CONFIG = {
    **make_config(),
    "lists": {},
    "dashboards": {
        "Main": {
            "rows": 1,
            "cols": 1,
            "slots": [{"row": 0, "col": 0, "widget_type": "sensor", "entity_id": "sensor.temperature"}],
        }
    },
}

_GRAPH_DASHBOARD_CONFIG = {
    **make_config(),
    "lists": {},
    "dashboards": {
        "Main": {
            "rows": 1,
            "cols": 1,
            "slots": [{"row": 0, "col": 0, "widget_type": "graph", "entity_id": "sensor.temperature"}],
        }
    },
}

_THERMOSTAT_ENTITY = {
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
    "last_changed": "2024-01-15T10:30:00.000000+00:00",
}

_THERMOSTAT_DASHBOARD_CONFIG = {
    **make_config(),
    "lists": {},
    "dashboards": {
        "Main": {
            "rows": 1,
            "cols": 1,
            "slots": [{"row": 0, "col": 0, "widget_type": "thermostat", "entity_id": "climate.thermostat"}],
        }
    },
}

_WEATHER_ENTITY = {
    "entity_id": "weather.home",
    "state": "partlycloudy",
    "attributes": {
        "friendly_name": "Home Weather",
        "temperature": 18.4,
        "temperature_unit": "°C",
        "humidity": 61,
        "wind_speed": 12,
        "wind_speed_unit": "km/h",
    },
    "last_changed": "2024-01-15T10:30:00.000000+00:00",
}

_WEATHER_DASHBOARD_CONFIG = {
    **make_config(),
    "lists": {},
    "dashboards": {
        "Main": {
            "rows": 1,
            "cols": 1,
            "slots": [{"row": 0, "col": 0, "widget_type": "weather", "entity_id": "weather.home"}],
        }
    },
}

_PANEL_DASHBOARD_CONFIG = {
    **make_config(),
    "lists": {},
    "dashboards": {
        "Main": {
            "rows": 1,
            "cols": 1,
            "slots": [
                {
                    "row": 0,
                    "col": 0,
                    "widget_type": "panel",
                    "entity_id": None,
                    "entity_ids": ["switch.fan", "light.kitchen_light"],
                }
            ],
        }
    },
}


async def test_switch_widget_toggles_and_reflects_confirmed_state(make_app, open_dashboard):
    app = make_app(config_data=_SWITCH_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        assert isinstance(app.screen, DashboardScreen)

        switch_widget = app.screen.query_one(SwitchSlotWidget)
        assert "off" in str(switch_widget.query_one("#slot_state").content)

        await pilot.press("enter")
        await pilot.pause()

        assert app.client.call_service_calls == [("switch", "turn_on", {"entity_id": "switch.fan"})]
        assert app.pending_call_status["switch.fan"] == "pending"
        assert "⏳" in str(switch_widget.query_one("#slot_state").content)

        app.client.inject_state_change(
            {
                "entity_id": "switch.fan",
                "state": "on",
                "attributes": {"friendly_name": "Fan Switch"},
                "last_changed": "2024-01-15T11:00:00.000000+00:00",
            }
        )
        await pilot.pause()

        assert "switch.fan" not in app.pending_call_status
        assert str(switch_widget.query_one("#slot_state").content) == "on"


async def test_switch_widget_toggles_via_enter_key(make_app, open_dashboard):
    app = make_app(config_data=_SWITCH_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        assert isinstance(app.screen, DashboardScreen)

        await pilot.press("enter")
        await pilot.pause()

        assert app.client.call_service_calls == [("switch", "turn_on", {"entity_id": "switch.fan"})]


async def test_lock_widget_renders_state_and_glyph(make_app, open_dashboard):
    app = make_app(entities=[_LOCK_ENTITY], config_data=_LOCK_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        lock_widget = app.screen.query_one(LockSlotWidget)
        assert str(lock_widget.query_one("#slot_name").content) == "Front Door Lock"
        assert str(lock_widget.query_one("#slot_state").content) == "locked"
        assert "🔐" in str(lock_widget.query_one("#slot_glyph").content)
        assert lock_widget.query_one("#slot_state").has_class("-on")

        app.client.inject_state_change({**_LOCK_ENTITY, "state": "unlocked"})
        await pilot.pause()

        assert str(lock_widget.query_one("#slot_state").content) == "unlocked"
        assert "🔓" in str(lock_widget.query_one("#slot_glyph").content)
        assert lock_widget.query_one("#slot_state").has_class("-off")


async def test_lock_widget_enter_does_not_toggle(make_app, open_dashboard):
    # Safety guarantee for issue #215: a lock dashboard slot must never dispatch
    # a service call from a single `enter` keypress, unlike switch/light slots.
    app = make_app(entities=[_LOCK_ENTITY], config_data=_LOCK_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        await pilot.press("enter")
        await pilot.pause()

        assert app.client.call_service_calls == []


async def test_text_widget_updates_live_on_state_change(make_app, open_dashboard):
    app = make_app(config_data=_SENSOR_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        text_widget = app.screen.query_one(TextSlotWidget)
        # The state/unit render as a markup-safe Text (#157); the unit is dimmed via
        # a style span rather than "[dim]…[/dim]" markup, so the plain text is clean.
        content = text_widget.query_one("#slot_state").content
        assert content.plain == "21.5°C"
        assert any("dim" in str(span.style) for span in content.spans)

        app.client.inject_state_change(
            {
                "entity_id": "sensor.temperature",
                "state": "25.0",
                "attributes": {"friendly_name": "Temperature Sensor", "unit_of_measurement": "°C"},
                "last_changed": "2024-01-15T11:00:00.000000+00:00",
            }
        )
        await pilot.pause()

        assert text_widget.query_one("#slot_state").content.plain == "25.0°C"


async def test_widget_escapes_markup_in_ha_name(make_app, open_dashboard):
    # A friendly_name from HA containing Rich markup must render literally, not
    # restyle the UI or crash on a bare "[" (#157).
    app = make_app(config_data=_SWITCH_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        switch_widget = app.screen.query_one(SwitchSlotWidget)

        app.client.inject_state_change(
            {
                "entity_id": "switch.fan",
                "state": "on [danger",
                "attributes": {"friendly_name": "[red]Pwn[/red]"},
                "last_changed": "2024-01-15T11:00:00.000000+00:00",
            }
        )
        await pilot.pause()

        assert switch_widget.query_one("#slot_name").content.plain == "[red]Pwn[/red]"
        assert switch_widget.query_one("#slot_state").content.plain == "on [danger"


async def test_graph_widget_fetches_history_and_appends_live_updates(make_app):
    app = make_app(config_data=_GRAPH_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data["sensor.temperature"] = [
            ("2024-01-15T08:00:00+00:00", 20.0),
            ("2024-01-15T08:01:00+00:00", 21.0),
        ]

        await pilot.press("d")
        await pilot.pause()

        graph_widget = app.screen.query_one(GraphSlotWidget)
        assert [v for _, v in graph_widget._data] == [20.0, 21.0]

        app.client.inject_state_change(
            {
                "entity_id": "sensor.temperature",
                "state": "22.0",
                "attributes": {"friendly_name": "Temperature Sensor", "unit_of_measurement": "°C"},
                "last_changed": "2024-01-15T11:00:00.000000+00:00",
            }
        )
        await pilot.pause()

        assert [v for _, v in graph_widget._data] == [20.0, 21.0, 22.0]


async def test_thermostat_widget_renders_and_updates_live(make_app, open_dashboard):
    app = make_app(entities=[_THERMOSTAT_ENTITY], config_data=_THERMOSTAT_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        thermostat_widget = app.screen.query_one(ThermostatSlotWidget)
        assert str(thermostat_widget.query_one("#slot_name").content) == "Hallway Thermostat"
        assert str(thermostat_widget.query_one("#slot_current").content) == "Now: 68.0"
        assert str(thermostat_widget.query_one("#slot_setpoint").content) == "Set: 70.0"
        assert str(thermostat_widget.query_one("#slot_mode").content) == "heat"

        app.client.inject_state_change(
            {
                "entity_id": "climate.thermostat",
                "state": "off",
                "attributes": {**_THERMOSTAT_ENTITY["attributes"], "current_temperature": 69.0},
                "last_changed": "2024-01-15T11:00:00.000000+00:00",
            }
        )
        await pilot.pause()

        assert str(thermostat_widget.query_one("#slot_current").content) == "Now: 69.0"
        assert str(thermostat_widget.query_one("#slot_mode").content) == "off"


async def test_weather_widget_renders_and_updates_live(make_app, open_dashboard):
    app = make_app(entities=[_WEATHER_ENTITY], config_data=_WEATHER_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        weather_widget = app.screen.query_one(WeatherSlotWidget)
        assert str(weather_widget.query_one("#slot_name").content) == "Home Weather"
        assert str(weather_widget.query_one("#slot_condition").content) == "Partly Cloudy"
        assert str(weather_widget.query_one("#slot_temp").content) == "18.4°C"
        assert str(weather_widget.query_one("#slot_detail").content) == "💧 61%  🌬 12 km/h"
        assert weather_widget.query_one("#weather_art").has_class("-cloudy")

        app.client.inject_state_change(
            {
                "entity_id": "weather.home",
                "state": "rainy",
                "attributes": {**_WEATHER_ENTITY["attributes"], "temperature": 14.0, "humidity": 88},
                "last_changed": "2024-01-15T11:00:00.000000+00:00",
            }
        )
        await pilot.pause()

        assert str(weather_widget.query_one("#slot_condition").content) == "Rainy"
        assert str(weather_widget.query_one("#slot_temp").content) == "14.0°C"
        assert str(weather_widget.query_one("#slot_detail").content) == "💧 88%  🌬 12 km/h"
        assert weather_widget.query_one("#weather_art").has_class("-rainy")


async def test_thermostat_widget_adjusts_setpoint_with_arrow_keys(make_app, open_dashboard):
    app = make_app(entities=[_THERMOSTAT_ENTITY], config_data=_THERMOSTAT_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        thermostat_widget = app.screen.query_one(ThermostatSlotWidget)

        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("up")
        await pilot.pause()

        assert app.client.call_service_calls == [
            ("climate", "set_temperature", {"entity_id": "climate.thermostat", "temperature": 70.5})
        ]
        assert app.pending_call_status["climate.thermostat"] == "pending"
        assert "⏳" in str(thermostat_widget.query_one("#slot_setpoint").content)
        # the grid cursor itself must not have moved (only one slot exists anyway, but
        # confirm the dashboard screen still treats this slot as selected)
        assert app.screen.cursor_row == 0 and app.screen.cursor_col == 0

        await pilot.press("down")
        await pilot.pause()

        # the real entity state hasn't changed yet (no confirmation injected), so this
        # nudges from the same cached 70.0 setpoint rather than compounding on 70.5
        assert app.client.call_service_calls[-1] == (
            "climate",
            "set_temperature",
            {"entity_id": "climate.thermostat", "temperature": 69.5},
        )


async def test_thermostat_widget_shows_gauge_and_action_color(make_app, open_dashboard):
    # Regression test for issue #53: the thermostat widget used to be four plain
    # labels with no visual indication of where current/setpoint sit within the
    # entity's min/max range, or whether it's actively heating/cooling.
    entity_with_action = {
        **_THERMOSTAT_ENTITY,
        "attributes": {**_THERMOSTAT_ENTITY["attributes"], "hvac_action": "heating"},
    }
    app = make_app(entities=[entity_with_action], config_data=_THERMOSTAT_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        thermostat_widget = app.screen.query_one(ThermostatSlotWidget)
        gauge = thermostat_widget.query_one("#thermo_gauge")
        gauge_text = str(gauge.content)
        bar_line, caret_line = gauge_text.split("\n")
        assert "█" in bar_line
        assert "▲" in caret_line
        assert gauge.has_class("-heating")

        current_label = thermostat_widget.query_one("#slot_current")
        assert current_label.has_class("-heating")
        assert "🔥" in str(thermostat_widget.query_one("#slot_mode").content)


async def test_thermostat_widget_shows_idle_action(make_app, open_dashboard):
    # Regression test for issue #211: hvac_action="idle" used to render no
    # icon and just the raw HVAC mode text, making idle indistinguishable
    # from actively heating/cooling.
    entity_idle = {
        **_THERMOSTAT_ENTITY,
        "attributes": {**_THERMOSTAT_ENTITY["attributes"], "hvac_action": "idle"},
    }
    app = make_app(entities=[entity_idle], config_data=_THERMOSTAT_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        thermostat_widget = app.screen.query_one(ThermostatSlotWidget)
        assert str(thermostat_widget.query_one("#slot_mode").content) == "• Idle"


async def test_thermostat_widget_gauge_hidden_without_min_max(make_app, open_dashboard):
    entity_no_range = {
        "entity_id": "climate.thermostat",
        "state": "heat",
        "attributes": {
            "friendly_name": "Hallway Thermostat",
            "current_temperature": 68.0,
            "temperature": 70.0,
        },
        "last_changed": "2024-01-15T10:30:00.000000+00:00",
    }
    app = make_app(entities=[entity_no_range], config_data=_THERMOSTAT_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        thermostat_widget = app.screen.query_one(ThermostatSlotWidget)
        gauge = thermostat_widget.query_one("#thermo_gauge")
        assert str(gauge.content) == ""


async def test_panel_widget_renders_two_column_list(make_app, open_dashboard):
    app = make_app(config_data=_PANEL_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        panel_widget = app.screen.query_one(PanelSlotWidget)
        assert panel_widget.entity_ids == ["switch.fan", "light.kitchen_light"]
        assert "Fan Switch" in str(panel_widget._row_labels[0].content)
        assert "off" in str(panel_widget._row_labels[0].content)
        assert "Kitchen Light" in str(panel_widget._row_labels[1].content)
        assert "-cursor" in panel_widget._row_labels[0].classes


async def test_panel_widget_toggles_selected_row_via_subcursor(make_app, open_dashboard):
    app = make_app(config_data=_PANEL_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.client.call_service_calls == [("switch", "turn_on", {"entity_id": "switch.fan"})]

        await pilot.press("down")
        await pilot.pause()

        panel_widget = app.screen.query_one(PanelSlotWidget)
        assert panel_widget.cursor_index == 1
        # moving the in-panel cursor must not move the dashboard grid cursor
        assert (app.screen.cursor_row, app.screen.cursor_col) == (0, 0)

        await pilot.press("enter")
        await pilot.pause()
        assert app.client.call_service_calls[-1] == ("light", "turn_on", {"entity_id": "light.kitchen_light"})


async def test_panel_widget_updates_one_row_live(make_app, open_dashboard):
    app = make_app(config_data=_PANEL_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        panel_widget = app.screen.query_one(PanelSlotWidget)

        app.client.inject_state_change(
            {
                "entity_id": "switch.fan",
                "state": "on",
                "attributes": {"friendly_name": "Fan Switch"},
                "last_changed": "2024-01-15T11:00:00.000000+00:00",
            }
        )
        await pilot.pause()

        assert "on" in str(panel_widget._row_labels[0].content)
        assert "-on" in panel_widget._row_labels[0].classes
        # the other row is untouched by an unrelated entity's update
        assert "off" in str(panel_widget._row_labels[1].content)


_GAUGE_DASHBOARD_CONFIG = {
    **make_config(),
    "lists": {},
    "dashboards": {
        "Main": {
            "rows": 1,
            "cols": 1,
            "slots": [{"row": 0, "col": 0, "widget_type": "gauge", "entity_id": "sensor.battery"}],
        }
    },
}

_BATTERY_ENTITY = {
    "entity_id": "sensor.battery",
    "state": "17",
    "attributes": {"friendly_name": "Phone Battery", "unit_of_measurement": "%", "device_class": "battery"},
    "last_changed": "2024-01-15T10:30:00.000000+00:00",
}


async def test_gauge_widget_renders_bar_with_threshold_colors(make_app, sample_entities, open_dashboard):
    from hatty.ui.dashboard.widgets.gauge import GaugeSlotWidget

    app = make_app(entities=[*sample_entities, _BATTERY_ENTITY], config_data=_GAUGE_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        gauge_widget = app.screen.query_one(GaugeSlotWidget)
        assert str(gauge_widget.query_one("#slot_value").content) == "17%"
        assert gauge_widget.query_one("#gauge_bar").has_class("-low")
        assert "█" in str(gauge_widget.query_one("#gauge_bar").content)

        app.client.inject_state_change({**_BATTERY_ENTITY, "state": "85"})
        await pilot.pause()
        assert str(gauge_widget.query_one("#slot_value").content) == "85%"
        assert gauge_widget.query_one("#gauge_bar").has_class("-high")


async def test_gauge_widget_honors_slot_bound_overrides(make_app, sample_entities, open_dashboard):
    from hatty.ui.dashboard.widgets.gauge import GaugeSlotWidget

    config = {
        **_GAUGE_DASHBOARD_CONFIG,
        "dashboards": {
            "Main": {
                "rows": 1,
                "cols": 1,
                "slots": [
                    {
                        "row": 0,
                        "col": 0,
                        "widget_type": "gauge",
                        "entity_id": "sensor.battery",
                        "gauge_min": 0,
                        "gauge_max": 20,
                    }
                ],
            }
        },
    }
    app = make_app(entities=[*sample_entities, _BATTERY_ENTITY], config_data=config)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        gauge_widget = app.screen.query_one(GaugeSlotWidget)
        # 17 of [0, 20] is 85% -> -high despite being a low battery percentage
        assert gauge_widget.query_one("#gauge_bar").has_class("-high")


async def test_gauge_widget_shows_dash_for_non_numeric_state(make_app, sample_entities, open_dashboard):
    from hatty.ui.dashboard.widgets.gauge import GaugeSlotWidget

    app = make_app(
        entities=[*sample_entities, {**_BATTERY_ENTITY, "state": "unavailable"}],
        config_data=_GAUGE_DASHBOARD_CONFIG,
    )
    async with app.run_test() as pilot:
        await open_dashboard(pilot)

        gauge_widget = app.screen.query_one(GaugeSlotWidget)
        assert str(gauge_widget.query_one("#slot_value").content) == "—"
        assert "█" not in str(gauge_widget.query_one("#gauge_bar").content)


async def test_assign_gauge_slot_with_bounds_via_popup(make_app, sample_entities):
    app = make_app(entities=[*sample_entities, _BATTERY_ENTITY])
    async with app.run_test() as pilot:
        from textual.widgets import Input, Select

        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("E")  # edit mode
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()

        popup = app.screen
        popup.query_one("#widget_type_select", Select).value = "gauge"
        await pilot.pause()
        popup.query_one("#btn_next_step").press()
        await pilot.pause()

        assert popup.query_one("#gauge_bounds_row").display
        popup.query_one("#gauge_min_input", Input).value = "0"
        popup.query_one("#gauge_max_input", Input).value = "20"

        table = popup.query_one("#entity_picker_table")
        table.jump_cursor_to_row_key("sensor.battery")
        table.focus()
        await pilot.press("enter")
        await pilot.pause()

        slot = app.dashboards["Main"]["slots"][0]
        assert slot["widget_type"] == "gauge"
        assert slot["entity_id"] == "sensor.battery"
        assert slot["gauge_min"] == 0.0
        assert slot["gauge_max"] == 20.0
