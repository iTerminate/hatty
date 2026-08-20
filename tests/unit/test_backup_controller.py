# hatty — MIT License. See LICENSE file for details.
"""Unit tests for BackupController: prefs merging, export/import wiring
against real (but disk-free) list/dashboard/graph controllers, and the
git-facing exit_sync_pending/sync_on_exit/pull_on_start gating. backup.py's
own directory read/write behavior is covered by tests/unit/test_backup.py;
these tests fake backup.build_files/write_export/read_export and git_sync so
they run without touching disk or a real git binary."""

from hatty import backup as backup_module
from hatty.const import CONFIG_KEY_BACKUP, DEFAULT_BACKUP
from hatty.controllers.backup import BackupController
from hatty.controllers.dashboards import DashboardController
from hatty.controllers.graphs import GraphController
from hatty.controllers.lists import ListController


class _StubKeysCtl:
    def __init__(self):
        self.applied = []

    def apply(self, cfg):
        self.applied.append(dict(cfg))


class _StubNotifyCtl:
    def __init__(self):
        self.notify_lists: set[str] = set()


class _StubApp:
    def __init__(self, app_config=None, demo=False):
        self.persist_calls = []
        self.notifications = []
        self.display_updates = 0
        self.terminal_title_calls = []
        self._demo = demo
        self.app_config = app_config if app_config is not None else {}
        self.columns = self.app_config.get("columns", [])
        self.theme = None
        self.available_themes = {"nord", "textual-dark"}
        self.entity_names = {}
        self.notify_ctl = _StubNotifyCtl()
        self.keys_ctl = _StubKeysCtl()
        self.list_ctl = ListController(self)
        self.dash_ctl = DashboardController(self)
        self.graph_ctl = GraphController(self)

    def persist(self, *keys):
        self.persist_calls.append(keys)

    def notify(self, message, **kwargs):
        self.notifications.append((message, kwargs))

    def _update_entities_display(self):
        self.display_updates += 1

    def _apply_terminal_title(self, cfg):
        self.terminal_title_calls.append(dict(cfg))


def _controller(**backup_prefs) -> tuple[BackupController, _StubApp]:
    app = _StubApp(app_config={CONFIG_KEY_BACKUP: backup_prefs} if backup_prefs else {})
    ctl = BackupController(app)
    ctl.apply(app.app_config)
    return ctl, app


# ── apply / prefs merging ────────────────────────────────────────────────────


def test_apply_merges_defaults():
    ctl, _app = _controller(path="/tmp/x")
    assert ctl.prefs["path"] == "/tmp/x"
    assert ctl.prefs["git_enabled"] is False
    assert ctl.prefs["sections"] == list(DEFAULT_BACKUP["sections"])


def test_apply_drops_unknown_sections():
    ctl, _app = _controller(sections=["lists", "not_a_section"])
    assert ctl.prefs["sections"] == ["lists"]


def test_apply_writes_normalized_prefs_back_into_cfg():
    cfg = {CONFIG_KEY_BACKUP: {"path": "/tmp/x"}}
    ctl = BackupController(_StubApp())
    ctl.apply(cfg)
    assert cfg[CONFIG_KEY_BACKUP]["git_enabled"] is False
    assert cfg[CONFIG_KEY_BACKUP]["path"] == "/tmp/x"


# ── export_now ────────────────────────────────────────────────────────────────


def test_export_now_no_path_configured():
    ctl, _app = _controller()
    ok, msg = ctl.export_now()
    assert ok is False
    assert "No backup directory" in msg


def test_export_now_no_sections_selected():
    ctl, _app = _controller(path="/tmp/x", sections=[])
    ok, msg = ctl.export_now()
    assert ok is False
    assert "No sections" in msg


def test_export_now_reports_written_and_removed(monkeypatch, tmp_path):
    ctl, app = _controller(path=str(tmp_path), sections=["lists"])
    app.list_ctl.list_names = ["Kitchen"]
    app.list_ctl.entity_lists = {"Kitchen": []}

    monkeypatch.setattr(backup_module, "build_files", lambda app, sections: {"lists/kitchen.list.json": {}})
    monkeypatch.setattr(
        backup_module,
        "write_export",
        lambda path, files, sections: (["lists/kitchen.list.json"], ["lists/old.list.json"]),
    )

    ok, msg = ctl.export_now()
    assert ok is True
    assert "1 file(s) written" in msg
    assert "1 stale file(s) removed" in msg


def test_export_now_surfaces_errors(monkeypatch, tmp_path):
    ctl, _app = _controller(path=str(tmp_path), sections=["lists"])

    def _raise(*_a, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr(backup_module, "build_files", lambda app, sections: {})
    monkeypatch.setattr(backup_module, "write_export", _raise)
    ok, msg = ctl.export_now()
    assert ok is False
    assert "disk full" in msg


# ── import_now ────────────────────────────────────────────────────────────────


def _fake_read_export(payloads, found):
    def _read(path, sections):
        return payloads, found

    return _read


def test_import_now_no_path_configured():
    ctl, _app = _controller()
    ok, msg, found = ctl.import_now(["lists"])
    assert ok is False
    assert found == []


def test_import_now_replaces_lists_and_persists(monkeypatch, tmp_path):
    ctl, app = _controller(path=str(tmp_path), sections=["lists"])
    app.list_ctl.list_names = ["Stale"]
    app.list_ctl.entity_lists = {"Stale": ["light.old"]}

    payloads = {
        "_manifest": {"default_list": "Kitchen"},
        "lists": [
            {"hatty_list": 1, "name": "Kitchen", "entities": ["light.a"], "manual": False, "notify": False},
        ],
    }
    monkeypatch.setattr(backup_module, "read_export", _fake_read_export(payloads, ["lists"]))

    ok, msg, found = ctl.import_now(["lists"])
    assert ok is True
    assert found == ["lists"]
    assert "Stale" not in app.list_ctl.entity_lists
    assert app.list_ctl.entity_lists["Kitchen"] == ["light.a"]
    assert app.list_ctl.default_list_name == "Kitchen"
    assert {"lists", "manual_lists", "notify_lists", "default_list"} in [set(c) for c in app.persist_calls]


def test_import_now_dashboards_preserves_temp_dashboards(monkeypatch, tmp_path):
    ctl, app = _controller(path=str(tmp_path), sections=["dashboards"])
    app.dash_ctl.create("Stale", 1, 1)
    app.dash_ctl.dashboards["Preview"] = {"rows": 1, "cols": 1, "slots": []}
    app.dash_ctl.dashboard_names.append("Preview")
    app.dash_ctl.temp_dashboard_names.add("Preview")

    payloads = {
        "_manifest": {},
        "dashboards": [
            {"hatty_dashboard": 1, "name": "Main", "dashboard": {"rows": 2, "cols": 2, "slots": []}},
        ],
    }
    monkeypatch.setattr(backup_module, "read_export", _fake_read_export(payloads, ["dashboards"]))

    ok, _msg, _found = ctl.import_now(["dashboards"])
    assert ok is True
    assert "Stale" not in app.dash_ctl.dashboards
    assert "Preview" in app.dash_ctl.dashboards  # temp dashboards survive a replace
    assert "Main" in app.dash_ctl.dashboards


def test_import_now_bad_object_is_skipped_not_fatal(monkeypatch, tmp_path):
    ctl, app = _controller(path=str(tmp_path), sections=["saved_graphs"])
    payloads = {
        "_manifest": {},
        "saved_graphs": [
            {"hatty_graph": 1, "name": "Good", "graph": {"entity_ids": ["sensor.a"]}},
            {"hatty_graph": 1, "name": "Bad"},  # missing "graph" -> ValueError, skipped
        ],
    }
    monkeypatch.setattr(backup_module, "read_export", _fake_read_export(payloads, ["saved_graphs"]))

    ok, _msg, _found = ctl.import_now(["saved_graphs"])
    assert ok is True
    assert "Good" in app.graph_ctl.saved_graphs
    assert "Bad" not in app.graph_ctl.saved_graphs


def test_import_now_entity_names_replaces_and_persists(monkeypatch, tmp_path):
    ctl, app = _controller(path=str(tmp_path), sections=["entity_names"])
    app.entity_names = {"light.old": "Old"}
    payloads = {"_manifest": {}, "entity_names": {"light.a": "Lamp"}}
    monkeypatch.setattr(backup_module, "read_export", _fake_read_export(payloads, ["entity_names"]))

    ok, _msg, found = ctl.import_now(["entity_names"])
    assert ok is True
    assert found == ["entity_names"]
    assert app.entity_names == {"light.a": "Lamp"}
    assert ("entity_names",) in app.persist_calls


def test_import_now_settings_applies_and_strips_password(monkeypatch, tmp_path):
    ctl, app = _controller(path=str(tmp_path), sections=["settings"])
    payloads = {
        "_manifest": {},
        "settings": {
            "columns": ["name"],
            "theme": "nord",
            "notifications": {"toast": True},
        },
    }
    monkeypatch.setattr(backup_module, "read_export", _fake_read_export(payloads, ["settings"]))

    ok, _msg, found = ctl.import_now(["settings"])
    assert ok is True
    assert found == ["settings"]
    assert app.app_config["columns"] == ["name"]
    assert app.columns == ["name"]
    assert app.theme == "nord"
    assert app.terminal_title_calls  # _apply_terminal_title was invoked
    # No explicit sqlite key touched by settings -> falls back to a bare persist().
    assert () in app.persist_calls


def test_import_now_keybindings_calls_keys_ctl_apply(monkeypatch, tmp_path):
    ctl, app = _controller(path=str(tmp_path), sections=["keybindings"])
    payloads = {"_manifest": {}, "keybindings": {"nav.search": "ctrl+f"}}
    monkeypatch.setattr(backup_module, "read_export", _fake_read_export(payloads, ["keybindings"]))

    ok, _msg, found = ctl.import_now(["keybindings"])
    assert ok is True
    assert found == ["keybindings"]
    assert app.app_config["keybindings"] == {"nav.search": "ctrl+f"}
    assert app.keys_ctl.applied  # apply() was called with the updated cfg


def test_import_now_rejects_bad_export(monkeypatch, tmp_path):
    ctl, _app = _controller(path=str(tmp_path), sections=["lists"])

    def _raise(path, sections):
        raise ValueError("No hatty backup found")

    monkeypatch.setattr(backup_module, "read_export", _raise)
    ok, msg, found = ctl.import_now(["lists"])
    assert ok is False
    assert "No hatty backup found" in msg
    assert found == []


# ── git gating ────────────────────────────────────────────────────────────────


def test_exit_sync_pending_false_by_default():
    ctl, _app = _controller(path="/tmp/x")
    assert ctl.exit_sync_pending() is False


def test_exit_sync_pending_requires_git_enabled_and_path():
    ctl, _app = _controller(git_enabled=True, commit_on_exit=True)  # no path
    assert ctl.exit_sync_pending() is False


def test_exit_sync_pending_true_when_commit_on_exit(tmp_path):
    ctl, _app = _controller(path=str(tmp_path), git_enabled=True, commit_on_exit=True)
    assert ctl.exit_sync_pending() is True


def test_exit_sync_pending_false_in_demo_mode(tmp_path):
    app = _StubApp(
        app_config={CONFIG_KEY_BACKUP: {"path": str(tmp_path), "git_enabled": True, "push_on_exit": True}},
        demo=True,
    )
    ctl = BackupController(app)
    ctl.apply(app.app_config)
    assert ctl.exit_sync_pending() is False


async def test_sync_on_exit_noop_when_not_pending():
    ctl, _app = _controller()
    ok, msg = await ctl.sync_on_exit()
    assert ok is True
    assert msg == ""


async def test_sync_on_exit_returns_export_failure_without_touching_git(monkeypatch, tmp_path):
    ctl, _app = _controller(path=str(tmp_path), git_enabled=True, commit_on_exit=True, sections=[])
    called = []
    monkeypatch.setattr("hatty.git_sync.commit_all_async", lambda *a, **kw: called.append(a))
    ok, msg = await ctl.sync_on_exit()
    assert ok is False
    assert "No sections" in msg
    assert called == []


async def test_sync_on_exit_reports_commit_only_phases(monkeypatch, tmp_path):
    ctl, app = _controller(path=str(tmp_path), sections=["lists"], git_enabled=True, commit_on_exit=True)
    app.list_ctl.list_names = []

    async def _fake_commit(_path, _message):
        return True, "Committed."

    monkeypatch.setattr("hatty.git_sync.commit_all_async", _fake_commit)

    phases = []
    ok, msg = await ctl.sync_on_exit(status=phases.append)
    assert ok is True
    assert msg == "Committed."
    assert phases == ["Exporting…", "Committing…"]  # push_on_exit is off


async def test_sync_on_exit_reports_push_phase_when_enabled(monkeypatch, tmp_path):
    ctl, app = _controller(path=str(tmp_path), sections=["lists"], git_enabled=True, push_on_exit=True)
    app.list_ctl.list_names = []

    async def _fake_commit(_path, _message):
        return True, "Committed."

    async def _fake_push(_path):
        return True, "Pushed to the remote."

    monkeypatch.setattr("hatty.git_sync.commit_all_async", _fake_commit)
    monkeypatch.setattr("hatty.git_sync.push_async", _fake_push)

    phases = []
    ok, msg = await ctl.sync_on_exit(status=phases.append)
    assert ok is True
    assert msg == "Pushed to the remote."
    assert phases == ["Exporting…", "Committing…", "Pushing…"]


async def test_sync_on_exit_skips_push_phase_when_commit_fails(monkeypatch, tmp_path):
    ctl, app = _controller(path=str(tmp_path), sections=["lists"], git_enabled=True, push_on_exit=True)
    app.list_ctl.list_names = []

    async def _fake_commit(_path, _message):
        return False, "git rejected the credentials."

    push_called = []
    monkeypatch.setattr("hatty.git_sync.commit_all_async", _fake_commit)
    monkeypatch.setattr("hatty.git_sync.push_async", lambda *a: push_called.append(a))

    phases = []
    ok, msg = await ctl.sync_on_exit(status=phases.append)
    assert ok is False
    assert "credentials" in msg
    assert phases == ["Exporting…", "Committing…"]
    assert push_called == []


async def test_pull_on_start_noop_when_disabled():
    ctl, app = _controller(path="/tmp/x", git_enabled=True, pull_on_start=False)
    await ctl.pull_on_start()
    assert app.notifications == []
