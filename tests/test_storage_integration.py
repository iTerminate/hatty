# hatty — MIT License. See LICENSE file for details.
"""App-level integration of the SQLite collections storage (issue #63)."""

import asyncio
import threading

import yaml

from tests.conftest import make_config, notified


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
        # And the app state reflects the migrated data.
        assert app.entity_lists == {"living": ["light.living_room_lamp"]}
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
        assert app.entity_lists == {"from_db": ["switch.fan"]}
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


async def test_save_worker_never_iterates_the_live_collections(make_app, sample_entities, monkeypatch):
    """The DB save runs in an asyncio.to_thread worker while the event loop keeps
    mutating app state. The snapshot it is handed must be detached — sharing the
    live dicts made the worker raise "dictionary changed size during iteration"
    (surfacing as the "Save Error" toast from _save_config_async)."""
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        entered = threading.Event()
        release = threading.Event()

        def slow_save_all(collections):
            entered.set()
            for _name in collections["lists"]:  # the iteration that used to race
                release.wait(2.0)

        monkeypatch.setattr(app.storage, "save_all", slow_save_all)

        app.persist("lists")
        for _ in range(200):
            if entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert entered.is_set(), "the save worker never started"

        app.entity_lists["added_mid_save"] = []  # grows the dict under the worker
        release.set()
        await pilot.pause(0.2)

        assert not notified(app, title="Save Error")


async def test_overlapping_persists_coalesce_into_one_trailing_save(make_app, sample_entities, monkeypatch):
    """persist() is fire-and-forget from many call sites; a burst must not stack
    one full-rewrite save per call, but the trailing state must still be written."""
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        calls: list[dict] = []
        entered = threading.Event()
        release = threading.Event()

        def counting_save_all(collections):
            entered.set()
            release.wait(2.0)
            calls.append(collections)

        monkeypatch.setattr(app.storage, "save_all", counting_save_all)

        app.persist("lists")
        for _ in range(200):
            if entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert entered.is_set(), "the save worker never started"

        for i in range(5):
            app.entity_lists[f"burst_{i}"] = []
            app.persist("lists")  # all coalesce behind the in-flight save

        release.set()
        for _ in range(200):
            if not app._save_running:
                break
            await asyncio.sleep(0.01)
        assert await app.drain_bg_tasks(timeout=5.0)

        assert len(calls) == 2  # the in-flight save + the one pass picking up the burst
        assert {f"burst_{i}" for i in range(5)} <= set(calls[-1]["lists"])


async def test_drain_bg_tasks_flushes_a_queued_persist(make_app, sample_entities):
    """The exit-time drain must still land the last persist (coalescing defers it
    to the in-flight save's trailing pass rather than starting a new task)."""
    app = make_app(entities=sample_entities)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.entity_lists["drained"] = ["light.living_room_lamp"]
        app.persist("lists")
        await asyncio.sleep(0)  # let the save task start
        app.entity_lists["drained_again"] = []
        app.persist("lists")

        assert await app.drain_bg_tasks(timeout=5.0)
        assert app.storage is not None
        stored = app.storage.load_all()
        assert "drained_again" in stored["lists"]
