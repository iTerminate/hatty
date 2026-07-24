# hatty — MIT License. See LICENSE file for details.
"""Acceptance tests for manually reordering entities within a list (issue #213)."""

from hatty.ui.entity_table import EntitiesTable
from tests.conftest import make_config, notified

# Three list members whose alphabetical display order (by friendly name) is
# switch.fan ("Fan Switch"), light.living_room_lamp ("Living Room Lamp"),
# sensor.temperature ("Temperature Sensor") — deliberately different from the
# stored add-order below, so a test asserting "alphabetical" vs "stored order"
# can't pass by coincidence.
_THREE_ITEM_CONFIG = {
    **make_config(),
    "default_list": "my_list",
    "lists": {"my_list": ["light.living_room_lamp", "switch.fan", "sensor.temperature"]},
}


async def test_shift_down_moves_entity_and_enables_manual_mode(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_THREE_ITEM_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        # Not manual yet: alphabetical display puts switch.fan first.
        assert table.ordered_entity_ids()[0] == "switch.fan"
        assert "my_list" not in app.manual_lists

        await pilot.press("shift+down")
        await pilot.pause()

        assert "my_list" in app.manual_lists
        # switch.fan (row 0) swapped with light.living_room_lamp (row 1).
        assert app.entity_lists["my_list"][:2] == ["light.living_room_lamp", "switch.fan"]
        assert table.cursor_row == 1


async def test_shift_up_at_top_row_is_noop(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_THREE_ITEM_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        assert table.cursor_row == 0

        await pilot.press("shift+up")
        await pilot.pause()

        assert "my_list" not in app.manual_lists
        assert app.entity_lists["my_list"] == ["light.living_room_lamp", "switch.fan", "sensor.temperature"]


async def test_o_toggles_manual_off_and_resumes_curated_order_on_re_enable(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_THREE_ITEM_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)

        # Curate an order via reorder, then toggle off and back on — the
        # curated order must survive the round trip rather than being reset
        # to whatever the alphabetical view showed while manual was off.
        await pilot.press("shift+down")
        await pilot.pause()
        curated = list(app.entity_lists["my_list"])
        assert "my_list" in app.manual_lists

        await pilot.press("o")
        await pilot.pause()
        assert "my_list" not in app.manual_lists
        assert app.entity_lists["my_list"] == curated  # stored order untouched
        assert table.ordered_entity_ids()[0] == "switch.fan"  # display is alphabetical again

        await pilot.press("o")
        await pilot.pause()
        assert "my_list" in app.manual_lists
        assert app.entity_lists["my_list"] == curated  # resumed, not re-frozen from the alphabetical view
        assert table.ordered_entity_ids() == curated


async def test_move_with_no_list_selected_shows_warning(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=make_config(lists={}))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name is None
        await pilot.press("shift+down")
        await pilot.pause()
        assert notified(app, title="Warning", message_contains="Select a list")


async def test_toggle_sort_with_no_list_selected_shows_warning(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=make_config(lists={}))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name is None
        await pilot.press("o")
        await pilot.pause()
        assert notified(app, title="Warning", message_contains="Select a list")


async def test_move_while_searching_is_refused(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_THREE_ITEM_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("f", "a", "n")
        await pilot.press("enter")
        await pilot.pause()
        assert app.search_term == "fan"

        await pilot.press("shift+down")
        await pilot.pause()

        assert "my_list" not in app.manual_lists
        assert notified(app, title="Warning", message_contains="Clear search")


async def test_manual_order_persists_across_relaunch(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_THREE_ITEM_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("shift+down")
        await pilot.pause()
        curated = list(app.entity_lists["my_list"])
        assert "my_list" in app.manual_lists

    # Second boot against the same tmp_path (same config + DB) — mirrors
    # test_storage_integration.py::test_collections_survive_a_restart.
    app2 = make_app(entities=sample_entities, config_data=_THREE_ITEM_CONFIG)
    async with app2.run_test() as pilot:
        await pilot.pause()
        assert "my_list" in app2.manual_lists
        assert app2.entity_lists["my_list"] == curated
        table = app2.query_one(EntitiesTable)
        assert table.ordered_entity_ids() == curated
