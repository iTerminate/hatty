# hatty — MIT License. See LICENSE file for details.
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from textual.coordinate import Coordinate
from textual.widgets import Label

from hatty.ui.entity_table import EntitiesTable
from hatty.ui.graph.entity_detail import EntityDetailPanel
from hatty.ui.graph.preview_screen import GraphPreviewScreen
from tests.conftest import make_config


def _label_text(widget) -> str:
    return str(widget._Static__content)


_NO_LIST_CONFIG = make_config(lists={})

# Alphabetical order with no list:
# Row 0: Fan Switch (switch.fan, off)
# Row 1: Kitchen Light (light.kitchen_light, off)
# Row 2: Living Room Lamp (light.living_room_lamp, on)
# Row 3: Temperature Sensor (sensor.temperature, 21.5)

_TWO_SENSOR_ENTITIES = [
    {
        "entity_id": "sensor.temperature",
        "state": "21.5",
        "attributes": {"friendly_name": "Temperature Sensor", "unit_of_measurement": "°C"},
        "last_changed": "2024-01-15T10:30:00.000000+00:00",
    },
    {
        "entity_id": "sensor.humidity",
        "state": "40",
        "attributes": {"friendly_name": "Humidity Sensor", "unit_of_measurement": "%"},
        "last_changed": "2024-01-15T10:30:00.000000+00:00",
    },
]


async def test_g_opens_detail_panel_for_numeric_entity(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()

        panel = app.query_one(EntityDetailPanel)
        assert not panel.has_class("-visible")

        await pilot.press("g")
        await pilot.pause()

        assert panel.has_class("-visible")
        assert app._detail_entity_id == "sensor.temperature"


async def test_g_hides_panel_when_pressed_again(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()

        await pilot.press("g")
        await pilot.pause()
        panel = app.query_one(EntityDetailPanel)
        assert panel.has_class("-visible")

        await pilot.press("g")
        await pilot.pause()
        assert not panel.has_class("-visible")
        assert app._detail_entity_id is None


async def test_g_shows_warning_for_non_numeric_entity(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(0, 0)
        await pilot.pause()

        panel = app.query_one(EntityDetailPanel)
        await pilot.press("g")
        await pilot.pause()

        assert not panel.has_class("-visible")


async def test_g_closes_panel_from_a_non_graphable_row(make_app, sample_entities):
    # Regression (#188): once the panel is open, moving the cursor onto a
    # non-graphable entity must not disable the g binding — g still closes it.
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # sensor.temperature (graphable)
        await pilot.pause()

        await pilot.press("g")
        await pilot.pause()
        panel = app.query_one(EntityDetailPanel)
        assert panel.has_class("-visible")

        table.cursor_coordinate = Coordinate(0, 0)  # switch.fan (non-graphable)
        await pilot.pause()
        assert app.check_action("toggle_graph", ()) is True

        await pilot.press("g")
        await pilot.pause()
        assert not panel.has_class("-visible")


async def test_g_uses_prefetched_history(make_app, sample_entities):
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
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()

        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        history = list(app.entity_history.get("sensor.temperature", []))
        assert any(v == 21.5 for _, v in history)
        assert len(history) >= 4


async def test_repeated_g_open_close_does_not_duplicate_history(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        history_data = [
            ("2024-01-01T12:00:00+00:00", 20.0),
            ("2024-01-01T12:01:00+00:00", 20.5),
            ("2024-01-01T12:02:00+00:00", 21.0),
            ("2024-01-01T12:03:00+00:00", 21.5),
        ]
        app.client._history_data = {"sensor.temperature": history_data}

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()

        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        history = list(app.entity_history.get("sensor.temperature", []))
        timestamps = [ts for ts, _ in history]
        assert len(timestamps) == len(set(timestamps)), "history contains duplicate timestamps"
        assert all(any(ts == ht and val == hv for ts, val in history) for ht, hv in history_data)


async def test_fullscreen_graph_updates_as_live_state_changes_stream_in(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {
            "sensor.temperature": [
                ("2024-01-01T12:00:00+00:00", 20.0),
                ("2024-01-01T12:01:00+00:00", 21.0),
            ]
        }

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        await pilot.press("G")
        await pilot.pause()
        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert [v for _, v in preview._data] == [20.0, 21.0]

        app.client.inject_state_change(
            {
                "entity_id": "sensor.temperature",
                "state": "22.5",
                "attributes": {"friendly_name": "Temperature Sensor", "unit_of_measurement": "°C"},
                "last_changed": "2024-01-01T12:02:00.000000+00:00",
            }
        )
        await pilot.pause()

        assert [v for _, v in preview._data] == [20.0, 21.0, 22.5]


async def test_initial_state_snapshot_does_not_seed_entity_history(make_app, sample_entities):
    # sensor.temperature's last_changed in sample_entities is 2024-01-15, far outside
    # any history window a real fetch would return. If the initial get_states snapshot
    # seeded entity_history with that point, a later duration change could pull it back
    # in as a "live update" and skew the graph's time axis (issue #24).
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.entity_history == {}


async def test_duration_change_does_not_reintroduce_stale_initial_state_point(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {
            "sensor.temperature": [
                ("2024-01-01T12:00:00+00:00", 20.0),
                ("2024-01-01T12:01:00+00:00", 21.0),
            ]
        }

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        app.app_config["graph_hours"] = 1
        app._on_graph_hours_changed()
        await pilot.pause()
        await pilot.pause()

        history = list(app.entity_history.get("sensor.temperature", []))
        assert all(v in (20.0, 21.0) for _, v in history)


async def test_left_right_scroll_fullscreen_graph_through_history(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()

        live_data = [
            ("2024-01-01T12:00:00+00:00", 20.0),
            ("2024-01-01T12:01:00+00:00", 21.0),
        ]
        older_data = [
            ("2024-01-01T08:00:00+00:00", 10.0),
            ("2024-01-01T08:01:00+00:00", 11.0),
        ]
        calls = []

        async def fake_fetch_history(entity_id, hours=4, end=None):
            calls.append(end)
            if end is None:
                return live_data
            return older_data

        app.client.fetch_history = fake_fetch_history

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert [v for _, v in preview._data] == [20.0, 21.0]
        assert preview._window_end is None

        await pilot.press("left")
        await pilot.pause()
        assert preview._window_end is not None
        assert [v for _, v in preview._data] == [10.0, 11.0]

        await pilot.press("right")
        await pilot.pause()
        assert preview._window_end is None
        assert [v for _, v in preview._data] == [20.0, 21.0]


async def test_shift_left_right_page_by_a_larger_stride(make_app, sample_entities):
    # Regression test for issue #51: left/right only ever paged by one
    # graph_hours window per press, making it slow to travel far back in
    # history. shift+left/shift+right should page by a larger multiple.
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()

        live_data = [
            ("2024-01-01T12:00:00+00:00", 20.0),
            ("2024-01-01T12:01:00+00:00", 21.0),
        ]
        far_data = [
            ("2023-12-25T08:00:00+00:00", 5.0),
        ]
        ends_requested = []

        async def fake_fetch_history(entity_id, hours=4, end=None):
            ends_requested.append(end)
            if end is None:
                return live_data
            return far_data

        app.client.fetch_history = fake_fetch_history

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert preview._window_end is None

        before_fast = preview._live_anchor or datetime.now(timezone.utc)
        await pilot.press("shift+left")
        await pilot.pause()

        assert preview._window_end is not None
        assert [v for _, v in preview._data] == [5.0]
        stride = before_fast - preview._window_end
        assert stride.total_seconds() >= 4 * 3600 * 6 * 0.99  # ~6x the 4h default window

        await pilot.press("shift+right")
        await pilot.pause()
        assert preview._window_end is None
        assert [v for _, v in preview._data] == [20.0, 21.0]


async def test_right_at_live_edge_is_a_no_op(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {
            "sensor.temperature": [
                ("2024-01-01T12:00:00+00:00", 20.0),
            ]
        }

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        await pilot.press("right")
        await pilot.pause()
        assert preview._window_end is None
        assert [v for _, v in preview._data] == [20.0]


async def test_dense_history_is_not_truncated_by_a_fixed_sample_count(make_app, sample_entities):
    # Regression test for issue #32: a fixed maxlen guessing ~30 samples/hour used
    # to silently drop everything but the newest ~120 points, collapsing a
    # multi-hour window down to whatever a chatty entity's real sample rate
    # happened to span (reported as "only the last 10-20 minutes").
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        dense_history = [(f"2024-01-01T08:{i // 60:02d}:{i % 60:02d}+00:00", float(i)) for i in range(130)]
        app.client._history_data = {"sensor.temperature": dense_history}

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        history = list(app.entity_history.get("sensor.temperature", []))
        assert len(history) == 130
        assert history[0] == dense_history[0]
        assert app.entity_history["sensor.temperature"].maxlen is None


async def test_live_updates_trim_only_points_outside_the_selected_window(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.app_config["graph_hours"] = 1
        app.client._history_data = {"sensor.temperature": [("2024-01-01T08:00:00+00:00", 20.0)]}

        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        app.client.inject_state_change(
            {
                "entity_id": "sensor.temperature",
                "state": "21.0",
                "attributes": {"friendly_name": "Temperature Sensor", "unit_of_measurement": "°C"},
                "last_changed": "2024-01-01T08:30:00.000000+00:00",
            }
        )
        await pilot.pause()
        history = list(app.entity_history.get("sensor.temperature", []))
        assert [v for _, v in history] == [20.0, 21.0], "point within the 1h window should be kept"

        app.client.inject_state_change(
            {
                "entity_id": "sensor.temperature",
                "state": "22.0",
                "attributes": {"friendly_name": "Temperature Sensor", "unit_of_measurement": "°C"},
                "last_changed": "2024-01-01T09:30:00.000000+00:00",
            }
        )
        await pilot.pause()
        history = list(app.entity_history.get("sensor.temperature", []))
        assert [v for _, v in history] == [21.0, 22.0], "08:00 point is now >1h older than the newest point"


async def test_stray_list_bindings_disabled_on_fullscreen_graph(make_app, sample_entities):
    # Regression test: "/", "e", "space" (and other entity-table-only actions)
    # are global App bindings with no local shadow on GraphPreviewScreen, so
    # they used to stay live (and shown in the footer) while viewing a graph,
    # firing against the hidden entity table behind it.
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)

        for action in (
            "toggle_search",
            "expand_entity",
            "toggle_list_membership",
            "rename_entity",
            "show_column_config",
            "toggle_activity_log",
            "toggle_device_log",
            "toggle_graph",
            "add_to_graph",
        ):
            assert app.check_action(action, ()) is False, action

        # Still-legitimate global actions remain enabled.
        assert app.check_action("show_saved_graphs_popup", ()) is True
        assert app.check_action("quit", ()) is True

        shown_keys = {active.binding.key for active in app.screen.active_bindings.values() if active.binding.show}
        assert "/" not in shown_keys
        assert "e" not in shown_keys
        assert "space" not in shown_keys

        # The keys themselves no longer trigger the underlying list actions.
        await pilot.press("space")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)


async def test_live_graph_shows_time_range_in_title(make_app, sample_entities):
    # Regression test: the live/default view showed no time-range indication
    # at all (only scrolled-back windows got a suffix).
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {
            "sensor.temperature": [
                ("2024-01-01T12:00:00+00:00", 20.0),
                ("2024-01-01T13:00:00+00:00", 21.0),
            ]
        }
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        assert isinstance(app.screen, GraphPreviewScreen)
        title = _label_text(app.screen.query_one("#preview_title", Label))
        assert "Jan 01" in title


async def test_multi_day_window_uses_dated_tick_labels(make_app, sample_entities):
    # Regression test: tick labels only ever showed HH:MM, so a multi-day
    # window (e.g. the 1 week graph_hours preset) had indistinguishable ticks.
    config_data = {**_NO_LIST_CONFIG, "graph_hours": 168}
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {
            "sensor.temperature": [
                ("2024-01-01T00:00:00+00:00", 20.0),
                ("2024-01-05T00:00:00+00:00", 25.0),
            ]
        }
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        plot = preview.query_one("#preview_plot")
        with patch.object(plot.plt, "xticks") as xticks:
            preview._update_display(app.find_entity("sensor.temperature"))
        tick_labels = xticks.call_args.args[1]
        assert any("Jan" in label for label in tick_labels)


async def test_enter_toggles_cursor_mode_and_left_right_move_cursor(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {
            "sensor.temperature": [
                ("2024-01-01T12:00:00+00:00", 20.0),
                ("2024-01-01T12:01:00+00:00", 21.0),
                ("2024-01-01T12:02:00+00:00", 22.0),
            ]
        }
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert preview._cursor_mode is False

        await pilot.press("enter")
        await pilot.pause()
        assert preview._cursor_mode is True
        assert preview._cursor_index == 2  # starts at the newest point

        stats = _label_text(preview.query_one("#preview_stats", Label))
        assert "22.0" in stats

        await pilot.press("left")
        await pilot.pause()
        assert preview._cursor_index == 1
        stats = _label_text(preview.query_one("#preview_stats", Label))
        assert "21.0" in stats

        # Clamped at the start.
        await pilot.press("left")
        await pilot.press("left")
        await pilot.press("left")
        await pilot.pause()
        assert preview._cursor_index == 0

        await pilot.press("right")
        await pilot.pause()
        assert preview._cursor_index == 1


async def test_cursor_mode_shows_values_for_all_compared_entities(make_app):
    app = make_app(entities=_TWO_SENSOR_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {
            "sensor.temperature": [
                ("2024-01-01T12:00:00+00:00", 20.0),
                ("2024-01-01T12:01:00+00:00", 21.0),
            ],
            "sensor.humidity": [
                ("2024-01-01T12:00:00+00:00", 40.0),
                ("2024-01-01T12:01:00+00:00", 45.0),
            ],
        }
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(1, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        app._graph_extra_ids = ["sensor.humidity"]
        await pilot.press("escape")
        await pilot.pause()
        table.cursor_coordinate = Coordinate(1, 0)
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert preview._entity_ids == ["sensor.temperature", "sensor.humidity"]

        await pilot.press("enter")
        await pilot.pause()
        stats = _label_text(preview.query_one("#preview_stats", Label))
        assert "21.0" in stats
        assert "45.0" in stats


async def test_multi_entity_stats_follow_the_active_entity(make_app):
    # Regression test for issue #52: the non-cursor stats line always summarized
    # the primary (first) entity's data, even after `tab` switched the active
    # entity to a comparison line with completely different values/units.
    app = make_app(entities=_TWO_SENSOR_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {
            "sensor.temperature": [
                ("2024-01-01T12:00:00+00:00", 10.0),
                ("2024-01-01T12:01:00+00:00", 20.0),
            ],
            "sensor.humidity": [
                ("2024-01-01T12:00:00+00:00", 30.0),
                ("2024-01-01T12:01:00+00:00", 40.0),
            ],
        }
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(1, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        app._graph_extra_ids = ["sensor.humidity"]
        await pilot.press("escape")
        await pilot.pause()
        table.cursor_coordinate = Coordinate(1, 0)
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert preview._entity_ids == ["sensor.temperature", "sensor.humidity"]

        stats = _label_text(preview.query_one("#preview_stats", Label))
        assert "min: 10.0" in stats
        assert "max: 20.0" in stats
        assert "Temperature Sensor" in stats

        await pilot.press("tab")
        await pilot.pause()
        stats = _label_text(preview.query_one("#preview_stats", Label))
        assert "min: 30.0" in stats
        assert "max: 40.0" in stats
        assert "Humidity Sensor" in stats


async def test_zoom_out_keeps_a_line_whose_wide_fetch_returns_empty(make_app):
    # Regression test for issue #179: zooming a comparison graph out past the
    # graph_hours store re-fetches each entity over the wider window via REST.
    # HAClient reports a failed/empty fetch as None, and the screen used to store
    # `values or []`, silently blanking that entity's line. It must instead fall
    # back to the in-memory history buffer so the line stays visible.
    app = make_app(entities=_TWO_SENSOR_ENTITIES, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        now = datetime.now(timezone.utc)
        recent = [
            ((now - timedelta(minutes=2)).isoformat(), 40.0),
            ((now - timedelta(minutes=1)).isoformat(), 45.0),
        ]
        app.client._history_data = {
            "sensor.temperature": recent,
            "sensor.humidity": recent,
        }
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(1, 0)  # Temperature Sensor (primary)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        app._graph_extra_ids = ["sensor.humidity"]
        await pilot.press("escape")
        await pilot.pause()
        table.cursor_coordinate = Coordinate(1, 0)
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        assert preview._entity_ids == ["sensor.temperature", "sensor.humidity"]
        assert preview._all_data["sensor.humidity"]  # present at the live view

        # The wide-window fetch now returns None for humidity only (a slow/failed
        # REST call), while temperature still resolves.
        async def flaky_fetch(entity_id, hours=4, end=None):
            if entity_id == "sensor.humidity":
                return None
            return recent

        app.client.fetch_history = flaky_fetch

        await pilot.press("minus")  # zoom out to 8h > graph_hours=4 -> wide fetch branch
        await pilot.pause()
        await pilot.pause()

        assert preview._local_hours == 8
        assert preview._all_data["sensor.temperature"], "temperature line vanished on zoom-out"
        assert preview._all_data["sensor.humidity"], "humidity line vanished on zoom-out (#179)"


async def test_escape_exits_cursor_mode_before_dismissing_screen(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()

        preview = app.screen
        assert isinstance(preview, GraphPreviewScreen)
        await pilot.press("enter")
        await pilot.pause()
        assert preview._cursor_mode is True

        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is preview
        assert preview._cursor_mode is False

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, GraphPreviewScreen)


async def _open_preview_on_temperature(pilot, app) -> GraphPreviewScreen:
    table = app.query_one(EntitiesTable)
    table.cursor_coordinate = Coordinate(3, 0)
    await pilot.pause()
    await pilot.press("g")
    await pilot.pause()
    await pilot.pause()
    await pilot.press("G")
    await pilot.pause()
    assert isinstance(app.screen, GraphPreviewScreen)
    return app.screen


async def test_left_pages_by_half_a_window(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("left")
        await pilot.pause()
        assert preview._window_end is not None
        stride = (preview._live_anchor - preview._window_end).total_seconds()
        assert abs(stride - 2 * 3600) < 5  # half the 4h default window


async def test_zoom_in_halves_window_without_touching_global_config(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        hours_requested = []
        original_fetch = app.client.fetch_history

        async def spying_fetch(entity_id, hours=4, end=None):
            hours_requested.append(hours)
            return await original_fetch(entity_id, hours=hours, end=end)

        app.client.fetch_history = spying_fetch
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("plus")
        await pilot.pause()
        assert preview._window_hours() == 2
        assert preview._window_end is None  # zooming while live stays anchored to "now" (#138)
        # Zoom-in reads the graph_hours store and slices, so no new hours=2 fetch is issued.
        assert 2 not in hours_requested
        assert app.app_config.get("graph_hours", 4) == 4

        await pilot.press("minus")
        await pilot.press("minus")
        await pilot.pause()
        assert preview._window_hours() == 8
        assert preview._window_end is None  # still live at the wider window
        # 8h exceeds the 4h store, so it's sourced by a one-shot windowed fetch.
        assert 8 in hours_requested


async def test_home_snaps_back_to_live_and_clears_zoom(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("plus")
        await pilot.pause()
        await pilot.press("left")
        await pilot.press("left")
        await pilot.pause()
        assert preview._window_end is not None

        await pilot.press("home")
        await pilot.pause()
        assert preview._window_end is None
        assert preview._local_hours is None


async def test_title_shows_live_and_paged_indicator(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        await _open_preview_on_temperature(pilot, app)

        title = _label_text(app.screen.query_one("#preview_title", Label))
        assert "LIVE" in title

        await pilot.press("left")
        await pilot.pause()
        title = _label_text(app.screen.query_one("#preview_title", Label))
        assert "back" in title and "LIVE" not in title


async def test_zoomed_paging_forward_reenters_live_keeping_zoom(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("plus")
        await pilot.pause()
        await pilot.press("left")
        await pilot.pause()
        assert preview._window_end is not None  # paged back off live
        await pilot.press("shift+right")
        await pilot.pause()
        # Paging forward past the anchor re-enters live, keeping the zoom level (#138).
        assert preview._window_end is None
        assert preview._local_hours == 2


async def test_zoom_in_stays_live_and_receives_updates(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("plus")
        await pilot.pause()
        assert preview._window_end is None

        now_iso = datetime.now(timezone.utc).isoformat()
        app.client.inject_state_change(
            {
                "entity_id": "sensor.temperature",
                "state": "27.0",
                "attributes": {"friendly_name": "Temperature Sensor", "unit_of_measurement": "°C"},
                "last_changed": now_iso,
            }
        )
        await pilot.pause()
        # Live refresh still fires while zoomed: the fresh sample reaches the screen.
        assert preview._window_end is None
        assert preview._data[-1][1] == 27.0


async def test_zoom_while_paged_back_still_freezes(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)

        await pilot.press("left")  # page off live
        await pilot.pause()
        assert preview._window_end is not None
        frozen_before = preview._window_end
        await pilot.press("plus")  # zoom while paged back stays frozen (re-centered)
        await pilot.pause()
        assert preview._window_end is not None
        assert preview._local_hours == 2
        assert frozen_before is not None


async def test_saving_a_zoomed_graph_persists_the_zoomed_hours(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        await _open_preview_on_temperature(pilot, app)

        await pilot.press("plus")
        await pilot.pause()
        await pilot.press("S")
        await pilot.pause()
        app.screen.query_one("#save_graph_name_input").value = "Zoomed"
        await pilot.press("enter")
        await pilot.pause()
        assert app.saved_graphs["Zoomed"]["hours"] == 2
