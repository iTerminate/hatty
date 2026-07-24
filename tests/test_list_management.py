# hatty — MIT License. See LICENSE file for details.
from textual.widgets import ListView

from hatty.ui.entity_table import EntitiesTable
from hatty.ui.list_selection_popup import ListSelectionPopup
from tests.conftest import make_config, notified

_NO_LIST_CONFIG = make_config(lists={})


async def test_l_opens_list_popup(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.screen, ListSelectionPopup)


async def test_escape_closes_list_popup(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.screen, ListSelectionPopup)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ListSelectionPopup)


async def test_selecting_view_all_shows_all_entities(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one(EntitiesTable).row_count == 1

        await pilot.press("l")
        await pilot.pause()
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_list_name is None
        assert app.query_one(EntitiesTable).row_count == len(sample_entities)


async def test_selecting_list_from_popup_filters_table(make_app, sample_entities):
    config_data = {
        **make_config(),
        "lists": {
            "list_a": ["light.living_room_lamp", "switch.fan"],
            "list_b": ["sensor.temperature"],
        },
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        await pilot.press("down", "down", "down")
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_list_name == "list_b"
        assert app.query_one(EntitiesTable).row_count == 1


async def test_space_removes_entity_from_list(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one(EntitiesTable).row_count == 1
        await pilot.press("space")
        await pilot.pause()
        # Locked by default (issue #214) — removal opens an unlock confirmation
        # rather than removing immediately.
        assert "light.living_room_lamp" in app.entity_lists["my_list"]
        await pilot.press("y")
        await pilot.pause()
        assert "light.living_room_lamp" not in app.entity_lists["my_list"]


async def test_space_adds_entity_to_list(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("f", "a", "n")
        await pilot.press("enter")
        await pilot.pause()
        assert app.query_one(EntitiesTable).row_count == 1
        assert app.current_list_name == "my_list"

        await pilot.press("space")
        await pilot.pause()
        assert "switch.fan" in app.entity_lists["my_list"]


async def test_space_keeps_cursor_row_in_filtered_results(make_app, sample_entities):
    # Searching "light" while in my_list context shows two entities:
    # row 0: light.living_room_lamp (in my_list) then row 1: light.kitchen_light (others).
    # After adding kitchen_light, both are in the list so both stay visible — cursor should
    # remain at row 1 rather than jumping to kitchen_light's new in_list position.
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("l", "i", "g", "h", "t")
        await pilot.press("enter")
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        assert table.row_count == 2
        await pilot.press("down")
        await pilot.pause()
        assert table.cursor_row == 1
        await pilot.press("space")
        await pilot.pause()
        assert "light.kitchen_light" in app.entity_lists["my_list"]
        assert table.cursor_row == 1


async def test_space_with_no_list_selected_shows_warning(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name is None
        await pilot.press("space")
        await pilot.pause()
        assert notified(app, title="Warning", message_contains="No list selected")


async def test_escape_exits_list_filter(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name is not None
        await pilot.press("escape")
        await pilot.pause()
        # Confirm the leave-list dialog
        await pilot.press("y")
        await pilot.pause()
        assert app.current_list_name is None
        assert app.query_one(EntitiesTable).row_count == len(sample_entities)


async def test_create_new_list_via_popup(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        popup = app.screen
        new_list_input = popup.query_one("#new_list_input")
        await pilot.click(new_list_input)
        await pilot.pause()
        await pilot.press("n", "e", "w", "l", "i", "s", "t")
        await pilot.press("enter")
        await pilot.pause()
        assert "newlist" in app.list_names


async def test_set_default_via_popup(make_app, sample_entities):
    config_data = {
        **make_config(),
        "lists": {"list_a": ["switch.fan"]},
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        await pilot.press("down", "down")
        await pilot.press("d")
        await pilot.pause()
        assert app.default_list_name == "list_a"


async def test_delete_list_via_popup(make_app, sample_entities):
    config_data = {
        **make_config(),
        "lists": {"list_a": ["switch.fan"]},
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        await pilot.press("down", "down")
        await pilot.press("delete")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert "list_a" not in app.entity_lists
        assert "list_a" not in app.list_names


async def test_rename_list_via_popup(make_app, sample_entities):
    config_data = {
        **make_config(),
        "lists": {"list_a": ["switch.fan"]},
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        await pilot.press("down", "down")
        await pilot.press("r")
        await pilot.pause()

        app.screen.query_one("#rename_list_input").value = "renamed_list"
        await pilot.press("enter")
        await pilot.pause()

        assert "list_a" not in app.entity_lists
        assert "list_a" not in app.list_names
        assert "renamed_list" in app.list_names
        assert app.entity_lists["renamed_list"] == ["switch.fan"]


async def test_rename_view_all_via_popup_refused(make_app, sample_entities):
    config_data = {
        **make_config(),
        "lists": {"list_a": ["switch.fan"]},
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        await pilot.press("down")  # highlight "View All" at index 0
        await pilot.press("r")
        await pilot.pause()
        assert notified(app, message_contains="cannot be renamed")
        assert isinstance(app.screen, ListSelectionPopup)


async def test_l_from_view_all_jumps_back_to_last_selected_list_over_default(make_app, sample_entities):
    config_data = {
        **make_config(),
        "default_list": "list_a",
        "lists": {"list_a": ["switch.fan"], "list_b": ["sensor.temperature"]},
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name == "list_a"

        # Switch to list_b so it becomes the most-recently-selected list.
        await pilot.press("l")
        await pilot.pause()
        await pilot.press("down", "down", "down")
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_list_name == "list_b"

        # Leave to View All.
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert app.current_list_name is None

        # 'l' should jump straight back to list_b (last selected), not the
        # default list_a, and without opening the popup.
        await pilot.press("l")
        await pilot.pause()
        assert app.current_list_name == "list_b"
        assert not isinstance(app.screen, ListSelectionPopup)


async def test_l_from_view_all_falls_back_to_default_list(make_app, sample_entities):
    config_data = {
        **make_config(),
        "default_list": "list_b",
        "lists": {"list_a": ["switch.fan"], "list_b": ["sensor.temperature"]},
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name == "list_b"

        await pilot.press("l")
        await pilot.pause()
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_list_name is None

        await pilot.press("l")
        await pilot.pause()
        assert app.current_list_name == "list_b"
        assert not isinstance(app.screen, ListSelectionPopup)


async def test_l_while_searching_returns_to_active_list(make_app, sample_entities):
    # A list stays "current" even while a free-text search overrides the
    # display with all-entity matches; `l` should clear the search and
    # return to that list rather than opening the picker again (issue #211).
    config_data = {
        **make_config(),
        "default_list": "list_a",
        "lists": {"list_a": ["switch.fan"], "list_b": ["sensor.temperature"]},
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name == "list_a"

        await pilot.press("/")
        await pilot.pause()
        await pilot.press("k", "i", "t", "c", "h", "e", "n")
        await pilot.press("enter")
        await pilot.pause()
        assert app.search_term == "kitchen"

        await pilot.press("l")
        await pilot.pause()
        assert app.search_term == ""
        assert app.current_list_name == "list_a"
        assert not isinstance(app.screen, ListSelectionPopup)


async def test_l_with_no_lists_still_opens_popup(make_app):
    app = make_app(config_data=_NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name is None

        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.screen, ListSelectionPopup)


_THREE_LIST_CONFIG = {
    **make_config(),
    "lists": {
        "list_a": ["switch.fan"],
        "list_b": ["sensor.temperature"],
        "list_c": ["light.living_room_lamp"],
    },
}


async def test_shift_down_reorders_list(make_app, sample_entities):
    # Mirrors the column-config Shift+up/down reorder (#212).
    app = make_app(entities=sample_entities, config_data=_THREE_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        original_order = list(app.list_names)
        list_view = app.screen.query_one(ListView)
        list_view.index = 1  # first real list, right below "View All"

        await pilot.press("shift+down")
        await pilot.pause()

        expected = original_order[:]
        expected[0], expected[1] = expected[1], expected[0]
        assert app.list_names == expected
        # Persisted order follows dict insertion order, not just list_names.
        assert list(app.entity_lists) == expected
        assert list_view.index == 2


async def test_view_all_row_cannot_be_reordered(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_THREE_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        original_order = list(app.list_names)
        list_view = app.screen.query_one(ListView)
        list_view.index = 0  # "View All"

        await pilot.press("shift+down")
        await pilot.pause()
        assert app.list_names == original_order

        list_view.index = 1  # first real list: can't move up into "View All"
        await pilot.press("shift+up")
        await pilot.pause()
        assert app.list_names == original_order


async def test_reorder_refused_while_searching(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_THREE_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        original_order = list(app.list_names)

        await pilot.press("/")
        await pilot.press("a")
        await pilot.pause()

        await pilot.press("shift+down")
        await pilot.pause()

        assert app.list_names == original_order
        assert notified(app, message_contains="Clear the search")
