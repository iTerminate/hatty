# hatty — MIT License. See LICENSE file for details.
from hatty.ui.graph.entity_detail import EntityDetailPanel
from hatty.ui.graph.preview_screen import GraphPreviewScreen
from tests.conftest import make_config

_CLIMATE_ENTITY = [
    {
        "entity_id": "climate.thermostat",
        "state": "heat",
        "attributes": {
            "friendly_name": "Thermostat",
            "temperature": 21.0,
            "current_temperature": 20.0,
            "hvac_modes": ["heat", "off"],
        },
        "last_changed": "",
    },
]

_CONFIG = {
    **make_config(),
    "lists": {},
}

_CLIMATE_HISTORY = [
    {
        "ts": "2024-01-01T08:00:00+00:00",
        "current_temperature": 18.0,
        "target_temperature": 21.0,
        "hvac_action": "heating",
    },
    {
        "ts": "2024-01-01T09:00:00+00:00",
        "current_temperature": 19.0,
        "target_temperature": 21.0,
        "hvac_action": "heating",
    },
    {
        "ts": "2024-01-01T10:00:00+00:00",
        "current_temperature": 21.0,
        "target_temperature": 21.0,
        "hvac_action": "idle",
    },
    {
        "ts": "2024-01-01T11:00:00+00:00",
        "current_temperature": 23.0,
        "target_temperature": 21.0,
        "hvac_action": "cooling",
    },
]


async def test_g_opens_climate_history_in_detail_panel(make_app):
    app = make_app(entities=_CLIMATE_ENTITY, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._climate_history_data = {"climate.thermostat": _CLIMATE_HISTORY}

        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        panel = app.query_one(EntityDetailPanel)
        assert panel.has_class("-visible")
        assert panel._is_climate is True
        assert len(panel._climate_data) == 4
        assert str(panel.query_one("#detail_title").content) == "Thermostat — heat  [Current/Target]"
        stats = str(panel.query_one("#detail_stats").content)
        assert "current: 23.0" in stats
        assert "target: 21.0" in stats
        assert "red=heating" in stats


async def test_climate_history_empty_shows_no_data_message(make_app):
    app = make_app(entities=_CLIMATE_ENTITY, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._climate_history_data = {"climate.thermostat": []}

        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        panel = app.query_one(EntityDetailPanel)
        assert panel.has_class("-visible")
        assert str(panel.query_one("#detail_stats").content) == "No climate history data available."


async def test_fullscreen_climate_graph_and_left_right_scroll(make_app):
    app = make_app(entities=_CLIMATE_ENTITY, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._climate_history_data = {"climate.thermostat": _CLIMATE_HISTORY}

        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert preview._is_climate is True
        assert len(preview._climate_data) == 4
        assert preview._window_end is None

        older_history = [
            {
                "ts": "2023-12-31T08:00:00+00:00",
                "current_temperature": 15.0,
                "target_temperature": 20.0,
                "hvac_action": "heating",
            },
        ]
        app.client._climate_history_data["climate.thermostat"] = older_history

        await pilot.press("left")
        await pilot.pause()
        assert preview._window_end is not None
        assert preview._climate_data == older_history

        await pilot.press("right")
        await pilot.pause()
        assert preview._window_end is None
        assert preview._climate_data == older_history  # FakeHAClient ignores end/hours


async def test_t_does_not_change_climate_graph_mode(make_app):
    app = make_app(entities=_CLIMATE_ENTITY, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._climate_history_data = {"climate.thermostat": _CLIMATE_HISTORY}

        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        panel = app.query_one(EntityDetailPanel)
        assert panel._is_climate is True
        panel.cycle_graph_type()
        assert panel._is_climate is True  # unaffected, no generic plot modes for climate


async def test_live_state_change_does_not_crash_open_climate_panel(make_app):
    app = make_app(entities=_CLIMATE_ENTITY, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._climate_history_data = {"climate.thermostat": _CLIMATE_HISTORY}

        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        app.client.inject_state_change(
            {
                "entity_id": "climate.thermostat",
                "state": "heat",
                "attributes": {
                    "friendly_name": "Thermostat",
                    "temperature": 22.0,
                    "current_temperature": 20.5,
                    "hvac_modes": ["heat", "off"],
                },
                "last_changed": "",
            }
        )
        await pilot.pause()

        panel = app.query_one(EntityDetailPanel)
        assert panel.has_class("-visible")
        assert panel._is_climate is True


async def test_climate_entity_cannot_be_added_as_comparison(make_app):
    app = make_app(entities=_CLIMATE_ENTITY, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._climate_history_data = {"climate.thermostat": _CLIMATE_HISTORY}

        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        app.action_add_to_graph()
        await pilot.pause()
        assert app._graph_extra_ids == []


async def test_dense_climate_history_is_not_truncated_by_a_fixed_sample_count(make_app):
    # Regression test for issue #32 (climate side): the old fixed maxlen (~30
    # samples/hour) silently dropped everything but the newest points for a
    # thermostat that reports more often than that guess.
    app = make_app(entities=_CLIMATE_ENTITY, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        dense_history = [
            {
                "ts": f"2024-01-01T08:{i // 60:02d}:{i % 60:02d}+00:00",
                "current_temperature": 18.0 + i * 0.01,
                "target_temperature": 21.0,
                "hvac_action": "heating",
            }
            for i in range(130)
        ]
        app.client._climate_history_data = {"climate.thermostat": dense_history}

        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        history = app.climate_history.get("climate.thermostat")
        assert history is not None
        assert len(history) == 130
        assert history[0] == dense_history[0]
        assert history.maxlen is None
