# hatty — MIT License. See LICENSE file for details.
"""Device log expands a whole list to its devices' entities (issue #69)."""

from textual.widgets import Label

from hatty.ui.activity_log_panel import ActivityLogPanel
from tests.conftest import make_config

# sample_registry fixture is shared from tests/conftest.py.


def _list_config(list_entities):
    return {
        **make_config(),
        "lists": {"my_list": list_entities},
        "default_list": "my_list",
    }


async def test_device_log_expands_all_devices_in_list(make_app, sample_entities, sample_registry):
    # List has one light; its device dev_abc also owns kitchen_light, so both appear.
    config = _list_config(["light.living_room_lamp"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name == "my_list"
        await pilot.press("A")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")
        assert app._log_entity_ids == {"light.living_room_lamp", "light.kitchen_light"}


async def test_device_log_title_shows_list_and_device_count(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        title = str(panel.query_one("#log_title", Label).content)
        assert "Device Log" in title
        assert "my_list" in title
        assert "2 devices" in title
        # Two devices -> three entities (lamp+kitchen from dev_abc, temperature from dev_xyz).
        assert app._log_entity_ids == {
            "light.living_room_lamp",
            "light.kitchen_light",
            "sensor.temperature",
        }


async def test_device_log_passes_through_entity_without_device(make_app, sample_entities, sample_registry):
    config = _list_config(["switch.fan"])  # no device_id in registry
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        assert app._log_entity_ids == {"switch.fan"}


async def test_device_log_sends_every_device_id_over_the_list(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        assert set(app.client.logbook_calls[-1][3]) == {"dev_abc", "dev_xyz"}


async def test_A_second_press_narrows_to_cursor_device_then_third_closes(make_app, sample_entities, sample_registry):
    # Row 0 after sort: light.kitchen_light (dev_abc); row 1: light.living_room_lamp (dev_abc).
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.jump_cursor_to_row_key("sensor.temperature")
        await pilot.pause()

        await pilot.press("A")  # 1st: list-wide, every device
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")
        assert set(app.client.logbook_calls[-1][3]) == {"dev_abc", "dev_xyz"}

        await pilot.press("A")  # 2nd: narrows to the cursor's device
        await pilot.pause()
        assert panel.has_class("-visible")
        assert app.client.logbook_calls[-1][3] == ["dev_xyz"]
        assert app._log_entity_ids == {"sensor.temperature"}
        title = str(panel.query_one("#log_title", Label).content)
        assert "devices)" not in title

        await pilot.press("A")  # 3rd: closes
        await pilot.pause()
        assert not panel.has_class("-visible")


async def test_left_arrow_paging_preserves_device_scope(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        assert app.client.logbook_calls[-1][3] == ["dev_abc"]

        await pilot.press("left")
        await pilot.pause()
        assert app.client.logbook_calls[-1][3] == ["dev_abc"]


async def test_device_log_empty_list_notifies_and_stays_hidden(make_app, sample_entities, sample_registry):
    config = _list_config([])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("A")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert not panel.has_class("-visible")


async def test_expand_helper_dedupes_and_counts_devices(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test():
        # Both list entities belong to dev_abc -> one device, deduped to two entities.
        expanded, device_ids = app._expand_to_device_entity_ids(["light.living_room_lamp", "light.kitchen_light"])
        assert device_ids == ["dev_abc"]
        assert expanded == ["light.living_room_lamp", "light.kitchen_light"]

        # An entity with no registry entry passes through as itself, no device.
        expanded, device_ids = app._expand_to_device_entity_ids(["sensor.unknown"])
        assert expanded == ["sensor.unknown"]
        assert device_ids == []
