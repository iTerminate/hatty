# hatty — MIT License. See LICENSE file for details.
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Input, Label, ListView

from hatty.controllers.keybindings import bindings_for
from hatty.ui.popup_base import ListPopup, PopupScreen

if TYPE_CHECKING:
    from hatty.main import HACLI


class SaveGraphNamePopup(PopupScreen):
    BINDINGS = bindings_for("save_graph_name")

    def __init__(self, initial_name: str | None = None):
        super().__init__(id="save_graph_name_popup")
        self._initial_name = initial_name

    def compose(self) -> ComposeResult:
        with Container(id="save_graph_name_container", classes="popup-container"):
            yield Label("Save Graph As", classes="popup-title")
            yield Input(value=self._initial_name or "", placeholder="Graph name...", id="save_graph_name_input")
            yield Footer()

    def on_mount(self) -> None:
        self.query_one("#save_graph_name_input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        name = event.value.strip()
        self.dismiss(name or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SavedGraphsPopup(ListPopup):
    parent: "HACLI"  # this popup's parent is always the app (annotation only, no runtime effect)

    BINDINGS = bindings_for("saved_graphs_popup")

    DEFAULT_CSS = """
    #saved_graphs_list {
        height: auto;
        max-height: 10;
    }
    #saved_graph_rename_input {
        margin-top: 1;
    }
    """

    def __init__(self):
        super().__init__(id="saved_graphs_popup")

    def compose(self) -> ComposeResult:
        with Container(id="saved_graphs_container", classes="popup-container"):
            yield Label("Saved Graphs", classes="popup-title")
            yield ListView(id="saved_graphs_list")
            yield Input(placeholder="Rename to...", id="saved_graph_rename_input")
            yield Footer()

    def on_mount(self) -> None:
        self.query_one("#saved_graph_rename_input", Input).display = False
        self._update_list_view()
        self._focus_and_preselect(self.parent.saved_graphs.keys())

    def _update_list_view(self) -> None:
        self._populate(self.parent.saved_graphs)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.dismiss({"action": "open", "name": self._name_at(event.index)})

    def action_rename_graph(self) -> None:
        if not self.selected_name:
            return
        rename_input = self.query_one("#saved_graph_rename_input", Input)
        rename_input.value = self.selected_name
        rename_input.display = True
        rename_input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "saved_graph_rename_input":
            return
        new_name = event.value.strip()
        event.input.display = False
        event.input.value = ""
        if new_name and self.selected_name and new_name != self.selected_name:
            self.dismiss({"action": "rename", "old_name": self.selected_name, "new_name": new_name})
        else:
            self.query_one(ListView).focus()

    def action_delete_graph(self) -> None:
        if self.selected_name:
            self.dismiss({"action": "delete", "name": self.selected_name})

    def action_export_graph(self) -> None:
        if self.selected_name:
            self.dismiss({"action": "export", "name": self.selected_name})

    def action_import_graph(self) -> None:
        self.dismiss({"action": "import"})

    def action_cancel(self) -> None:
        rename_input = self.query_one("#saved_graph_rename_input", Input)
        if rename_input.display:
            rename_input.display = False
            rename_input.value = ""
            self.query_one(ListView).focus()
        else:
            self.dismiss(None)
