# hatty — MIT License. See LICENSE file for details.
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Label, OptionList
from textual.widgets.option_list import Option

from hatty.ui.controls.entity_picker_modal import EntityPickerModal
from hatty.ui.entity_table import get_display_name
from hatty.ui.popup_base import PopupScreen

if TYPE_CHECKING:
    from hatty.main import HACLI


class PanelManagePopup(PopupScreen):
    """One place to manage a dashboard panel's entities: reorder (shift+↑/↓),
    remove (del/x), add (a). Dismisses with the final entity_id list (or None if
    cancelled untouched); the caller persists and re-renders."""

    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect
    parent: "HACLI"  # this popup's parent is always the app

    BINDINGS = [
        Binding("escape", "done", "Done"),
        Binding("q", "done", "Done", show=False),
        Binding("shift+up", "move(-1)", "Move up"),
        Binding("shift+down", "move(1)", "Move down"),
        Binding("delete", "remove", "Remove"),
        Binding("x", "remove", "Remove"),
        Binding("a", "add", "Add"),
    ]

    DEFAULT_CSS = """
    #panel_manage_container {
        width: 60;
    }
    #panel_manage_title {
        text-style: bold;
        margin-bottom: 1;
    }
    #panel_manage_list {
        height: auto;
        max-height: 16;
        border: solid $accent;
    }
    """

    def __init__(self, entity_ids: list[str]):
        super().__init__()
        self._entity_ids = list(entity_ids)
        self._changed = False

    def compose(self) -> ComposeResult:
        with Container(id="panel_manage_container", classes="popup-container"):
            yield Label("Manage panel — ↑↓ select · shift+↑↓ move · del remove · a add", id="panel_manage_title")
            yield OptionList(id="panel_manage_list")
            yield Footer()

    def on_mount(self) -> None:
        self._rebuild(0)

    def _rebuild(self, keep_index: int) -> None:
        options = self.query_one("#panel_manage_list", OptionList)
        options.clear_options()
        if not self._entity_ids:
            options.add_option(Option("(no entities — press 'a' to add)", disabled=True))
            return
        options.add_options([Option(self._row_text(eid), id=eid) for eid in self._entity_ids])
        options.highlighted = max(0, min(len(self._entity_ids) - 1, keep_index))

    def _row_text(self, entity_id: str) -> str:
        entity = self.app.find_entity(entity_id)
        name = get_display_name(entity) if entity else entity_id
        state = entity.get("state", "") if entity else ""
        return f"{name}  —  {state}"

    def _index(self) -> int:
        highlighted = self.query_one("#panel_manage_list", OptionList).highlighted
        return highlighted if highlighted is not None else 0

    def action_move(self, delta: int) -> None:
        if len(self._entity_ids) < 2:
            return
        i = self._index()
        j = i + delta
        if j < 0 or j >= len(self._entity_ids):
            return
        self._entity_ids[i], self._entity_ids[j] = self._entity_ids[j], self._entity_ids[i]
        self._changed = True
        self._rebuild(j)

    def action_remove(self) -> None:
        if not self._entity_ids:
            return
        i = self._index()
        self._entity_ids.pop(i)
        self._changed = True
        self._rebuild(min(i, len(self._entity_ids) - 1) if self._entity_ids else 0)

    def action_add(self) -> None:
        present = set(self._entity_ids)
        candidates = [e for e in self.parent.all_entities if e.get("entity_id") not in present]

        def _picked(entity_id: str | None) -> None:
            if entity_id and entity_id not in self._entity_ids:
                self._entity_ids.append(entity_id)
                self._changed = True
                self._rebuild(len(self._entity_ids) - 1)

        self.app.push_screen(EntityPickerModal(candidates, title="Add entity to panel"), _picked)

    def action_done(self) -> None:
        self.dismiss(list(self._entity_ids) if self._changed else None)
