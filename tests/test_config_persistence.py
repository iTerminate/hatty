# hatty — MIT License. See LICENSE file for details.
from tests.conftest import NO_LIST_CONFIG, make_config

# Collections (lists, defaults, etc.) persist to SQLite now (#63), so persistence
# assertions read them back through app.storage rather than the YAML file.


async def test_space_key_saves_entity_removal_to_storage(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        await pilot.press("y")  # confirm unlock-to-remove (issue #214)
        await pilot.pause()

        saved = app.storage.load_all()
        assert "light.living_room_lamp" not in saved["lists"]["my_list"]


async def test_space_key_saves_entity_addition_to_storage(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("f", "a", "n")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()

        saved = app.storage.load_all()
        assert "switch.fan" in saved["lists"]["my_list"]


async def test_new_list_created_via_popup_does_not_auto_save(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=NO_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await pilot.pause()
        popup = app.screen
        new_list_input = popup.query_one("#new_list_input")
        await pilot.click(new_list_input)
        await pilot.pause()
        await pilot.press("t", "e", "s", "t", "l", "i", "s", "t")
        await pilot.press("enter")
        await pilot.pause()

        assert "testlist" in app.list_names


async def test_set_default_saves_to_config_file(make_app, sample_entities):
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

        saved = app.storage.load_all()
        assert saved["default_list"] == "list_a"
