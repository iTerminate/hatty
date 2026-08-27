# hatty — MIT License. See LICENSE file for details.
from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Label

from hatty.types import Entity
from hatty.ui.dashboard.widgets.base import EntitySlotWidget
from hatty.ui.dashboard.widgets.visuals import SENSOR_CLASS_ICONS, trend_arrow
from hatty.ui.entity_table import apply_pending_suffix, entity_unit, get_display_name_text


class TextSlotWidget(EntitySlotWidget):
    DEFAULT_CSS = """
    TextSlotWidget {
        content-align: center middle;
    }
    TextSlotWidget #slot_name {
        text-style: bold;
    }
    TextSlotWidget #slot_state {
        color: $accent;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("", id="slot_name")
        yield Label("", id="slot_state")

    def _render_entity(self, entity: Entity, pending: str | None) -> None:
        name_label = self.query_one("#slot_name", Label)
        state_label = self.query_one("#slot_state", Label)

        attrs = entity.get("attributes", {})
        state = entity.get("state", "")
        unit = entity_unit(entity)
        icon = SENSOR_CLASS_ICONS.get(attrs.get("device_class") or "", "")
        # Opportunistic: only shown when the graph store already has history loaded.
        arrow = trend_arrow(list(self.app.entity_history.get(self.entity_id, [])))

        # Build a markup-safe Text: state/unit are appended as plain runs (no markup
        # parsing, #157); only the unit gets a dim style, applied as a span.
        value = Text()
        if icon:
            value.append(f"{icon} ")
        value.append(state)
        if unit:
            value.append(unit, style="dim")
        if arrow:
            value.append(f" {arrow}")
        name_label.update(get_display_name_text(entity))
        state_label.update(apply_pending_suffix(value, pending))
