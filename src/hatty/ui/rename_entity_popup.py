# hatty — MIT License. See LICENSE file for details.
from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Footer, Input, Label

from hatty.controllers.keybindings import bindings_for
from hatty.ui.popup_base import PopupScreen


class RenameEntityPopup(PopupScreen):
    BINDINGS = bindings_for("rename_popup")

    DEFAULT_CSS = """
    #rename_container {
        width: 60;
    }
    #rename_container Label.title {
        text-style: bold;
        margin-bottom: 1;
    }
    #rename_container Label.override-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    #button_row {
        margin-top: 1;
        height: 3;
        align-horizontal: right;
    }
    """

    def __init__(self, entity_id: str, current_name: str, has_override: bool = False):
        super().__init__()
        self._entity_id = entity_id
        self._current_name = current_name
        self._has_override = has_override
        self._button_order = ["btn_save_local", "btn_save_ha"]
        if has_override:
            self._button_order.append("btn_revert")
        self._button_order.append("btn_cancel")

    def compose(self) -> ComposeResult:
        with Container(id="rename_container", classes="popup-container"):
            yield Label(f"Rename: {self._entity_id}", classes="title")
            if self._has_override:
                yield Label("Local override active", classes="override-hint")
            yield Input(value=self._current_name, id="rename_input")
            with Horizontal(id="button_row"):
                yield Button("Save Locally", variant="primary", id="btn_save_local")
                yield Button("Save to Home Assistant", id="btn_save_ha")
                if self._has_override:
                    yield Button("Revert to HA Name", id="btn_revert")
                yield Button("Cancel", id="btn_cancel")
            yield Footer()

    def on_mount(self) -> None:
        self.query_one("#rename_input", Input).focus()

    def _save(self, scope: str) -> None:
        name = self.query_one("#rename_input", Input).value.strip()
        self.dismiss({"name": name or None, "scope": scope})

    def action_save_local(self) -> None:
        self._save("local")

    def action_save_ha(self) -> None:
        self._save("ha")

    def action_revert(self) -> None:
        self.dismiss({"name": None, "scope": "local"})

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_save_local":
            self.action_save_local()
        elif event.button.id == "btn_save_ha":
            self.action_save_ha()
        elif event.button.id == "btn_revert":
            self.action_revert()
        elif event.button.id == "btn_cancel":
            self.action_cancel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_save_local()

    def on_key(self, event: events.Key) -> None:
        focused = self.focused
        if isinstance(focused, Button) and focused.id and event.key in ("left", "right"):
            idx = self._button_order.index(focused.id)
            delta = 1 if event.key == "right" else -1
            next_id = self._button_order[(idx + delta) % len(self._button_order)]
            self.query_one(f"#{next_id}", Button).focus()
            event.stop()
