# hatty — MIT License. See LICENSE file for details.
"""`v` widens the activity log over a whole list: its entities' devices
(issue #69), then narrows to the cursor's entity and its device, then wraps
(issue #27)."""

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


async def test_v_adds_the_lists_device_ids_without_expanding_siblings(make_app, sample_entities, sample_registry):
    # List has one light; its device dev_abc also owns kitchen_light, but the
    # "base_devices" view (v once) only widens the event-type query, not the
    # entity set.
    config = _list_config(["light.living_room_lamp"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.current_list_name == "my_list"
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")
        assert app._log_entity_ids == {"light.living_room_lamp"}
        assert app.client.logbook_calls[-1][3] == ["dev_abc"]


async def test_v_title_shows_list_and_device_count(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        title = str(panel.query_one("#log_title", Label).content)
        assert "Device Log" in title
        assert "my_list" in title
        assert "2 devices" in title


async def test_v_passes_through_entity_without_device(make_app, sample_entities, sample_registry):
    config = _list_config(["switch.fan"])  # no device_id in registry
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        assert app._log_entity_ids == {"switch.fan"}


async def test_v_sends_every_device_id_over_the_list(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        assert set(app.client.logbook_calls[-1][3]) == {"dev_abc", "dev_xyz"}


async def test_v_cycles_the_list_base_through_four_scopes_and_wraps(make_app, sample_entities, sample_registry):
    # Row 0 after sort: light.kitchen_light (dev_abc); row 1: light.living_room_lamp (dev_abc).
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.jump_cursor_to_row_key("sensor.temperature")
        await pilot.pause()

        await pilot.press("a")  # 1: list entities only
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")
        assert app._log_entity_ids == {"light.living_room_lamp", "sensor.temperature"}
        assert app.client.logbook_calls[-1][3] == []

        await pilot.press("v")  # 2: list entities' devices
        await pilot.pause()
        assert app._log_entity_ids == {"light.living_room_lamp", "sensor.temperature"}
        assert set(app.client.logbook_calls[-1][3]) == {"dev_abc", "dev_xyz"}

        await pilot.press("v")  # 3: the cursor entity alone
        await pilot.pause()
        assert app._log_entity_ids == {"sensor.temperature"}
        assert app.client.logbook_calls[-1][3] == []
        title = str(panel.query_one("#log_title", Label).content)
        assert title.startswith("Activity Log — Temperature Sensor")

        await pilot.press("v")  # 4: the cursor entity's device
        await pilot.pause()
        assert app.client.logbook_calls[-1][3] == ["dev_xyz"]
        assert app._log_entity_ids == {"sensor.temperature"}
        title = str(panel.query_one("#log_title", Label).content)
        assert "devices)" not in title  # a single device never shows the count suffix

        await pilot.press("v")  # wraps back to the plain list scope
        await pilot.pause()
        assert app._log_entity_ids == {"light.living_room_lamp", "sensor.temperature"}
        assert app.client.logbook_calls[-1][3] == []
        assert panel.has_class("-visible")  # the cycle never closes the panel


async def test_left_arrow_paging_preserves_device_scope(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("v")
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
        await pilot.press("a")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert not panel.has_class("-visible")
