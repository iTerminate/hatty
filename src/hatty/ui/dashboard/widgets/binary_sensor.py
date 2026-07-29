# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.widgets import Label

from hatty.const import binary_state_label
from hatty.types import Entity
from hatty.ui.dashboard.widgets.base import EntitySlotWidget
from hatty.ui.entity_table import apply_pending_suffix, get_display_name_text

# device_class -> (on icon, off icon); classes without an entry fall back to generic dots.
DEVICE_CLASS_ICONS = {
    "battery": ("🪫", "🔋"),
    "connectivity": ("🔗", "⛓"),
    "door": ("🚪", "🚪"),
    "garage_door": ("🚪", "🚪"),
    "gas": ("☁", "☁"),
    "lock": ("🔓", "🔐"),
    "moisture": ("💧", "💧"),
    "motion": ("🏃", "·"),
    "occupancy": ("👤", "·"),
    "opening": ("▢", "▣"),
    "plug": ("🔌", "🔌"),
    "presence": ("🏠", "🌙"),
    "problem": ("⚠", "✓"),
    "safety": ("⚠", "✓"),
    "smoke": ("🔥", "✓"),
    "tamper": ("⚠", "✓"),
    "update": ("⬆", "✓"),
    "window": ("▢", "▣"),
}

# device_classes where "on" is an alert condition rather than a healthy one.
ALERT_ON_CLASSES = {
    "battery",
    "cold",
    "gas",
    "heat",
    "lock",
    "moisture",
    "problem",
    "safety",
    "smoke",
    "tamper",
}


def binary_sensor_label(entity: Entity) -> str:
    device_class = entity.get("attributes", {}).get("device_class") or ""
    return binary_state_label(entity.get("state", ""), device_class)


def binary_sensor_icon(entity: Entity) -> str:
    state = entity.get("state", "")
    device_class = entity.get("attributes", {}).get("device_class") or ""
    on_icon, off_icon = DEVICE_CLASS_ICONS.get(device_class, ("●", "○"))
    if state == "on":
        return on_icon
    if state == "off":
        return off_icon
    return "?"


def binary_sensor_severity(entity: Entity) -> str:
    """CSS class expressing how the current state should be colored."""
    state = entity.get("state", "")
    device_class = entity.get("attributes", {}).get("device_class") or ""
    if state == "on" and device_class in ALERT_ON_CLASSES:
        return "-alert"
    if state == "on":
        return "-on"
    if state == "off":
        return "-off"
    return ""


class BooleanSensorSlotWidget(EntitySlotWidget):
    DEFAULT_CSS = """
    BooleanSensorSlotWidget {
        content-align: center middle;
    }
    BooleanSensorSlotWidget #slot_name {
        text-style: bold;
    }
    BooleanSensorSlotWidget #slot_state.-on {
        color: $success;
    }
    BooleanSensorSlotWidget #slot_state.-off {
        color: $text-muted;
    }
    BooleanSensorSlotWidget #slot_state.-alert {
        color: $error;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("", id="slot_name")
        yield Label("", id="slot_state")

    def _render_entity(self, entity: Entity, pending: str | None) -> None:
        name_label = self.query_one("#slot_name", Label)
        state_label = self.query_one("#slot_state", Label)

        name_label.update(get_display_name_text(entity))
        text = f"{binary_sensor_icon(entity)} {binary_sensor_label(entity)}"
        state_label.update(apply_pending_suffix(text, pending))
        state_label.set_classes(binary_sensor_severity(entity))
