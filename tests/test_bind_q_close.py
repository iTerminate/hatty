# hatty — MIT License. See LICENSE file for details.
"""`q` is a hidden alias for the existing Esc dismiss/back binding on the
fullscreen graph and modal popups (issue #296) — a quick vim-style close key
that never touches ctrl+q (quit). `SplitSlotPopup` is deliberately excluded
(`q` already means "Quarters" there — see test_dashboard_split.py) and isn't
retested here.
"""

from textual.coordinate import Coordinate
from textual.widgets import Input, RadioSet

from hatty.ui.entity_table import EntitiesTable
from hatty.ui.graph.duration_popup import GraphDurationPopup
from hatty.ui.graph.preview_screen import GraphPreviewScreen
from hatty.ui.list_selection_popup import ListSelectionPopup
from tests.conftest import NO_LIST_CONFIG


async def test_q_closes_fullscreen_graph(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)  # Temperature Sensor (graphable)
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)

        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, GraphPreviewScreen)


async def test_q_closes_duration_popup_when_no_input_focused(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("T")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, GraphDurationPopup)
        assert app.focused is popup.query_one(RadioSet)

        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, GraphDurationPopup)


async def test_q_types_into_focused_input_instead_of_closing(make_app, sample_entities):
    """A focused text Input consumes `q` as a character before the screen's `q`
    binding is ever consulted (Textual's Input._on_key stops printable keys
    unconditionally) — the same mechanism that already lets bare letters like
    `r`/`v`/`a` coexist with search/name fields elsewhere in the app."""
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        table.cursor_coordinate = Coordinate(3, 0)
        await pilot.pause()
        await pilot.press("T")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, GraphDurationPopup)

        hours_input = popup.query_one("#duration_hours_input", Input)
        hours_input.focus()
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()

        assert hours_input.value == "q"
        assert isinstance(app.screen, GraphDurationPopup)


async def test_q_closes_list_selection_popup(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.screen, ListSelectionPopup)

        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, ListSelectionPopup)


async def test_q_types_into_list_popup_search_instead_of_closing(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, ListSelectionPopup)

        await pilot.press("/")  # open the popup's search input and focus it
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()

        assert popup.search_term == "q"
        assert isinstance(app.screen, ListSelectionPopup)
