# hatty — MIT License. See LICENSE file for details.
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Input, Label, ListView

from hatty.const import NOTIFY_LIST_NAME
from hatty.ui.popup_base import ListPopup
from hatty.ui.search_input import SearchInput

if TYPE_CHECKING:
    from hatty.main import HACLI


class ListSelectionPopup(ListPopup):
    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect
    parent: "HACLI"  # this popup's parent is always the app

    BINDINGS = [
        ("delete", "delete_list", "Delete List"),
        ("r", "rename_list", "Rename"),
        ("d", "set_default", "Set as Default"),
        ("v", "view_as_dashboard", "View as Dashboard"),
        ("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel", show=False),
        ("/", "toggle_search", "Search"),
        Binding("shift+up", "move_up", "Move Up", priority=True),
        Binding("shift+down", "move_down", "Move Down", priority=True),
    ]

    DEFAULT_CSS = """
    ListSelectionPopup #list_selection_container {
        width: 80%;
        height: 80%;
        max-width: 80;
        max-height: 40;
    }
    ListSelectionPopup #list_view {
        height: 1fr;
    }
    ListSelectionPopup #rename_list_input {
        margin-top: 1;
    }
    """

    def __init__(self):
        super().__init__(id="list_selection_popup")
        self.search_term = ""

    def compose(self) -> ComposeResult:
        with Container(id="list_selection_container", classes="popup-container"):
            yield Label("Select a List", classes="popup-title")
            yield SearchInput(id="list_search_input")
            yield ListView(id="list_view")
            yield Input(placeholder="Create new list...", id="new_list_input")
            yield Input(placeholder="Rename to...", id="rename_list_input")
            yield Footer()

    def on_mount(self) -> None:
        self._update_list_view()
        self.query_one("#list_search_input", SearchInput).action_hide_display()
        self.query_one("#rename_list_input", Input).display = False
        self.query_one(ListView).focus()

    def action_toggle_search(self) -> None:
        search_input = self.query_one("#list_search_input", SearchInput)
        if search_input.display:
            self._close_search()
        else:
            search_input.action_focus_display()

    def _close_search(self) -> None:
        search_input = self.query_one("#list_search_input", SearchInput)
        search_input.action_hide_display()
        search_input.value = ""
        self.search_term = ""
        self._update_list_view()
        self.query_one(ListView).focus()

    def _update_list_view(self) -> None:
        names = [
            name
            for name in ["View All"] + self.parent.list_names
            if self.search_term.lower() in name.lower()
        ]
        self._populate(names, self.parent.default_list_name)

    def on_search_input_search_submitted(self, event: SearchInput.SearchSubmitted) -> None:
        event.stop()
        self.search_term = event.value
        self._update_list_view()
        self.query_one("#list_search_input", SearchInput).action_hide_display()
        self.query_one(ListView).focus()

    def on_search_input_search_changed(self, event: SearchInput.SearchChanged) -> None:
        event.stop()
        self.search_term = event.value
        self._update_list_view()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.dismiss(self._item_name(event.item))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "new_list_input" and event.value:
            self.dismiss(event.value)
        elif event.input.id == "rename_list_input":
            new_name = event.value.strip()
            event.input.display = False
            event.input.value = ""
            if new_name and self.selected_name and new_name != self.selected_name:
                self.dismiss({"action": "rename", "list_name": self.selected_name, "new_name": new_name})
            else:
                self.query_one(ListView).focus()

    def action_cancel(self) -> None:
        rename_input = self.query_one("#rename_list_input", Input)
        search_input = self.query_one("#list_search_input", SearchInput)
        if rename_input.display:
            rename_input.display = False
            rename_input.value = ""
            self.query_one(ListView).focus()
        elif search_input.display:
            self._close_search()
        else:
            self.dismiss(None)

    def action_delete_list(self) -> None:
        if self.selected_name == "View All":
            self.app.notify("'View All' cannot be deleted.", severity="information")
        elif self.selected_name == NOTIFY_LIST_NAME:
            self.app.notify(f"'{NOTIFY_LIST_NAME}' cannot be deleted.", severity="information")
        elif self.selected_name:
            self.dismiss({"action": "delete", "list_name": self.selected_name})

    def action_rename_list(self) -> None:
        if not self.selected_name:
            return
        if self.selected_name == "View All":
            self.app.notify("'View All' cannot be renamed.", severity="information")
            return
        if self.selected_name == NOTIFY_LIST_NAME:
            self.app.notify(f"'{NOTIFY_LIST_NAME}' cannot be renamed.", severity="information")
            return
        rename_input = self.query_one("#rename_list_input", Input)
        rename_input.value = self.selected_name
        rename_input.display = True
        rename_input.focus()

    def action_set_default(self) -> None:
        if self.selected_name == NOTIFY_LIST_NAME:
            self.app.notify(f"'{NOTIFY_LIST_NAME}' cannot be set as default.", severity="information")
        elif self.selected_name and self.selected_name != "View All":
            self.dismiss({"action": "set_default", "list_name": self.selected_name})

    def action_view_as_dashboard(self) -> None:
        if self.selected_name and self.selected_name != "View All":
            self.dismiss({"action": "view_as_dashboard", "list_name": self.selected_name})

    def _move(self, delta: int) -> None:
        # Mirrors ColumnConfigPopup's Shift+up/down reorder (issue #212). The
        # synthetic "View All" row at index 0 isn't part of list_names and can't
        # be reordered; a search filter shows a subset, so order is ambiguous.
        if self.search_term:
            self.app.notify("Clear the search to reorder lists.", severity="warning")
            return
        names = self.parent.list_names
        list_view = self.query_one(ListView)
        index = list_view.index
        if index is None or index == 0:
            return
        target = index + delta
        if not (1 <= target <= len(names)):
            return
        reordered = list(names)
        reordered[index - 1], reordered[target - 1] = reordered[target - 1], reordered[index - 1]
        self.parent.list_ctl.reorder_lists(reordered)
        self._relabel(["View All"] + reordered, self.parent.default_list_name)
        list_view.index = target

    def action_move_up(self) -> None:
        self._move(-1)

    def action_move_down(self) -> None:
        self._move(1)
