# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.widgets import Label, Static

from hatty.types import Entity, EntityAttributes
from hatty.ui.dashboard.widgets.base import EntitySlotWidget
from hatty.ui.dashboard.widgets.visuals import empty_bar, render_bar
from hatty.ui.entity_table import apply_pending_suffix, get_display_name_text

# % per nudge when the fan exposes no percentage_step of its own.
DEFAULT_STEP = 10


class FanSlotWidget(EntitySlotWidget):
    """Dashboard tile for a `fan` entity: on/off glyph plus a speed bar
    (percentage) or preset-mode label. up/down nudge the speed in widget mode;
    full control (incl. presets/oscillation) is available via expand (o)."""

    DEFAULT_CSS = """
    FanSlotWidget {
        content-align: center middle;
    }
    FanSlotWidget #slot_name {
        text-style: bold;
    }
    FanSlotWidget #slot_glyph {
        color: $text-muted;
        text-style: bold;
    }
    FanSlotWidget #slot_glyph.-on {
        color: $success;
    }
    FanSlotWidget #fan_speed {
        color: $text-muted;
    }
    FanSlotWidget #fan_speed.-on {
        color: $success;
    }
    """

    def __init__(self, entity_id: str | None):
        super().__init__(entity_id)
        self._attrs: EntityAttributes = {}

    def compose(self) -> ComposeResult:
        yield Label("", id="slot_name")
        yield Label("", id="slot_glyph")
        yield Static("", id="fan_speed")

    def _render_empty(self) -> None:
        super()._render_empty()
        self._attrs = {}

    def _render_entity(self, entity: Entity, pending: str | None) -> None:
        name_label = self.query_one("#slot_name", Label)
        glyph_label = self.query_one("#slot_glyph", Label)
        speed_label = self.query_one("#fan_speed", Static)

        self._attrs = entity.get("attributes", {})
        state = entity.get("state", "")
        is_on = state == "on"
        percentage = self._attrs.get("percentage")
        preset = self._attrs.get("preset_mode")

        name_label.update(get_display_name_text(entity))

        if is_on:
            detail = f"{int(percentage)}%" if percentage is not None else (preset or "")
            glyph_text = f"❋ on   {detail}".rstrip()
        else:
            glyph_text = "❋ off"
        glyph_label.update(apply_pending_suffix(glyph_text, pending))
        glyph_label.set_class(is_on, "-on")

        if percentage is not None:
            speed_text = render_bar(percentage, 0, 100)
        elif preset:
            speed_text = preset
        else:
            speed_text = empty_bar()
        speed_label.update(speed_text)
        speed_label.set_class(is_on, "-on")

    def adjust_speed(self, direction: int) -> None:
        """Nudge fan speed: by percentage when supported, else by cycling preset modes."""
        if not self.entity_id:
            return

        percentage = self._attrs.get("percentage")
        if percentage is not None:
            step = self._attrs.get("percentage_step") or DEFAULT_STEP
            new_pct = int(max(0, min(100, round(percentage + direction * step))))
            if new_pct == int(percentage):
                limit = "maximum" if direction > 0 else "minimum"
                self.app.notify(f"Already at {limit} speed.", severity="information")
                return
            self.app.dispatch_service_call(
                self.entity_id, "fan", "set_percentage", {"entity_id": self.entity_id, "percentage": new_pct}
            )
            return

        preset_modes = self._attrs.get("preset_modes") or []
        if not preset_modes:
            return
        current = self._attrs.get("preset_mode")
        idx = preset_modes.index(current) if current in preset_modes else -1
        new_idx = max(0, min(len(preset_modes) - 1, idx + direction))
        if new_idx == idx:
            return
        self.app.dispatch_service_call(
            self.entity_id,
            "fan",
            "set_preset_mode",
            {"entity_id": self.entity_id, "preset_mode": preset_modes[new_idx]},
        )
