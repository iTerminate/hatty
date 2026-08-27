# hatty — MIT License. See LICENSE file for details.
"""Full-screen overlay shown while an exit-time export + git sync
(`commit_on_exit`/`push_on_exit`) runs, pushed from `HACLI.action_quit`.
Never traps the user: escape or the (unrebindable, RESERVED_KEYS) quit key
skips the sync and exits immediately, mirroring SplashScreen's "any keypress
dismisses it" rule for a slow/failing connection."""

import asyncio
import time
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
        /* Not auto: an auto container with only 100%-width children measures 0 wide. */
        width: 60;
        max-width: 90%;
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
        self._phase = "Saving…"
        self._phase_started: float = 0.0

    def compose(self) -> ComposeResult:
        with Vertical(id="exit_sync_body"):
            yield Static("hatty — syncing", id="exit_sync_title")
            yield Label("Saving…", id="exit_sync_status")
            yield Label("escape to skip and quit now", id="exit_sync_hint")

    def on_mount(self) -> None:
        self.set_interval(1.0, self._render_status)
        self.app.spawn(self._sync())

    def _set_status(self, text: str, final: bool = False) -> None:
        if self._done:
            return
        if final:
            self._update_label(text)
            return
        self._phase = text
        self._phase_started = time.monotonic()
        self._render_status()

    def _render_status(self) -> None:
        if self._done:
            return
        elapsed = int(time.monotonic() - self._phase_started)
        text = f"{self._phase}  {elapsed}s" if elapsed >= 1 else self._phase
        self._update_label(text)

    def _update_label(self, text: str) -> None:
        try:
            self.query_one("#exit_sync_status", Label).update(text)
        except Exception:
            pass  # the screen may already be torn down by a concurrent skip

    async def _sync(self) -> None:
        try:
            self._set_status("Saving…")
            await self.app.drain_bg_tasks(timeout=5.0)
            # sync_on_exit calls this back before each of its own phases
            # (Exporting…/Committing…/Pushing…), so the overlay always shows
            # what's actually happening instead of one static message for
            # however long the whole thing takes.
            ok, msg = await self.app.backup_ctl.sync_on_exit(status=self._set_status)
            if msg:
                self._set_status(msg, final=True)
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
