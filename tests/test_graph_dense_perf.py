# hatty — MIT License. See LICENSE file for details.
"""Dense-plot rendering downsamples for display but keeps raw data (issue #68)."""

from textual.coordinate import Coordinate
from textual.widgets import Label

from hatty.ui.entity_table import EntitiesTable
from hatty.ui.graph.downsample import minmax_downsample
from hatty.ui.graph.preview_screen import GraphPreviewScreen
from tests.conftest import make_config

_NO_LIST_CONFIG = make_config(lists={})


def _dense(n):
    # A sawtooth so min/max buckets have real extremes to preserve.
    return [(f"2024-01-01T08:{i // 60:02d}:{i % 60:02d}+00:00", float(i % 50)) for i in range(n)]


async def _open_graph(pilot, app, points):
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


async def test_dense_graph_keeps_full_reading_count_in_stats(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        preview = await _open_graph(pilot, app, _dense(3000))
        # Raw data preserved: stats report every reading, not the downsampled set.
        assert len(preview._data) == 3000
        stats = str(preview.query_one("#preview_stats", Label).content)
        assert "3000 readings" in stats


async def test_downsample_helper_reduces_points_for_render(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        preview = await _open_graph(pilot, app, _dense(3000))
        indices = [float(i) for i in range(3000)]
        values = [float(i % 50) for i in range(3000)]
        # render_numeric/plot_numeric_series downsample to the plot width for
        # display; the raw series stays intact (asserted above).
        ds_i, ds_v = minmax_downsample(indices, values, preview._plot_width())
        # Downsampled to at most ~2 points per plot column.
        assert len(ds_v) <= 2 * preview._plot_width()
        assert len(ds_v) < 3000


async def test_cursor_mode_freezes_live_refresh(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        preview = await _open_graph(pilot, app, _dense(100))
        await pilot.press("enter")  # cursor mode
        await pilot.pause()
        before = list(preview._data)

        app.client.inject_state_change(
            {
                "entity_id": "sensor.temperature",
                "state": "999.0",
                "attributes": {"friendly_name": "Temperature Sensor", "unit_of_measurement": "°C"},
                "last_changed": "2024-01-01T09:30:00.000000+00:00",
            }
        )
        await pilot.pause()
        # Preview data is frozen while inspecting; the new point isn't merged in.
        assert list(preview._data) == before
