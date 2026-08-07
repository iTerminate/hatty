# hatty — MIT License. See LICENSE file for details.
from datetime import datetime, timedelta, timezone

from rich.text import Text
from textual.app import App, ComposeResult

from hatty.ui.entity_table import (
    DEFAULT_COLUMNS,
    EntitiesTable,
    entity_matches,
    entity_title,
    entity_unit,
    format_relative,
    get_display_name,
    is_dead,
)


class TableApp(App):
    def compose(self) -> ComposeResult:
        yield EntitiesTable(id="table")


SAMPLE = [
    {
        "entity_id": "light.lamp",
        "state": "on",
        "attributes": {"friendly_name": "Lamp"},
        "last_changed": "",
    },
    {
        "entity_id": "sensor.temp",
        "state": "21",
        "attributes": {"friendly_name": "Temp", "unit_of_measurement": "°C"},
        "last_changed": "",
    },
    {
        "entity_id": "switch.fan",
        "state": "off",
        "attributes": {"friendly_name": "Fan"},
        "last_changed": "",
    },
]


def _update(table, entities, entity_lists=None, current_list_name=None, columns=None):
    table.update_table_data(
        entities_to_display=entities,
        entity_lists=entity_lists or {},
        current_list_name=current_list_name,
        columns=columns,
    )


async def test_update_table_data_renders_all_rows():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, SAMPLE)
        assert table.row_count == 3


async def test_in_list_entities_sorted_to_top():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, SAMPLE, {"my_list": ["sensor.temp"]}, "my_list", columns=["name", "state", "entity_id"])
        row_0 = table.get_row_at(0)
        assert str(row_0[2]) == "sensor.temp"


async def test_manual_sort_list_uses_stored_order_not_alphabetical():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        # Deliberately not alphabetical by display name (Fan/Lamp/Temp).
        stored_order = ["sensor.temp", "switch.fan", "light.lamp"]
        table.update_table_data(
            entities_to_display=SAMPLE,
            entity_lists={"my_list": stored_order},
            current_list_name="my_list",
            columns=["name", "state", "entity_id"],
            manual_lists={"my_list"},
        )
        displayed = [str(table.get_row_at(i)[2]) for i in range(table.row_count)]
        assert displayed == stored_order


async def test_list_without_manual_flag_still_sorts_alphabetically():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        stored_order = ["sensor.temp", "switch.fan", "light.lamp"]  # same as above, not alphabetical
        table.update_table_data(
            entities_to_display=SAMPLE,
            entity_lists={"my_list": stored_order},
            current_list_name="my_list",
            columns=["name", "state", "entity_id"],
            manual_lists=set(),  # today's default: alphabetical regardless of stored order
        )
        displayed = [str(table.get_row_at(i)[2]) for i in range(table.row_count)]
        assert displayed == ["switch.fan", "light.lamp", "sensor.temp"]  # Fan, Lamp, Temp


async def test_in_list_entities_have_star():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, SAMPLE, {"my_list": ["light.lamp"]}, "my_list", columns=["name", "in_list"])
        row_0 = table.get_row_at(0)
        assert str(row_0[1]) == "✓"


async def test_entities_not_in_list_have_no_star():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, SAMPLE, {"my_list": ["light.lamp"]}, "my_list", columns=["name", "in_list"])
        row_1 = table.get_row_at(1)
        assert str(row_1[1]) == ""


async def test_entities_sorted_alphabetically():
    entities = [
        {"entity_id": "a.zebra", "state": "off", "attributes": {"friendly_name": "Zebra"}, "last_changed": ""},
        {"entity_id": "a.apple", "state": "on", "attributes": {"friendly_name": "Apple"}, "last_changed": ""},
        {"entity_id": "a.mango", "state": "off", "attributes": {"friendly_name": "Mango"}, "last_changed": ""},
    ]
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, entities)
        names = [str(table.get_row_at(i)[0]) for i in range(3)]
        assert names == ["Apple", "Mango", "Zebra"]


async def test_in_list_group_sorted_alphabetically_before_others():
    entities = [
        {"entity_id": "a.zebra", "state": "off", "attributes": {"friendly_name": "Zebra"}, "last_changed": ""},
        {"entity_id": "a.apple", "state": "on", "attributes": {"friendly_name": "Apple"}, "last_changed": ""},
        {"entity_id": "a.mango", "state": "off", "attributes": {"friendly_name": "Mango"}, "last_changed": ""},
    ]
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, entities, {"my_list": ["a.zebra", "a.mango"]}, "my_list")
        names = [str(table.get_row_at(i)[0]) for i in range(3)]
        assert names == ["Mango", "Zebra", "Apple"]


async def test_unit_column_renders_unit_of_measurement():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, SAMPLE, columns=["name", "state", "unit"])
        row_temp = table.get_row_at(2)
        assert str(row_temp[2]) == "°C"


async def test_unit_column_empty_when_no_unit():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, SAMPLE, columns=["name", "state", "unit"])
        row_fan = table.get_row_at(0)
        assert str(row_fan[2]) == ""


async def test_column_width_shrinks_after_filtering_to_shorter_content():
    wide_entity = {
        "entity_id": "sensor.long",
        "state": "on",
        "attributes": {"friendly_name": "A Very Long Friendly Name For This Entity"},
        "last_changed": "",
    }
    narrow_entity = {
        "entity_id": "a.x",
        "state": "on",
        "attributes": {"friendly_name": "X"},
        "last_changed": "",
    }
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, [wide_entity], columns=["name"])
        await pilot.pause()
        wide_width = table.ordered_columns[0].content_width

        _update(table, [narrow_entity], columns=["name"])
        await pilot.pause()
        narrow_width = table.ordered_columns[0].content_width

        assert narrow_width < wide_width


async def test_column_width_unchanged_when_only_data_changes():
    entity = {
        "entity_id": "sensor.s",
        "state": "on",
        "attributes": {"friendly_name": "S"},
        "last_changed": "",
    }
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, [entity], columns=["name", "state"])
        await pilot.pause()
        width_before = table.ordered_columns[1].content_width

        updated_entity = dict(entity, state="unavailable")
        _update(table, [updated_entity], columns=["name", "state"])
        await pilot.pause()
        width_after = table.ordered_columns[1].content_width

        assert width_after == width_before
        row_0 = table.get_row_at(0)
        assert str(row_0[1]) == "unavailable"


async def test_column_width_recomputes_when_entity_set_changes():
    entity_a = {
        "entity_id": "sensor.a",
        "state": "on",
        "attributes": {"friendly_name": "A"},
        "last_changed": "",
    }
    entity_b = {
        "entity_id": "sensor.b",
        "state": "a very very long state value indeed",
        "attributes": {"friendly_name": "B"},
        "last_changed": "",
    }
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, [entity_a], columns=["name", "state"])
        await pilot.pause()
        width_before = table.ordered_columns[1].content_width

        _update(table, [entity_a, entity_b], columns=["name", "state"])
        await pilot.pause()
        width_after = table.ordered_columns[1].content_width

        assert width_after > width_before
        assert table.row_count == 2


async def test_column_change_rebuilds_headers():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, SAMPLE, columns=["name", "state"])
        assert list(table.columns.keys()) == ["name", "state"]
        _update(table, SAMPLE, columns=["name", "state", "unit"])
        assert list(table.columns.keys()) == ["name", "state", "unit"]


def test_entity_unit_present_and_missing():
    assert entity_unit({"attributes": {"unit_of_measurement": "°C"}}) == "°C"
    assert entity_unit({"attributes": {}}) == ""
    assert entity_unit({}) == ""
    # None and empty-string units both normalize to "".
    assert entity_unit({"attributes": {"unit_of_measurement": None}}) == ""
    assert entity_unit({"attributes": {"unit_of_measurement": ""}}) == ""


def test_entity_title_core_and_options():
    entity = {
        "entity_id": "sensor.temp",
        "state": "21.5",
        "attributes": {"friendly_name": "Living Room", "unit_of_measurement": "°C"},
    }
    assert entity_title(entity).plain == "Living Room — 21.5°C"
    assert entity_title(entity, mode_label="Line").plain == "Living Room — 21.5°C  [Line]"
    assert entity_title(entity, extra_count=2).plain == "Living Room +2 more — 21.5°C"
    assert entity_title(entity, show_unit=False).plain == "Living Room — 21.5"


def test_entity_title_is_markup_safe():
    # A friendly_name with Rich markup must render as literal text, not styling (#157).
    entity = {"entity_id": "x", "state": "on", "attributes": {"friendly_name": "[red]Boom"}}
    title = entity_title(entity)
    assert isinstance(title, Text)
    assert title.plain == "[red]Boom — on"


def test_default_columns_constant():
    assert DEFAULT_COLUMNS == ["name", "value", "last_changed", "in_list"]


def test_format_relative_just_now():
    iso = datetime.now(timezone.utc).isoformat()
    assert format_relative(iso) == "just now"


def test_format_relative_minutes():
    iso = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert format_relative(iso) == "5m ago"


def test_format_relative_hours():
    iso = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    assert format_relative(iso) == "3h ago"


def test_format_relative_days():
    iso = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    assert format_relative(iso) == "2d ago"


def test_format_relative_empty_string():
    assert format_relative("") == ""


def test_format_relative_invalid():
    assert format_relative("not-a-date") == "not-a-date"


def test_entity_matches_by_entity_id():
    assert entity_matches(SAMPLE[2], "fan") is True


def test_entity_matches_by_friendly_name():
    assert entity_matches(SAMPLE[0], "lamp") is True


def test_entity_matches_by_state():
    assert entity_matches(SAMPLE[1], "21") is True


def test_entity_matches_returns_false_when_no_match():
    assert entity_matches(SAMPLE[0], "nonexistent") is False


_LIVING_ROOM_LAMP = {
    "entity_id": "light.living_room_lamp",
    "state": "on",
    "attributes": {"friendly_name": "Living Room Lamp"},
    "last_changed": "",
}


def test_entity_matches_multi_word_skips_words():
    assert entity_matches(_LIVING_ROOM_LAMP, "living lamp") is True


def test_entity_matches_multi_word_is_order_independent():
    assert entity_matches(_LIVING_ROOM_LAMP, "lamp living") is True


def test_entity_matches_multi_word_requires_every_word():
    assert entity_matches(_LIVING_ROOM_LAMP, "living kitchen") is False


async def test_jump_cursor_to_row_key_moves_cursor():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, SAMPLE, columns=["name", "state", "entity_id"])
        assert table.jump_cursor_to_row_key("switch.fan") is True
        cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
        assert cell_key.row_key.value == "switch.fan"


async def test_jump_cursor_to_row_key_returns_false_when_missing():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, SAMPLE, columns=["name", "state", "entity_id"])
        assert table.jump_cursor_to_row_key("light.nonexistent") is False


async def test_value_column_joins_state_and_unit():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, SAMPLE, columns=["value"])
        row_temp = table.get_row_at(2)  # sensor.temp, state "21", unit "°C"
        assert str(row_temp[0]) == "21°C"


async def test_value_column_shows_state_only_when_no_unit():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, SAMPLE, columns=["value"])
        row_lamp = table.get_row_at(1)  # light.lamp, state "on", no unit
        assert str(row_lamp[0]) == "on"


async def test_value_column_shows_pending_suffix():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        table.update_table_data(
            entities_to_display=SAMPLE,
            entity_lists={},
            current_list_name=None,
            columns=["value"],
            pending_status={"light.lamp": "pending"},
        )
        row_lamp = table.get_row_at(1)
        assert "⏳" in str(row_lamp[0])


async def test_value_column_shows_stalled_suffix():
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        table.update_table_data(
            entities_to_display=SAMPLE,
            entity_lists={},
            current_list_name=None,
            columns=["value"],
            pending_status={"light.lamp": "stalled"},
        )
        row_lamp = table.get_row_at(1)
        assert "unresponsive" in str(row_lamp[0])


def test_get_display_name_falls_back_to_friendly_name():
    entity = {"entity_id": "light.lamp", "attributes": {"friendly_name": "Lamp"}}
    assert get_display_name(entity) == "Lamp"


def test_get_display_name_falls_back_to_entity_id():
    entity = {"entity_id": "light.lamp", "attributes": {}}
    assert get_display_name(entity) == "light.lamp"


def test_get_display_name_uses_override_when_present():
    entity = {
        "entity_id": "light.lamp",
        "attributes": {"friendly_name": "Lamp"},
        "_local_name_override": "Reading Light",
    }
    assert get_display_name(entity) == "Reading Light"


def test_get_display_name_override_none_falls_back():
    entity = {"entity_id": "light.lamp", "attributes": {"friendly_name": "Lamp"}, "_local_name_override": None}
    assert get_display_name(entity) == "Lamp"


def test_is_dead_matches_only_dead_states():
    assert is_dead({"state": "unavailable"}) is True
    assert is_dead({"state": "unknown"}) is True
    assert is_dead({"state": "on"}) is False
    assert is_dead({"state": ""}) is False
    assert is_dead({}) is False


async def test_dead_entity_cells_are_dimmed():
    entities = [
        {
            "entity_id": "sensor.dead",
            "state": "unavailable",
            "attributes": {"friendly_name": "Dead"},
            "last_changed": "",
        },
        {"entity_id": "sensor.live", "state": "21", "attributes": {"friendly_name": "Live"}, "last_changed": ""},
    ]
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, entities, columns=["name", "state"])
        dead_name = table.get_row_at(0)[0]
        live_name = table.get_row_at(1)[0]
        assert isinstance(dead_name, Text)
        assert "dim" in str(dead_name.style)
        # A healthy entity's cell is still a Text (markup-escaped, #157) but not dimmed.
        assert isinstance(live_name, Text)
        assert "dim" not in str(live_name.style)


async def test_markup_in_ha_strings_is_escaped_not_parsed():
    # Entity names/states come from HA and must not be parsed as Rich markup:
    # "[red]" would restyle the UI and a bare "[" crashes rendering (#157).
    entities = [
        {
            "entity_id": "sensor.evil",
            "state": "on [danger",
            "attributes": {"friendly_name": "[red]Pwn[/red]"},
            "last_changed": "",
        },
    ]
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, entities, columns=["name", "state"])
        # No MarkupError raised, and the value round-trips literally (markup escaped).
        name_cell = table.get_row_at(0)[0]
        state_cell = table.get_row_at(0)[1]
        assert isinstance(name_cell, Text)
        assert name_cell.plain == "[red]Pwn[/red]"
        assert isinstance(state_cell, Text)
        assert state_cell.plain == "on [danger"
        # Forcing a render must not raise MarkupError.
        pilot.app.query_one("#table", EntitiesTable).refresh()
        await pilot.pause()


async def test_dead_entity_dimmed_on_in_place_update():
    entity = {"entity_id": "sensor.s", "state": "21", "attributes": {"friendly_name": "S"}, "last_changed": ""}
    async with TableApp().run_test() as pilot:
        table = pilot.app.query_one("#table", EntitiesTable)
        _update(table, [entity], columns=["name", "state"])
        live_name = table.get_row_at(0)[0]
        assert isinstance(live_name, Text)  # escaped, but not dimmed (#157)
        assert "dim" not in str(live_name.style)
        # Same entity set → fast in-place path; going dead should dim it.
        _update(table, [dict(entity, state="unavailable")], columns=["name", "state"])
        dead_name = table.get_row_at(0)[0]
        assert isinstance(dead_name, Text)
        assert "dim" in str(dead_name.style)
