# hatty — MIT License. See LICENSE file for details.
"""Full-screen overlay shown while an exit-time export + git sync
(`commit_on_exit`/`push_on_exit`) runs, pushed from `HACLI.action_quit`.
Never traps the user: escape or the (unrebindable, RESERVED_KEYS) quit key
skips the sync and exits immediately, mirroring SplashScreen's "any keypress
dismisses it" rule for a slow/failing connection."""

import asyncio
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Label, Static

if TYPE_CHECKING:
    from hatty.main import HACLI


class ExitSyncScreen(Screen):
    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect

    BINDINGS = [
        Binding("escape", "skip", "Skip and quit now"),
        Binding("ctrl+q", "skip", "Skip and quit now", show=False),
    ]

    DEFAULT_CSS = """
    ExitSyncScreen {
        align: center middle;
        background: $background;
    }
    #exit_sync_body {
        width: auto;
        height: auto;
        align: center middle;
    }
    #exit_sync_title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: $accent;
    }
    #exit_sync_status {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    #exit_sync_hint {
        width: 100%;
        text-align: center;
        color: $text-disabled;
        margin-top: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._done = False

    def compose(self) -> ComposeResult:
        with Vertical(id="exit_sync_body"):
            yield Static("hatty — syncing", id="exit_sync_title")
            yield Label("Saving…", id="exit_sync_status")
            yield Label("escape to skip and quit now", id="exit_sync_hint")

    def on_mount(self) -> None:
        self.app.spawn(self._sync())

    def _set_status(self, text: str) -> None:
        if self._done:
            return
        try:
            self.query_one("#exit_sync_status", Label).update(text)
        except Exception:
            pass  # the screen may already be torn down by a concurrent skip

    async def _sync(self) -> None:
        try:
            self._set_status("Saving…")
            await self.app.drain_bg_tasks(timeout=5.0)
            self._set_status("Syncing with git…")
            ok, msg = await self.app.backup_ctl.sync_on_exit()
            if msg:
                self._set_status(msg)
                if not ok:
                    await asyncio.sleep(2.0)  # let the user read the failure
        except Exception as e:
            self.app.log.error(f"git sync on exit failed: {e}")
        finally:
            self._done = True
            self.app.exit()

    def action_skip(self) -> None:
        self._done = True
        self.app.exit()
