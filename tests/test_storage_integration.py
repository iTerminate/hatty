# hatty — MIT License. See LICENSE file for details.
"""App-level integration of the SQLite collections storage (issue #63)."""

import yaml

from hatty.const import NOTIFY_LIST_NAME
from tests.conftest import make_config


async def test_legacy_yaml_collections_migrate_into_the_db(make_app, sample_entities):
    # A pre-existing all-in-YAML config is imported into the DB on first boot.
    config_data = {
        **make_config(),
        "lists": {"living": ["light.living_room_lamp"]},
        "default_list": "living",
        "entity_names": {"sensor.temperature": "Temp"},
        "dashboards": {"Main": {"rows": 2, "cols": 2, "slots": []}},
        "saved_graphs": {"Trend": {"entity_ids": ["sensor.temperature"], "graph_type": "line", "hours": 4}},
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.storage is not None
        stored = app.storage.load_all()
        assert stored["lists"] == {"living": ["light.living_room_lamp"]}
        assert stored["default_list"] == "living"
        assert stored["entity_names"] == {"sensor.temperature": "Temp"}
        assert stored["dashboards"]["Main"]["rows"] == 2
        assert stored["saved_graphs"]["Trend"]["entity_ids"] == ["sensor.temperature"]
        # And the app state reflects the migrated data. entity_lists always carries
        # the reserved notifications list too (issue #224 — seeded so watched
        # entities persist even while notifications are disabled).
        assert app.entity_lists == {"living": ["light.living_room_lamp"], NOTIFY_LIST_NAME: []}
        assert app.current_list_name == "living"


async def test_db_is_authoritative_over_yaml_on_boot(make_app, sample_entities, tmp_path):
    # Pre-seed a DB with different lists than the YAML; the DB wins.
    from hatty.storage import Storage

    db = Storage(tmp_path / "hatty.db")
    db.connect()
    db.save_all({"lists": {"from_db": ["switch.fan"]}, "default_list": "from_db"})
    db.close()

    config_data = {
        **make_config(),
        "lists": {"from_yaml": ["light.living_room_lamp"]},
        "default_list": "from_yaml",
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.entity_lists == {"from_db": ["switch.fan"], NOTIFY_LIST_NAME: []}
        assert app.current_list_name == "from_db"


async def test_saving_leaves_collections_out_of_the_yaml(make_app, sample_entities):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Toggle list membership to trigger a save.
        await pilot.press("space")
        await pilot.pause()
        await pilot.press("y")  # confirm unlock-to-remove (issue #214)
        await pilot.pause()

        with open(app.config_path) as f:
            saved = yaml.safe_load(f)
        # Lean YAML: collections are gone, connection + prefs remain.
        for key in ("lists", "dashboards", "saved_graphs", "entity_names", "default_list", "default_dashboard"):
            assert key not in saved
        assert saved["home_assistant"]["url"] == "http://fake.ha.local:8123"
        assert "columns" in saved

        # But the DB has the updated list.
        assert "my_list" in app.storage.load_all()["lists"]


async def test_collections_survive_a_restart(make_app, sample_entities, tmp_path):
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("space")  # remove living_room_lamp from my_list
        await pilot.pause()
        await pilot.press("y")  # confirm unlock-to-remove (issue #214)
        await pilot.pause()

    # Second boot against the same tmp_path (same config + DB).
    app2 = make_app(entities=sample_entities)
    async with app2.run_test() as pilot:
        await pilot.pause()
        assert "light.living_room_lamp" not in app2.entity_lists.get("my_list", [])
