# hatty — MIT License. See LICENSE file for details.
from typing import TYPE_CHECKING, Any, cast

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Footer, Input, Label, Select

from hatty.const import NUMERIC_INPUT_TYPES
from hatty.controllers.keybindings import bindings_for

if TYPE_CHECKING:
    from textual.widgets._input import InputType
from hatty.types import Entity
from hatty.ui.controls.percentage_slider import PercentageSlider
from hatty.ui.dashboard.widgets.visuals import HVAC_ACTION_CLASSES, HVAC_ACTION_ICONS, HVAC_ACTION_WORDS
from hatty.ui.entity_table import entity_unit, get_display_name
from hatty.ui.popup_base import PopupScreen


class EntityControlPopup(PopupScreen):
    BINDINGS = bindings_for("control_popup")

    DEFAULT_CSS = """
    #control_container {
        width: 60;
    }
    #control_container Label.title {
        text-style: bold;
        margin-bottom: 1;
    }
    #control_container Label.field-label {
        margin-top: 1;
        color: $text-muted;
    }
    #control_container Label.climate-status {
        margin-bottom: 1;
        color: $text-muted;
    }
    #control_container Label.climate-status.-heating {
        color: $error;
    }
    #control_container Label.climate-status.-cooling {
        color: $primary;
    }
    #button_row {
        margin-top: 1;
        height: 3;
        align-horizontal: right;
    }
    #control_container PercentageSlider {
        margin-top: 0;
    }
    #lock_buttons {
        margin-top: 1;
        height: 3;
    }
    """

    def __init__(self, entity: Entity):
        super().__init__()
        self._entity = entity
        self._entity_id = entity.get("entity_id", "")
        self._domain = self._entity_id.split(".")[0]
        self._attrs = entity.get("attributes", {})
        self._fields: list[str] = []
        self._field_steps: dict[str, float] = {}

    def compose(self) -> ComposeResult:
        name = get_display_name(self._entity)
        with VerticalScroll(id="control_container", classes="popup-container"):
            yield Label(f"Control: {name}", classes="title")
            yield from self._climate_status()
            yield from self._build_fields()
            with Horizontal(id="button_row"):
                yield Button("Save", variant="primary", id="btn_save")
                yield Button("Cancel", id="btn_cancel")
            yield Footer()

    def on_mount(self) -> None:
        if self._fields:
            self.query_one(f"#{self._fields[0]}").focus()
        elif self._domain == "lock":
            enabled_id = "field_lock_unlock" if self._entity.get("state") == "locked" else "field_lock_lock"
            self.query_one(f"#{enabled_id}").focus()

    def _build_fields(self) -> ComposeResult:
        builders = {
            "fan": self._fields_fan,
            "climate": self._fields_climate,
            "cover": self._fields_cover,
            "input_number": self._fields_input_number,
            "lock": self._fields_lock,
        }
        builder = builders.get(self._domain)
        if builder:
            yield from builder()

    def _field(self, field_id: str, label: str, value, placeholder: str, input_type: str | None, step: float = 1):
        self._fields.append(field_id)
        if input_type in NUMERIC_INPUT_TYPES:
            self._field_steps[field_id] = step
        display_label = f"{label} (↑↓ to nudge)" if input_type in NUMERIC_INPUT_TYPES else label
        yield Label(display_label, classes="field-label")
        yield Input(
            value=str(value) if value is not None else "",
            placeholder=placeholder,
            type=cast("InputType", input_type or "text"),
            id=field_id,
        )

    def _slider_field(self, field_id: str, label: str, value: int, step: int = 1, big_step: int = 10):
        self._fields.append(field_id)
        yield Label(label, classes="field-label")
        yield PercentageSlider(value=value, id=field_id, step=step, big_step=big_step)

    def _select_field(self, field_id: str, label: str, options: list[str], current_value):
        self._fields.append(field_id)
        yield Label(label, classes="field-label")
        kwargs: dict[str, Any] = {"allow_blank": True}
        if current_value in options:
            kwargs["value"] = current_value
        yield Select([(o, o) for o in options], id=field_id, **kwargs)

    def _fields_fan(self) -> ComposeResult:
        percentage = self._attrs.get("percentage")
        raw_step = self._attrs.get("percentage_step", 1.0)
        step = max(1, round(raw_step))
        speed_count = round(100 / raw_step) if raw_step > 1 else None
        label = f"Speed ({speed_count} levels)" if speed_count else "Speed"
        yield from self._slider_field(
            "field_percentage",
            label,
            int(percentage) if percentage is not None else 0,
            step=step,
            big_step=step,
        )

        preset_modes = self._attrs.get("preset_modes") or []
        if preset_modes:
            yield from self._select_field(
                "field_preset_mode", "Preset Mode", preset_modes, self._attrs.get("preset_mode")
            )

    def _climate_status(self) -> ComposeResult:
        if self._domain != "climate":
            return
        action = self._attrs.get("hvac_action") or ""
        word = HVAC_ACTION_WORDS.get(action)
        if not word:
            return
        icon = HVAC_ACTION_ICONS.get(action, "")
        action_class = HVAC_ACTION_CLASSES.get(action, "")
        yield Label(f"{icon} {word}".strip(), classes=f"climate-status {action_class}".strip())

    def _fields_climate(self) -> ComposeResult:
        temperature = self._attrs.get("temperature")
        yield from self._field("field_temperature", "Target Temperature", temperature, "target temp", "number")

        hvac_modes = self._attrs.get("hvac_modes") or []
        if hvac_modes:
            yield from self._select_field("field_hvac_mode", "HVAC Mode", hvac_modes, self._entity.get("state", ""))

        fan_modes = self._attrs.get("fan_modes") or []
        if fan_modes:
            yield from self._select_field("field_fan_mode", "Fan Mode", fan_modes, self._attrs.get("fan_mode"))

    def _fields_cover(self) -> ComposeResult:
        position = self._attrs.get("current_position")
        yield from self._slider_field("field_position", "Position", int(position) if position is not None else 0)

    def _fields_lock(self) -> ComposeResult:
        current = self._entity.get("state", "")
        with Horizontal(id="lock_buttons"):
            yield Button("🔐 Lock", id="field_lock_lock", disabled=current == "locked")
            yield Button("🔓 Unlock", id="field_lock_unlock", disabled=current == "unlocked")

    def _fields_input_number(self) -> ComposeResult:
        min_v = self._attrs.get("min")
        max_v = self._attrs.get("max")
        step = self._attrs.get("step", 1)
        unit = entity_unit(self._entity)
        label = "Value"
        if min_v is not None and max_v is not None:
            label = f"Value ({min_v}–{max_v}{unit})"
        yield from self._field("field_value", label, self._entity.get("state", ""), "value", "number", step=step)

    def _collect_values(self) -> dict:
        result = {}
        for field_id in self._fields:
            key = field_id.removeprefix("field_")
            widget = self.query_one(f"#{field_id}")
            if isinstance(widget, PercentageSlider):
                result[key] = str(widget.value)
            elif isinstance(widget, Input):
                val = widget.value.strip()
                if val:
                    result[key] = val
            elif isinstance(widget, Select):
                if not widget.is_blank():
                    result[key] = widget.value
        return result

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_save(self) -> None:
        self.dismiss(self._collect_values())

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_save":
            self.action_save()
        elif event.button.id == "btn_cancel":
            self.action_cancel()
        elif event.button.id == "field_lock_lock":
            self.dismiss({"locked": "locked"})
        elif event.button.id == "field_lock_unlock":
            self.dismiss({"locked": "unlocked"})

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_save()

    def on_key(self, event: events.Key) -> None:
        focused = self.focused
        if isinstance(focused, Input) and focused.type in NUMERIC_INPUT_TYPES and event.key in ("up", "down"):
            self._nudge_input(focused, 1 if event.key == "up" else -1)
            event.stop()
        elif event.key in ("left", "right") and not isinstance(focused, (Input, PercentageSlider)):
            if event.key == "left":
                self.focus_previous()
            else:
                self.focus_next()
            event.stop()

    def _nudge_input(self, widget: Input, direction: int) -> None:
        try:
            current = float(widget.value) if widget.value.strip() else 0.0
        except ValueError:
            return
        step = self._field_steps.get(widget.id or "", 1)
        new_value = current + direction * step
        widget.value = str(int(new_value)) if widget.type == "integer" else str(new_value)
