# hatty — MIT License. See LICENSE file for details.
"""Acceptance tests for the device/area tree view (issue #124)."""

from textual.widgets import Tree

from hatty.ui.device_tree_screen import (
    NO_DEVICE_LABEL,
    NO_INTEGRATION_LABEL,
    UNASSIGNED_LABEL,
    AreaNamePopup,
    AreaPickerPopup,
    DeviceInfoPopup,
    DeviceTreeScreen,
)
from hatty.ui.entity_table import EntitiesTable
from tests.conftest import make_config


async def _focus_node(pilot, app, node) -> None:
    """Point the tree cursor at a node, expanding its parents so it's visible."""
    tree = app.screen.query_one(Tree)
    parent = node.parent
    while parent is not None:
        parent.expand()
        parent = parent.parent
    await pilot.pause()
    tree.move_cursor(node)
    await pilot.pause()


async def _focus_leaf(pilot, app, entity_id: str) -> None:
    await _focus_node(pilot, app, app.screen._entity_nodes[entity_id][0])


REGISTRY = [
    {"entity_id": "light.living_room_lamp", "device_id": "dev_lamp"},
    {"entity_id": "sensor.temperature", "device_id": "dev_lamp"},
    {"entity_id": "switch.fan", "device_id": "dev_fan"},
    {"entity_id": "light.kitchen_light"},  # no device
]
DEVICES = [
    {"id": "dev_lamp", "name": "Lamp", "area_id": "living_room"},
    {"id": "dev_fan", "name_by_user": "Fan", "area_id": None},
]
AREAS = [
    {"area_id": "living_room", "name": "Living Room"},
    {"area_id": "kitchen", "name": "Kitchen"},
]


def _labels(node):
    return [str(child.label) for child in node.children]


def _child_by_data(node, key, value):
    return next(c for c in node.children if (c.data or {}).get(key) == value)


async def test_D_opens_device_tree_in_device_mode(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()

        assert isinstance(app.screen, DeviceTreeScreen)
        tree = app.screen.query_one(Tree)
        # Device mode: flat Device -> Entity, sorted by device name, no-device last.
        assert _labels(tree.root) == ["Fan", "Lamp", NO_DEVICE_LABEL]
        lamp = _child_by_data(tree.root, "device_id", "dev_lamp")
        assert [(c.data or {}).get("entity_id") for c in lamp.children] == [
            "light.living_room_lamp",
            "sensor.temperature",
        ]


async def test_disabled_entity_is_hidden_from_tree(make_app):
    registry = [
        {"entity_id": "light.living_room_lamp", "device_id": "dev_lamp"},
        {"entity_id": "sensor.battery", "device_id": "dev_lamp", "disabled_by": "user"},
    ]
    app = make_app(registry=registry, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()

        # The disabled entity has no leaf; its enabled device sibling still shows.
        assert "sensor.battery" not in app.screen._entity_nodes
        assert "light.living_room_lamp" in app.screen._entity_nodes
        lamp = _child_by_data(app.screen.query_one(Tree).root, "device_id", "dev_lamp")
        assert [(c.data or {}).get("entity_id") for c in lamp.children] == ["light.living_room_lamp"]


async def test_root_node_is_hidden(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()

        tree = app.screen.query_one(Tree)
        # The synthetic "Devices"/"Areas" root is hidden (issue #144); the cursor
        # opens on the table's selected entity (issue #153), never the hidden root.
        assert tree.show_root is False
        assert tree.cursor_node is not tree.root
        assert (tree.cursor_node.data or {}).get("entity_id") == "light.living_room_lamp"


async def test_v_toggles_to_area_grouping(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()

        tree = app.screen.query_one(Tree)
        # Area -> Device -> Entity. Only areas with devices appear (kitchen has
        # none); Fan has no area (Unassigned); the deviceless entity is No device.
        assert _labels(tree.root) == ["Living Room", UNASSIGNED_LABEL, NO_DEVICE_LABEL]
        living_room = _child_by_data(tree.root, "area_id", "living_room")
        assert _labels(living_room) == ["Lamp"]
        unassigned = tree.root.children[1]
        assert _labels(unassigned) == ["Fan"]
        # Areas collapse by default (issue #145) so a big home isn't a wall of
        # devices — except the area holding the followed selection, which the
        # cursor-follow expands (issue #153). The selection lives in Living Room,
        # so Unassigned (Fan) still demonstrates the default-collapsed state.
        assert living_room.is_expanded
        assert not unassigned.is_expanded


async def test_X_expands_all_and_x_collapses_all(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await pilot.press("v")  # area mode
        await pilot.pause()

        tree = app.screen.query_one(Tree)
        living_room = _child_by_data(tree.root, "area_id", "living_room")
        # Unassigned holds no followed entity, so it demonstrates the collapsed
        # default (Living Room is expanded to reveal the followed selection, #153).
        unassigned = tree.root.children[1]
        assert not unassigned.is_expanded

        await pilot.press("X")  # expand all
        await pilot.pause()
        lamp = _child_by_data(living_room, "device_id", "dev_lamp")
        assert living_room.is_expanded and lamp.is_expanded

        await pilot.press("x")  # collapse all
        await pilot.pause()
        assert not living_room.is_expanded
        # The hidden root stays expanded, so top-level areas remain visible.
        assert tree.root.is_expanded
        assert _labels(tree.root) == ["Living Room", UNASSIGNED_LABEL, NO_DEVICE_LABEL]


async def test_area_nodes_expand_under_active_filter(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await pilot.press("v")  # area mode
        await pilot.pause()
        await pilot.press("ctrl+s")  # area -> all, so the entity name matches (#206)
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press(*"temp")
        await pilot.pause()

        tree = app.screen.query_one(Tree)
        living_room = _child_by_data(tree.root, "area_id", "living_room")
        # A filter must auto-expand matching areas or the hits stay hidden.
        assert living_room.is_expanded


async def test_v_cycles_through_integration_grouping(make_app):
    registry = [
        {"entity_id": "light.living_room_lamp", "device_id": "dev_lamp", "platform": "hue"},
        {"entity_id": "sensor.temperature", "device_id": "dev_lamp", "platform": "hue"},
        {"entity_id": "switch.fan", "device_id": "dev_fan", "platform": "mqtt"},
        {"entity_id": "light.kitchen_light"},  # no device, no platform
    ]
    app = make_app(registry=registry, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await pilot.press("v", "v")  # device -> area -> integration
        await pilot.pause()

        assert app.screen._mode == "integration"
        tree = app.screen.query_one(Tree)
        assert _labels(tree.root) == ["hue", "mqtt", NO_INTEGRATION_LABEL]
        hue = _child_by_data(tree.root, "integration", "hue")
        assert _labels(hue) == ["Lamp"]

        # area-only actions are disabled in integration mode.
        assert app.screen.check_action("area_to_dashboard", ()) is False
        # devices are still movable.
        assert app.screen.check_action("move_device", ()) is True


async def test_entity_leaf_shows_and_refreshes_state(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()

        tree = app.screen.query_one(Tree)
        lamp = _child_by_data(tree.root, "device_id", "dev_lamp")
        leaf = _child_by_data(lamp, "entity_id", "light.living_room_lamp")
        # The lamp is in the default list, so it carries the in-list marker.
        assert str(leaf.label) == "Living Room Lamp — on ✓"

        app.client.inject_state_change(
            {
                "entity_id": "light.living_room_lamp",
                "state": "off",
                "attributes": {"friendly_name": "Living Room Lamp"},
            }
        )
        await pilot.pause()
        assert str(leaf.label) == "Living Room Lamp — off ✓"


async def test_i_on_device_node_opens_info_popup(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()

        tree = app.screen.query_one(Tree)
        lamp = _child_by_data(tree.root, "device_id", "dev_lamp")
        await _focus_node(pilot, app, lamp)
        await pilot.press("i")
        await pilot.pause()

        assert isinstance(app.screen, DeviceInfoPopup)
        assert app.screen._title == "Lamp"
        rows = dict(app.screen._rows)
        assert rows["Name"] == "Lamp"
        assert rows["Area"] == "Living Room"
        assert rows["Entities"] == "2"  # light.living_room_lamp + sensor.temperature


async def test_i_on_non_device_node_notifies(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await _focus_leaf(pilot, app, "sensor.temperature")

        await pilot.press("i")
        await pilot.pause()
        # Entity leaves get the bonus entity-info popup rather than a notify.
        assert isinstance(app.screen, DeviceInfoPopup)


async def test_enter_on_nontogglable_leaf_opens_fullscreen_graph(make_app):
    from hatty.ui.graph.preview_screen import GraphPreviewScreen

    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await _focus_leaf(pilot, app, "sensor.temperature")

        await pilot.press("enter")  # non-togglable → open-controls fallback (#150)
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)


async def test_dead_entity_leaf_is_dimmed(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()

        tree = app.screen.query_one(Tree)
        lamp = _child_by_data(tree.root, "device_id", "dev_lamp")
        leaf = _child_by_data(lamp, "entity_id", "light.living_room_lamp")
        # Healthy entity → no dim style (Textual normalizes str labels to Text).
        assert "dim" not in str(leaf.label.style)

        app.client.inject_state_change(
            {
                "entity_id": "light.living_room_lamp",
                "state": "unavailable",
                "attributes": {"friendly_name": "Living Room Lamp"},
            }
        )
        await pilot.pause()
        assert "dim" in str(leaf.label.style)


async def test_enter_on_entity_leaf_toggles_it(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()

        await _focus_leaf(pilot, app, "light.living_room_lamp")
        await pilot.press("enter")  # toggle it
        await pilot.pause()

        assert ("light", "turn_off", {"entity_id": "light.living_room_lamp"}) in app.client.call_service_calls


async def test_m_moves_device_to_selected_area(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()

        tree = app.screen.query_one(Tree)
        await _focus_node(pilot, app, _child_by_data(tree.root, "device_id", "dev_lamp"))
        await pilot.press("m")
        await pilot.pause()
        assert isinstance(app.screen, AreaPickerPopup)

        # Picker: index 0 "(No area)", then areas sorted by name: Kitchen, Living Room.
        await pilot.press("down")  # -> Kitchen
        await pilot.press("enter")
        await pilot.pause()

        assert app.client.update_device_registry_calls == [("dev_lamp", "kitchen")]


async def test_escape_closes_device_tree(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        assert isinstance(app.screen, DeviceTreeScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, DeviceTreeScreen)


# ── e expand/control (issue #130) ─────────────────────────────────────────────

CLIMATE_ENTITY = {
    "entity_id": "climate.thermostat",
    "state": "heat",
    "attributes": {
        "friendly_name": "Hallway Thermostat",
        "current_temperature": 68.0,
        "temperature": 70.0,
        "target_temp_step": 0.5,
        "min_temp": 60.0,
        "max_temp": 80.0,
        "hvac_modes": ["heat", "off"],
    },
    "last_changed": "",
}


async def test_e_on_light_leaf_opens_light_control(make_app):
    from hatty.ui.controls.light_screen import LightControlScreen

    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await _focus_leaf(pilot, app, "light.living_room_lamp")
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, LightControlScreen)


async def test_e_on_climate_leaf_opens_control_popup(make_app, sample_entities):
    from hatty.ui.controls.control_popup import EntityControlPopup

    registry = [*REGISTRY, {"entity_id": "climate.thermostat", "device_id": "dev_thermo"}]
    devices = [*DEVICES, {"id": "dev_thermo", "name": "Thermo", "area_id": None}]
    app = make_app(entities=[*sample_entities, CLIMATE_ENTITY], registry=registry, devices=devices, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await _focus_leaf(pilot, app, "climate.thermostat")
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, EntityControlPopup)


async def test_e_on_graphable_sensor_opens_fullscreen_graph(make_app):
    from hatty.ui.graph.preview_screen import GraphPreviewScreen

    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await _focus_leaf(pilot, app, "sensor.temperature")
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)


async def test_e_on_device_node_does_nothing(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        tree = app.screen.query_one(Tree)
        await _focus_node(pilot, app, _child_by_data(tree.root, "device_id", "dev_lamp"))
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, DeviceTreeScreen)


async def test_question_mark_opens_help_on_device_tree(make_app):
    from hatty.ui.help_popup import HelpPopup

    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpPopup)
        descriptions = [desc for _, desc in app.screen._binding_rows]
        assert "Controls" in descriptions
        assert "Help" in descriptions


# ── G fullscreen graph (issue #131) ───────────────────────────────────────────


async def test_G_on_sensor_leaf_opens_fullscreen_graph(make_app):
    from hatty.ui.graph.preview_screen import GraphPreviewScreen

    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await _focus_leaf(pilot, app, "sensor.temperature")
        await pilot.press("G")
        await pilot.pause()
        assert isinstance(app.screen, GraphPreviewScreen)
        assert app.screen._entity_ids == ["sensor.temperature"]

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DeviceTreeScreen)


async def test_G_on_non_graphable_leaf_stays_on_tree(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await _focus_leaf(pilot, app, "light.living_room_lamp")
        await pilot.press("G")
        await pilot.pause()
        assert isinstance(app.screen, DeviceTreeScreen)


# ── space list membership (issue #132) ────────────────────────────────────────


async def test_space_adds_entity_to_current_list_with_marker(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        assert app.current_list_name == "my_list"

        await _focus_leaf(pilot, app, "sensor.temperature")
        leaf = app.screen._entity_nodes["sensor.temperature"][0]
        assert "✓" not in str(leaf.label)

        await pilot.press("space")
        await pilot.pause()
        assert "sensor.temperature" in app.entity_lists["my_list"]
        assert str(leaf.label).endswith("✓")
        assert app.list_ctl.undo_stack[-1] == {
            "list_name": "my_list",
            "entity_id": "sensor.temperature",
            "action": "add",
        }

        await pilot.press("space")
        await pilot.pause()
        assert "sensor.temperature" not in app.entity_lists["my_list"]
        assert "✓" not in str(leaf.label)


async def test_space_falls_back_to_default_list_without_selecting_it(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.current_list_name = None  # "View All" on the main table
        await pilot.press("D")
        await pilot.pause()

        await _focus_leaf(pilot, app, "sensor.temperature")
        await pilot.press("space")
        await pilot.pause()

        assert "sensor.temperature" in app.entity_lists["my_list"]
        assert app.current_list_name is None


async def test_space_with_no_lists_opens_list_popup_then_applies(make_app):
    from hatty.ui.list_selection_popup import ListSelectionPopup

    cfg = {
        **make_config(),
        "lists": {},
    }
    app = make_app(config_data=cfg, registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()

        await _focus_leaf(pilot, app, "sensor.temperature")
        await pilot.press("space")
        await pilot.pause()
        assert isinstance(app.screen, ListSelectionPopup)

        app.screen.query_one("#new_list_input").focus()
        await pilot.pause()
        await pilot.press(*"tree_list")
        await pilot.press("enter")
        await pilot.pause()

        assert "sensor.temperature" in app.entity_lists["tree_list"]


async def test_space_on_device_node_toggles_expansion(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()

        tree = app.screen.query_one(Tree)
        lamp = _child_by_data(tree.root, "device_id", "dev_lamp")
        await _focus_node(pilot, app, lamp)
        lamp.collapse()
        await pilot.pause()

        await pilot.press("space")
        await pilot.pause()
        assert lamp.is_expanded
        assert "sensor.temperature" not in app.entity_lists["my_list"]


async def test_space_types_into_focused_search_input(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("a", "space", "b")
        await pilot.pause()

        assert app.screen.query_one("#device_tree_search").value == "a b"
        assert app.entity_lists["my_list"] == ["light.living_room_lamp"]


# ── n new dashboard from area (issue #133) ───────────────────────────────────────────


async def _open_area_mode(pilot, app) -> None:
    await pilot.pause()
    await pilot.press("D")
    await pilot.pause()
    await pilot.press("v")  # area mode
    await pilot.pause()


async def test_n_on_area_node_creates_and_opens_dashboard(make_app):
    from hatty.ui.dashboard.screen import DashboardScreen

    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await _open_area_mode(pilot, app)
        tree = app.screen.query_one(Tree)
        await _focus_node(pilot, app, _child_by_data(tree.root, "area_id", "living_room"))
        await pilot.press("n")
        await pilot.pause()

        dashboard = app.dashboards["Living Room"]
        assert [(s["widget_type"], s["entity_id"]) for s in dashboard["slots"]] == [
            ("light", "light.living_room_lamp"),
            ("sensor", "sensor.temperature"),
        ]
        assert app.current_dashboard_name == "Living Room"
        assert isinstance(app.screen, DashboardScreen)

        await pilot.press("escape")  # "Leave dashboard?" confirm
        await pilot.press("y")
        await pilot.pause()
        assert isinstance(app.screen, DeviceTreeScreen)


async def test_n_suffixes_name_on_collision(make_app):
    cfg = {
        **make_config(),
        "lists": {},
        "dashboards": {"Living Room": {"rows": 1, "cols": 1, "slots": []}},
    }
    app = make_app(config_data=cfg, registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await _open_area_mode(pilot, app)
        tree = app.screen.query_one(Tree)
        await _focus_node(pilot, app, _child_by_data(tree.root, "area_id", "living_room"))
        await pilot.press("n")
        await pilot.pause()

        assert app.dashboards["Living Room"] == {"rows": 1, "cols": 1, "slots": []}
        assert len(app.dashboards["Living Room (2)"]["slots"]) == 2
        assert app.current_dashboard_name == "Living Room (2)"


async def test_n_excludes_diagnostic_entities(make_app):
    registry = [
        {"entity_id": "light.living_room_lamp", "device_id": "dev_lamp"},
        {"entity_id": "sensor.temperature", "device_id": "dev_lamp", "entity_category": "diagnostic"},
    ]
    app = make_app(registry=registry, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await _open_area_mode(pilot, app)
        tree = app.screen.query_one(Tree)
        await _focus_node(pilot, app, _child_by_data(tree.root, "area_id", "living_room"))
        await pilot.press("n")
        await pilot.pause()

        assert [s["entity_id"] for s in app.dashboards["Living Room"]["slots"]] == ["light.living_room_lamp"]


async def test_n_in_device_mode_does_nothing(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()

        assert app.dashboards == {}
        assert isinstance(app.screen, DeviceTreeScreen)


async def test_n_on_device_node_in_area_mode_notifies(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await _open_area_mode(pilot, app)
        tree = app.screen.query_one(Tree)
        living_room = _child_by_data(tree.root, "area_id", "living_room")
        await _focus_node(pilot, app, _child_by_data(living_room, "device_id", "dev_lamp"))
        await pilot.press("n")
        await pilot.pause()

        assert app.dashboards == {}
        assert isinstance(app.screen, DeviceTreeScreen)


async def test_n_respects_active_search_filter(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await _open_area_mode(pilot, app)
        await pilot.press("ctrl+s")  # area -> all, so the device label matches (#206)
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press(*"lamp")
        await pilot.press("enter")
        await pilot.pause()

        tree = app.screen.query_one(Tree)
        await _focus_node(pilot, app, _child_by_data(tree.root, "area_id", "living_room"))
        await pilot.press("n")
        await pilot.pause()

        # "lamp" matches the Lamp device label, keeping both its entities.
        assert len(app.dashboards["Living Room"]["slots"]) == 2


# ── a create / r rename areas (issue #146) ────────────────────────────────────


async def test_a_creates_area_in_area_mode(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await _open_area_mode(pilot, app)
        await pilot.press("a")
        await pilot.pause()
        assert isinstance(app.screen, AreaNamePopup)

        await pilot.press(*"Garage")  # input is auto-focused on mount
        await pilot.press("enter")
        await pilot.pause()
        assert app.client.create_area_calls == ["Garage"]


async def test_r_renames_area_node(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await _open_area_mode(pilot, app)
        tree = app.screen.query_one(Tree)
        await _focus_node(pilot, app, _child_by_data(tree.root, "area_id", "living_room"))
        await pilot.press("r")
        await pilot.pause()
        assert isinstance(app.screen, AreaNamePopup)

        inp = app.screen.query_one("#area_name_input")
        assert inp.value == "Living Room"  # prefilled with the current name
        inp.value = ""
        await pilot.press(*"Lounge")
        await pilot.press("enter")
        await pilot.pause()
        assert app.client.rename_area_calls == [("living_room", "Lounge")]


async def test_a_is_disabled_in_device_mode(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        # Device mode: area creation is gated off (rename is not — it dispatches
        # by node kind and works on devices/entities everywhere, issue #152).
        assert app.screen.check_action("create_area", ()) is False

        await pilot.press("a")
        await pilot.pause()
        assert isinstance(app.screen, DeviceTreeScreen)
        assert app.client.create_area_calls == []


async def test_r_renames_device_node(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        tree = app.screen.query_one(Tree)
        await _focus_node(pilot, app, _child_by_data(tree.root, "device_id", "dev_lamp"))
        await pilot.press("r")
        await pilot.pause()
        assert isinstance(app.screen, AreaNamePopup)

        inp = app.screen.query_one("#area_name_input")
        assert inp.value == "Lamp"  # prefilled with the current display name
        inp.value = ""
        await pilot.press(*"Reading Lamp")
        await pilot.press("enter")
        await pilot.pause()
        # Rename writes name_by_user, never touches the area.
        assert app.client.rename_device_calls == [("dev_lamp", "Reading Lamp")]
        assert app.client.update_device_registry_calls == []


async def test_r_on_entity_leaf_opens_rename_popup(make_app):
    from hatty.ui.rename_entity_popup import RenameEntityPopup

    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await _focus_leaf(pilot, app, "light.living_room_lamp")
        await pilot.press("r")
        await pilot.pause()
        # Reuses the main table's exact rename seam (local-override vs push-to-HA).
        assert isinstance(app.screen, RenameEntityPopup)


# ── cursor follows the entity (issue #153) ────────────────────────────────────


# A list holding two of the REGISTRY entities so the main table shows more than
# one selectable row (the default make_app list has a single entity).
_MULTI_LIST_CONFIG = {
    **make_config(),
    "default_list": "my_list",
    "lists": {"my_list": ["light.living_room_lamp", "sensor.temperature"]},
}


async def test_D_focuses_the_table_selection(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS, config_data=_MULTI_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#entities_table", EntitiesTable)
        assert table.jump_cursor_to_row_key("sensor.temperature")
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        tree = app.screen.query_one(Tree)
        # The tree opens with the cursor on that entity's leaf, ancestors expanded.
        assert (tree.cursor_node.data or {}).get("entity_id") == "sensor.temperature"


async def test_view_switch_keeps_cursor_on_entity(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await _focus_leaf(pilot, app, "sensor.temperature")
        await pilot.press("v")  # device -> area
        await pilot.pause()
        tree = app.screen.query_one(Tree)
        assert app.screen._mode == "area"
        assert (tree.cursor_node.data or {}).get("entity_id") == "sensor.temperature"


async def test_escape_returns_table_cursor_to_entity(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS, config_data=_MULTI_LIST_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await _focus_leaf(pilot, app, "sensor.temperature")
        await pilot.press("escape")
        await pilot.pause()
        # Back on the main table, the cursor landed on the tree's last entity.
        assert not isinstance(app.screen, DeviceTreeScreen)
        assert app._selected_entity_id() == "sensor.temperature"


# ── l lists / d dashboard jumps (issue #141) ──────────────────────────────────


async def test_d_opens_dashboard_and_dismisses_tree(make_app):
    from hatty.ui.dashboard.screen import DashboardScreen

    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        assert isinstance(app.screen, DeviceTreeScreen)

        await pilot.press("d")  # jump to the last-shown/default dashboard
        await pilot.pause()
        assert isinstance(app.screen, DashboardScreen)
        assert not isinstance(app.screen, DeviceTreeScreen)


async def test_l_jumps_to_default_list_and_dismisses_tree(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.current_list_name = None
        await pilot.press("D")
        await pilot.pause()

        await pilot.press("l")  # jump to the last-shown/default list
        await pilot.pause()
        assert not isinstance(app.screen, DeviceTreeScreen)
        assert app.current_list_name == "my_list"


async def test_l_with_no_lists_opens_list_popup(make_app):
    from hatty.ui.list_selection_popup import ListSelectionPopup

    cfg = {
        **make_config(),
        "lists": {},
    }
    app = make_app(config_data=cfg, registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()

        await pilot.press("l")
        await pilot.pause()
        # No list exists yet, so the picker opens (over the base table, tree gone).
        assert isinstance(app.screen, ListSelectionPopup)


# ── search / filter (issue #129) ──────────────────────────────────────────────


async def _open_tree_and_search(pilot, term: str) -> None:
    await pilot.pause()
    await pilot.press("D")
    await pilot.pause()
    await pilot.press("/")
    await pilot.pause()
    await pilot.press(*term)
    await pilot.pause()


async def test_search_filters_to_matching_entities(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await _open_tree_and_search(pilot, "temp")
        await pilot.press("ctrl+s")  # device -> all, so the entity name matches (#206)
        await pilot.pause()

        search = app.screen.query_one("#device_tree_search")
        assert search.display
        tree = app.screen.query_one(Tree)
        # Only Lamp survives (it holds sensor.temperature), pruned to the match.
        assert _labels(tree.root) == ["Lamp"]
        lamp = tree.root.children[0]
        assert lamp.is_expanded
        assert [(c.data or {}).get("entity_id") for c in lamp.children] == ["sensor.temperature"]


async def test_filter_status_shows_match_count(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await _open_tree_and_search(pilot, "temp")
        await pilot.press("ctrl+s")  # device -> all, so the entity name matches (#206)
        await pilot.pause()

        status = app.screen._status_text()
        assert "Filter: 'temp' — 1 entity" in status


async def test_filter_no_matches_shows_placeholder(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await _open_tree_and_search(pilot, "zzzznope")

        tree = app.screen.query_one(Tree)
        assert _labels(tree.root) == ["— no matches —"]
        assert (tree.root.children[0].data or {}).get("kind") == "placeholder"
        status = app.screen._status_text()
        assert "Filter: 'zzzznope' — 0 entities" in status


async def test_search_device_label_match_keeps_all_entities(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await _open_tree_and_search(pilot, "lamp")

        tree = app.screen.query_one(Tree)
        assert _labels(tree.root) == ["Lamp"]
        # The device label matched, so the non-matching sensor stays too.
        lamp = tree.root.children[0]
        assert [(c.data or {}).get("entity_id") for c in lamp.children] == [
            "light.living_room_lamp",
            "sensor.temperature",
        ]


async def test_ctrl_s_cycles_scope_to_entity_only(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await _open_tree_and_search(pilot, "lamp")

        tree = app.screen.query_one(Tree)
        # Device view defaults to "device" scope: the "lamp" device label keeps
        # both its entities.
        assert app.screen._scope == "device"
        assert len(tree.root.children[0].children) == 2

        # Device view cycles device → all → entity (area/integration aren't
        # offered here, issue #206). Two presses reach entity.
        await pilot.press("ctrl+s", "ctrl+s")
        await pilot.pause()
        assert app.screen._scope == "entity"
        # Entity scope ignores the "lamp" device label: only the lamp entity
        # itself (whose entity_id contains "lamp") survives, not the sensor.
        lamp = tree.root.children[0]
        assert [(c.data or {}).get("entity_id") for c in lamp.children] == ["light.living_room_lamp"]

        # A final press wraps back to "device".
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.screen._scope == "device"


async def test_ctrl_s_scope_restricted_to_view(make_app):
    """Device view never offers the area/integration scopes (issue #206)."""
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()

        seen = {app.screen._scope}
        for _ in range(len(app.screen._VIEW_SCOPES["device"])):
            await pilot.press("ctrl+s")
            await pilot.pause()
            seen.add(app.screen._scope)

        assert seen == {"device", "all", "entity"}
        assert "area" not in seen and "integration" not in seen


async def test_switching_view_resets_scope_to_default(make_app):
    """`v` sets the scope to the new view's default (issue #206)."""
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        assert app.screen._mode == "device"
        assert app.screen._scope == "device"

        await pilot.press("v")  # area
        await pilot.pause()
        assert app.screen._mode == "area"
        assert app.screen._scope == "area"

        await pilot.press("v")  # integration
        await pilot.pause()
        assert app.screen._mode == "integration"
        assert app.screen._scope == "integration"

        await pilot.press("v")  # back to device
        await pilot.pause()
        assert app.screen._mode == "device"
        assert app.screen._scope == "device"


async def test_switching_view_clears_active_search(make_app):
    """`v` clears any active search filter rather than carrying it into the new grouping (issue #211)."""
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await _open_tree_and_search(pilot, "temp")
        assert app.screen._filter == "temp"
        await pilot.press("enter")  # submit search, moving focus back to the tree
        await pilot.pause()

        await pilot.press("v")
        await pilot.pause()

        assert app.screen._filter == ""
        search = app.screen.query_one("#device_tree_search")
        assert not search.display
        assert search.value == ""


async def test_search_area_label_match_keeps_subtree(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await pilot.press("v")  # area mode
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        await pilot.press(*"living room")
        await pilot.pause()

        tree = app.screen.query_one(Tree)
        assert _labels(tree.root) == ["Living Room"]
        living_room = tree.root.children[0]
        assert _labels(living_room) == ["Lamp"]
        # Whole subtree kept: both of Lamp's entities, not just matching ones.
        assert len(living_room.children[0].children) == 2


async def test_escape_clears_search_before_closing(make_app):
    app = make_app(registry=REGISTRY, devices=DEVICES, areas=AREAS)
    async with app.run_test() as pilot:
        await _open_tree_and_search(pilot, "temp")

        await pilot.press("escape")
        await pilot.pause()
        # First escape clears the filter and stays on the tree.
        assert isinstance(app.screen, DeviceTreeScreen)
        assert not app.screen.query_one("#device_tree_search").display
        tree = app.screen.query_one(Tree)
        assert _labels(tree.root) == ["Fan", "Lamp", NO_DEVICE_LABEL]

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, DeviceTreeScreen)
