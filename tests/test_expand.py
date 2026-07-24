# hatty — MIT License. See LICENSE file for details.
from textual.coordinate import Coordinate
from textual.widgets import Sparkline

from hatty.ui.controls.control_popup import EntityControlPopup
from hatty.ui.entity_table import EntitiesTable
from hatty.ui.graph.entity_detail import EntityDetailPanel
from tests.conftest import make_config

_NO_LIST_CONFIG = make_config(lists={})

# Alphabetical order with no list:
# Row 0: Fan Switch (switch.fan, off)
# Row 1: Kitchen Light (light.kitchen_light, off)
# Row 2: Living Room Lamp (light.living_room_lamp, on)
# Row 3: Temperature Sensor (sensor.temperature, 21.5)


async def test_e_opens_graph_for_numeric_noncontrollable_entity(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # sensor.temperature
        await pilot.pause()

        await pilot.press("e")
        await pilot.pause()

        panel = app.query_one(EntityDetailPanel)
        assert panel.has_class("-visible")
        assert app._detail_entity_id == "sensor.temperature"
        assert not isinstance(app.screen, EntityControlPopup)


async def test_enter_opens_graph_for_nontogglable_entity(make_app, sample_entities):
    """Issue #150: enter on a sensor falls back to open-controls (graph here),
    not a dead key."""
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # sensor.temperature
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        panel = app.query_one(EntityDetailPanel)
        assert panel.has_class("-visible")
        assert app._detail_entity_id == "sensor.temperature"


async def test_enter_still_toggles_togglable_entity(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)  # switch.fan (off)
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        assert ("switch", "turn_on", {"entity_id": "switch.fan"}) in app.client.call_service_calls
        # A toggle, not a control screen / graph.
        assert not app.query_one(EntityDetailPanel).has_class("-visible")


async def test_e_still_opens_control_screen_for_controllable_entity(make_app, sample_entities):
    from hatty.ui.controls.light_screen import LightControlScreen

    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(1, 0)  # light.kitchen_light
        await pilot.pause()

        await pilot.press("e")
        await pilot.pause()

        assert isinstance(app.screen, LightControlScreen)
        panel = app.query_one(EntityDetailPanel)
        assert not panel.has_class("-visible")


async def test_e_noop_for_noncontrollable_nonnumeric_entity(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)  # switch.fan
        await pilot.pause()

        await pilot.press("e")
        await pilot.pause()

        panel = app.query_one(EntityDetailPanel)
        assert not panel.has_class("-visible")
        assert not isinstance(app.screen, EntityControlPopup)


async def test_check_action_expand_entity_false_for_noncontrollable_nonnumeric(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)  # switch.fan
        await pilot.pause()

        assert app.check_action("expand_entity", ()) is False


async def test_check_action_expand_entity_true_for_numeric_entity(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # sensor.temperature
        await pilot.pause()

        assert app.check_action("expand_entity", ()) is True


async def test_check_action_expand_entity_true_for_controllable_entity(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(1, 0)  # light.kitchen_light
        await pilot.pause()

        assert app.check_action("expand_entity", ()) is True


# Sorted with a second numeric sensor added:
# Row 0: Fan Switch (switch.fan, off)
# Row 1: Humidity Sensor (sensor.humidity, 55.0)
# Row 2: Kitchen Light (light.kitchen_light, off)
# Row 3: Living Room Lamp (light.living_room_lamp, on)
# Row 4: Temperature Sensor (sensor.temperature, 21.5)

_TWO_SENSOR_ENTITIES = [
    {
        "entity_id": "light.living_room_lamp",
        "state": "on",
        "attributes": {"friendly_name": "Living Room Lamp"},
        "last_changed": "",
    },
    {
        "entity_id": "switch.fan",
        "state": "off",
        "attributes": {"friendly_name": "Fan Switch"},
        "last_changed": "",
    },
    {
        "entity_id": "sensor.temperature",
        "state": "21.5",
        "attributes": {"friendly_name": "Temperature Sensor", "unit_of_measurement": "°C"},
        "last_changed": "",
    },
    {
        "entity_id": "light.kitchen_light",
        "state": "off",
        "attributes": {"friendly_name": "Kitchen Light"},
        "last_changed": "",
    },
    {
        "entity_id": "sensor.humidity",
        "state": "55.0",
        "attributes": {"friendly_name": "Humidity Sensor", "unit_of_measurement": "%"},
        "last_changed": "",
    },
]


async def test_cursor_follow_updates_panel_to_new_numeric_entity(make_app):
    app = make_app(entities=_TWO_SENSOR_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(4, 0)  # sensor.temperature
        await pilot.pause()

        await pilot.press("g")
        await pilot.pause()
        assert app._detail_entity_id == "sensor.temperature"

        table.cursor_coordinate = Coordinate(1, 0)  # sensor.humidity
        await pilot.pause()

        assert app._detail_entity_id == "sensor.humidity"
        panel = app.query_one(EntityDetailPanel)
        assert panel.has_class("-visible")
        title = panel.query_one("#detail_title").content
        assert "Humidity Sensor" in str(title)


async def test_cursor_follow_shows_placeholder_for_nongraphable_entity(make_app):
    app = make_app(entities=_TWO_SENSOR_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(4, 0)  # sensor.temperature
        await pilot.pause()

        await pilot.press("g")
        await pilot.pause()

        table.cursor_coordinate = Coordinate(0, 0)  # switch.fan
        await pilot.pause()

        panel = app.query_one(EntityDetailPanel)
        assert panel.has_class("-visible")
        assert app._detail_entity_id == "switch.fan"
        stats = panel.query_one("#detail_stats").content
        assert str(stats) == "No graph data for this entity"


async def test_cursor_follow_inactive_when_panel_not_open(make_app):
    app = make_app(entities=_TWO_SENSOR_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(4, 0)  # sensor.temperature
        await pilot.pause()
        table.cursor_coordinate = Coordinate(1, 0)  # sensor.humidity
        await pilot.pause()

        panel = app.query_one(EntityDetailPanel)
        assert not panel.has_class("-visible")
        assert app._detail_entity_id is None


async def test_cursor_follow_backfills_history_for_new_entity(make_app):
    app = make_app(entities=_TWO_SENSOR_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {
            "sensor.humidity": [
                ("2024-01-01T12:00:00+00:00", 50.0),
                ("2024-01-01T12:01:00+00:00", 52.0),
                ("2024-01-01T12:02:00+00:00", 54.0),
                ("2024-01-01T12:03:00+00:00", 55.0),
            ]
        }

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(4, 0)  # sensor.temperature
        await pilot.pause()

        await pilot.press("g")
        await pilot.pause()

        table.cursor_coordinate = Coordinate(1, 0)  # sensor.humidity
        await pilot.pause()
        await pilot.pause()

        history = list(app.entity_history.get("sensor.humidity", []))
        assert any(v == 55.0 for _, v in history)
        assert len(history) >= 4


async def test_t_cycles_graph_type_label(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {
            "sensor.temperature": [
                ("2024-01-01T12:00:00+00:00", 20.0),
                ("2024-01-01T12:01:00+00:00", 20.5),
                ("2024-01-01T12:02:00+00:00", 21.0),
                ("2024-01-01T12:03:00+00:00", 21.5),
            ]
        }

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # sensor.temperature
        await pilot.pause()

        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        panel = app.query_one(EntityDetailPanel)
        title = panel.query_one("#detail_title")
        assert "[Line]" in str(title.content)

        await pilot.press("t")
        await pilot.pause()
        assert "[Scatter]" in str(title.content)

        await pilot.press("t")
        await pilot.pause()
        assert "[Max]" in str(title.content)

        await pilot.press("t")
        await pilot.pause()
        assert "[Min]" in str(title.content)

        await pilot.press("t")
        await pilot.pause()
        assert "[Mean]" in str(title.content)

        # wraps back to first mode
        await pilot.press("t")
        await pilot.pause()
        assert "[Line]" in str(title.content)


async def test_t_check_action_false_when_panel_closed(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.check_action("cycle_graph_type", ()) is False

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # sensor.temperature
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()

        assert app.check_action("cycle_graph_type", ()) is True


async def test_t_cycles_graph_modes(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # sensor.temperature
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()

        panel = app.query_one(EntityDetailPanel)
        # starts at mode 3 (plotext Line), sparkline hidden
        assert panel._mode_index == 3
        sparkline = panel.query_one("#detail_sparkline", Sparkline)
        assert not sparkline.display

        # cycle through the remaining plotext modes
        await pilot.press("t")
        await pilot.pause()
        assert panel._mode_index == 4  # Scatter

        # wraps into the first sparkline mode (Max), sparkline shown again
        await pilot.press("t")
        await pilot.pause()
        assert panel._mode_index == 0  # sparkline Max
        assert sparkline.display
        assert sparkline.summary_function is max

        # cycle to mode 1 (sparkline Min)
        await pilot.press("t")
        await pilot.pause()
        assert panel._mode_index == 1
        assert sparkline.summary_function is min
