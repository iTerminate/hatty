# hatty — MIT License. See LICENSE file for details.
"""`v` opens a preview-then-commit popup for the activity log's scope
(issue #38), replacing the old blind cycle (issue #27, mirrored on the
fullscreen graph by issue #21) — a scope change in place, not a reopen, so
the paged window and the maximized state survive committing a new one."""

from textual.widgets import Label, Log, OptionList, Static

import hatty.controllers.logbook as logbook_module
from hatty.ui.activity_log_panel import ActivityLogPanel
from hatty.ui.log_scope_popup import LogScopePopup
from tests.conftest import make_config, notified
from tests.test_graph_event_log import _open_preview_on_temperature

# sample_registry fixture is shared from tests/conftest.py.


def _list_config(list_entities):
    return {
        **make_config(),
        "lists": {"my_list": list_entities},
        "default_list": "my_list",
    }


async def _pick_via_popup(pilot, index: int) -> None:
    """Open the popup (assumes it's not already open), jump to the row at
    `index`, and commit it."""
    await pilot.press("v")
    await pilot.pause()
    await pilot.press("home")
    for _ in range(index):
        await pilot.press("down")
    await pilot.press("enter")
    await pilot.pause()


async def test_v_opens_the_popup_with_four_options_for_a_table_base(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a", "v")
        await pilot.pause()
        assert isinstance(app.screen, LogScopePopup)
        options = app.screen.query_one("#log_scope_options", OptionList)
        assert options.option_count == 4


async def test_v_offers_two_options_for_a_fixed_entity_base(make_app, sample_entities, sample_registry):
    app = make_app(entities=sample_entities, config_data=make_config(lists={}), registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.jump_cursor_to_row_key("light.living_room_lamp")
        await pilot.pause()
        await pilot.press("i", "v")
        await pilot.pause()
        assert isinstance(app.screen, LogScopePopup)
        options = app.screen.query_one("#log_scope_options", OptionList)
        assert options.option_count == 2


async def test_v_offers_two_options_on_the_graph_screen(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=make_config(lists={}))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.client._history_data = {"sensor.temperature": [("2024-01-01T12:00:00+00:00", 20.0)]}
        await _open_preview_on_temperature(pilot, app)
        await pilot.press("a", "v")
        await pilot.pause()
        assert isinstance(app.screen, LogScopePopup)
        options = app.screen.query_one("#log_scope_options", OptionList)
        assert options.option_count == 2


async def test_cursor_options_omitted_when_no_row_is_selected(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()

        app.search_term = "zzz_no_match"
        app._update_entities_display()
        await pilot.pause()

        await pilot.press("v")
        await pilot.pause()
        options = app.screen.query_one("#log_scope_options", OptionList)
        assert options.option_count == 2  # cursor / cursor_device both unresolvable


async def test_highlighting_previews_entity_and_device_names(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    devices = [{"id": "dev_abc", "name": "Living Room Hub"}, {"id": "dev_xyz", "name": "Temperature Hub"}]
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry, devices=devices)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a", "v")
        await pilot.pause()

        preview = app.screen.query_one("#log_scope_preview_body", Static)
        assert "Living Room Lamp" in str(preview.content)
        assert "Temperature Sensor" in str(preview.content)

        await pilot.press("down")  # list_devices
        await pilot.pause()
        assert "Living Room Hub" in str(preview.content)  # devices are shown by name, not id
        summary = app.screen.query_one("#log_scope_summary", Label)
        assert "device" in str(summary.content)


async def test_cap_notice_in_summary_and_toast_fires_only_on_apply(
    make_app, sample_entities, sample_registry, monkeypatch
):
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    monkeypatch.setattr(logbook_module, "_DEVICE_LOG_MAX_DEVICES", 1)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a", "v")
        await pilot.pause()

        await pilot.press("down")  # list_devices — widened to 2 devices, capped to 1
        await pilot.pause()
        summary = app.screen.query_one("#log_scope_summary", Label)
        assert "first 1 of 2 devices" in str(summary.content)
        assert not notified(app, title="Device Log")  # highlighting alone must not toast

        await pilot.press("enter")
        await pilot.pause()
        assert app.client.logbook_calls[-1][3] == ["dev_abc"]
        assert notified(app, title="Device Log")


async def test_enter_applies_and_preserves_paged_window_and_maximized(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("left")  # page back
        await pilot.press("f")  # maximize
        await pilot.pause()
        paged_end = app.log_ctl.session_for(app).end
        assert paged_end is not None
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-maximized")

        await _pick_via_popup(pilot, 1)  # list_devices

        assert app.log_ctl.session_for(app).option_id == "list_devices"
        assert app.log_ctl.session_for(app).end == paged_end
        assert panel.has_class("-maximized")
        last_call = app.client.logbook_calls[-1]
        assert last_call[2] == paged_end
        assert last_call[3] == ["dev_abc", "dev_xyz"]


async def test_v_resubscribes_the_live_stream_with_the_new_scope(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert app.client.subscribe_logbook_calls[-1] == (["light.living_room_lamp"], [])

        await _pick_via_popup(pilot, 1)  # list_devices

        assert app.client.subscribe_logbook_calls[-1] == (["light.living_room_lamp"], ["dev_abc"])


async def test_escape_cancels_leaving_scope_untouched(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        calls_before = len(app.client.logbook_calls)

        await pilot.press("v")
        await pilot.pause()
        await pilot.press("down", "down")  # move around, but never commit
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()
        assert app.log_ctl.session_for(app).option_id == "list"
        assert len(app.client.logbook_calls) == calls_before
        panel = app.query_one("#activity_log_panel", ActivityLogPanel)
        assert panel.has_class("-visible")  # back on the main screen, log untouched


async def test_v_is_a_noop_while_the_log_is_closed(make_app):
    app = make_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.check_action("show_log_scope", ()) is False

        await pilot.press("v")
        await pilot.pause()
        assert not app.query_one("#activity_log_panel", ActivityLogPanel).has_class("-visible")


async def test_reaching_cursor_device_retargets_the_live_append_filter(make_app, sample_entities, sample_registry):
    config = _list_config(["light.living_room_lamp", "sensor.temperature"])
    app = make_app(entities=sample_entities, config_data=config, registry=sample_registry)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("EntitiesTable")
        table.jump_cursor_to_row_key("light.living_room_lamp")
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()

        await _pick_via_popup(pilot, 3)  # cursor_device
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
