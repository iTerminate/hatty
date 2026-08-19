# hatty — MIT License. See LICENSE file for details.
"""Shared FileSave/FileOpen plumbing for hatty's single-object JSON export/import
popups (lists, saved graphs — mirrors dashboards' pre-existing export/import,
`ui/dashboard/screen.py`). One JSON file per object, always `{"hatty_<kind>":
<version>, "name": ..., <kind>: {...}}`, so any file this writes can be dropped
into a directory another hatty instance treats as an import source."""

import json
from collections.abc import Callable
from pathlib import Path

from textual_fspicker import FileOpen, FileSave, Filters


def json_filters(label: str) -> Filters:
    return Filters(
        (label, lambda p: p.suffix.lower() == ".json"),
        ("All files", lambda _p: True),
    )


def slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "-") or "export"


def export_json(
    host,
    *,
    payload: dict,
    default_filename: str,
    title: str,
    save_button: str,
    success: Callable[[Path], str],
    filters_label: str,
    error_title: str = "Export Failed",
    success_title: str = "Exported",
) -> None:
    """Push a FileSave dialog and write `payload` as indent=2 JSON to the chosen
    path. `success(path)` builds the notify message on success. `host` is
    anything with `push_screen`/`notify` directly — the App itself, or a Screen
    via `self.app`."""

    def _do_export(path: Path | None) -> None:
        if path is None:
            return
        try:
            path.expanduser().write_text(json.dumps(payload, indent=2))
        except OSError as exc:
            host.notify(f"Could not write '{path}': {exc}", title=error_title, severity="error")
            return
        host.notify(success(path), title=success_title)

    host.push_screen(
        FileSave(
            location=str(Path.home()),
            title=title,
            save_button=save_button,
            cancel_button="Cancel",
            default_file=default_filename,
            filters=json_filters(filters_label),
        ),
        _do_export,
    )


def import_json(
    host,
    *,
    title: str,
    open_button: str,
    apply: Callable[[dict], str],
    filters_label: str,
    error_title: str = "Import Failed",
    success_title: str = "Imported",
) -> None:
    """Push a FileOpen dialog, parse the chosen file as JSON, and hand it to
    `apply(payload)`, which performs the import and returns the notify message
    (raising `ValueError` with a user-facing message to reject it). `host` is
    anything with `push_screen`/`notify` directly — the App itself, or a Screen
    via `self.app`."""

    def _do_import(path: Path | None) -> None:
        if path is None:
            return
        try:
            payload = json.loads(path.expanduser().read_text())
        except (OSError, ValueError) as exc:
            host.notify(f"Could not read '{path}': {exc}", title=error_title, severity="error")
            return
        try:
            message = apply(payload)
        except ValueError as exc:
            host.notify(str(exc), title=error_title, severity="error")
            return
        host.notify(message, title=success_title)

    host.push_screen(
        FileOpen(
            location=str(Path.home()),
            title=title,
            open_button=open_button,
            cancel_button="Cancel",
            filters=json_filters(filters_label),
        ),
        _do_import,
    )
