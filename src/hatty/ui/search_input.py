# hatty — MIT License. See LICENSE file for details.
from typing import TYPE_CHECKING

from textual.message import Message
from textual.widgets import Input

from hatty.controllers.keybindings import bindings_for

if TYPE_CHECKING:
    from hatty.main import HACLI

# Static fallbacks — used only in __init__, before the widget is mounted and
# self.app is available; overwritten by the dynamic (keymap-aware) versions
# below the moment either placeholder is next set.
FILTER_PLACEHOLDER = "Filter all entities... (Enter to apply, Tab: jump in current view, Esc to cancel)"
VI_PLACEHOLDER = "Jump in current view... (Enter/Esc to close, n/N after, Tab: filter all entities)"


class SearchInput(Input):
    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect

    DEFAULT_CSS = """
    SearchInput.-active {
        border: heavy $accent;
        background: $boost;
    }
    SearchInput.-vi-mode {
        border: heavy $warning;
    }
    """

    BINDINGS = bindings_for("search_input")

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

    def _filter_placeholder(self) -> str:
        d = self.app.keys_ctl.display
        return (
            f"Filter all entities... (Enter to apply, {d('search_input.toggle_mode')}: "
            f"jump in current view, {d('nav.back')} to cancel)"
        )

    def _vi_placeholder(self) -> str:
        d = self.app.keys_ctl.display
        return (
            f"Jump in current view... (Enter/{d('nav.back')} to close, "
            f"{d('nav.search_next')}/{d('nav.search_prev')} after, {d('search_input.toggle_mode')}: "
            f"filter all entities)"
        )

    def action_toggle_mode(self) -> None:
        self.vi_mode = not self.vi_mode
        if self.vi_mode:
            self.add_class("-vi-mode")
            self.placeholder = self._vi_placeholder()
        else:
            self.remove_class("-vi-mode")
            self.placeholder = self._filter_placeholder()
        self.post_message(self.SearchChanged(self.value))

    def action_focus_display(self) -> None:
        self.value = ""
        self.vi_mode = False
        self.remove_class("-vi-mode")
        self.placeholder = self._filter_placeholder()
        self.display = True
        self.add_class("-active")
        self.focus()

    def action_hide_display(self) -> None:
        self.display = False
        self.remove_class("-active")
