# hatty — MIT License. See LICENSE file for details.
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label

from hatty.types import Entity
from hatty.ui.entity_table import apply_pending_suffix, entity_unit, get_display_name

if TYPE_CHECKING:
    from hatty.main import HACLI

NAME_COLUMN_WIDTH = 18


class PanelSlotWidget(Vertical):
    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect

    DEFAULT_CSS = """
    PanelSlotWidget .-row.-cursor {
        background: $accent 30%;
    }
    PanelSlotWidget .-row.-on {
        color: $success;
    }
    PanelSlotWidget .-row.-off {
        color: $text-muted;
    }
    """

    def __init__(self, entity_ids: list[str]):
        super().__init__()
        self.entity_ids = list(entity_ids)
        self.cursor_index = 0
        self._row_labels: list[Label] = []

    def compose(self) -> ComposeResult:
        if not self.entity_ids:
            yield Label("No entities", id="panel_empty")
            return
        for entity_id in self.entity_ids:
            label = Label(self._row_text(entity_id), classes="-row")
            self._row_labels.append(label)
            yield label

    def on_mount(self) -> None:
        self._apply_row_classes()

    def _row_text(self, entity_id: str, pending: str | None = None):
        entity = self.app.find_entity(entity_id)
        if entity is None:
            return Text(entity_id)
        name = get_display_name(entity)
        state = entity.get("state", "")
        return apply_pending_suffix(f"{name:<{NAME_COLUMN_WIDTH}} {state}{entity_unit(entity)}", pending)

    def _apply_row_classes(self) -> None:
        for index, (entity_id, label) in enumerate(zip(self.entity_ids, self._row_labels)):
            entity = self.app.find_entity(entity_id)
            state = entity.get("state") if entity else None
            is_cursor = index == self.cursor_index
            label.set_class(is_cursor, "-cursor")
            label.set_class(state == "on", "-on")
            label.set_class(state == "off", "-off")

    def move_cursor(self, delta: int) -> None:
        if not self.entity_ids:
            return
        self.cursor_index = max(0, min(len(self.entity_ids) - 1, self.cursor_index + delta))
        self._apply_row_classes()

    def toggle_selected(self) -> None:
        if not self.entity_ids:
            return
        self.app.toggle_entity(self.entity_ids[self.cursor_index])

    def update_entity_state(self, entity_id: str, entity: Entity | None, pending: str | None = None) -> None:
        if entity_id not in self.entity_ids:
            return
        index = self.entity_ids.index(entity_id)
        self._row_labels[index].update(self._row_text(entity_id, pending))
        self._apply_row_classes()
