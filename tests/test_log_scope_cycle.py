# hatty — MIT License. See LICENSE file for details.
"""`v` cycles the main screen's activity log scope in place (issue #27),
mirroring the fullscreen graph's `v` (issue #21) — a scope change, not a
reopen, so the paged window and the maximized state survive it."""

from textual.widgets import Label, Log

import hatty.controllers.logbook as logbook_module
from hatty.ui.activity_log_panel import ActivityLogPanel
from tests.conftest import make_config

# sample_registry fixture is shared from tests/conftest.py.


def _list_config(list_entities):
    return {
        **make_config(),
        "lists": {"my_list": list_entities},
        "default_list": "my_list",
    }


async def test_v_preserves_the_paged_window(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("left")
        await pilot.pause()
        paged_end = app.log_ctl.session_for(app).end
        assert paged_end is not None

        await pilot.press("v")
        await pilot.pause()

        assert app.log_ctl.session_for(app).end == paged_end
        last_call = app.client.logbook_calls[-1]
        assert last_call[2] == paged_end  # end


async def test_v_preserves_the_maximized_panel(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-maximized")

        await pilot.press("v")
        await pilot.pause()

        assert panel.has_class("-maximized")


async def test_v_resubscribes_the_live_stream_with_the_new_scope(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert app.client.subscribe_logbook_calls[-1] == (["light.living_room_lamp"], [])

        await pilot.press("v")
        await pilot.pause()

        assert app.client.subscribe_logbook_calls[-1] == (["light.living_room_lamp"], ["dev_abc"])


async def test_v_stays_unsubscribed_while_paged_back(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("left")
        await pilot.pause()
        assert app.client.logbook_subscription_id is None

        await pilot.press("v")
        await pilot.pause()

        assert app.client.logbook_subscription_id is None


async def test_v_v_v_retargets_the_live_append_filter(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.jump_cursor_to_row_key("light.living_room_lamp")
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("v")  # base_devices
        await pilot.pause()
        await pilot.press("v")  # cursor: narrows to living_room_lamp alone
        await pilot.pause()
        await pilot.press("v")  # cursor_device: sibling kitchen_light now in scope
        await pilot.pause()
        assert app.log_ctl.session_for(app).entity_ids == {"light.living_room_lamp", "light.kitchen_light"}

        app.client.logbook_subscription_id = None
        log_widget = app.query_one("#activity_log_panel", ActivityLogPanel).query_one("#log_widget", Log)
        count_before = log_widget.line_count

        app.client.inject_state_change(
            {
                "entity_id": "light.kitchen_light",
                "state": "on",
                "attributes": {"friendly_name": "Kitchen Light"},
                "last_changed": "2024-01-15T10:32:00.000000+00:00",
            }
        )
        await pilot.pause()
        assert log_widget.line_count == count_before + 1

        # An entity outside every widened view (not in the list, no shared device)
        # is still filtered out.
        count_before = log_widget.line_count
        app.client.inject_state_change(
            {
                "entity_id": "sensor.temperature",
                "state": "22.0",
                "attributes": {"friendly_name": "Temperature Sensor"},
                "last_changed": "2024-01-15T10:33:00.000000+00:00",
            }
        )
        await pilot.pause()
        assert log_widget.line_count == count_before


async def test_v_is_a_noop_while_the_log_is_closed(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.check_action("cycle_log_scope", ()) is False

        await pilot.press("v")
        await pilot.pause()
        assert not app.query_one("#activity_log_panel", ActivityLogPanel).has_class("-visible")


async def test_v_skips_the_cursor_views_when_no_row_is_selected(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()

        # Filter the table down to no rows, so _selected_entity_id() has nothing
        # to resolve for the cursor-scoped views.
        app.search_term = "zzz_no_match"
        app._update_entities_display()
        await pilot.pause()

        await pilot.press("v")  # base_devices
        await pilot.pause()
        await pilot.press("v")  # cursor / cursor_device would resolve to nothing — skip straight back to base
        await pilot.pause()

        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")
        title = str(panel.query_one("#log_title", Label).content)
        assert title.startswith("Activity Log — my_list")
        assert app.log_ctl.session_for(app).entity_ids == {"light.living_room_lamp", "sensor.temperature"}


async def test_v_caps_the_widened_scope(make_app, sample_entities, sample_registry, monkeypatch):
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    monkeypatch.setattr(logbook_module, "_DEVICE_LOG_MAX_DEVICES", 1)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()

        assert len(app.client.logbook_calls[-1][3]) == 1


async def test_v_walks_the_fixed_base_through_two_views_and_wraps(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=make_config(lists={}), registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.jump_cursor_to_row_key("light.living_room_lamp")
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        title = str(panel.query_one("#log_title", Label).content)
        assert title.startswith("Activity Log")
        assert app.client.logbook_calls[-1][3] == []

        await pilot.press("v")
        await pilot.pause()
        title = str(panel.query_one("#log_title", Label).content)
        assert title.startswith("Device Log")
        assert app.client.logbook_calls[-1][3] == ["dev_abc"]
        assert app.log_ctl.session_for(app).entity_ids == {"light.living_room_lamp"}

        await pilot.press("v")  # wraps — a fixed base has no cursor views
        await pilot.pause()
        title = str(panel.query_one("#log_title", Label).content)
        assert title.startswith("Activity Log")
        assert app.client.logbook_calls[-1][3] == []
        assert app.log_ctl.session_for(app).entity_ids == {"light.living_room_lamp"}
