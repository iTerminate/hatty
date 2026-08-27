# hatty — MIT License. See LICENSE file for details.
"""Config screen "Backup & Sync" category: navigation, saving prefs, and the
export/import/git buttons acting on the currently-entered (unsaved) widget
values — the action_test_connection precedent."""

from textual.widgets import Input, SelectionList

from hatty import backup as backup_module
from hatty.ui.config_screen import ConfigScreen
from hatty.ui.confirm_popup import ConfirmPopup
from tests.conftest import make_config

_CONFIG = {**make_config(), "lists": {}}


async def _open_backup(app, pilot):
    await pilot.pause()
    app.action_show_config()
    await pilot.pause()
    assert isinstance(app.screen, ConfigScreen)
    screen = app.screen
    screen.show_category("cat_backup")
    await pilot.pause()
    return screen


async def test_backup_category_listed_and_navigable(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_backup(app, pilot)
        assert screen.query_one("#cfg_backup_path", Input)
        assert screen.focused is screen.query_one("#cfg_backup_path")


async def test_save_persists_path_sections_and_git_toggles(make_app, sample_entities, tmp_path):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_backup(app, pilot)

        screen.query_one("#cfg_backup_path", Input).value = str(tmp_path)
        sections = screen.query_one("#cfg_backup_sections", SelectionList)
        sections.deselect_all()
        sections.select("lists")
        sections.select("dashboards")
        git = screen.query_one("#cfg_backup_git", SelectionList)
        git.select("git_enabled")
        git.select("push_on_exit")

        await pilot.press("ctrl+s")
        await pilot.pause()

    saved = app.app_config["backup"]
    assert saved["path"] == str(tmp_path)
    assert sorted(saved["sections"]) == ["dashboards", "lists"]
    assert saved["git_enabled"] is True
    assert saved["push_on_exit"] is True
    assert saved["commit_on_exit"] is False


async def test_export_now_writes_files_for_selected_sections(make_app, sample_entities, tmp_path):
    config_data = {**_CONFIG, "lists": {"list_a": ["switch.fan"]}}
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        screen = await _open_backup(app, pilot)

        screen.query_one("#cfg_backup_path", Input).value = str(tmp_path)
        sections = screen.query_one("#cfg_backup_sections", SelectionList)
        sections.deselect_all()
        sections.select("lists")

        await pilot.press("tab")  # leave the Input so its .value is committed
        await screen.run_worker(screen._do_backup_export(str(tmp_path), ["lists"])).wait()
        await pilot.pause()

        status = screen.query_one("#cfg_backup_status")
        assert "Exported" in str(status.content)

    assert (tmp_path / "lists" / "list_a.list.json").exists()
    assert not (tmp_path / "dashboards").exists()


async def test_export_requires_path_and_section(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_backup(app, pilot)
        screen.query_one("#cfg_backup_sections", SelectionList).deselect_all()

        screen.action_backup_export()
        await pilot.pause()

        status = screen.query_one("#cfg_backup_status")
        assert "directory and at least one section" in str(status.content)


async def test_import_now_confirms_then_replaces(make_app, sample_entities, tmp_path):
    config_data = {**_CONFIG, "lists": {"stale": ["light.old"]}}
    app = make_app(entities=sample_entities, config_data=config_data)

    export_dir = tmp_path / "export"
    export_dir.mkdir()
    files = {
        "lists/kitchen.list.json": {
            "hatty_list": 1,
            "name": "Kitchen",
            "entities": ["light.a"],
            "manual": False,
            "notify": False,
        },
    }
    backup_module.write_export(export_dir, files, ["lists"])

    async with app.run_test() as pilot:
        screen = await _open_backup(app, pilot)
        screen.query_one("#cfg_backup_path", Input).value = str(export_dir)
        sections = screen.query_one("#cfg_backup_sections", SelectionList)
        sections.deselect_all()
        sections.select("lists")

        screen.action_backup_import()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmPopup)
        await pilot.press("y")
        await pilot.pause()
        await pilot.pause()

    assert "stale" not in app.entity_lists
    assert app.entity_lists["Kitchen"] == ["light.a"]


async def test_import_cancelled_leaves_data_untouched(make_app, sample_entities, tmp_path):
    config_data = {**_CONFIG, "lists": {"stale": ["light.old"]}}
    app = make_app(entities=sample_entities, config_data=config_data)

    export_dir = tmp_path / "export"
    export_dir.mkdir()
    files = {
        "lists/kitchen.list.json": {
            "hatty_list": 1,
            "name": "Kitchen",
            "entities": ["light.a"],
            "manual": False,
            "notify": False,
        },
    }
    backup_module.write_export(export_dir, files, ["lists"])

    async with app.run_test() as pilot:
        screen = await _open_backup(app, pilot)
        screen.query_one("#cfg_backup_path", Input).value = str(export_dir)
        sections = screen.query_one("#cfg_backup_sections", SelectionList)
        sections.deselect_all()
        sections.select("lists")

        screen.action_backup_import()
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()

    assert "stale" in app.entity_lists
    assert "Kitchen" not in app.entity_lists


async def test_init_pull_push_status_buttons_drive_git_sync(make_app, sample_entities, tmp_path, monkeypatch):
    from hatty import git_sync

    calls = []

    def fake_run_git(args, cwd, timeout=None):
        calls.append(args)
        if args[:3] == ["diff", "--cached", "--quiet"]:
            return (1, "", "")
        if args[0] == "remote":
            return (0, "origin\n", "")
        if args[:2] == ["symbolic-ref", "--quiet"]:
            return (0, "main\n", "")
        return (0, "", "")

    monkeypatch.setattr(git_sync, "_run_git", fake_run_git)

    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_backup(app, pilot)
        screen.query_one("#cfg_backup_path", Input).value = str(tmp_path)

        await screen.run_worker(screen._do_backup_init(str(tmp_path))).wait()
        await pilot.pause()
        assert any(c[0] == "init" for c in calls)

        await screen.run_worker(screen._do_backup_pull(str(tmp_path), False)).wait()
        await pilot.pause()
        assert any(c[0] == "pull" for c in calls)

        await screen.run_worker(screen._do_backup_push(str(tmp_path))).wait()
        await pilot.pause()
        assert any(c[0] == "push" for c in calls)

        await screen.run_worker(screen._do_backup_status_check(str(tmp_path))).wait()
        await pilot.pause()
        assert any(c[:2] == ["rev-parse", "--show-toplevel"] for c in calls)


async def test_git_buttons_require_path_first(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CONFIG)
    async with app.run_test() as pilot:
        screen = await _open_backup(app, pilot)
        screen.query_one("#cfg_backup_path", Input).value = ""

        screen.action_backup_init()
        await pilot.pause()
        status = screen.query_one("#cfg_backup_status")
        assert "directory first" in str(status.content)
