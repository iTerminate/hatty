# hatty — MIT License. See LICENSE file for details.
from textual.coordinate import Coordinate

from hatty.ui.entity_table import EntitiesTable
from hatty.ui.search_input import SearchInput
from tests.conftest import NO_LIST_CONFIG


async def test_slash_opens_search_input(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        assert app.query_one("#search_input", SearchInput).display is True


async def test_escape_hides_search_input(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.query_one("#search_input", SearchInput).display is False


async def test_search_filters_entities_by_entity_id(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("f", "a", "n")
        await pilot.press("enter")
        await pilot.pause()
        assert app.query_one(EntitiesTable).row_count == 1
        assert app.search_term == "fan"


async def test_search_filters_by_friendly_name(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("k", "i", "t", "c", "h", "e", "n")
        await pilot.press("enter")
        await pilot.pause()
        assert app.query_one(EntitiesTable).row_count == 1


async def test_search_multi_word_skips_words(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("l", "i", "v", "i", "n", "g", "space", "l", "a", "m", "p")
        await pilot.press("enter")
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        assert table.row_count == 1
        cell_key = table.coordinate_to_cell_key(Coordinate(0, 0))
        assert cell_key.row_key.value == "light.living_room_lamp"


async def test_search_filters_by_state(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("2", "1", ".", "5")
        await pilot.press("enter")
        await pilot.pause()
        assert app.query_one(EntitiesTable).row_count == 1


async def test_escape_after_search_restores_prior_filter(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("f", "a", "n")
        await pilot.press("enter")
        await pilot.pause()
        assert app.query_one(EntitiesTable).row_count == 1

        await pilot.press("escape")
        await pilot.pause()
        assert app.search_term == ""
        assert app.query_one(EntitiesTable).row_count == 1


async def test_subtitle_shows_search_term_after_search(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("f", "a", "n")
        await pilot.press("enter")
        await pilot.pause()
        assert "fan" in app.sub_title


async def test_subtitle_shows_match_count(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("f", "a", "n")
        await pilot.press("enter")
        await pilot.pause()
        visible = app.query_one(EntitiesTable).row_count
        assert f"{visible}/{len(app.all_entities)}" in app.sub_title


async def test_subtitle_combines_list_and_search_term(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name == "my_list"

        await pilot.press("/")
        await pilot.pause()
        await pilot.press("f", "a", "n")
        await pilot.press("enter")
        await pilot.pause()

        assert "my_list" in app.sub_title
        assert "fan" in app.sub_title
        # filter-mode search matches across all entities, not just the active list
        assert app.query_one(EntitiesTable).row_count == 1


async def test_jump_mode_subtitle_retains_list_context(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()
        await pilot.press("l", "i", "v", "i", "n", "g")
        await pilot.pause()

        assert "my_list" in app.sub_title
        assert "jump" in app.sub_title.lower()


async def test_filter_applies_live_before_enter(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("f", "a", "n")
        await pilot.pause()
        assert app.query_one(EntitiesTable).row_count == 1
        assert app.search_term == "fan"


async def test_enter_closes_search_box(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("f", "a", "n")
        await pilot.press("enter")
        await pilot.pause()
        assert app.query_one("#search_input", SearchInput).display is False


async def test_tab_toggles_vi_mode(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        search_input = app.query_one("#search_input", SearchInput)
        assert search_input.vi_mode is False

        await pilot.press("tab")
        await pilot.pause()
        assert search_input.vi_mode is True

        await pilot.press("tab")
        await pilot.pause()
        assert search_input.vi_mode is False


async def test_vi_mode_jumps_cursor_without_filtering(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        full_row_count = table.row_count

        await pilot.press("/")
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()
        await pilot.press("k", "i", "t", "c", "h", "e", "n")
        await pilot.pause()

        assert table.row_count == full_row_count
        assert app.search_term == ""
        cell_key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0))
        assert cell_key.row_key.value == "light.kitchen_light"


async def test_n_and_N_cycle_vi_search_matches_with_wraparound(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)

        await pilot.press("/")
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()
        await pilot.press("l", "i", "g", "h", "t")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        def current_entity_id():
            cell_key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0))
            return cell_key.row_key.value

        first_match = current_entity_id()

        await pilot.press("n")
        await pilot.pause()
        second_match = current_entity_id()
        assert second_match != first_match

        await pilot.press("n")
        await pilot.pause()
        assert current_entity_id() == first_match  # wrapped back around

        await pilot.press("N")
        await pilot.pause()
        assert current_entity_id() == second_match


async def test_escape_in_vi_mode_leaves_filter_state_untouched(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()
        await pilot.press("k", "i", "t", "c", "h", "e", "n")
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()

        assert app.search_term == ""
        assert app.current_list_name is None
        assert app.query_one("#search_input", SearchInput).display is False
