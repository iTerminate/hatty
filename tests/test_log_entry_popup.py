# hatty — MIT License. See LICENSE file for details.
"""`V` browses the open activity log's retained entries in a popup and shows
a selected entry's full, untruncated text (issue #23) — from both hosts of
ActivityLogPanel: the main table's docked panel and the fullscreen graph's."""

from textual.widgets import OptionList, Static

from hatty.ui.activity_log_panel import ActivityLogPanel
from hatty.ui.log_entry_popup import LogEntryPopup
from tests.conftest import NO_LIST_CONFIG
from tests.test_graph_event_log import _open_preview_on_temperature

_LONG_NAME = "A Very Long Entity Name That Goes On And On And On And On And On"


async def test_v_opens_log_entry_popup_with_all_entries(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = [
            {"when": "2024-01-15T10:29:58+00:00", "name": "Front Door", "state": "on"},
            {"when": "2024-01-15T10:30:00+00:00", "name": _LONG_NAME, "state": "on"},
        ]
        await pilot.press("a")
        await pilot.pause()

        await pilot.press("V")
        await pilot.pause()

        assert isinstance(app.screen, LogEntryPopup)
        options = app.screen.query_one("#log_entry_list", OptionList)
        assert options.option_count == 2
        assert options.highlighted == 1  # newest preselected


async def test_detail_pane_shows_full_untruncated_text(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = [{"when": "2024-01-15T10:30:00+00:00", "name": _LONG_NAME, "state": "on"}]
        await pilot.press("a")
        await pilot.pause()

        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        # The panel's own truncated line must not contain the full name.
        assert not any(_LONG_NAME in line for line in panel.query_one("#log_widget").lines)

        await pilot.press("V")
        await pilot.pause()

        detail = str(app.screen.query_one("#log_entry_detail", Static).content)
        assert _LONG_NAME in detail
        assert "on" in detail


async def test_escape_closes_popup_and_leaves_panel_visible(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._logbook_data = [{"when": "2024-01-15T10:30:00+00:00", "name": "Front Door", "state": "on"}]
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("V")
        await pilot.pause()
        assert isinstance(app.screen, LogEntryPopup)

        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, LogEntryPopup)
        assert app.query_one("#activity_log_panel", ActivityLogPanel).has_class("-visible")


async def test_v_is_a_noop_when_log_closed(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.check_action("show_log_entries", ()) is False

        await pilot.press("V")
        await pilot.pause()

        assert not isinstance(app.screen, LogEntryPopup)


async def test_v_opens_log_entry_popup_from_fullscreen_graph(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        preview = await _open_preview_on_temperature(pilot, app)
        app.client._logbook_data = [{"when": "2024-01-15T10:30:00+00:00", "name": _LONG_NAME, "state": "on"}]

        assert preview.check_action("show_log_entries", ()) is False

        await pilot.press("a")
        await pilot.pause()
        assert preview.check_action("show_log_entries", ()) is True

        await pilot.press("V")
        await pilot.pause()

        assert isinstance(app.screen, LogEntryPopup)
        detail = str(app.screen.query_one("#log_entry_detail", Static).content)
        assert _LONG_NAME in detail
