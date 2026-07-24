# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Label

from hatty.ui.popup_base import PopupScreen


class SplitSlotPopup(PopupScreen):
    """Ask how to split the selected pane. Dismisses with 'v' (left/right),
    'h' (top/bottom), 'quad' (quarters), or None on cancel."""

    BINDINGS = [
        ("v", "split('v')", "Left/Right"),
        ("h", "split('h')", "Top/Bottom"),
        ("q", "split('quad')", "Quarters"),
        ("escape", "cancel", "Cancel"),
    ]

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
            yield Label("[v] Left / Right    [h] Top / Bottom    [q] Quarters    [Esc] Cancel", id="split_hint")
            yield Footer()

    def action_split(self, direction: str) -> None:
        self.dismiss(direction)

    def action_cancel(self) -> None:
        self.dismiss(None)
