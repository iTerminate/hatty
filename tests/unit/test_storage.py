# hatty — MIT License. See LICENSE file for details.
"""Unit tests for the SQLite collections storage layer (issue #63)."""

import os
import stat
import threading

from hatty.storage import COLLECTION_KEYS, PERSISTED, SCHEMA_VERSION, Storage


def _open(tmp_path):
    s = Storage(tmp_path / "hatty.db")
    s.connect()
    return s


def test_connect_creates_schema_and_version(tmp_path):
    s = _open(tmp_path)
    version = s._get_meta("schema_version")
    assert version == str(SCHEMA_VERSION)
    # A fresh DB has nothing imported yet.
    assert s.is_empty() is True
    s.close()


def test_connect_writes_private_permissions(tmp_path):
    # User data must not be world-readable (#156).
    db_dir = tmp_path / "data"
    s = Storage(db_dir / "hatty.db")
    s.connect()
    assert stat.S_IMODE(os.stat(s.db_path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(db_dir).st_mode) == 0o700
    s.close()


def test_round_trip_lists(tmp_path):
    s = _open(tmp_path)
    collections = {
        "lists": {"living": ["light.a", "light.b"], "empty": []},
        "default_list": "living",
    }
    s.save_all(collections)
    loaded = s.load_all()
    assert loaded["lists"] == {"living": ["light.a", "light.b"], "empty": []}
    assert loaded["default_list"] == "living"
    assert s.is_empty() is False
    s.close()


def test_round_trip_entity_names(tmp_path):
    s = _open(tmp_path)
    s.save_all({"entity_names": {"light.kitchen": "Main Light", "sensor.x": "X"}})
    loaded = s.load_all()
    assert loaded["entity_names"] == {"light.kitchen": "Main Light", "sensor.x": "X"}
    s.close()


def test_round_trip_dashboards_with_spans_and_gauge_and_panel(tmp_path):
    s = _open(tmp_path)
    dashboards = {
        "Main": {
            "rows": 3,
            "cols": 3,
            "slots": [
                {"row": 0, "col": 0, "widget_type": "graph", "entity_id": "sensor.temp"},
                {"row": 0, "col": 1, "widget_type": "sensor", "entity_id": "sensor.hum",
                 "row_span": 2, "col_span": 2},
                {"row": 2, "col": 0, "widget_type": "gauge", "entity_id": "sensor.co2",
                 "gauge_min": 400, "gauge_max": 2000},
                {"row": 2, "col": 1, "widget_type": "panel", "entity_id": None,
                 "entity_ids": ["light.a", "switch.b"]},
            ],
        }
    }
    s.save_all({"dashboards": dashboards, "default_dashboard": "Main"})
    loaded = s.load_all()
    assert loaded["default_dashboard"] == "Main"
    got = loaded["dashboards"]["Main"]
    assert got["rows"] == 3 and got["cols"] == 3
    slots = {(sl["row"], sl["col"]): sl for sl in got["slots"]}
    # Unspanned slot keeps the legacy shape (no span keys).
    assert slots[(0, 0)] == {"row": 0, "col": 0, "widget_type": "graph", "entity_id": "sensor.temp"}
    # Spanned slot carries the spans back.
    assert slots[(0, 1)]["row_span"] == 2 and slots[(0, 1)]["col_span"] == 2
    # Gauge bounds preserved.
    assert slots[(2, 0)]["gauge_min"] == 400 and slots[(2, 0)]["gauge_max"] == 2000
    # Panel entity_ids preserved.
    assert slots[(2, 1)]["entity_ids"] == ["light.a", "switch.b"]
    assert slots[(2, 1)]["entity_id"] is None
    s.close()


def test_round_trip_split_slot_children(tmp_path):
    s = _open(tmp_path)
    children = {
        "rows": 2,
        "cols": 2,
        "slots": [
            {"row": 0, "col": 0, "widget_type": "switch", "entity_id": "switch.a"},
            {"row": 1, "col": 1, "widget_type": "sensor", "entity_id": "sensor.b"},
        ],
    }
    dashboards = {
        "Main": {
            "rows": 2,
            "cols": 2,
            "slots": [
                {"row": 0, "col": 0, "widget_type": "split", "entity_id": None, "children": children},
                {"row": 0, "col": 1, "widget_type": "switch", "entity_id": "switch.plain"},
            ],
        }
    }
    s.save_all({"dashboards": dashboards})
    loaded = s.load_all()["dashboards"]["Main"]
    slots = {(sl["row"], sl["col"]): sl for sl in loaded["slots"]}
    assert slots[(0, 0)]["children"] == children
    # Non-split slot keeps the legacy shape (no children key).
    assert "children" not in slots[(0, 1)]
    s.close()


def test_children_column_added_to_pre_split_db(tmp_path):
    # A DB created before the children column existed must be migrated on connect.
    import sqlite3

    db = tmp_path / "hatty.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE dashboard_slots (
            dashboard TEXT, row INTEGER, col INTEGER,
            widget_type TEXT, entity_id TEXT,
            row_span INTEGER, col_span INTEGER,
            gauge_min REAL, gauge_max REAL,
            entity_ids TEXT,
            PRIMARY KEY (dashboard, row, col)
        );
        """
    )
    conn.execute(
        "INSERT INTO dashboard_slots (dashboard, row, col, widget_type, entity_id, row_span, col_span) "
        "VALUES ('Main', 0, 0, 'switch', 'switch.a', 1, 1)"
    )
    conn.commit()
    conn.close()

    s = _open(tmp_path)
    s.save_all({"dashboards": {"Main": {"rows": 1, "cols": 1, "slots": [
        {"row": 0, "col": 0, "widget_type": "split", "entity_id": None,
         "children": {"rows": 1, "cols": 2, "slots": []}},
    ]}}})
    loaded = s.load_all()["dashboards"]["Main"]
    assert loaded["slots"][0]["children"] == {"rows": 1, "cols": 2, "slots": []}
    s.close()


def test_round_trip_dashboard_row_height(tmp_path):
    s = _open(tmp_path)
    dashboards = {
        "Main": {"rows": 3, "cols": 3, "slots": [], "row_height": 12},
        "Office": {"rows": 2, "cols": 2, "slots": []},
    }
    s.save_all({"dashboards": dashboards})
    loaded = s.load_all()["dashboards"]
    # row_height round-trips when set...
    assert loaded["Main"]["row_height"] == 12
    # ...and stays absent (legacy shape) when never set.
    assert "row_height" not in loaded["Office"]
    s.close()


def test_row_height_column_added_to_pre_row_height_db(tmp_path):
    # A DB created before the row_height column existed must be migrated on connect.
    import sqlite3

    db = tmp_path / "hatty.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE dashboards (name TEXT PRIMARY KEY, rows INTEGER, cols INTEGER, position INTEGER);
        """
    )
    conn.execute("INSERT INTO dashboards (name, rows, cols, position) VALUES ('Main', 3, 3, 0)")
    conn.commit()
    conn.close()

    s = _open(tmp_path)
    s.save_all({"dashboards": {"Main": {"rows": 3, "cols": 3, "slots": [], "row_height": 10}}})
    loaded = s.load_all()["dashboards"]["Main"]
    assert loaded["row_height"] == 10
    s.close()


def test_round_trip_saved_graphs_with_and_without_colors(tmp_path):
    s = _open(tmp_path)
    graphs = {
        "Trend": {"entity_ids": ["sensor.a"], "graph_type": "line", "hours": 24},
        "Compare": {
            "entity_ids": ["sensor.a", "sensor.b"],
            "graph_type": "scatter",
            "hours": 4.5,
            "colors": {"sensor.a": "red", "sensor.b": "cyan"},
        },
    }
    s.save_all({"saved_graphs": graphs})
    loaded = s.load_all()["saved_graphs"]
    assert loaded["Trend"] == {"entity_ids": ["sensor.a"], "graph_type": "line", "hours": 24}
    assert loaded["Compare"]["colors"] == {"sensor.a": "red", "sensor.b": "cyan"}
    assert loaded["Compare"]["hours"] == 4.5
    s.close()


def test_save_all_replaces_previous_contents(tmp_path):
    s = _open(tmp_path)
    s.save_all({"lists": {"a": ["x"], "b": ["y"]}})
    s.save_all({"lists": {"a": ["z"]}})  # b dropped, a's contents replaced
    loaded = s.load_all()["lists"]
    assert loaded == {"a": ["z"]}
    s.close()


def test_defaults_can_be_cleared(tmp_path):
    s = _open(tmp_path)
    s.save_all({"default_list": "living", "default_dashboard": "Main"})
    assert s.load_all()["default_list"] == "living"
    s.save_all({"default_list": None, "default_dashboard": None})
    loaded = s.load_all()
    assert loaded["default_list"] is None
    assert loaded["default_dashboard"] is None
    s.close()


def test_load_all_on_empty_db_returns_empty_shapes(tmp_path):
    s = _open(tmp_path)
    loaded = s.load_all()
    assert loaded == {
        "lists": {},
        "entity_names": {},
        "dashboards": {},
        "saved_graphs": {},
        "manual_lists": [],
        "notify_lists": [],
        "default_list": None,
        "default_dashboard": None,
    }
    s.close()


def test_round_trip_manual_lists(tmp_path):
    s = _open(tmp_path)
    s.save_all({"manual_lists": {"living", "bedroom"}})
    loaded = s.load_all()
    assert loaded["manual_lists"] == ["bedroom", "living"]
    s.close()


def test_manual_lists_empty_set_round_trips_as_empty_list(tmp_path):
    s = _open(tmp_path)
    s.save_all({"manual_lists": set()})
    loaded = s.load_all()
    assert loaded["manual_lists"] == []
    s.close()


def test_round_trip_notify_lists(tmp_path):
    s = _open(tmp_path)
    s.save_all({"notify_lists": {"Security", "Climate"}})
    loaded = s.load_all()
    assert loaded["notify_lists"] == ["Climate", "Security"]
    s.close()


def test_notify_lists_empty_set_round_trips_as_empty_list(tmp_path):
    s = _open(tmp_path)
    s.save_all({"notify_lists": set()})
    loaded = s.load_all()
    assert loaded["notify_lists"] == []
    s.close()


def test_migrate_reserved_notify_list_designates_nonempty_list(tmp_path):
    # issue #24: a pre-#24 DB carrying entities in the old reserved list should
    # have it survive as an ordinary designated list, not vanish or stay reserved.
    s = _open(tmp_path)
    s.save_all({"lists": {"\U0001f514 Notifications": ["switch.fan"]}})
    s.migrate_reserved_notify_list()
    loaded = s.load_all()
    assert loaded["lists"] == {"\U0001f514 Notifications": ["switch.fan"]}
    assert loaded["notify_lists"] == ["\U0001f514 Notifications"]
    s.close()


def test_migrate_reserved_notify_list_drops_empty_list(tmp_path):
    s = _open(tmp_path)
    s.save_all({"lists": {"\U0001f514 Notifications": []}})
    s.migrate_reserved_notify_list()
    loaded = s.load_all()
    assert loaded["lists"] == {}
    assert loaded["notify_lists"] == []
    s.close()


def test_migrate_reserved_notify_list_is_a_noop_when_absent(tmp_path):
    s = _open(tmp_path)
    s.save_all({"lists": {"Kitchen": ["light.a"]}})
    s.migrate_reserved_notify_list()
    loaded = s.load_all()
    assert loaded["lists"] == {"Kitchen": ["light.a"]}
    assert loaded["notify_lists"] == []
    s.close()


def test_migrate_reserved_notify_list_runs_only_once(tmp_path):
    # A user un-toggling the migrated list (or later creating a new list with the
    # same legacy name) must not be re-designated by a second migration call.
    s = _open(tmp_path)
    s.save_all({"lists": {"\U0001f514 Notifications": ["switch.fan"]}})
    s.migrate_reserved_notify_list()
    s.save_all({"notify_lists": set()})  # user toggled it off
    s.migrate_reserved_notify_list()  # would-be second run, e.g. next boot
    loaded = s.load_all()
    assert loaded["notify_lists"] == []
    s.close()


def test_concurrent_saves_and_close_do_not_crash(tmp_path):
    """The single sqlite3 connection is shared across threads (saves run in
    asyncio.to_thread workers, close() on the main thread) with
    check_same_thread=False, so Storage must serialize access itself. Without
    the internal lock this races — concurrent save_all calls and a close()
    landing mid-write corrupt the connection or crash the process. Here we
    hammer it from several threads and assert it stays consistent and errors
    (post-close) surface cleanly instead of crashing."""
    s = _open(tmp_path)

    errors: list[Exception] = []

    def hammer(worker: int) -> None:
        try:
            for i in range(50):
                s.save_all(
                    {
                        "lists": {f"list_{worker}": [f"light.{worker}_{i}"]},
                        "dashboards": {
                            "Main": {
                                "rows": 2,
                                "cols": 2,
                                "slots": [
                                    {"row": 0, "col": 0, "widget_type": "sensor",
                                     "entity_id": f"sensor.{worker}_{i}"}
                                ],
                            }
                        },
                    }
                )
        except Exception as e:  # pragma: no cover - only hit on a real regression
            errors.append(e)

    threads = [threading.Thread(target=hammer, args=(w,)) for w in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # No thread should have crashed or raised while the connection was live.
    assert errors == []
    # DB is still readable and internally consistent after the concurrent churn.
    loaded = s.load_all()
    assert "Main" in loaded["dashboards"]

    # A save that lands after close() must no-op cleanly, not raise or crash.
    s.close()
    s.save_all({"lists": {"after": ["light.x"]}})


def test_persists_across_reopen(tmp_path):
    s = _open(tmp_path)
    s.save_all({"lists": {"a": ["x"]}, "default_list": "a"})
    s.close()

    s2 = Storage(tmp_path / "hatty.db")
    s2.connect()
    assert s2.is_empty() is False
    assert s2.load_all()["lists"] == {"a": ["x"]}
    s2.close()


def test_collection_keys_derived_from_persisted():
    # COLLECTION_KEYS is exactly the sqlite slice of the PERSISTED SSOT (issue #168).
    assert set(COLLECTION_KEYS) == {key for key, (_, dest) in PERSISTED.items() if dest == "sqlite"}
    # "columns" is the deliberate YAML-only asymmetry that must never leak into sqlite.
    assert "columns" in PERSISTED and PERSISTED["columns"][1] == "yaml"
    assert "columns" not in COLLECTION_KEYS


def test_persist_attrs_derived_from_persisted():
    # _PERSIST_ATTRS mirrors every PERSISTED key — one of the three lists that used
    # to drift (#168). _collections_snapshot's own runtime assert guards its key set
    # against COLLECTION_KEYS, exercised by the config-persistence acceptance tests.
    from hatty.main import HACLI

    assert set(HACLI._PERSIST_ATTRS) == set(PERSISTED)
    assert HACLI._PERSIST_ATTRS == {key: attr for key, (attr, _dest) in PERSISTED.items()}
