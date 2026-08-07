# hatty — MIT License. See LICENSE file for details.
from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Label, Static

from hatty.types import Entity, EntityAttributes
from hatty.ui.dashboard.widgets.base import EntitySlotWidget
from hatty.ui.dashboard.widgets.visuals import (  # noqa: F401  (re-exported for callers/tests)
    GAUGE_WIDTH,
    HVAC_ACTION_CLASSES,
    HVAC_ACTION_ICONS,
    HVAC_ACTION_WORDS,
    gauge_position,
    render_gauge,
)
from hatty.ui.entity_table import apply_pending_suffix, entity_unit, get_display_name_text

DEFAULT_STEP = 0.5


class ThermostatSlotWidget(EntitySlotWidget):
    DEFAULT_CSS = """
    ThermostatSlotWidget {
        content-align: center middle;
    }
    ThermostatSlotWidget #slot_name {
        text-style: bold;
    }
    ThermostatSlotWidget #slot_current.-heating, ThermostatSlotWidget #thermo_gauge.-heating {
        color: $error;
    }
    ThermostatSlotWidget #slot_current.-cooling, ThermostatSlotWidget #thermo_gauge.-cooling {
        color: $primary;
    }
    ThermostatSlotWidget #slot_current, ThermostatSlotWidget #thermo_gauge {
        color: $text-muted;
        text-style: bold;
    }
    """

    def __init__(self, entity_id: str | None, *, show_last_changed: bool = False):
        super().__init__(entity_id, show_last_changed=show_last_changed)
        self._attrs: EntityAttributes = {}

    def compose(self) -> ComposeResult:
        yield Label("", id="slot_name")
        yield Label("", id="slot_current")
        yield Static("", id="thermo_gauge")
        yield Label("", id="slot_setpoint")
        yield Label("", id="slot_mode")

    def _render_empty(self) -> None:
        super()._render_empty()
        self._attrs = {}

    def _render_entity(self, entity: Entity, pending: str | None) -> None:
        name_label = self.query_one("#slot_name", Label)
        current_label = self.query_one("#slot_current", Label)
        gauge = self.query_one("#thermo_gauge", Static)
        setpoint_label = self.query_one("#slot_setpoint", Label)
        mode_label = self.query_one("#slot_mode", Label)

        self._attrs = entity.get("attributes", {})
        unit = entity_unit(entity)
        current = self._attrs.get("current_temperature")
        setpoint = self._attrs.get("temperature")
        min_temp = self._attrs.get("min_temp")
        max_temp = self._attrs.get("max_temp")
        action = self._attrs.get("hvac_action") or ""

        name_label.update(get_display_name_text(entity))
        current_label.update(Text(f"Now: {current}{unit}" if current is not None else "Now: —"))
        setpoint_text = f"Set: {setpoint}{unit}" if setpoint is not None else "Set: —"
        setpoint_label.update(apply_pending_suffix(setpoint_text, pending))
        icon = HVAC_ACTION_ICONS.get(action, "")
        word = HVAC_ACTION_WORDS.get(action)
        mode_text = f"{icon} {word}".strip() if word else entity.get("state", "")
        mode_label.update(Text(mode_text))

        action_class = HVAC_ACTION_CLASSES.get(action, "")
        current_label.set_classes(action_class)
        gauge.set_classes(action_class)

        if current is not None and min_temp is not None and max_temp is not None:
            gauge.update(render_gauge(current, setpoint, min_temp, max_temp))
        else:
            gauge.update("")

    def adjust_setpoint(self, direction: int) -> None:
        current_temp = self._attrs.get("temperature")
        if not self.entity_id or current_temp is None:
            return

        step = self._attrs.get("target_temp_step") or DEFAULT_STEP
        new_temp = current_temp + direction * step

        min_temp = self._attrs.get("min_temp")
        max_temp = self._attrs.get("max_temp")
        if min_temp is not None:
            new_temp = max(min_temp, new_temp)
        if max_temp is not None:
            new_temp = min(max_temp, new_temp)

        if new_temp == current_temp:
            limit = "maximum" if direction > 0 else "minimum"
            self.app.notify(f"Already at {limit} temperature.", severity="information")
            return

        self.app.dispatch_service_call(
            self.entity_id, "climate", "set_temperature", {"entity_id": self.entity_id, "temperature": new_temp}
        )
