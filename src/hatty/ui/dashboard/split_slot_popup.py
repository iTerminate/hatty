# hatty — MIT License. See LICENSE file for details.
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Label

from hatty.controllers.keybindings import bindings_for
from hatty.ui.popup_base import PopupScreen

if TYPE_CHECKING:
    from hatty.main import HACLI


class SplitSlotPopup(PopupScreen):
    """Ask how to split the selected pane. Dismisses with 'v' (left/right),
    'h' (top/bottom), 'quad' (quarters), or None on cancel."""

    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect

    BINDINGS = bindings_for("split_slot")

    DEFAULT_CSS = """
    #split_title {
        text-style: bold;
        margin-bottom: 1;
    }
    #split_hint {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="split_container", classes="popup-container"):
            yield Label("Split this pane into smaller sections", id="split_title")
            back = self.app.keys_ctl.display("nav.back")
            yield Label(f"[v] Left / Right    [h] Top / Bottom    [q] Quarters    [{back}] Cancel", id="split_hint")
            yield Footer()

    def action_split(self, direction: str) -> None:
        self.dismiss(direction)

    def action_cancel(self) -> None:
        self.dismiss(None)
