# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Label

from hatty.client import probe_connection


class OnboardingScreen(Screen):
    """First-run wizard: collect the Home Assistant URL + long-lived token, test
    the connection, and dismiss with {"url", "token"} on save (or None on cancel).

    Only shown when the app can't connect yet (no config, or missing/placeholder
    credentials); it never overwrites a hand-edited config that merely failed to
    parse — that decision lives in main.py via config.needs_onboarding.
    """

    BINDINGS = [
        Binding("ctrl+t", "test_connection", "Test Connection"),
        Binding("ctrl+s", "save", "Save & Connect"),
        Binding("ctrl+v", "toggle_token", "Show/Hide Token"),
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    OnboardingScreen {
        background: $background;
        align: center middle;
    }
    #onboarding_body {
        width: 80;
        max-width: 90%;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: heavy $accent;
        background: $panel;
    }
    #onboarding_title {
        text-style: bold;
        color: $accent;
    }
    .onboarding-help {
        color: $text-muted;
        margin-bottom: 1;
    }
    .field-label {
        color: $text-muted;
        margin-top: 1;
    }
    #onboarding_status {
        margin-top: 1;
        color: $text;
    }
    #onboarding_status.-ok {
        color: $success;
    }
    #onboarding_status.-error {
        color: $error;
    }
    #onboarding_buttons {
        height: auto;
        margin-top: 1;
    }
    #onboarding_buttons Button {
        margin-right: 2;
    }
    """

    def __init__(self, url: str = "", token: str = "") -> None:
        super().__init__()
        self._initial_url = url or "http://homeassistant.local:8123"
        self._initial_token = token or ""

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="onboarding_body", can_focus=False):
            yield Label("Welcome to hatty", id="onboarding_title")
            yield Label(
                "Let's connect to Home Assistant. You'll need your instance URL and a "
                "long-lived access token. This is saved to your config file.",
                classes="onboarding-help",
            )
            yield Label("Home Assistant URL", classes="field-label")
            yield Input(value=self._initial_url, placeholder="http://homeassistant.local:8123", id="onboarding_url")
            yield Label(
                "Prefer https:// — with http:// your access token is sent unencrypted.",
                classes="onboarding-help",
            )
            yield Label("Long-lived access token", classes="field-label")
            yield Input(value=self._initial_token, password=True, placeholder="paste token", id="onboarding_token")
            yield Label(
                "To create one: open Home Assistant → click your profile (bottom-left avatar) "
                "→ Security tab → Long-lived access tokens → Create token → paste it here. "
                "(Ctrl+V shows/hides the token.)",
                classes="onboarding-help",
            )
            yield Label("", id="onboarding_status")
            with Horizontal(id="onboarding_buttons"):
                yield Button("Test connection", id="onboarding_test")
                yield Button("Save & connect", variant="primary", id="onboarding_save")
            yield Footer()

    def on_mount(self) -> None:
        self.query_one("#onboarding_url", Input).focus()

    def _values(self) -> tuple[str, str]:
        url = self.query_one("#onboarding_url", Input).value.strip()
        token = self.query_one("#onboarding_token", Input).value.strip()
        return url, token

    def _set_status(self, text: str, ok: bool | None = None) -> None:
        status = self.query_one("#onboarding_status", Label)
        status.update(text)
        status.set_class(ok is True, "-ok")
        status.set_class(ok is False, "-error")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Enter advances the keyboard flow: URL → token, token → save.
        if event.input.id == "onboarding_url":
            self.query_one("#onboarding_token", Input).focus()
        elif event.input.id == "onboarding_token":
            self.action_save()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "onboarding_test":
            self.action_test_connection()
        elif event.button.id == "onboarding_save":
            self.action_save()

    def action_toggle_token(self) -> None:
        token_input = self.query_one("#onboarding_token", Input)
        token_input.password = not token_input.password

    def action_test_connection(self) -> None:
        url, token = self._values()
        if not url or not token:
            self._set_status("Enter both a URL and a token first.", ok=False)
            return
        self._set_status("Testing connection…")
        self.run_worker(self._do_test(url, token), exclusive=True)

    async def _do_test(self, url: str, token: str) -> None:
        ok, message = await probe_connection(url, token)
        self._set_status(message, ok=ok)

    def action_save(self) -> None:
        url, token = self._values()
        if not url or not token:
            self._set_status("Enter both a URL and a token before saving.", ok=False)
            return
        self.dismiss({"url": url, "token": token})

    def action_cancel(self) -> None:
        self.dismiss(None)
