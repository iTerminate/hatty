# hatty — MIT License. See LICENSE file for details.
"""Directory export/import for the Backup & Sync feature: a directory of small
JSON files — one per list/dashboard/saved graph, plus a handful of
whole-collection files — that mirrors the single-object export format
`to_export_payload`/`import_from_payload` already use (`controllers/lists.py`,
`controllers/dashboards.py`, `controllers/graphs.py`), so any file here can
also be hand-exported/imported through the normal popups, and vice versa.

No git here — `git_sync.py` is the separate layer that treats this directory
as an optional git working tree. This module only knows how to read and write
the files.

Layout:

    <dir>/hatty-backup.json           manifest: format version, which sections
                                       have ever been exported here, and the
                                       cross-object scalars default_list /
                                       default_dashboard
    <dir>/lists/<slug>.list.json      one hatty_list export per list
    <dir>/dashboards/<slug>.dashboard.json   one hatty_dashboard export per dashboard
    <dir>/graphs/<slug>.graph.json    one hatty_graph export per saved graph
    <dir>/entity_names.json           the whole entity_names mapping
    <dir>/settings.json               display prefs (never the HA token or ntfy password)
    <dir>/keybindings.json            the keybinding overrides
"""

import json
import os
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from hatty import __version__
from hatty.const import (
    CONFIG_KEY_COLUMNS,
    CONFIG_KEY_DEFAULT_DASHBOARD,
    CONFIG_KEY_DEFAULT_LIST,
    CONFIG_KEY_ENTITY_NAMES,
    CONFIG_KEY_GRAPH_HOURS,
    CONFIG_KEY_GRAPH_TYPE,
    CONFIG_KEY_KEYBINDINGS,
    CONFIG_KEY_LOG_HOURS,
    CONFIG_KEY_NOTIFICATIONS,
    CONFIG_KEY_TERMINAL_TITLE,
    CONFIG_KEY_TERMINAL_TITLE_ENABLED,
    CONFIG_KEY_THEME,
)

#: Bumped if the manifest/object-file shapes ever change incompatibly.
BACKUP_FORMAT_VERSION = 1

MANIFEST_FILENAME = "hatty-backup.json"

SECTIONS: tuple[str, ...] = ("lists", "dashboards", "saved_graphs", "entity_names", "settings", "keybindings")

SECTION_LABELS: dict[str, str] = {
    "lists": "Lists",
    "dashboards": "Dashboards",
    "saved_graphs": "Saved Graphs",
    "entity_names": "Entity Name Overrides",
    "settings": "Display Settings",
    "keybindings": "Keybindings",
}

# section id -> (subdirectory, single-object marker key). The three sections
# with one file per object, mirroring each controller's export/import format.
_OBJECT_SECTIONS: dict[str, tuple[str, str]] = {
    "lists": ("lists", "hatty_list"),
    "dashboards": ("dashboards", "hatty_dashboard"),
    "saved_graphs": ("graphs", "hatty_graph"),
}

# The "settings" section's config keys — display prefs only, never the HA
# token (not in this list) or the ntfy password (stripped from notifications
# below).
_SETTINGS_KEYS = (
    CONFIG_KEY_COLUMNS,
    CONFIG_KEY_THEME,
    CONFIG_KEY_GRAPH_TYPE,
    CONFIG_KEY_GRAPH_HOURS,
    CONFIG_KEY_LOG_HOURS,
    CONFIG_KEY_TERMINAL_TITLE_ENABLED,
    CONFIG_KEY_TERMINAL_TITLE,
)


def slug(name: str) -> str:
    """Mirrors the dashboard-export filename rule (`ui/dashboard/screen.py`)."""
    return name.strip().lower().replace(" ", "-") or "export"


def _validate_sections(sections: Sequence[str]) -> tuple[str, ...]:
    unknown = set(sections) - set(SECTIONS)
    if unknown:
        raise ValueError(f"Unknown backup section(s): {', '.join(sorted(unknown))}")
    return tuple(s for s in SECTIONS if s in sections)


def _settings_payload(cfg: dict) -> dict:
    settings = {key: cfg.get(key) for key in _SETTINGS_KEYS}
    notifications = dict(cfg.get(CONFIG_KEY_NOTIFICATIONS) or {})
    notifications.pop("ntfy_password", None)
    settings[CONFIG_KEY_NOTIFICATIONS] = notifications
    return settings


def build_files(app, sections: Sequence[str]) -> dict[str, dict]:
    """{relative path: JSON-able payload} for `sections`. Object sections
    (lists/dashboards/saved_graphs) delegate to the matching controller's
    `to_export_payload` so there is exactly one definition of each format."""
    sections = _validate_sections(sections)
    files: dict[str, dict] = {}

    if "lists" in sections:
        for name in app.list_ctl.list_names:
            files[f"lists/{slug(name)}.list.json"] = app.list_ctl.to_export_payload(name)
    if "dashboards" in sections:
        temp = app.dash_ctl.temp_dashboard_names
        for name in app.dash_ctl.dashboard_names:
            if name in temp:
                continue
            files[f"dashboards/{slug(name)}.dashboard.json"] = app.dash_ctl.to_export_payload(name)
    if "saved_graphs" in sections:
        for name in app.graph_ctl.saved_graphs:
            files[f"graphs/{slug(name)}.graph.json"] = app.graph_ctl.to_export_payload(name)
    if "entity_names" in sections:
        files["entity_names.json"] = {
            "hatty_entity_names": BACKUP_FORMAT_VERSION,
            "names": dict(app.app_config.get(CONFIG_KEY_ENTITY_NAMES) or {}),
        }
    if "settings" in sections:
        files["settings.json"] = {
            "hatty_settings": BACKUP_FORMAT_VERSION,
            "settings": _settings_payload(app.app_config),
        }
    if "keybindings" in sections:
        files["keybindings.json"] = {
            "hatty_keybindings": BACKUP_FORMAT_VERSION,
            "keybindings": dict(app.app_config.get(CONFIG_KEY_KEYBINDINGS) or {}),
        }

    # The manifest is a *patch*: write_export merges it over whatever manifest
    # already exists, so exporting a subset of sections never forgets what a
    # previous export (of other sections) recorded.
    manifest: dict = {"hatty_backup": BACKUP_FORMAT_VERSION, "sections": list(sections)}
    if "lists" in sections:
        manifest[CONFIG_KEY_DEFAULT_LIST] = app.app_config.get(CONFIG_KEY_DEFAULT_LIST)
    if "dashboards" in sections:
        manifest[CONFIG_KEY_DEFAULT_DASHBOARD] = app.app_config.get(CONFIG_KEY_DEFAULT_DASHBOARD)
    files[MANIFEST_FILENAME] = manifest

    return files


def _write_json_if_changed(path: Path, payload: dict) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2) + "\n"
    if path.exists() and path.read_text() == text:
        return False
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return True


def _read_manifest_tolerant(directory: Path) -> dict:
    """Best-effort read for merging — a missing/corrupt manifest just means
    "nothing recorded yet", not an error (that's `read_export`'s job)."""
    path = directory / MANIFEST_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _prune_stale(directory: Path, files: dict[str, dict], sections: Sequence[str]) -> list[str]:
    removed: list[str] = []
    for section in sections:
        entry = _OBJECT_SECTIONS.get(section)
        if entry is None:
            continue
        subdir_name, _marker = entry
        subdir = directory / subdir_name
        if not subdir.is_dir():
            continue
        keep = {Path(p).name for p in files if p.startswith(f"{subdir_name}/")}
        for existing in subdir.glob("*.json"):
            if existing.name not in keep:
                existing.unlink()
                removed.append(f"{subdir_name}/{existing.name}")
    return removed


#: Manifest keys that change on every export regardless of content, so they're
#: excluded when deciding whether an export actually changed anything.
_VOLATILE_MANIFEST_KEYS = ("exported_at", "hatty_version")


def _manifest_content_equal(a: dict, b: dict) -> bool:
    def _strip(d: dict) -> dict:
        return {k: v for k, v in d.items() if k not in _VOLATILE_MANIFEST_KEYS}

    return _strip(a) == _strip(b)


def write_export(directory: Path, files: dict[str, dict], sections: Sequence[str]) -> tuple[list[str], list[str]]:
    """Write `files` (from `build_files`) under `directory`, merge the
    manifest patch over any existing manifest, and prune object files in the
    exported sections whose object no longer exists. Only rewrites files whose
    content changed, so git diffs stay minimal — including the manifest's
    `exported_at`/`hatty_version`, which only move when something else in the
    export actually did, so a no-op export (nothing but the clock) never looks
    like a change to git and never triggers a commit/push on exit. Returns
    (written, removed), both relative paths."""
    sections = _validate_sections(sections)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)

    data_files = {k: v for k, v in files.items() if k != MANIFEST_FILENAME}
    written = [path for path, payload in data_files.items() if _write_json_if_changed(directory / path, payload)]
    removed = _prune_stale(directory, files, sections)

    existing_manifest = _read_manifest_tolerant(directory)
    manifest_patch = files.get(MANIFEST_FILENAME, {})
    manifest = {**existing_manifest, **manifest_patch}
    manifest["sections"] = sorted(set(existing_manifest.get("sections") or []) | set(sections))
    manifest["hatty_backup"] = BACKUP_FORMAT_VERSION

    if written or removed or not _manifest_content_equal(existing_manifest, manifest):
        manifest["exported_at"] = datetime.now(timezone.utc).isoformat()
        manifest["hatty_version"] = __version__
    else:
        manifest["exported_at"] = existing_manifest.get("exported_at", datetime.now(timezone.utc).isoformat())
        manifest["hatty_version"] = existing_manifest.get("hatty_version", __version__)

    if _write_json_if_changed(directory / MANIFEST_FILENAME, manifest):
        written.append(MANIFEST_FILENAME)

    return written, removed


def _read_object(path: Path, marker_key: str) -> dict:
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(f"Could not read {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get(marker_key) != BACKUP_FORMAT_VERSION:
        raise ValueError(f"{path} is not a valid hatty export file.")
    return payload


def read_export(directory: Path, sections: Sequence[str]) -> tuple[dict, list[str]]:
    """Read `sections` back from `directory`. Returns `(payloads, found)`:
    `found` is the subset of `sections` actually present, and `payloads[id]`
    is either a list of raw single-object export payloads — for "lists" /
    "dashboards" / "saved_graphs", feed each to the matching controller's
    `import_from_payload` — or, for "entity_names" / "settings" /
    "keybindings", the config value ready to assign directly. `payloads
    ["_manifest"]` carries the manifest dict (default_list/default_dashboard).
    Raises `ValueError` (with a user-facing message) on a missing/bad manifest
    or an unreadable object file."""
    sections = _validate_sections(sections)
    directory = Path(directory)
    manifest_path = directory / MANIFEST_FILENAME
    if not manifest_path.exists():
        raise ValueError(f"No hatty backup found in {directory} (missing {MANIFEST_FILENAME}).")
    manifest = _read_object(manifest_path, "hatty_backup")

    payloads: dict = {"_manifest": manifest}
    found: list[str] = []

    for section, (subdir_name, marker) in _OBJECT_SECTIONS.items():
        if section not in sections:
            continue
        subdir = directory / subdir_name
        if not subdir.is_dir():
            continue
        payloads[section] = [_read_object(p, marker) for p in sorted(subdir.glob("*.json"))]
        found.append(section)

    if "entity_names" in sections:
        path = directory / "entity_names.json"
        if path.exists():
            payload = _read_object(path, "hatty_entity_names")
            names = payload.get("names")
            if not isinstance(names, dict):
                raise ValueError(f"{path} is missing its names.")
            payloads["entity_names"] = dict(names)
            found.append("entity_names")

    if "settings" in sections:
        path = directory / "settings.json"
        if path.exists():
            payload = _read_object(path, "hatty_settings")
            settings = payload.get("settings")
            if not isinstance(settings, dict):
                raise ValueError(f"{path} is missing its settings.")
            payloads["settings"] = dict(settings)
            found.append("settings")

    if "keybindings" in sections:
        path = directory / "keybindings.json"
        if path.exists():
            payload = _read_object(path, "hatty_keybindings")
            keybindings = payload.get("keybindings")
            if not isinstance(keybindings, dict):
                raise ValueError(f"{path} is missing its keybindings.")
            payloads["keybindings"] = dict(keybindings)
            found.append("keybindings")

    return payloads, found
