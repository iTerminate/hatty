# hatty — MIT License. See LICENSE file for details.
import yaml
from textual.widgets import SelectionList

from hatty.ui.column_config_popup import ColumnConfigPopup
from hatty.ui.entity_table import EntitiesTable
from tests.conftest import NO_LIST_CONFIG


async def test_c_opens_column_config_popup(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, ColumnConfigPopup)


async def test_column_popup_initially_focuses_selection_list(make_app):
    app = make_app(config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert app.focused is app.screen.query_one("#column_selection", SelectionList)


async def test_escape_saves_and_closes_column_popup(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()

        selection_list = app.screen.query_one("#column_selection", SelectionList)
        selection_list.deselect("value")
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()

        assert "value" not in app.columns
        assert list(app.query_one(EntitiesTable).columns.keys()) == [str(k) for k in app.columns]


async def test_enter_saves_and_closes_column_popup(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()

        selection_list = app.screen.query_one("#column_selection", SelectionList)
        selection_list.deselect("value")
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()

        assert "value" not in app.columns
        assert list(app.query_one(EntitiesTable).columns.keys()) == [str(k) for k in app.columns]
        assert not isinstance(app.screen, ColumnConfigPopup)


async def test_column_toggle_persists_to_config_file(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()

        selection_list = app.screen.query_one("#column_selection", SelectionList)
        selection_list.select("device_class")
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()

        with open(app.config_path) as f:
            saved = yaml.safe_load(f)
        assert saved["columns"] == app.columns
        assert "device_class" in app.columns


async def test_existing_column_order_preserved_when_unchanged(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        original_order = list(app.columns)

        await pilot.press("c")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

        assert app.columns == original_order


async def test_newly_added_column_appended_after_existing_order(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        original_order = list(app.columns)  # name, value, last_changed, in_list

        await pilot.press("c")
        await pilot.pause()
        selection_list = app.screen.query_one("#column_selection", SelectionList)
        selection_list.select("entity_id")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

        assert app.columns == original_order + ["entity_id"]


async def test_shift_down_reorders_column(make_app, sample_entities):
    """Shift+↓ moves the highlighted column down one slot in display order (#202)."""
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        original_order = list(app.columns)  # name, value, last_changed, in_list

        await pilot.press("c")
        await pilot.pause()
        selection_list = app.screen.query_one("#column_selection", SelectionList)
        selection_list.highlighted = 0  # "name"
        await pilot.pause()
        await pilot.press("shift+down")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

        # name and value swap; the rest keep their order.
        expected = original_order[:]
        expected[0], expected[1] = expected[1], expected[0]
        assert app.columns == expected


async def test_reorder_then_toggle_keeps_new_order(make_app, sample_entities):
    """Reordering and toggling compose: a moved column that stays enabled keeps
    its new position, and disabled columns drop out (#202)."""
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("c")
        await pilot.pause()
        selection_list = app.screen.query_one("#column_selection", SelectionList)
        selection_list.highlighted = 0  # "name"
        await pilot.pause()
        await pilot.press("shift+down")  # name -> position 1
        await pilot.pause()
        # name is now highlighted at index 1; deselect it.
        selection_list.deselect("name")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

        assert "name" not in app.columns
        assert app.columns[0] == "value"
