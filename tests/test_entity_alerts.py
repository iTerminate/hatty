# hatty — MIT License. See LICENSE file for details.
"""Acceptance tests for entity change alerts (issue #224): a live state_changed
event on a watched entity should notify + highlight it end to end. The
negative cases here (unwatched entity, attribute-only change) exist to confirm
the wiring discriminates correctly at the app level; the same distinctions are
unit-tested directly in tests/unit/test_notifications.py."""

from hatty.const import NOTIFY_LIST_NAME
from hatty.ui.entity_table import EntitiesTable
from tests.conftest import make_config, notified

# Notifications default to enabled (toast/beep/highlight on, desktop/ntfy off —
# see config.default_config), so pre-seeding the reserved list is all this needs.
_WATCH_CONFIG = make_config(lists={NOTIFY_LIST_NAME: ["switch.fan"]})


async def test_state_change_alert_wiring(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_WATCH_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()

        # Changing an unwatched entity doesn't alert.
        old_state = {**sample_entities[0], "state": "on"}  # light.living_room_lamp, not watched
        new_state = {**sample_entities[0], "state": "off"}
        app.client.inject_state_change(new_state, old_state)
        await pilot.pause()
        assert not notified(app, title="Entity Alert")
        assert app.notify_ctl.alerted == set()

        # An attribute-only change on the watched entity doesn't alert either.
        same_state = {**sample_entities[1], "state": "off"}
        changed_attrs = {**same_state, "attributes": {**same_state["attributes"], "icon": "mdi:fan"}}
        app.client.inject_state_change(changed_attrs, same_state)
        await pilot.pause()
        assert not notified(app, title="Entity Alert")
        assert app.notify_ctl.alerted == set()

        # A real state-value change on the watched entity alerts + highlights.
        old_state = {**sample_entities[1], "state": "off"}  # switch.fan
        new_state = {**sample_entities[1], "state": "on"}
        app.client.inject_state_change(new_state, old_state)
        await pilot.pause()

        assert notified(app, title="Entity Alert", message_contains="off → on")
        assert app.notify_ctl.alerted == {"switch.fan"}

        table = app.query_one(EntitiesTable)
        row_key = table.get_row_index("switch.fan")
        assert table.get_row_at(row_key)  # sanity: row still renders


async def test_notifications_disabled_hides_reserved_list_but_keeps_membership(make_app, sample_entities):
    disabled_config = make_config(lists={NOTIFY_LIST_NAME: ["switch.fan"]}, notifications={"enabled": False})
    app = make_app(entities=sample_entities, config_data=disabled_config)
    async with app.run_test() as pilot:
        await pilot.pause()

        assert NOTIFY_LIST_NAME not in app.list_names
        assert app.entity_lists[NOTIFY_LIST_NAME] == ["switch.fan"]  # data intact, just hidden

        # And a state change doesn't alert while disabled.
        old_state = {**sample_entities[1], "state": "off"}
        new_state = {**sample_entities[1], "state": "on"}
        app.client.inject_state_change(new_state, old_state)
        await pilot.pause()
        assert not notified(app, title="Entity Alert")
