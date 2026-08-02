# hatty — MIT License. See LICENSE file for details.
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Input, Label, ListView

from hatty.ui.popup_base import ListPopup

if TYPE_CHECKING:
    from hatty.main import HACLI


class DashboardSelectionPopup(ListPopup):
    parent: "HACLI"  # this popup's parent is always the app (annotation only, no runtime effect)

    BINDINGS = [
        ("delete", "delete_dashboard", "Delete"),
        ("e", "edit_dashboard", "Edit"),
        ("d", "set_default", "Set as Default"),
        ("x", "export_dashboard", "Export"),
        ("i", "import_dashboard", "Import"),
        ("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel", show=False),
        Binding("shift+up", "move_up", "Move Up", priority=True),
        Binding("shift+down", "move_down", "Move Down", priority=True),
    ]

    DEFAULT_CSS = """
    #dashboard_selection_container Input {
        margin-bottom: 1;
    }
    #dashboard_selection_container .field-label {
        text-style: bold;
    }
    #dashboard_list_view {
        height: auto;
        max-height: 8;
    }
    """

    def __init__(self):
        super().__init__(id="dashboard_selection_popup")
        self._edit_target: str | None = None

    def compose(self) -> ComposeResult:
        with Container(id="dashboard_selection_container", classes="popup-container"):
            yield Label("Select a Dashboard", classes="popup-title")
            yield ListView(id="dashboard_list_view")
            yield Label("Name", classes="field-label")
            yield Input(placeholder="New dashboard name…", id="new_dashboard_name")
            yield Label("Rows", classes="field-label")
            yield Input(placeholder="default 3", id="new_dashboard_rows")
            yield Label("Columns", classes="field-label")
            yield Input(placeholder="default 3", id="new_dashboard_cols")
            yield Label("Row height", classes="field-label")
            yield Input(placeholder="optional", id="new_dashboard_row_height")
            yield Footer()

    def on_mount(self) -> None:
        self._update_list_view()
        self._focus_and_preselect(self.parent.dashboard_names)

    def _update_list_view(self) -> None:
        self._populate(self.parent.dashboard_names, self.parent.default_dashboard_name)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.dismiss({"action": "select", "name": self._name_at(event.index)})

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id in {
            "new_dashboard_name",
            "new_dashboard_rows",
            "new_dashboard_cols",
            "new_dashboard_row_height",
        }:
            self._submit_create_or_rename()

    def _submit_create_or_rename(self) -> None:
        row_height = self._parse_row_height(self.query_one("#new_dashboard_row_height", Input).value)
        if self._edit_target:
            current = self.parent.dashboards[self._edit_target]
            new_name = self.query_one("#new_dashboard_name", Input).value.strip() or self._edit_target
            rows = self._parse_dim(self.query_one("#new_dashboard_rows", Input).value, default=current["rows"])
            cols = self._parse_dim(self.query_one("#new_dashboard_cols", Input).value, default=current["cols"])
            self.dismiss(
                {
                    "action": "edit",
                    "old_name": self._edit_target,
                    "new_name": new_name,
                    "rows": rows,
                    "cols": cols,
                    "row_height": row_height,
                }
            )
            return

        name = self.query_one("#new_dashboard_name", Input).value.strip()
        if not name:
            return

        rows = self._parse_dim(self.query_one("#new_dashboard_rows", Input).value)
        cols = self._parse_dim(self.query_one("#new_dashboard_cols", Input).value)
        self.dismiss({"action": "create", "name": name, "rows": rows, "cols": cols, "row_height": row_height})

    @staticmethod
    def _parse_dim(value: str, default: int = 3) -> int:
        try:
            parsed = int(value.strip())
        except ValueError:
            return default
        return parsed if parsed > 0 else default

    @staticmethod
    def _parse_row_height(value: str) -> int | None:
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 else None

    def action_delete_dashboard(self) -> None:
        if self.selected_name:
            self.dismiss({"action": "delete", "name": self.selected_name})

    def action_set_default(self) -> None:
        if self.selected_name:
            self.dismiss({"action": "set_default", "name": self.selected_name})

    def action_export_dashboard(self) -> None:
        if self.selected_name:
            self.dismiss({"action": "export", "name": self.selected_name})

    def action_import_dashboard(self) -> None:
        self.dismiss({"action": "import"})

    def _move(self, delta: int) -> None:
        # Mirrors ColumnConfigPopup's Shift+up/down reorder (issue #212).
        names = self.parent.dashboard_names
        list_view = self.query_one(ListView)
        index = list_view.index
        if index is None:
            return
        target = index + delta
        if not (0 <= target < len(names)):
            return
        reordered = list(names)
        reordered[index], reordered[target] = reordered[target], reordered[index]
        self.parent.dash_ctl.reorder_dashboards(reordered)
        self._relabel(reordered, self.parent.default_dashboard_name)
        list_view.index = target

    def action_move_up(self) -> None:
        self._move(-1)

    def action_move_down(self) -> None:
        self._move(1)

    def action_edit_dashboard(self) -> None:
        if not self.selected_name:
            return
        self._edit_target = self.selected_name
        dashboard = self.parent.dashboards[self._edit_target]
        self.query_one("#new_dashboard_name", Input).value = self._edit_target
        self.query_one("#new_dashboard_rows", Input).value = str(dashboard["rows"])
        self.query_one("#new_dashboard_cols", Input).value = str(dashboard["cols"])
        self.query_one("#new_dashboard_row_height", Input).value = str(dashboard.get("row_height") or "")
        self.query_one("#new_dashboard_name", Input).focus()

    def action_cancel(self) -> None:
        if self._edit_target:
            self._edit_target = None
            self.query_one("#new_dashboard_name", Input).value = ""
            self.query_one("#new_dashboard_rows", Input).value = ""
            self.query_one("#new_dashboard_cols", Input).value = ""
            self.query_one("#new_dashboard_row_height", Input).value = ""
            self.query_one(ListView).focus()
        else:
            self.dismiss(None)
