# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Footer, Input, Label, RadioButton, RadioSet

from hatty.controllers.keybindings import bindings_for
from hatty.ui.popup_base import PopupScreen

_DURATION_OPTIONS = [
    (1, "1 hour"),
    (4, "4 hours"),
    (12, "12 hours"),
    (24, "24 hours"),
    (48, "48 hours"),
    (168, "1 week"),
]


def _split_hours(hours: float) -> tuple[str, str]:
    whole_hours = int(hours)
    minutes = round((hours - whole_hours) * 60)
    if minutes == 60:
        whole_hours += 1
        minutes = 0
    return (str(whole_hours) if whole_hours else "", str(minutes) if minutes else "")


class GraphDurationPopup(PopupScreen):
    AUTO_FOCUS = "RadioSet"

    BINDINGS = bindings_for("graph_duration")

    DEFAULT_CSS = """
    #duration_container {
        width: 40;
    }
    #duration_container Label {
        margin-bottom: 1;
        text-style: bold;
    }
    #duration_custom_row {
        height: auto;
    }
    #duration_custom_row Input {
        width: 1fr;
    }
    """

    def __init__(self, current_hours: float, title: str = "Graph Timeframe"):
        super().__init__()
        self._current_hours = current_hours
        self._title = title
        self._preset_hours = {h for h, _ in _DURATION_OPTIONS}

    def compose(self) -> ComposeResult:
        is_preset = self._current_hours in self._preset_hours
        custom_hours, custom_minutes = ("", "") if is_preset else _split_hours(self._current_hours)

        with Container(id="duration_container", classes="popup-container"):
            yield Label(self._title)
            with RadioSet():
                for hours, label in _DURATION_OPTIONS:
                    yield RadioButton(label, value=(is_preset and hours == self._current_hours))
            yield Label("Custom (leave blank to use selection above):")
            with Horizontal(id="duration_custom_row"):
                yield Input(value=custom_hours, placeholder="hours", id="duration_hours_input")
                yield Input(value=custom_minutes, placeholder="minutes", id="duration_minutes_input")
            yield Footer()

    def action_confirm(self) -> None:
        hours_value = self.query_one("#duration_hours_input", Input).value.strip()
        minutes_value = self.query_one("#duration_minutes_input", Input).value.strip()

        if hours_value or minutes_value:
            try:
                hours = float(hours_value) if hours_value else 0.0
                minutes = float(minutes_value) if minutes_value else 0.0
            except ValueError:
                self.notify("Enter numeric hours/minutes.", title="Invalid duration", severity="error")
                return
            total_hours = hours + minutes / 60
            if total_hours <= 0:
                self.notify("Duration must be greater than 0.", title="Invalid duration", severity="error")
                return
            self.dismiss(total_hours)
            return

        radio_set = self.query_one(RadioSet)
        idx = radio_set.pressed_index
        if idx >= 0:
            self.dismiss(_DURATION_OPTIONS[idx][0])
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
