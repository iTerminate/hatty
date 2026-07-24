# hatty — MIT License. See LICENSE file for details.
"""Acceptance tests for locking a list against accidental removal (issue #214)."""

from hatty.ui.entity_table import EntitiesTable
from tests.conftest import make_config, notified


async def test_space_on_locked_list_opens_unlock_popup_and_keeps_member(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name == "my_list"
        assert app.list_ctl.is_locked("my_list")

        await pilot.press("space")
        await pilot.pause()

        assert "light.living_room_lamp" in app.entity_lists["my_list"]
        assert app.list_ctl.is_locked("my_list")


async def test_confirming_unlock_popup_unlocks_and_removes(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()

        await pilot.press("y")
        await pilot.pause()

        assert "light.living_room_lamp" not in app.entity_lists["my_list"]
        assert not app.list_ctl.is_locked("my_list")


async def test_cancelling_unlock_popup_removes_nothing_and_stays_locked(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()

        await pilot.press("n")
        await pilot.pause()

        assert "light.living_room_lamp" in app.entity_lists["my_list"]
        assert app.list_ctl.is_locked("my_list")


async def test_second_removal_after_unlock_needs_no_popup(make_app, sample_entities):
    # Alphabetical display order: "Fan Switch" (switch.fan) sorts before
    # "Living Room Lamp", so the cursor starts on switch.fan.
    config_data = {
        **make_config(),
        "default_list": "my_list",
        "lists": {"my_list": ["light.living_room_lamp", "switch.fan"]},
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert "switch.fan" not in app.entity_lists["my_list"]
        assert not app.list_ctl.is_locked("my_list")

        # Second member's removal goes through immediately, no popup.
        await pilot.press("space")
        await pilot.pause()
        assert "light.living_room_lamp" not in app.entity_lists["my_list"]


async def test_removal_while_searching_is_never_gated(make_app, sample_entities):
    # Searching is the "filter list for adding items" path the issue exempts —
    # add/remove both stay free there (issue #214).
    config_data = {
        **make_config(),
        "default_list": "my_list",
        "lists": {"my_list": ["switch.fan"]},
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("f", "a", "n")
        await pilot.press("enter")
        await pilot.pause()
        assert app.search_term == "fan"

        await pilot.press("space")
        await pilot.pause()

        assert "switch.fan" not in app.entity_lists["my_list"]
        # The lock state itself is untouched — search just bypasses the gate.
        assert app.list_ctl.is_locked("my_list")


async def test_capital_l_toggles_lock_manually(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.list_ctl.is_locked("my_list")

        await pilot.press("L")
        await pilot.pause()
        assert not app.list_ctl.is_locked("my_list")
        assert notified(app, title="List Lock", message_contains="unlocked")

        # Now removal goes through with no popup.
        await pilot.press("space")
        await pilot.pause()
        assert "light.living_room_lamp" not in app.entity_lists["my_list"]

        await pilot.press("L")
        await pilot.pause()
        assert app.list_ctl.is_locked("my_list")
        assert notified(app, title="List Lock", message_contains="locked")


async def test_capital_l_with_no_list_selected_shows_warning(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=make_config(lists={}))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name is None
        await pilot.press("L")
        await pilot.pause()
        assert notified(app, title="Warning", message_contains="Select a list")


async def test_switching_lists_relocks(make_app, sample_entities):
    config_data = {
        **make_config(),
        "default_list": "list_a",
        "lists": {"list_a": ["switch.fan"], "list_b": ["sensor.temperature"]},
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name == "list_a"

        await pilot.press("L")
        await pilot.pause()
        assert not app.list_ctl.is_locked("list_a")

        # Switch to list_b and back to list_a via the list popup.
        await pilot.press("l")
        await pilot.pause()
        await pilot.press("down", "down", "down")
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_list_name == "list_b"

        await pilot.press("l")
        await pilot.pause()
        await pilot.press("down", "down")
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_list_name == "list_a"

        assert app.list_ctl.is_locked("list_a")


async def test_lock_glyph_in_subtitle(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "🔐" in app.sub_title

        await pilot.press("L")
        await pilot.pause()
        assert "🔓" in app.sub_title


async def test_undo_bypasses_lock(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert "light.living_room_lamp" not in app.entity_lists["my_list"]

        # Re-lock, then confirm undo still restores the entity without a popup.
        await pilot.press("L")
        await pilot.pause()
        assert app.list_ctl.is_locked("my_list")

        await pilot.press("u")
        await pilot.pause()
        assert "light.living_room_lamp" in app.entity_lists["my_list"]
        assert app.list_ctl.is_locked("my_list")


async def test_row_count_unaffected_by_locked_removal_attempt(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one(EntitiesTable)
        assert table.row_count == 1

        await pilot.press("space")
        await pilot.pause()
        assert table.row_count == 1

        await pilot.press("n")
        await pilot.pause()
        assert table.row_count == 1
