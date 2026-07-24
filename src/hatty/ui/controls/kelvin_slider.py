# hatty — MIT License. See LICENSE file for details.
from textual import events
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget


class KelvinSlider(Widget, can_focus=True):
    DEFAULT_CSS = """
    KelvinSlider {
        height: 1;
        width: 1fr;
    }
    KelvinSlider:focus {
        text-style: bold;
        color: $accent;
    }
    """

    value: reactive[int] = reactive(0)

    class Changed(Message):
        def __init__(self, slider: "KelvinSlider", value: int) -> None:
            super().__init__()
            self.slider = slider
            self.value = value

    def __init__(
        self,
        value: int = 0,
        min_value: int = 2000,
        max_value: int = 6500,
        step: int = 100,
        big_step: int = 500,
        id: str | None = None,
    ):
        super().__init__(id=id)
        self.min_value = min_value
        self.max_value = max_value
        self.step = step
        self.big_step = big_step
        self.set_reactive(KelvinSlider.value, self._clamp(value))

    def _clamp(self, value: int) -> int:
        return max(self.min_value, min(self.max_value, int(value)))

    def validate_value(self, value: int) -> int:
        return self._clamp(value)

    def watch_value(self, value: int) -> None:
        self.post_message(self.Changed(self, value))
        self.refresh()

    def render(self) -> str:
        suffix = f" {self.value:>5}K"
        width = max(self.size.width - len(suffix), 1)
        span = max(self.max_value - self.min_value, 1)
        ratio = (self.value - self.min_value) / span
        filled = round(width * ratio)
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
            self.value = self.min_value
            event.stop()
        elif event.key == "end":
            self.value = self.max_value
            event.stop()
        elif event.key == "pageup":
            self.value += self.big_step
            event.stop()
        elif event.key == "pagedown":
            self.value -= self.big_step
            event.stop()

    def on_click(self, event: events.Click) -> None:
        suffix_len = len(f" {self.value:>5}K")
        width = max(self.size.width - suffix_len, 1)
        ratio = max(0.0, min(1.0, event.x / width))
        self.value = round(self.min_value + ratio * (self.max_value - self.min_value))
        self.focus()
        event.stop()
