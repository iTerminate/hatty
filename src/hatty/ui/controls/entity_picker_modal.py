# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import DataTable, Footer, Label

from hatty.ui.entity_table import EntitiesTable, entity_matches
from hatty.ui.popup_base import PopupScreen
from hatty.ui.search_input import SearchInput


class EntityPickerModal(PopupScreen):
    """A small reusable modal for picking one entity from a filterable list.

    Dismisses with the chosen entity_id, or None on cancel. The virtualized
    EntitiesTable (same widget as the main list) is reused for its row rendering.
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    #entity_picker_container {
        width: 70;
    }
    #entity_picker_title {
        text-style: bold;
        margin-bottom: 1;
    }
    #entity_picker_container SearchInput {
        margin-bottom: 1;
    }
    #entity_picker_table {
        height: 10;
        border: solid $accent;
    }
    """

    def __init__(self, entities: list[dict], title: str = "Add entity"):
        super().__init__()
        self._entities = list(entities)
        self._title = title

    def compose(self) -> ComposeResult:
        with Container(id="entity_picker_container", classes="popup-container"):
            yield Label(self._title, id="entity_picker_title")
            yield SearchInput(id="entity_picker_search")
            yield EntitiesTable(id="entity_picker_table", cursor_type="row")
            yield Footer()

    def on_mount(self) -> None:
        self._refresh()
        self.query_one("#entity_picker_search", SearchInput).action_focus_display()

    def _refresh(self) -> None:
        term = self.query_one("#entity_picker_search", SearchInput).value.strip().lower()
        rows = self._entities
        if term:
            rows = [e for e in rows if entity_matches(e, term)]
        self.query_one("#entity_picker_table", EntitiesTable).update_table_data(
            entities_to_display=rows,
            entity_lists={},
            current_list_name=None,
            columns=["name", "entity_id"],
        )

    def on_search_input_search_changed(self, event: SearchInput.SearchChanged) -> None:
        event.stop()
        self._refresh()

    def on_search_input_search_submitted(self, event: SearchInput.SearchSubmitted) -> None:
        event.stop()
        self.query_one("#entity_picker_table", EntitiesTable).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "entity_picker_table":
            self.dismiss(event.row_key.value or None)

    def action_cancel(self) -> None:
        search = self.query_one("#entity_picker_search", SearchInput)
        if search.value:
            search.value = ""
            self._refresh()
            return
        self.dismiss(None)
