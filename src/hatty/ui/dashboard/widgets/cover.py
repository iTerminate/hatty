# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.widgets import Label, Static

from hatty.types import Entity
from hatty.ui.dashboard.widgets.base import EntitySlotWidget
from hatty.ui.dashboard.widgets.visuals import render_bar
from hatty.ui.entity_table import apply_pending_suffix, get_display_name_text

_STATE_GLYPHS = {"open": "▲", "closed": "▼", "opening": "△", "closing": "▽"}


class CoverSlotWidget(EntitySlotWidget):
    """Display-only: covers aren't toggled like switches, so this widget has no key interaction."""

    DEFAULT_CSS = """
    CoverSlotWidget {
        content-align: center middle;
    }
    CoverSlotWidget #slot_name {
        text-style: bold;
    }
    CoverSlotWidget #cover_bar {
        color: $primary;
        text-style: bold;
    }
    CoverSlotWidget #slot_state.-on {
        color: $success;
    }
    CoverSlotWidget #slot_state.-off {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("", id="slot_name")
        yield Static("", id="cover_bar")
        yield Label("", id="slot_state")

    def _render_entity(self, entity: Entity, pending: str | None) -> None:
        name_label = self.query_one("#slot_name", Label)
        bar = self.query_one("#cover_bar", Static)
        state_label = self.query_one("#slot_state", Label)

        state = entity.get("state", "")
        name_label.update(get_display_name_text(entity))
        glyph = _STATE_GLYPHS.get(state, "◆")

        text = state
        position = entity.get("attributes", {}).get("current_position")
        if position is not None:
            text = f"{state}, {position}%"
            bar.update(f"{glyph} {render_bar(position, 0, 100)}")
        else:
            bar.update(glyph)

        state_label.update(apply_pending_suffix(text, pending))
        state_label.set_class(state == "open", "-on")
        state_label.set_class(state == "closed", "-off")
