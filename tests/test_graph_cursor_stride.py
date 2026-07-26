# hatty — MIT License. See LICENSE file for details.
"""Proportional cursor stride + home/end in the fullscreen graph inspect mode (#67).

On a plot with a couple thousand readings, a flat 6-sample fast step made
crossing the window take hundreds of keypresses.
"""

from textual.coordinate import Coordinate
from textual.widgets import Label

from hatty.ui.entity_table import EntitiesTable
from hatty.ui.graph.preview_screen import GraphPreviewScreen
from tests.conftest import NO_LIST_CONFIG


def _label_text(label: Label) -> str:
    return str(label.content)


async def _open_graph_with_history(pilot, app, points):
    app.client._history_data = {"sensor.temperature": points}
    table = app.query_one(EntitiesTable)
    table.cursor_coordinate = Coordinate(3, 0)
    await pilot.pause()
    await pilot.press("g")
    await pilot.pause()
    await pilot.press("G")
    await pilot.pause()
    preview = app.screen
    assert isinstance(preview, GraphPreviewScreen)
    return preview


def _dense(n):
    return [(f"2024-01-01T08:{i // 60:02d}:{i % 60:02d}+00:00", float(i)) for i in range(n)]


async def test_fast_stride_is_ten_percent_on_dense_plot(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        preview = await _open_graph_with_history(pilot, app, _dense(2000))
        assert preview._fast_cursor_stride() == 200

        await pilot.press("enter")  # cursor mode, starts at newest (index 1999)
        await pilot.pause()
        assert preview._cursor_index == 1999

        await pilot.press("shift+left")
        await pilot.pause()
        assert preview._cursor_index == 1799  # moved by 10% = 200


async def test_fast_stride_floor_on_small_plot(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        preview = await _open_graph_with_history(pilot, app, _dense(30))
        assert preview._fast_cursor_stride() == 6  # max(6, round(3.0))

        await pilot.press("enter")
        await pilot.pause()
        assert preview._cursor_index == 29
        await pilot.press("shift+left")
        await pilot.pause()
        assert preview._cursor_index == 23


async def test_home_and_end_jump_within_cursor_mode_without_reload(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        preview = await _open_graph_with_history(pilot, app, _dense(500))
        await pilot.press("enter")
        await pilot.pause()
        assert preview._cursor_index == 499
        assert preview._window_end is None  # live

        await pilot.press("home")
        await pilot.pause()
        assert preview._cursor_index == 0
        # Home in cursor mode must NOT reload the window / leave live anchoring.
        assert preview._window_end is None

        await pilot.press("end")
        await pilot.pause()
        assert preview._cursor_index == 499


async def test_home_outside_cursor_mode_still_snaps_live(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        preview = await _open_graph_with_history(pilot, app, _dense(100))
        # Page back so there is a frozen window to snap out of.
        await pilot.press("left")
        await pilot.pause()
        assert preview._window_end is not None
        assert preview._cursor_mode is False

        await pilot.press("home")
        await pilot.pause()
        assert preview._window_end is None  # snapped back to live


async def test_cursor_stats_show_sample_position(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        preview = await _open_graph_with_history(pilot, app, _dense(50))
        await pilot.press("enter")
        await pilot.pause()
        stats = _label_text(preview.query_one("#preview_stats", Label))
        assert "sample 50/50" in stats
        await pilot.press("home")
        await pilot.pause()
        stats = _label_text(preview.query_one("#preview_stats", Label))
        assert "sample 1/50" in stats
