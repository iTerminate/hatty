# hatty — MIT License. See LICENSE file for details.
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Input

FILTER_PLACEHOLDER = "Filter all entities... (Enter to apply, Tab: jump in current view, Esc to cancel)"
VI_PLACEHOLDER = "Jump in current view... (Enter/Esc to close, n/N after, Tab: filter all entities)"


class SearchInput(Input):
    DEFAULT_CSS = """
    SearchInput.-active {
        border: heavy $accent;
        background: $boost;
    }
    SearchInput.-vi-mode {
        border: heavy $warning;
    }
    """

    BINDINGS = [
        Binding("tab", "toggle_mode", "Toggle filter/jump", show=False),
    ]

    class SearchSubmitted(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    class SearchChanged(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, *args, **kwargs):
        super().__init__(*args, placeholder=FILTER_PLACEHOLDER, **kwargs)
        self.display = False
        self.vi_mode = False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.post_message(self.SearchSubmitted(event.value))

    def on_input_changed(self, event: Input.Changed) -> None:
        self.post_message(self.SearchChanged(event.value))

    def action_toggle_mode(self) -> None:
        self.vi_mode = not self.vi_mode
        if self.vi_mode:
            self.add_class("-vi-mode")
            self.placeholder = VI_PLACEHOLDER
        else:
            self.remove_class("-vi-mode")
            self.placeholder = FILTER_PLACEHOLDER
        self.post_message(self.SearchChanged(self.value))

    def action_focus_display(self) -> None:
        self.value = ""
        self.vi_mode = False
        self.remove_class("-vi-mode")
        self.placeholder = FILTER_PLACEHOLDER
        self.display = True
        self.add_class("-active")
        self.focus()

    def action_hide_display(self) -> None:
        self.display = False
        self.remove_class("-active")
