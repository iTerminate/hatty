# hatty — MIT License. See LICENSE file for details.
"""G opens the fullscreen graph for any graphable dashboard slot (issue #65).

Previously G only worked on a graph-type slot; on a sensor/thermostat/panel slot
it silently did nothing.
"""

from hatty.ui.dashboard.screen import DashboardScreen
from hatty.ui.graph.preview_screen import GraphPreviewScreen
from tests.conftest import make_config

_ENTITIES = [
    {
        "entity_id": "sensor.temperature",
        "state": "21.5",
        "attributes": {"friendly_name": "Temperature Sensor", "unit_of_measurement": "°C"},
        "last_changed": "2024-01-15T10:30:00.000000+00:00",
    },
    {
        "entity_id": "sensor.humidity",
        "state": "48",
        "attributes": {"friendly_name": "Humidity Sensor", "unit_of_measurement": "%"},
        "last_changed": "2024-01-15T10:30:00.000000+00:00",
    },
    {
        "entity_id": "climate.thermostat",
        "state": "heat",
        "attributes": {
            "friendly_name": "Thermostat",
            "current_temperature": 20.0,
            "temperature": 22.0,
            "min_temp": 7,
            "max_temp": 35,
            "hvac_action": "heating",
        },
        "last_changed": "2024-01-15T10:30:00.000000+00:00",
    },
    {
        "entity_id": "sensor.washer_status",
        "state": "running",  # non-numeric text state -> not graphable
        "attributes": {"friendly_name": "Washer Status"},
        "last_changed": "2024-01-15T10:30:00.000000+00:00",
    },
]


def _config_with_slots(slots):
    return {
        **make_config(),
        "lists": {},
        "dashboards": {"Main": {"rows": 3, "cols": 3, "slots": slots}},
        "default_dashboard": "Main",
    }


async def _open_dashboard(pilot, app):
    await pilot.pause()
    await pilot.press("d")
    await pilot.pause()
    assert isinstance(app.screen, DashboardScreen)


async def test_g_on_sensor_slot_opens_graph(make_app):
    config = _config_with_slots([{"row": 0, "col": 0, "widget_type": "sensor", "entity_id": "sensor.temperature"}])
    app = make_app(entities=_ENTITIES, config_data=config)
    async with app.run_test() as pilot:
        await _open_dashboard(pilot, app)
        await pilot.press("G")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)
        assert app.screen._entity_id == "sensor.temperature"


async def test_g_on_thermostat_slot_opens_climate_graph(make_app):
    config = _config_with_slots([{"row": 0, "col": 0, "widget_type": "thermostat", "entity_id": "climate.thermostat"}])
    app = make_app(entities=_ENTITIES, config_data=config)
    async with app.run_test() as pilot:
        await _open_dashboard(pilot, app)
        await pilot.press("G")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)
        assert app.screen._entity_id == "climate.thermostat"
        assert app.screen._is_climate is True


async def test_g_on_panel_slot_graphs_highlighted_row(make_app):
    config = _config_with_slots(
        [
            {
                "row": 0,
                "col": 0,
                "widget_type": "panel",
                "entity_id": None,
                "entity_ids": ["sensor.temperature", "sensor.humidity"],
            }
        ]
    )
    app = make_app(entities=_ENTITIES, config_data=config)
    async with app.run_test() as pilot:
        await _open_dashboard(pilot, app)
        # Enter the panel's interactive mode and move its internal cursor to row 2.
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)
        assert app.screen._entity_id == "sensor.humidity"


async def test_g_on_nongraphable_slot_notifies_and_does_not_open(make_app):
    config = _config_with_slots([{"row": 0, "col": 0, "widget_type": "sensor", "entity_id": "sensor.washer_status"}])
    app = make_app(entities=_ENTITIES, config_data=config)
    async with app.run_test() as pilot:
        await _open_dashboard(pilot, app)
        await pilot.press("G")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)


async def test_g_on_empty_slot_is_a_noop(make_app):
    config = _config_with_slots([])  # cursor at (0,0) covers no slot
    app = make_app(entities=_ENTITIES, config_data=config)
    async with app.run_test() as pilot:
        await _open_dashboard(pilot, app)
        await pilot.press("G")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)


async def test_escape_from_graph_returns_to_dashboard(make_app):
    config = _config_with_slots([{"row": 0, "col": 0, "widget_type": "sensor", "entity_id": "sensor.temperature"}])
    app = make_app(entities=_ENTITIES, config_data=config)
    async with app.run_test() as pilot:
        await _open_dashboard(pilot, app)
        await pilot.press("G")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
