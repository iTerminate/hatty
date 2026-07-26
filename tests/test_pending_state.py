# hatty — MIT License. See LICENSE file for details.
from textual.coordinate import Coordinate

from hatty.ui.entity_table import EntitiesTable
from tests.conftest import NO_LIST_CONFIG, notified

# Alphabetical order with no list (see tests/test_entity_toggle.py):
# Row 0: Fan Switch (switch.fan, off)


async def test_toggle_marks_entity_pending(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        assert app.pending_call_status["switch.fan"] == "pending"
        assert "⏳" in str(table.get_row_at(0)[1])


async def test_state_confirmation_clears_pending(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()
        assert "switch.fan" in app.pending_call_status

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
        assert str(table.get_row_at(0)[1]) == "on"


async def test_unresponsive_entity_marked_stalled_after_timeout(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    app.PENDING_TIMEOUT_SECONDS = 0.05
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause(0.2)

        assert app.pending_call_status["switch.fan"] == "stalled"
        assert "unresponsive" in str(table.get_row_at(0)[1])
        assert notified(app, title="Unresponsive", message_contains="No response from Home Assistant")


async def test_entity_control_dispatch_also_tracks_pending(make_app):
    entities = [
        {
            "entity_id": "light.lamp",
            "state": "on",
            "attributes": {"friendly_name": "Lamp", "brightness": 128, "color_temp": 300},
            "last_changed": "",
        },
    ]
    app = make_app(entities=entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        from hatty.ui.controls.percentage_slider import PercentageSlider

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()

        brightness_slider = app.screen.query_one("#field_brightness", PercentageSlider)
        brightness_slider.focus()
        brightness_slider.value = 80
        await pilot.pause(delay=0.5)  # light control applies live after a 0.3s debounce

        assert app.pending_call_status["light.lamp"] == "pending"
