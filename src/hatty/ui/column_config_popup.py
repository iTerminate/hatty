# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Label, SelectionList
from textual.widgets.selection_list import Selection

from hatty.ui.entity_table import COLUMNS
from hatty.ui.popup_base import PopupScreen


class ColumnConfigPopup(PopupScreen):
    AUTO_FOCUS = "#column_selection"

    BINDINGS = [
        ("escape", "save_and_close", "Save & Close"),
        Binding("q", "save_and_close", "Save & Close", show=False),
        Binding("enter", "save_and_close", "Save & Close", priority=True),
        Binding("shift+up", "move_up", "Move Up", priority=True),
        Binding("shift+down", "move_down", "Move Down", priority=True),
    ]

    DEFAULT_CSS = """
    #column_config_container Label {
        margin-bottom: 1;
        text-style: bold;
    }
    #column_config_hint {
        color: $text-muted;
        text-style: none;
    }
    """

    def __init__(self, current_columns: list[str]):
        super().__init__()
        # Display order: currently-shown columns first (in their order), then the
        # rest. Reordering mutates this list; save reads order straight from it.
        self._order = list(current_columns) + [k for k in COLUMNS if k not in current_columns]
        self._selected = set(current_columns)
        self._original = list(current_columns)

    def compose(self) -> ComposeResult:
        with Container(id="column_config_container", classes="popup-container"):
            yield Label("Configure Columns")
            yield Label("Space toggle · Shift+↑/↓ reorder", id="column_config_hint")
            yield SelectionList(*self._build_selections(), id="column_selection")
            yield Footer()

    def _build_selections(self) -> list[Selection]:
        return [Selection(COLUMNS[key][0], key, key in self._selected) for key in self._order]

    def _move(self, delta: int) -> None:
        sel = self.query_one("#column_selection", SelectionList)
        index = sel.highlighted
        if index is None:
            return
        target = index + delta
        if not (0 <= target < len(self._order)):
            return
        # Preserve live selection state across the rebuild.
        self._selected = set(sel.selected)
        self._order[index], self._order[target] = self._order[target], self._order[index]
        sel.clear_options()
        for selection in self._build_selections():
            sel.add_option(selection)
        sel.highlighted = target

    def action_move_up(self) -> None:
        self._move(-1)

    def action_move_down(self) -> None:
        self._move(1)

    def action_save_and_close(self) -> None:
        selected = set(self.query_one("#column_selection", SelectionList).selected)
        result = [k for k in self._order if k in selected]
        self.dismiss(result if result else self._original)
