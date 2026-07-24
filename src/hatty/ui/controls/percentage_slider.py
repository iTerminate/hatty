# hatty — MIT License. See LICENSE file for details.
from textual import events
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget


class PercentageSlider(Widget, can_focus=True):
    DEFAULT_CSS = """
    PercentageSlider {
        height: 1;
        width: 1fr;
    }
    PercentageSlider:focus {
        text-style: bold;
        color: $accent;
    }
    """

    value: reactive[int] = reactive(0)

    class Changed(Message):
        def __init__(self, slider: "PercentageSlider", value: int) -> None:
            super().__init__()
            self.slider = slider
            self.value = value

    def __init__(self, value: int = 0, step: int = 1, big_step: int = 10, id: str | None = None):
        super().__init__(id=id)
        self.step = step
        self.big_step = big_step
        self.set_reactive(PercentageSlider.value, self._clamp(value))

    def _clamp(self, value: int) -> int:
        return max(0, min(100, int(value)))

    def validate_value(self, value: int) -> int:
        return self._clamp(value)

    def watch_value(self, value: int) -> None:
        self.post_message(self.Changed(self, value))
        self.refresh()

    def render(self) -> str:
        suffix = f" {self.value:>3}%"
        width = max(self.size.width - len(suffix), 1)
        filled = round(width * self.value / 100)
        bar = "█" * filled + "░" * (width - filled)
        return f"{bar}{suffix}"

    def on_key(self, event: events.Key) -> None:
        if event.key in ("right", "up"):
            self.value += self.step
            event.stop()
        elif event.key in ("left", "down"):
            self.value -= self.step
            event.stop()
        elif event.key == "home":
            self.value = 0
            event.stop()
        elif event.key == "end":
            self.value = 100
            event.stop()
        elif event.key == "pageup":
            self.value += self.big_step
            event.stop()
        elif event.key == "pagedown":
            self.value -= self.big_step
            event.stop()

    def on_click(self, event: events.Click) -> None:
        suffix_len = len(f" {self.value:>3}%")
        width = max(self.size.width - suffix_len, 1)
        ratio = max(0.0, min(1.0, event.x / width))
        self.value = round(ratio * 100)
        self.focus()
        event.stop()
