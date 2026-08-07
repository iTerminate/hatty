# hatty — MIT License. See LICENSE file for details.
"""SQLite persistence for hatty's user-data collections (issue #63).

The connection settings and display preferences stay in the hand-editable
config.yaml; the *collections* that keep growing in complexity — lists,
entity-name overrides, dashboards with spanned/panel slots, and saved graphs —
live here in a real schema instead.

The app keeps these as in-memory dicts (the same shapes it always used); this
module is only the load/save boundary. Writes replace a whole collection in one
transaction — the collections are small (tens of rows), so diffing isn't worth
it, and a full replace can never leave a half-updated dashboard.

Shapes (see `_SCHEMA` for the actual columns):

- `dashboards`: dict keyed by name, each `{rows, cols, slots: [...]}` — a flat
  list of `{row, col, widget_type, entity_id}` for occupied cells only. A
  `panel` slot carries `entity_ids` instead of `entity_id`; a `gauge` slot may
  add `gauge_min`/`gauge_max`; any single-entity slot may add
  `show_last_changed` (true = show elapsed time since the entity's last state
  change); any slot may add `row_span`/`col_span` (absent = 1); a `split` slot
  carries a `children` fragment — a nested `{rows, cols, slots}` mini-grid
  whose own slots can't span or nest further.
- `saved_graphs`: dict keyed by name, each `{entity_ids, graph_type, hours,
  colors}` — `colors` (optional) maps entity_id → plotext color name.
- `manual_lists`: a set of list names currently in manual-sort order rather
  than the default alphabetical-by-display-name sort.
"""

import json
import os
import sqlite3
import threading
from pathlib import Path

from hatty.const import (
    CONFIG_KEY_COLUMNS,
    CONFIG_KEY_DASHBOARDS,
    CONFIG_KEY_DEFAULT_DASHBOARD,
    CONFIG_KEY_DEFAULT_LIST,
    CONFIG_KEY_ENTITY_NAMES,
    CONFIG_KEY_LISTS,
    CONFIG_KEY_MANUAL_LISTS,
    CONFIG_KEY_SAVED_GRAPHS,
)

SCHEMA_VERSION = 1


def _load_json(column: str | None):
    """Nullable JSON TEXT column -> Python value; NULL/empty stays None."""
    return json.loads(column) if column else None


def _dump_json(value) -> str | None:
    """Python value -> nullable JSON TEXT column; None stays NULL. An empty
    list/dict is stored as JSON (not NULL) so it round-trips unchanged."""
    return json.dumps(value) if value is not None else None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS lists (name TEXT PRIMARY KEY, position INTEGER);
CREATE TABLE IF NOT EXISTS list_entities (
    list_name TEXT, entity_id TEXT, position INTEGER,
    PRIMARY KEY (list_name, entity_id)
);
CREATE TABLE IF NOT EXISTS entity_names (entity_id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE IF NOT EXISTS dashboards (
    name TEXT PRIMARY KEY, rows INTEGER, cols INTEGER, position INTEGER, row_height INTEGER
);
CREATE TABLE IF NOT EXISTS dashboard_slots (
    dashboard TEXT, row INTEGER, col INTEGER,
    widget_type TEXT, entity_id TEXT,
    row_span INTEGER, col_span INTEGER,
    gauge_min REAL, gauge_max REAL,
    entity_ids TEXT,
    children TEXT,
    show_last_changed INTEGER,
    PRIMARY KEY (dashboard, row, col)
);
CREATE TABLE IF NOT EXISTS saved_graphs (
    name TEXT PRIMARY KEY,
    entity_ids TEXT NOT NULL,
    graph_type TEXT, hours REAL, colors TEXT, position INTEGER
);
"""

# Single source of truth for every persisted config key: key -> (app attribute
# holding its in-memory working copy, destination). SQLite keys are the growing
# user-data collections this module owns; YAML keys (just "columns") are display
# preferences that stay in the lean config.yaml. HACLI derives _PERSIST_ATTRS and
# _collections_snapshot from this table, and COLLECTION_KEYS below is the sqlite
# slice — a test in tests/unit/test_storage.py guards that they stay in sync so a
# new collection can't be half-registered (issue #168).
PERSISTED = {
    CONFIG_KEY_LISTS: ("entity_lists", "sqlite"),
    CONFIG_KEY_DEFAULT_LIST: ("default_list_name", "sqlite"),
    CONFIG_KEY_DASHBOARDS: ("dashboards", "sqlite"),
    CONFIG_KEY_DEFAULT_DASHBOARD: ("default_dashboard_name", "sqlite"),
    CONFIG_KEY_SAVED_GRAPHS: ("saved_graphs", "sqlite"),
    CONFIG_KEY_ENTITY_NAMES: ("entity_names", "sqlite"),
    CONFIG_KEY_MANUAL_LISTS: ("manual_lists", "sqlite"),
    CONFIG_KEY_COLUMNS: ("columns", "yaml"),
}

# The config keys this layer owns; stripped from the lean YAML.
COLLECTION_KEYS = tuple(key for key, (_, dest) in PERSISTED.items() if dest == "sqlite")


class Storage:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None
        # A single sqlite3 connection is shared across threads (saves run in
        # asyncio.to_thread workers, close() runs on the app's main thread).
        # check_same_thread=False disables sqlite's own guard, so we serialize
        # every access to the connection ourselves — two concurrent save_all
        # calls, or a close() racing an in-flight save, are otherwise a C-level
        # crash rather than a clean error.
        self._lock = threading.Lock()

    @property
    def _db(self) -> sqlite3.Connection:
        """The live connection, narrowed non-None. Every DB operation runs after
        connect(); callers that might race close() (save_all) still guard
        self._conn explicitly first."""
        if self._conn is None:
            raise RuntimeError("Storage.connect() has not been called")
        return self._conn

    def connect(self) -> None:
        # Keep the DB (user data) and its dir private, mirroring config.py (issue
        # #156). The WAL sidecar files (-wal/-shm) inherit the main file's mode.
        parent = Path(self.db_path).parent
        parent.mkdir(parents=True, exist_ok=True)
        os.chmod(parent, 0o700)
        with self._lock:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            os.chmod(self.db_path, 0o600)
            self._conn.row_factory = sqlite3.Row
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(_SCHEMA)
            self._migrate()
            self._db.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),)
            )
            self._db.commit()

    def _migrate(self) -> None:
        """Column additions for DBs created before the column existed —
        CREATE TABLE IF NOT EXISTS never alters an existing table."""
        slot_columns = {r["name"] for r in self._db.execute("PRAGMA table_info(dashboard_slots)")}
        if "children" not in slot_columns:
            self._db.execute("ALTER TABLE dashboard_slots ADD COLUMN children TEXT")
        if "show_last_changed" not in slot_columns:
            self._db.execute("ALTER TABLE dashboard_slots ADD COLUMN show_last_changed INTEGER")
        dashboard_columns = {r["name"] for r in self._db.execute("PRAGMA table_info(dashboards)")}
        if "row_height" not in dashboard_columns:
            self._db.execute("ALTER TABLE dashboards ADD COLUMN row_height INTEGER")

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def is_empty(self) -> bool:
        """True when no collections have been stored yet — the signal to import
        from a legacy YAML config exactly once."""
        cur = self._db.execute("SELECT COUNT(*) AS n FROM meta WHERE key = 'imported'")
        return cur.fetchone()["n"] == 0

    def _mark_imported(self) -> None:
        self._db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('imported', '1')")

    # ── Loading ──────────────────────────────────────────────────────────────

    def load_all(self) -> dict:
        """Return the collections in the same shapes the app holds in memory."""
        return {
            "lists": self._load_lists(),
            "entity_names": self._load_entity_names(),
            "dashboards": self._load_dashboards(),
            "saved_graphs": self._load_saved_graphs(),
            "manual_lists": _load_json(self._get_meta("manual_lists")) or [],
            "default_list": self._get_meta("default_list"),
            "default_dashboard": self._get_meta("default_dashboard"),
        }

    def _get_meta(self, key: str) -> str | None:
        cur = self._db.execute("SELECT value FROM meta WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else None

    def _load_lists(self) -> dict[str, list]:
        lists: dict[str, list] = {}
        for row in self._db.execute("SELECT name FROM lists ORDER BY position, name"):
            lists[row["name"]] = []
        for row in self._db.execute(
            "SELECT list_name, entity_id FROM list_entities ORDER BY list_name, position"
        ):
            lists.setdefault(row["list_name"], []).append(row["entity_id"])
        return lists

    def _load_entity_names(self) -> dict[str, str]:
        return {r["entity_id"]: r["name"] for r in self._db.execute("SELECT entity_id, name FROM entity_names")}

    def _load_dashboards(self) -> dict[str, dict]:
        dashboards: dict[str, dict] = {}
        for row in self._db.execute("SELECT name, rows, cols, row_height FROM dashboards ORDER BY position, name"):
            dash = {"rows": row["rows"], "cols": row["cols"], "slots": []}
            if row["row_height"] is not None:
                dash["row_height"] = row["row_height"]
            dashboards[row["name"]] = dash
        for row in self._db.execute(
            "SELECT dashboard, row, col, widget_type, entity_id, row_span, col_span, "
            "gauge_min, gauge_max, entity_ids, children, show_last_changed "
            "FROM dashboard_slots ORDER BY dashboard, row, col"
        ):
            dash = dashboards.get(row["dashboard"])
            if dash is None:
                continue
            slot = {
                "row": row["row"],
                "col": row["col"],
                "widget_type": row["widget_type"],
                "entity_id": row["entity_id"],
            }
            if row["row_span"] and row["row_span"] != 1:
                slot["row_span"] = row["row_span"]
            if row["col_span"] and row["col_span"] != 1:
                slot["col_span"] = row["col_span"]
            if row["gauge_min"] is not None:
                slot["gauge_min"] = row["gauge_min"]
            if row["gauge_max"] is not None:
                slot["gauge_max"] = row["gauge_max"]
            entity_ids = _load_json(row["entity_ids"])
            if entity_ids is not None:
                slot["entity_ids"] = entity_ids
            children = _load_json(row["children"])
            if children is not None:
                slot["children"] = children
            if row["show_last_changed"]:
                slot["show_last_changed"] = True
            dash["slots"].append(slot)
        return dashboards

    def _load_saved_graphs(self) -> dict[str, dict]:
        graphs: dict[str, dict] = {}
        for row in self._db.execute(
            "SELECT name, entity_ids, graph_type, hours, colors FROM saved_graphs ORDER BY position, name"
        ):
            graph = {
                "entity_ids": json.loads(row["entity_ids"]),
                "graph_type": row["graph_type"],
                "hours": row["hours"],
            }
            colors = _load_json(row["colors"])
            if colors is not None:
                graph["colors"] = colors
            graphs[row["name"]] = graph
        return graphs

    # ── Saving ───────────────────────────────────────────────────────────────

    def save_all(self, collections: dict) -> None:
        """Replace every collection in one transaction from the app's in-memory
        dicts (keys: lists, entity_names, dashboards, saved_graphs, manual_lists,
        default_list, default_dashboard). Missing keys are treated as empty."""
        with self._lock:
            conn = self._conn
            if conn is None:  # closed out from under a queued save — no-op
                return
            with conn:  # transaction
                self._write_lists(collections.get("lists") or {})
                self._write_entity_names(collections.get("entity_names") or {})
                self._write_dashboards(collections.get("dashboards") or {})
                self._write_saved_graphs(collections.get("saved_graphs") or {})
                self._set_meta("manual_lists", _dump_json(sorted(collections.get("manual_lists") or [])))
                self._set_meta("default_list", collections.get("default_list"))
                self._set_meta("default_dashboard", collections.get("default_dashboard"))
                self._mark_imported()

    def _set_meta(self, key: str, value: str | None) -> None:
        if value is None:
            self._db.execute("DELETE FROM meta WHERE key = ?", (key,))
        else:
            self._db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    def _write_lists(self, lists: dict) -> None:
        self._db.execute("DELETE FROM lists")
        self._db.execute("DELETE FROM list_entities")
        for pos, (name, entities) in enumerate(lists.items()):
            self._db.execute("INSERT INTO lists (name, position) VALUES (?, ?)", (name, pos))
            self._db.executemany(
                "INSERT INTO list_entities (list_name, entity_id, position) VALUES (?, ?, ?)",
                [(name, eid, i) for i, eid in enumerate(entities)],
            )

    def _write_entity_names(self, names: dict) -> None:
        self._db.execute("DELETE FROM entity_names")
        self._db.executemany(
            "INSERT INTO entity_names (entity_id, name) VALUES (?, ?)", list(names.items())
        )

    def _write_dashboards(self, dashboards: dict) -> None:
        self._db.execute("DELETE FROM dashboards")
        self._db.execute("DELETE FROM dashboard_slots")
        for pos, (name, dash) in enumerate(dashboards.items()):
            self._db.execute(
                "INSERT INTO dashboards (name, rows, cols, position, row_height) VALUES (?, ?, ?, ?, ?)",
                (name, dash.get("rows"), dash.get("cols"), pos, dash.get("row_height")),
            )
            for slot in dash.get("slots", []):
                self._db.execute(
                    "INSERT INTO dashboard_slots (dashboard, row, col, widget_type, entity_id, "
                    "row_span, col_span, gauge_min, gauge_max, entity_ids, children, show_last_changed) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        name,
                        slot.get("row"),
                        slot.get("col"),
                        slot.get("widget_type"),
                        slot.get("entity_id"),
                        slot.get("row_span", 1),
                        slot.get("col_span", 1),
                        slot.get("gauge_min"),
                        slot.get("gauge_max"),
                        _dump_json(slot.get("entity_ids")),
                        _dump_json(slot.get("children")),
                        1 if slot.get("show_last_changed") else None,
                    ),
                )

    def _write_saved_graphs(self, graphs: dict) -> None:
        self._db.execute("DELETE FROM saved_graphs")
        for pos, (name, graph) in enumerate(graphs.items()):
            self._db.execute(
                "INSERT INTO saved_graphs (name, entity_ids, graph_type, hours, colors, position) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    name,
                    json.dumps(graph.get("entity_ids", [])),
                    graph.get("graph_type"),
                    graph.get("hours"),
                    _dump_json(graph.get("colors")),
                    pos,
                ),
            )
