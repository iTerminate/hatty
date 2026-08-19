# hatty — MIT License. See LICENSE file for details.
"""Unit tests for backup.py: directory export/import, no git, no UI."""

import json

from hatty import backup
from hatty.controllers.dashboards import DashboardController
from hatty.controllers.graphs import GraphController
from hatty.controllers.lists import ListController


class _StubNotifyCtl:
    def __init__(self):
        self.notify_lists: set[str] = set()


class _StubApp:
    def __init__(self, app_config=None):
        self.persist_calls = []
        self.notifications = []
        self.notify_ctl = _StubNotifyCtl()
        self.app_config = app_config if app_config is not None else {}
        self.list_ctl = ListController(self)
        self.dash_ctl = DashboardController(self)
        self.graph_ctl = GraphController(self)

    def persist(self, *keys):
        self.persist_calls.append(keys)

    def notify(self, message, **kwargs):
        self.notifications.append((message, kwargs))


def _app(**config) -> _StubApp:
    return _StubApp(app_config=config)


# ── build_files ───────────────────────────────────────────────────────────────


def test_build_files_lists_section():
    app = _app()
    app.list_ctl.list_names = ["Kitchen"]
    app.list_ctl.entity_lists = {"Kitchen": ["light.a"]}
    files = backup.build_files(app, ["lists"])
    assert files["lists/kitchen.list.json"] == {
        "hatty_list": 1,
        "name": "Kitchen",
        "entities": ["light.a"],
        "manual": False,
        "notify": False,
    }
    assert backup.MANIFEST_FILENAME in files
    assert files[backup.MANIFEST_FILENAME]["sections"] == ["lists"]


def test_build_files_dashboards_excludes_temp_dashboards():
    app = _app()
    app.dash_ctl.create("Main", 2, 2)
    app.dash_ctl.dashboards["Preview"] = {"rows": 1, "cols": 1, "slots": []}
    app.dash_ctl.dashboard_names.append("Preview")
    app.dash_ctl.temp_dashboard_names.add("Preview")
    files = backup.build_files(app, ["dashboards"])
    assert "dashboards/main.dashboard.json" in files
    assert "dashboards/preview.dashboard.json" not in files


def test_build_files_saved_graphs_section():
    app = _app()
    app.graph_ctl.saved_graphs = {"Temps": {"entity_ids": ["sensor.a"], "graph_type": "line", "hours": 4}}
    files = backup.build_files(app, ["saved_graphs"])
    assert files["graphs/temps.graph.json"]["hatty_graph"] == 1
    assert files["graphs/temps.graph.json"]["graph"] == app.graph_ctl.saved_graphs["Temps"]


def test_build_files_entity_names_settings_keybindings_sections():
    app = _app(
        entity_names={"light.a": "Lamp"},
        columns=["name", "value"],
        theme="nord",
        notifications={"toast": True, "ntfy_password": "secret"},
        keybindings={"nav.search": "ctrl+f"},
    )
    files = backup.build_files(app, ["entity_names", "settings", "keybindings"])
    assert files["entity_names.json"] == {"hatty_entity_names": 1, "names": {"light.a": "Lamp"}}
    assert files["settings.json"]["settings"]["columns"] == ["name", "value"]
    assert files["settings.json"]["settings"]["theme"] == "nord"
    # The ntfy password never leaves the app.
    assert "ntfy_password" not in files["settings.json"]["settings"]["notifications"]
    assert files["keybindings.json"] == {"hatty_keybindings": 1, "keybindings": {"nav.search": "ctrl+f"}}


def test_build_files_manifest_carries_defaults_only_for_exported_sections():
    app = _app(default_list="Kitchen", default_dashboard="Main")
    files = backup.build_files(app, ["lists"])
    manifest = files[backup.MANIFEST_FILENAME]
    assert manifest["default_list"] == "Kitchen"
    assert "default_dashboard" not in manifest


def test_build_files_rejects_unknown_section():
    app = _app()
    try:
        backup.build_files(app, ["not_a_section"])
        assert False, "expected ValueError"
    except ValueError:
        pass


# ── write_export / read_export round trip ───────────────────────────────────


def test_write_then_read_round_trip_lists(tmp_path):
    app = _app()
    app.list_ctl.list_names = ["Kitchen"]
    app.list_ctl.entity_lists = {"Kitchen": ["light.a"]}
    app.list_ctl.manual_lists = {"Kitchen"}
    app.app_config["default_list"] = "Kitchen"

    files = backup.build_files(app, ["lists"])
    written, removed = backup.write_export(tmp_path, files, ["lists"])
    assert removed == []
    assert "lists/kitchen.list.json" in written
    assert backup.MANIFEST_FILENAME in written

    payloads, found = backup.read_export(tmp_path, ["lists"])
    assert found == ["lists"]
    assert payloads["lists"] == [
        {"hatty_list": 1, "name": "Kitchen", "entities": ["light.a"], "manual": True, "notify": False}
    ]
    assert payloads["_manifest"]["default_list"] == "Kitchen"


def test_write_export_is_byte_identical_to_dashboard_screen_export(tmp_path):
    # The whole point of sharing the single-object format: a file this writes
    # is exactly what "Export dashboard" already writes for the same object.
    app = _app()
    app.dash_ctl.create("Main", 2, 2)
    app.dash_ctl.set_slot("Main", 0, 0, "sensor", "sensor.temp")

    files = backup.build_files(app, ["dashboards"])
    backup.write_export(tmp_path, files, ["dashboards"])

    on_disk = json.loads((tmp_path / "dashboards" / "main.dashboard.json").read_text())
    assert on_disk == app.dash_ctl.to_export_payload("Main")


def test_write_export_only_rewrites_changed_files(tmp_path):
    app = _app()
    app.list_ctl.list_names = ["Kitchen"]
    app.list_ctl.entity_lists = {"Kitchen": ["light.a"]}
    files = backup.build_files(app, ["lists"])
    backup.write_export(tmp_path, files, ["lists"])

    written_again, _removed = backup.write_export(tmp_path, files, ["lists"])
    # Nothing changed since the last export (aside from exported_at in the
    # manifest, which always changes) -> the object file is skipped.
    assert "lists/kitchen.list.json" not in written_again
    assert backup.MANIFEST_FILENAME in written_again


def test_write_export_prunes_deleted_object_but_leaves_other_sections(tmp_path):
    app = _app()
    app.list_ctl.list_names = ["Kitchen", "Office"]
    app.list_ctl.entity_lists = {"Kitchen": [], "Office": []}
    files = backup.build_files(app, ["lists"])
    backup.write_export(tmp_path, files, ["lists"])
    assert (tmp_path / "lists" / "office.list.json").exists()

    app.list_ctl.list_names = ["Kitchen"]
    del app.list_ctl.entity_lists["Office"]
    files = backup.build_files(app, ["lists"])
    written, removed = backup.write_export(tmp_path, files, ["lists"])
    assert removed == ["lists/office.list.json"]
    assert not (tmp_path / "lists" / "office.list.json").exists()
    assert (tmp_path / "lists" / "kitchen.list.json").exists()


def test_write_export_of_subset_preserves_other_sections_manifest_fields(tmp_path):
    app = _app(default_list="Kitchen", default_dashboard="Main")
    app.list_ctl.list_names = ["Kitchen"]
    app.list_ctl.entity_lists = {"Kitchen": []}
    app.dash_ctl.create("Main", 1, 1)

    backup.write_export(tmp_path, backup.build_files(app, ["lists"]), ["lists"])
    backup.write_export(tmp_path, backup.build_files(app, ["dashboards"]), ["dashboards"])

    manifest = json.loads((tmp_path / backup.MANIFEST_FILENAME).read_text())
    assert manifest["default_list"] == "Kitchen"
    assert manifest["default_dashboard"] == "Main"
    assert sorted(manifest["sections"]) == ["dashboards", "lists"]

    payloads, found = backup.read_export(tmp_path, ["lists", "dashboards"])
    assert sorted(found) == ["dashboards", "lists"]


def test_read_export_settings_omits_ntfy_password(tmp_path):
    app = _app(
        columns=["name"],
        theme=None,
        graph_type="line",
        graph_hours=4,
        log_hours=24,
        terminal_title_enabled=True,
        terminal_title="hatty",
        notifications={"toast": True, "ntfy_password": "secret"},
    )
    backup.write_export(tmp_path, backup.build_files(app, ["settings"]), ["settings"])
    on_disk = (tmp_path / "settings.json").read_text()
    assert "secret" not in on_disk

    payloads, found = backup.read_export(tmp_path, ["settings"])
    assert found == ["settings"]
    assert "ntfy_password" not in payloads["settings"]["notifications"]


def test_read_export_missing_manifest_raises():
    import pytest

    with pytest.raises(ValueError, match="No hatty backup found"):
        backup.read_export("/nonexistent/hatty-backup-dir", ["lists"])


def test_read_export_bad_object_file_raises(tmp_path):
    import pytest

    (tmp_path / "lists").mkdir()
    (tmp_path / "lists" / "broken.list.json").write_text("not json")
    (tmp_path / backup.MANIFEST_FILENAME).write_text(json.dumps({"hatty_backup": 1, "sections": ["lists"]}))

    with pytest.raises(ValueError, match="Could not read"):
        backup.read_export(tmp_path, ["lists"])


def test_read_export_only_reads_requested_sections(tmp_path):
    app = _app()
    app.list_ctl.list_names = ["Kitchen"]
    app.list_ctl.entity_lists = {"Kitchen": []}
    app.graph_ctl.saved_graphs = {"Temps": {"entity_ids": ["sensor.a"], "graph_type": "line", "hours": 4}}
    backup.write_export(tmp_path, backup.build_files(app, ["lists", "saved_graphs"]), ["lists", "saved_graphs"])

    payloads, found = backup.read_export(tmp_path, ["lists"])
    assert found == ["lists"]
    assert "saved_graphs" not in payloads


def test_slug_matches_dashboard_slug_rule():
    assert backup.slug("Main Dashboard") == "main-dashboard"
    assert backup.slug("  ") == "export"
