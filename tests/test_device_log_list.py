# hatty — MIT License. See LICENSE file for details.
"""Device log expands a whole list to its devices' entities (issue #69)."""

import pytest
from textual.widgets import Label

from hatty.ui.activity_log_panel import ActivityLogPanel
from tests.conftest import make_config


@pytest.fixture
def sample_registry():
    return [
        {"entity_id": "light.living_room_lamp", "device_id": "dev_abc"},
        {"entity_id": "light.kitchen_light", "device_id": "dev_abc"},
        {"entity_id": "sensor.temperature", "device_id": "dev_xyz"},
        {"entity_id": "switch.fan", "device_id": None},
    ]


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
        expanded, count = app._expand_to_device_entity_ids(["light.living_room_lamp", "light.kitchen_light"])
        assert count == 1
        assert expanded == ["light.living_room_lamp", "light.kitchen_light"]

        # An entity with no registry entry passes through as itself, no device.
        expanded, count = app._expand_to_device_entity_ids(["sensor.unknown"])
        assert expanded == ["sensor.unknown"]
        assert count == 0
