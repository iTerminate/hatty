# hatty — MIT License. See LICENSE file for details.
"""CLI-style ASCII splash shown while the app connects and loads initial state.

Pushed by main.py right before the client starts (never on the onboarding or
config-error paths) and popped automatically the moment the first get_states
result populates the table. Any keypress dismisses it early — it must never
trap the user behind a slow or failing connection.

Also re-pushed by ConnectionController (issue #243) over whatever screen is
currently showing on a mid-session disconnect, with an initial `status`
message, and dismissed the same way once the reconnect's get_states result
lands.
"""

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Label, Static

# Pre-rendered figlet-style logo; a runtime figlet dependency buys nothing
# for a fixed string and would only add import cost at startup.
LOGO = r"""
 _           _   _
| |__   __ _| |_| |_ _   _
| '_ \ / _` | __| __| | | |
| | | | (_| | |_| |_| |_| |
|_| |_|\__,_|\__|\__|\__, |
                     |___/
"""


class SplashScreen(Screen):
    DEFAULT_CSS = """
    SplashScreen {
        align: center middle;
        background: $background;
    }
    #splash_body {
        width: auto;
        height: auto;
        align: center middle;
    }
    #splash_logo {
        width: auto;
        color: $accent;
        text-style: bold;
    }
    #splash_tagline {
        width: 100%;
        text-align: center;
        color: $text-muted;
    }
    #splash_status {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, status: str = "Connecting to Home Assistant…") -> None:
        super().__init__()
        self._status = status

    def compose(self) -> ComposeResult:
        with Vertical(id="splash_body"):
            yield Static(LOGO, id="splash_logo")
            yield Label("Home Assistant Terminal UI", id="splash_tagline")
            yield Label(self._status, id="splash_status")

    def update_status(self, text: str) -> None:
        self.query_one("#splash_status", Label).update(text)

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()
        self.dismiss()
