# hatty — MIT License. See LICENSE file for details.
"""Key-capture popup for the config screen's Keybindings category: shows the
action being rebound and its current key, then records the *next* raw
keypress instead of routing it through the binding system — the same
swallow-everything `on_key` pattern as `splash_screen.py`, which is what lets
`escape` itself (nav.back's own default) be captured as a new key rather than
dismissing the popup.

`ctrl+c` is the fixed cancel key (dismiss with `None`, no change) and `delete`
resets to the id's registry default — both still go through `validate()` so a
default that now collides with another rebind is reported the same as any
other candidate. Every other key is validated against the *working* overrides
dict the config screen passes in (its uncommitted edits, not yet saved) via
`keybindings.validate`; a conflict is shown inline and the popup stays open
for another attempt."""

from textual import events
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Label, Static

from hatty.controllers.keybindings import KeySpec, display_key, validate
from hatty.ui.popup_base import PopupScreen

# Keys that never reach validate() as a candidate — ctrl+c is the fixed cancel
# key here (mirroring RESERVED_KEYS' reasoning: the popup must always have a
# way out), delete is the reset-to-default shortcut.
_CANCEL_KEY = "ctrl+c"
_RESET_KEY = "delete"


class KeyCapturePopup(PopupScreen[str | None]):
    DEFAULT_CSS = """
    KeyCapturePopup .popup-container {
        width: 60;
    }
    KeyCapturePopup #key_capture_prompt {
        margin-top: 1;
        text-style: bold;
    }
    KeyCapturePopup #key_capture_hint {
        color: $text-muted;
        margin-top: 1;
    }
    KeyCapturePopup #key_capture_error {
        color: $error;
        margin-top: 1;
    }
    """

    def __init__(self, spec: KeySpec, current_key: str, overrides: dict[str, str]) -> None:
        super().__init__()
        self._spec = spec
        self._current_key = current_key
        self._overrides = overrides

    def compose(self) -> ComposeResult:
        with Container(classes="popup-container"):
            yield Label(f"Rebind: {self._spec.label or self._spec.description}", classes="popup-title")
            yield Static(f"Current: {display_key(self._current_key)}", id="key_capture_current")
            yield Static("Press the new key…", id="key_capture_prompt")
            yield Static(f"{_CANCEL_KEY} cancel · {_RESET_KEY} reset to default", id="key_capture_hint")
            yield Static("", id="key_capture_error")

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()

        if event.key == _CANCEL_KEY:
            self.dismiss(None)
            return

        key = self._spec.key if event.key == _RESET_KEY else event.key
        error = validate(self._spec.id, key, self._overrides)
        if error:
            self.query_one("#key_capture_error", Static).update(error)
            return
        self.dismiss(key)
