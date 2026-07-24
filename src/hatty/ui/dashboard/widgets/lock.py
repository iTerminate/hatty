# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.widgets import Label

from hatty.types import Entity
from hatty.ui.dashboard.widgets.base import EntitySlotWidget
from hatty.ui.entity_table import apply_pending_suffix, get_display_name_text

_STATE_GLYPHS = {"locked": "🔐", "unlocked": "🔓", "locking": "🔄", "unlocking": "🔄", "jammed": "⚠"}


class LockSlotWidget(EntitySlotWidget):
    """Display-only: locks are safety-sensitive and must not be toggled from the
    dashboard (issue #215) — lock/unlock is only reachable via expand controls."""

    DEFAULT_CSS = """
    LockSlotWidget {
        content-align: center middle;
    }
    LockSlotWidget #slot_name {
        text-style: bold;
    }
    LockSlotWidget #slot_state.-on {
        color: $success;
    }
    LockSlotWidget #slot_state.-off {
        color: $error;
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
        name_label.update(get_display_name_text(entity))
        glyph_label.update(_STATE_GLYPHS.get(state, "◆"))
        state_label.update(apply_pending_suffix(state, pending))
        state_label.set_class(state == "locked", "-on")
        state_label.set_class(state == "unlocked", "-off")
