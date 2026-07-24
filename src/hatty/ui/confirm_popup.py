# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Label

from hatty.ui.popup_base import PopupScreen


class ConfirmPopup(PopupScreen[bool]):
    BINDINGS = [
        ("y", "confirm", "Yes"),
        ("n", "cancel", "No"),
        ("escape", "cancel", "No"),
        Binding("q", "cancel", "No", show=False),
    ]

    DEFAULT_CSS = """
    #confirm_container {
        border: heavy $warning;
    }
    #confirm_message {
        margin-bottom: 1;
    }
    #confirm_hint {
        color: $text-muted;
    }
    """

    def __init__(self, message: str):
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Container(id="confirm_container", classes="popup-container"):
            yield Label(self._message, id="confirm_message")
            yield Label("[y] Yes    [n / Esc] No", id="confirm_hint")
            yield Footer()

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
