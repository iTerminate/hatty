# hatty — MIT License. See LICENSE file for details.
from hatty.ui.dashboard.screen import DashboardScreen
from hatty.ui.help_popup import HelpPopup, filter_pages


async def test_question_mark_opens_help_on_main_screen(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpPopup)


async def test_escape_dismisses_help(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpPopup)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpPopup)


async def test_help_lists_main_screen_bindings(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        descriptions = [desc for _, desc in app.screen._binding_rows]
        assert "Search" in descriptions
        assert "Controls" in descriptions
        assert "Help" in descriptions


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


async def test_help_page_names_cover_every_screen(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        titles = [title for title, _ in app.screen._pages]
        assert titles == ["Main", "Dashboard", "Device Tree", "Graph", "Light Control", "Media Player"]
        assert app.screen._active_index == 0  # opened from the main table


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
