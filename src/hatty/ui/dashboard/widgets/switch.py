# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.widgets import Label

from hatty.types import Entity
from hatty.ui.dashboard.widgets.base import EntitySlotWidget
from hatty.ui.entity_table import apply_pending_suffix, get_display_name_text


class SwitchSlotWidget(EntitySlotWidget):
    DEFAULT_CSS = """
    SwitchSlotWidget {
        content-align: center middle;
    }
    SwitchSlotWidget #slot_name {
        text-style: bold;
    }
    SwitchSlotWidget #slot_glyph {
        text-style: bold;
        color: $text-muted;
    }
    SwitchSlotWidget #slot_glyph.-on {
        color: $success;
    }
    SwitchSlotWidget #slot_state.-on {
        color: $success;
    }
    SwitchSlotWidget #slot_state.-off {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("", id="slot_name")
        yield Label("", id="slot_glyph")
        yield Label("", id="slot_state")

    def _render_entity(self, entity: Entity, pending: str | None) -> None:
        name_label = self.query_one("#slot_name", Label)
        glyph_label = self.query_one("#slot_glyph", Label)
        state_label = self.query_one("#slot_state", Label)

        state = entity.get("state", "")
        is_on = state == "on"
        name_label.update(get_display_name_text(entity))
        glyph_label.update("⏻ ▰▰▰" if is_on else "⏻ ▱▱▱")
        state_label.update(apply_pending_suffix(state, pending))
        glyph_label.set_class(is_on, "-on")
        state_label.set_class(is_on, "-on")
        state_label.set_class(state == "off", "-off")
