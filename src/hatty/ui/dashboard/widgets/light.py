# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.widgets import Label, Static

from hatty.types import Entity
from hatty.ui.dashboard.widgets.base import EntitySlotWidget
from hatty.ui.dashboard.widgets.visuals import empty_bar, render_bar
from hatty.ui.entity_table import apply_pending_suffix, get_display_name_text


class LightSlotWidget(EntitySlotWidget):
    DEFAULT_CSS = """
    LightSlotWidget {
        content-align: center middle;
    }
    LightSlotWidget #slot_name {
        text-style: bold;
    }
    LightSlotWidget #light_bar {
        color: $warning;
        text-style: bold;
    }
    LightSlotWidget #light_bar.-off {
        color: $text-muted;
        text-style: none;
    }
    LightSlotWidget #slot_state.-on {
        color: $success;
    }
    LightSlotWidget #slot_state.-off {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("", id="slot_name")
        yield Static("", id="light_bar")
        yield Label("", id="slot_state")

    def _render_entity(self, entity: Entity, pending: str | None) -> None:
        name_label = self.query_one("#slot_name", Label)
        bar = self.query_one("#light_bar", Static)
        state_label = self.query_one("#slot_state", Label)

        state = entity.get("state", "")
        attrs = entity.get("attributes", {})
        is_on = state == "on"
        name_label.update(get_display_name_text(entity))

        text = state
        if is_on:
            brightness = attrs.get("brightness")
            percent = round(brightness / 255 * 100) if brightness is not None else 100
            if brightness is not None:
                text = f"on, {percent}%"
            bar_str = render_bar(percent, 0, 100)
            rgb = attrs.get("rgb_color")
            if rgb:
                r, g, b = (int(x) for x in rgb)
                bar.update(f"💡 [#{r:02x}{g:02x}{b:02x}]{bar_str}[/]")
            else:
                bar.update(f"💡 {bar_str}")
        else:
            bar.update(f"○ {empty_bar()}")

        bar.set_class(not is_on, "-off")
        state_label.update(apply_pending_suffix(text, pending))
        state_label.set_class(is_on, "-on")
        state_label.set_class(state == "off", "-off")
