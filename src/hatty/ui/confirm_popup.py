# hatty — MIT License. See LICENSE file for details.
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Label

from hatty.controllers.keybindings import bindings_for
from hatty.ui.popup_base import PopupScreen

if TYPE_CHECKING:
    from hatty.main import HACLI


class ConfirmPopup(PopupScreen[bool]):
    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect

    BINDINGS = bindings_for("confirm")

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
            back = self.app.keys_ctl.display("nav.back")
            yield Label(f"[y] Yes    [n / {back}] No", id="confirm_hint")
            yield Footer()

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
