# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.widgets import Label

from hatty.types import Entity
from hatty.ui.dashboard.widgets.base import EntitySlotWidget
from hatty.ui.entity_table import apply_pending_suffix, get_display_name_text

# device_class -> (on label, off label), per Home Assistant's binary_sensor conventions
DEVICE_CLASS_LABELS = {
    "battery": ("Low", "Normal"),
    "battery_charging": ("Charging", "Not Charging"),
    "cold": ("Cold", "Normal"),
    "connectivity": ("Connected", "Disconnected"),
    "door": ("Open", "Closed"),
    "garage_door": ("Open", "Closed"),
    "gas": ("Detected", "Clear"),
    "heat": ("Hot", "Normal"),
    "light": ("Detected", "No Light"),
    "lock": ("Unlocked", "Locked"),
    "moisture": ("Wet", "Dry"),
    "motion": ("Detected", "Clear"),
    "moving": ("Moving", "Not Moving"),
    "occupancy": ("Detected", "Clear"),
    "opening": ("Open", "Closed"),
    "plug": ("Plugged In", "Unplugged"),
    "power": ("Detected", "No Power"),
    "presence": ("Home", "Away"),
    "problem": ("Problem", "OK"),
    "running": ("Running", "Not Running"),
    "safety": ("Unsafe", "Safe"),
    "smoke": ("Detected", "Clear"),
    "sound": ("Detected", "Clear"),
    "tamper": ("Tampering", "Clear"),
    "update": ("Update Available", "Up-to-date"),
    "vibration": ("Detected", "Clear"),
    "window": ("Open", "Closed"),
}


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
    state = entity.get("state", "")
    device_class = entity.get("attributes", {}).get("device_class") or ""
    on_label, off_label = DEVICE_CLASS_LABELS.get(device_class, ("On", "Off"))
    if state == "on":
        return on_label
    if state == "off":
        return off_label
    return state


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
