# hatty — MIT License. See LICENSE file for details.
"""Acceptance coverage for the u/ctrl+r undo/redo keybindings and their
notification toasts (issue #169). The underlying ListController undo/redo
mechanics — action recording, inverse application, redo-stack clearing on a
new action — are unit-tested directly in tests/unit/test_lists_controller.py;
these two tests exist to confirm the keys and toasts are wired up end to end,
not to re-verify the controller logic."""

from tests.conftest import make_config, notified

_LIST_CONFIG = {
    **make_config(),
    "default_list": "my_list",
    "lists": {"my_list": ["light.living_room_lamp"]},
}


async def test_undo_then_redo_restores_and_renotifies(make_app, sample_entities):
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

        await pilot.press("ctrl+r")
        await pilot.pause()
        assert "light.living_room_lamp" not in app.entity_lists["my_list"]
        assert notified(app, title="Redo", message_contains="Redo:")


async def test_undo_and_redo_with_empty_stack_notify_without_crashing(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
        assert notified(app, title="Undo", message_contains="Nothing to undo")

        await pilot.press("ctrl+r")
        await pilot.pause()
        assert notified(app, title="Redo", message_contains="Nothing to redo")
