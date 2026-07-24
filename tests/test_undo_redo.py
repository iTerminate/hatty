# hatty — MIT License. See LICENSE file for details.
from tests.conftest import make_config, notified

_LIST_CONFIG = {
    **make_config(),
    "default_list": "my_list",
    "lists": {"my_list": ["light.living_room_lamp"]},
}


async def test_undo_restores_removed_entity(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "light.living_room_lamp" in app.entity_lists["my_list"]

        await pilot.press("space")
        await pilot.pause()
        await pilot.press("y")  # confirm unlock-to-remove (issue #214)
        await pilot.pause()
        assert "light.living_room_lamp" not in app.entity_lists["my_list"]

        await pilot.press("u")
        await pilot.pause()
        assert "light.living_room_lamp" in app.entity_lists["my_list"]
        assert notified(app, title="Undo", message_contains="Undo:")


async def test_redo_reapplies_removal(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        await pilot.press("y")  # confirm unlock-to-remove (issue #214)
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
        assert "light.living_room_lamp" in app.entity_lists["my_list"]

        await pilot.press("ctrl+r")
        await pilot.pause()
        assert "light.living_room_lamp" not in app.entity_lists["my_list"]
        assert notified(app, title="Redo", message_contains="Redo:")


async def test_undo_redo_for_added_entity(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Search for switch.fan, which isn't in my_list, while my_list stays the active list.
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("f", "a", "n")
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_list_name == "my_list"

        await pilot.press("space")
        await pilot.pause()
        assert "switch.fan" in app.entity_lists["my_list"]

        await pilot.press("u")
        await pilot.pause()
        assert "switch.fan" not in app.entity_lists["my_list"]

        await pilot.press("ctrl+r")
        await pilot.pause()
        assert "switch.fan" in app.entity_lists["my_list"]


async def test_undo_with_empty_stack_notifies_without_crashing(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
        assert notified(app, title="Undo", message_contains="Nothing to undo")


async def test_redo_with_empty_stack_notifies_without_crashing(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert notified(app, title="Redo", message_contains="Nothing to redo")


async def test_new_action_clears_redo_stack(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        await pilot.press("y")  # confirm unlock-to-remove (issue #214)
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
        assert app._redo_stack

        await pilot.press("/")
        await pilot.pause()
        await pilot.press("f", "a", "n")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()

        assert not app._redo_stack
