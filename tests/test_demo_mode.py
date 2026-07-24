# hatty — MIT License. See LICENSE file for details.
"""Demo mode boots offline against curated fake data and stays disk-free."""

from textual.widgets import Tree

from hatty.main import HACLI
from hatty.ui.device_tree_screen import DeviceTreeScreen


async def test_demo_mode_boots_populated_offline():
    app = HACLI(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()

        ids = {e["entity_id"] for e in app.all_entities}
        assert "light.living_room_lamp" in ids
        assert "climate.living_room" in ids
        assert "binary_sensor.front_door" in ids

        # Seeded collections are present…
        assert "Living Room" in app.entity_lists
        assert app.current_list_name == "Living Room"
        assert "Home" in app.dashboards
        assert "Temperatures" in app.saved_graphs

        # …and demo mode never opened the SQLite DB.
        assert app.storage is None


async def test_demo_mode_service_call_echoes_state():
    app = HACLI(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()

        assert app.find_entity("switch.coffee_maker")["state"] == "off"
        await app.client.call_service("switch", "turn_on", {}, "switch.coffee_maker")
        await pilot.pause()

        assert app.find_entity("switch.coffee_maker")["state"] == "on"


async def test_demo_mode_lock_unlock_service_calls_echo_state():
    app = HACLI(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()

        assert app.find_entity("lock.front_door")["state"] == "locked"
        await app.client.call_service("lock", "unlock", {}, "lock.front_door")
        await pilot.pause()

        assert app.find_entity("lock.front_door")["state"] == "unlocked"
        await app.client.call_service("lock", "lock", {}, "lock.front_door")
        await pilot.pause()

        assert app.find_entity("lock.front_door")["state"] == "locked"


async def test_demo_mode_media_player_service_calls_echo_state():
    app = HACLI(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()

        assert app.find_entity("media_player.living_room_speaker")["state"] == "playing"
        await app.client.call_service("media_player", "media_play_pause", {}, "media_player.living_room_speaker")
        await pilot.pause()

        assert app.find_entity("media_player.living_room_speaker")["state"] == "paused"
        await app.client.call_service(
            "media_player", "volume_set", {"volume_level": 0.75}, "media_player.living_room_speaker"
        )
        await pilot.pause()

        entity = app.find_entity("media_player.living_room_speaker")
        assert entity["attributes"]["volume_level"] == 0.75


async def test_demo_mode_serves_devices_and_areas_and_populates_tree():
    app = HACLI(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()

        # Device/area registries are served on connect.
        assert app.device_registry and app.area_registry
        area_names = {a["name"] for a in app.area_registry}
        assert {"Living Room", "Kitchen", "Bedroom"} <= area_names

        # The demo splash hold (issue #268) is still up and swallows the first
        # keypress as an early dismiss, same as the real-HA splash.
        await pilot.press("D")
        await pilot.pause()

        # D opens a populated Area -> Device -> Entity tree.
        await pilot.press("D")
        await pilot.pause()
        assert isinstance(app.screen, DeviceTreeScreen)
        await pilot.press("v")  # -> area grouping
        await pilot.pause()

        tree = app.screen.query_one(Tree)
        top = [str(c.label) for c in tree.root.children]
        assert "Living Room" in top
        # An area expands into device nodes, which expand into entity leaves.
        living_room = next(c for c in tree.root.children if str(c.label) == "Living Room")
        assert living_room.children  # has devices
        assert any(dev.children for dev in living_room.children)  # devices have entities


async def test_demo_mode_history_is_generated():
    app = HACLI(demo=True)
    async with app.run_test() as pilot:
        await pilot.pause()

        numeric = await app.client.fetch_history("sensor.living_room_temperature", hours=4)
        assert numeric and all(isinstance(v, float) for _, v in numeric)

        climate = await app.client.fetch_climate_history("climate.living_room", hours=4)
        assert climate and "current_temperature" in climate[0]

        binary = await app.client.fetch_binary_history("binary_sensor.front_door", hours=4)
        assert binary and all(v in (0.0, 1.0) for _, v in binary)
