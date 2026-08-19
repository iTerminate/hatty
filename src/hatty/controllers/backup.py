# hatty — MIT License. See LICENSE file for details.
"""Backup & Sync: owns the user's export/git prefs and drives backup.py +
git_sync.py against the running app's live state (`app.list_ctl`, `app.dash_ctl`,
`app.graph_ctl`, `app.app_config`). `apply()` is called from HACLI._apply_config
(boot, demo, and the post-onboarding restart) and again from _on_config_saved,
mirroring KeybindingController."""

import asyncio
from collections.abc import Sequence
from pathlib import Path

from hatty import backup as backup_module
from hatty import git_sync
from hatty.const import (
    CONFIG_KEY_BACKUP,
    CONFIG_KEY_COLUMNS,
    CONFIG_KEY_GRAPH_HOURS,
    CONFIG_KEY_GRAPH_TYPE,
    CONFIG_KEY_KEYBINDINGS,
    CONFIG_KEY_LOG_HOURS,
    CONFIG_KEY_NOTIFICATIONS,
    CONFIG_KEY_TERMINAL_TITLE,
    CONFIG_KEY_TERMINAL_TITLE_ENABLED,
    CONFIG_KEY_THEME,
    DEFAULT_BACKUP,
)

# section id -> attribute holding the controller with to_export_payload /
# import_from_payload for that section's objects.
_OBJECT_CONTROLLERS = {"lists": "list_ctl", "dashboards": "dash_ctl", "saved_graphs": "graph_ctl"}

# section id -> storage.PERSISTED keys it needs saved after a replace.
_OBJECT_PERSIST_KEYS = {
    "lists": ("lists", "manual_lists", "notify_lists", "default_list"),
    "dashboards": ("dashboards", "default_dashboard"),
    "saved_graphs": ("saved_graphs",),
}

_SETTINGS_KEYS = (
    CONFIG_KEY_COLUMNS,
    CONFIG_KEY_THEME,
    CONFIG_KEY_GRAPH_TYPE,
    CONFIG_KEY_GRAPH_HOURS,
    CONFIG_KEY_LOG_HOURS,
    CONFIG_KEY_TERMINAL_TITLE_ENABLED,
    CONFIG_KEY_TERMINAL_TITLE,
)


class BackupController:
    def __init__(self, app) -> None:
        self._app = app
        self.prefs: dict = dict(DEFAULT_BACKUP)

    def apply(self, cfg: dict) -> None:
        """Merge cfg[backup] over the defaults, store the result, and
        normalize cfg in place so a save right afterwards writes back the
        merged prefs (mirrors KeybindingController.apply)."""
        merged = dict(DEFAULT_BACKUP)
        merged.update(cfg.get(CONFIG_KEY_BACKUP) or {})
        merged["sections"] = [s for s in backup_module.SECTIONS if s in (merged.get("sections") or [])]
        self.prefs = merged
        cfg[CONFIG_KEY_BACKUP] = dict(merged)

    # ── Export / import ──────────────────────────────────────────────────────

    def export_now(self, path: str | None = None, sections: Sequence[str] | None = None) -> tuple[bool, str]:
        """`path`/`sections` default to the saved prefs; the config screen
        passes the currently-entered (unsaved) widget values instead, the
        same "act on unsaved fields" precedent as action_test_connection."""
        path = path if path is not None else self.prefs.get("path")
        if not path:
            return False, "No backup directory set."
        sections = sections if sections is not None else (self.prefs.get("sections") or [])
        sections = [s for s in backup_module.SECTIONS if s in sections]
        if not sections:
            return False, "No sections selected to export."
        try:
            files = backup_module.build_files(self._app, sections)
            written, removed = backup_module.write_export(Path(path), files, sections)
        except (OSError, ValueError) as exc:
            return False, f"Export failed: {exc}"
        parts = []
        if written:
            parts.append(f"{len(written)} file(s) written")
        if removed:
            parts.append(f"{len(removed)} stale file(s) removed")
        detail = f" ({', '.join(parts)})" if parts else " (already up to date)"
        return True, f"Exported to {path}{detail}."

    def import_now(self, sections: Sequence[str], path: str | None = None) -> tuple[bool, str, list[str]]:
        path = path if path is not None else self.prefs.get("path")
        if not path:
            return False, "No backup directory set.", []
        sections = [s for s in backup_module.SECTIONS if s in sections]
        if not sections:
            return False, "No sections selected to import.", []
        try:
            payloads, found = backup_module.read_export(Path(path), sections)
        except ValueError as exc:
            return False, str(exc), []

        self._apply_imported(payloads, found)

        labels = [backup_module.SECTION_LABELS[s] for s in found]
        return True, f"Imported {', '.join(labels)} from {path}.", found

    def _apply_imported(self, payloads: dict, found: Sequence[str]) -> None:
        app = self._app
        manifest = payloads.get("_manifest") or {}
        persist_keys: set[str] = set()

        for section in ("lists", "dashboards", "saved_graphs"):
            if section not in found:
                continue
            ctl = getattr(app, _OBJECT_CONTROLLERS[section])
            self._replace_collection(section, ctl)
            for payload in payloads[section]:
                try:
                    ctl.import_from_payload(payload)
                except ValueError:
                    continue  # one bad object shouldn't abort the whole import
            persist_keys.update(_OBJECT_PERSIST_KEYS[section])

        if "lists" in found:
            default_list = manifest.get("default_list")
            app.list_ctl.default_list_name = default_list if default_list in app.list_ctl.entity_lists else None
        if "dashboards" in found:
            default_dashboard = manifest.get("default_dashboard")
            app.dash_ctl.default_dashboard_name = (
                default_dashboard if default_dashboard in app.dash_ctl.dashboards else None
            )

        if "entity_names" in found:
            app.entity_names = payloads["entity_names"]
            persist_keys.add("entity_names")

        if "settings" in found:
            self._apply_settings(payloads["settings"])

        if "keybindings" in found:
            app.app_config[CONFIG_KEY_KEYBINDINGS] = payloads["keybindings"]
            app.keys_ctl.apply(app.app_config)

        if persist_keys:
            app.persist(*sorted(persist_keys))
        elif "settings" in found or "keybindings" in found:
            app.persist()

        app._update_entities_display()

    def _replace_collection(self, section: str, ctl) -> None:
        """Wipe `section`'s in-memory collection ahead of a wholesale replace
        (behind a confirm popup in the UI) — dashboards keeps any in-session
        temp/preview dashboards, which are never part of an export."""
        if section == "lists":
            ctl.entity_lists.clear()
            ctl.list_names.clear()
            ctl.manual_lists.clear()
            self._app.notify_ctl.notify_lists.clear()
        elif section == "dashboards":
            temp = ctl.temp_dashboard_names
            for name in [n for n in ctl.dashboards if n not in temp]:
                del ctl.dashboards[name]
            ctl.dashboard_names[:] = [n for n in ctl.dashboard_names if n in temp]
            if ctl.current_dashboard_name not in ctl.dashboards:
                ctl.current_dashboard_name = ctl.dashboard_names[0] if ctl.dashboard_names else None
        elif section == "saved_graphs":
            ctl.saved_graphs.clear()

    def _apply_settings(self, settings: dict) -> None:
        app = self._app
        for key in _SETTINGS_KEYS:
            if key in settings:
                app.app_config[key] = settings[key]
        if CONFIG_KEY_NOTIFICATIONS in settings:
            merged = dict(app.app_config.get(CONFIG_KEY_NOTIFICATIONS) or {})
            merged.update(settings[CONFIG_KEY_NOTIFICATIONS])  # export never carries ntfy_password
            app.app_config[CONFIG_KEY_NOTIFICATIONS] = merged

        app.columns = app.app_config.get(CONFIG_KEY_COLUMNS, app.columns)
        new_theme = app.app_config.get(CONFIG_KEY_THEME)
        if new_theme and new_theme in app.available_themes:
            app.theme = new_theme
        app._apply_terminal_title(app.app_config)

    # ── Git ───────────────────────────────────────────────────────────────────

    def exit_sync_pending(self) -> bool:
        if self._app._demo:
            return False
        if not self.prefs.get("git_enabled") or not self.prefs.get("path"):
            return False
        return bool(self.prefs.get("commit_on_exit") or self.prefs.get("push_on_exit"))

    async def pull_on_start(self) -> None:
        app = self._app
        if app._demo or not self.prefs.get("git_enabled") or not self.prefs.get("pull_on_start"):
            return
        path = self.prefs.get("path")
        if not path:
            return
        ok, msg = await git_sync.pull_async(path, rebase=bool(self.prefs.get("pull_rebase")))
        if not ok:
            app.notify(msg, title="Backup Pull Failed", severity="error")
            return
        if not self.prefs.get("import_on_pull"):
            app.notify(msg, title="Backup Pulled")
            return
        ok, msg, _found = self.import_now(self.prefs.get("sections") or [])
        title = "Backup Imported" if ok else "Backup Import Failed"
        app.notify(msg, title=title, severity="information" if ok else "error")

    async def sync_on_exit(self, timeout: float = 75.0) -> tuple[bool, str]:
        # 75s: room for git_sync's own NETWORK_TIMEOUT (60s) on the push plus a
        # buffer for the local commit and export, as a belt-and-suspenders cap
        # so a stalled network can't hang the exit-sync overlay indefinitely.
        if not self.exit_sync_pending():
            return True, ""
        path = self.prefs.get("path") or ""
        ok, msg = self.export_now()
        if not ok:
            return False, msg

        message = git_sync.default_commit_message()
        op = git_sync.commit_and_push_async if self.prefs.get("push_on_exit") else git_sync.commit_all_async
        try:
            return await asyncio.wait_for(op(path, message), timeout=timeout)
        except asyncio.TimeoutError:
            return False, "Timed out syncing with git."
