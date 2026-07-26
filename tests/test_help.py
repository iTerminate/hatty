# hatty — MIT License. See LICENSE file for details.
from hatty.ui.dashboard.screen import DashboardScreen
from hatty.ui.help_popup import HelpPopup, filter_pages


async def test_question_mark_opens_help_listing_bindings_and_pages(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpPopup)

        descriptions = [desc for _, desc in app.screen._binding_rows]
        assert "Search" in descriptions
        assert "Controls" in descriptions
        assert "Help" in descriptions

        titles = [title for title, _ in app.screen._pages]
        assert titles == ["Main", "Dashboard", "Device Tree", "Graph", "Light Control", "Media Player"]
        assert app.screen._active_index == 0  # opened from the main table

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpPopup)


async def test_main_page_hides_meaningless_datatable_rows(make_app):
    """Issue #7: EntitiesTable is a Textual DataTable, so its own key bindings
    (cursor_left/right, select_cursor, home/end-within-row) leak into the live
    Main page's active_bindings even though moving *columns* means nothing in
    a table whose selection model only cares about the row. Row navigation
    (↑/↓, PgUp/PgDn, Ctrl+Home/Ctrl+End) is real and stays."""
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        descriptions = [desc for _, desc in app.screen._binding_rows]
        assert "Cursor left" not in descriptions
        assert "Cursor right" not in descriptions
        assert "Select" not in descriptions
        assert "Home" not in descriptions
        assert "End" not in descriptions
        assert "Cursor up" in descriptions
        assert "Cursor down" in descriptions
        assert "Page up" in descriptions
        assert "Page down" in descriptions
        assert "Top" in descriptions
        assert "Bottom" in descriptions


async def test_question_mark_opens_help_on_dashboard_screen_use_mode(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpPopup)
        descriptions = [desc for _, desc in app.screen._binding_rows]
        assert "Dashboards" in descriptions
        assert "Edit" in descriptions
        assert "Controls" in descriptions
        assert "Device Tree" in descriptions
        # Edit-only actions are hidden from the use-mode help screen.
        assert "Assign" not in descriptions
        assert "Move" not in descriptions


async def test_question_mark_opens_help_on_dashboard_screen_edit_mode(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("E")  # enter edit mode
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpPopup)
        descriptions = [desc for _, desc in app.screen._binding_rows]
        assert "Assign" in descriptions
        assert "Move" in descriptions
        assert "Dashboards" in descriptions
        # Use-only action "Edit" (entering edit mode) is hidden once already in edit mode.
        assert "Edit" not in descriptions


async def test_right_arrow_switches_help_to_next_page(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        await pilot.press("right")
        await pilot.pause()
        assert app.screen._active_index == 1
        descriptions = [desc for _, desc in app.screen._binding_rows]
        # The static Dashboard page (not the active mode-filtered view) lists
        # both use-mode and edit-mode actions together.
        assert "Dashboards" in descriptions
        assert "Assign" in descriptions
        await pilot.press("left")
        await pilot.pause()
        assert app.screen._active_index == 0


async def test_left_arrow_wraps_to_last_page(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        await pilot.press("left")
        await pilot.pause()
        assert app.screen._active_index == len(app.screen._pages) - 1
        assert app.screen._pages[app.screen._active_index][0] == "Media Player"


async def test_slash_searches_across_every_page(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        for ch in "zoom":
            await pilot.press(ch)
        await pilot.pause()
        assert app.screen._filter == "zoom"
        assert app.screen._show_all is True
        matched = filter_pages(app.screen._pages, app.screen._filter)
        matched_titles = [title for title, _ in matched]
        # "Zoom In"/"Zoom Out" only exist on the Graph page's bindings.
        assert matched_titles == ["Graph"]
        descriptions = [desc for _, desc in matched[0][1]]
        assert "Zoom In" in descriptions
        assert "Zoom Out" in descriptions


async def test_escape_clears_search_before_closing_help(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        await pilot.press("/")
        for ch in "zoom":
            await pilot.press(ch)
        await pilot.pause()
        assert isinstance(app.screen, HelpPopup)
        await pilot.press("escape")
        await pilot.pause()
        # First escape only clears the search, help stays open.
        assert isinstance(app.screen, HelpPopup)
        assert app.screen._filter == ""
        assert app.screen._show_all is False
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpPopup)


async def test_a_toggles_show_all_pages(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert app.screen._show_all is True
        matched = filter_pages(app.screen._pages, "")
        matched_titles = [title for title, _ in matched]
        assert matched_titles == ["Main", "Dashboard", "Device Tree", "Graph", "Light Control", "Media Player"]
        await pilot.press("a")
        await pilot.pause()
        assert app.screen._show_all is False


def _rows_for(app, title: str) -> list[tuple[str, str]]:
    return next(rows for page_title, rows in app.screen._pages if page_title == title)


async def test_graph_help_page_shows_both_modes_sectioned(make_app):
    """Issue #7: the Graph page must show both the paging and inspect-mode
    meaning of a key like `home`, grouped under section headers, regardless
    of which mode the graph screen happens to be in when help is opened."""
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        rows = _rows_for(app, "Graph")

        headers = [desc for key, desc in rows if not key]
        assert "Window" in headers
        assert "Inspect mode (Enter)" in headers
        assert "From anywhere" in headers

        descriptions_by_key: dict[str, list[str]] = {}
        for key, desc in rows:
            if key:
                descriptions_by_key.setdefault(key, []).append(desc)
        assert descriptions_by_key["home"] == ["Now", "Oldest Sample"]
        assert descriptions_by_key["left"] == ["Older", "Prev Sample"]

        # App-level keys that don't do anything on the graph screen are absent;
        # the ones that still work (Dashboard/Device Tree/Saved Graphs/Duration)
        # show up under "From anywhere".
        assert "n" not in descriptions_by_key
        flat_descriptions = [desc for _, desc in rows]
        assert "Dashboard" in flat_descriptions
        assert "Saved Graphs" in flat_descriptions


async def test_dashboard_help_page_sectioned_by_mode(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        rows = _rows_for(app, "Dashboard")
        headers = [desc for key, desc in rows if not key]
        assert headers == ["Use mode", "Edit mode", "Both modes"]

        descriptions = [desc for key, desc in rows if key]
        assert "Toggle" in descriptions  # use mode
        assert "Assign" in descriptions  # edit mode
        assert "Dashboards" in descriptions  # both modes
