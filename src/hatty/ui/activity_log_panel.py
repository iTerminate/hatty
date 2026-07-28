# hatty — MIT License. See LICENSE file for details.
"""The activity log side panel: a docked, togglable log of Home Assistant
logbook entries, hosted both on the main entity table (`a`/`A`/`i` — list,
device, single-entity scope; scoped to the graphed entity/entities instead
when the inline graph panel is open) and on the fullscreen graph screen
(`a`, its events additionally marked on the plot).

The panel itself is dumb — a title, a scrolling `Log`, and a bottom hint line
(`set_hint`) the host screen fills in with its own keys, since the two hosts
offer different actions around it (`f` maximize only exists on the main
screen). Scope, time-window paging and live-append all live on the host.

`load_history` renders normalized `LogEntry`s (see `hatty.logbook`) — both the
REST and WS logbook transports get unified to that shape before reaching this
widget, so it never has to know which one an entry came from."""

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, Log

from hatty.logbook import LogEntry, format_log_line


class ActivityLogPanel(Widget):
    DEFAULT_CSS = """
    ActivityLogPanel {
        dock: right;
        width: 52;
        border-left: heavy $accent;
        background: $panel;
        padding: 0 1;
        display: none;
    }
    ActivityLogPanel.-visible {
        display: block;
    }
    ActivityLogPanel.-maximized {
        width: 100%;
    }
    ActivityLogPanel #log_title {
        text-style: bold;
        height: 1;
        color: $text;
    }
    ActivityLogPanel #log_widget {
        height: 1fr;
    }
    ActivityLogPanel #log_hint {
        dock: bottom;
        height: 1;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Activity Log", id="log_title")
        log = Log(max_lines=2000, id="log_widget", auto_scroll=True)
        # Log/ScrollableContainer defaults to can_focus=True with its own
        # left/right/home/end scroll bindings — a host screen's auto-focus
        # (Textual scans descendants regardless of `display`, so even hidden
        # counts) would land here and swallow those keys before the host's
        # own paging bindings ever see them (the fullscreen graph's `left`/
        # `right` page the window, not this log). The log is never meant to
        # take keyboard focus, so keep it out of the focus chain entirely.
        log.can_focus = False
        yield log
        yield Label("", id="log_hint")

    def set_title(self, text: str) -> None:
        self.query_one("#log_title", Label).update(text)

    def set_hint(self, text: str) -> None:
        self.query_one("#log_hint", Label).update(text)

    def add_entry(self, name: str, state: str, when: str) -> None:
        self.query_one("#log_widget", Log).write_line(f"[{when}] {name} → {state}")

    def load_history(self, entries: list[LogEntry]) -> None:
        log = self.query_one("#log_widget", Log)
        log.clear()
        if not entries:
            log.write_line("(no history available)")
            return
        # content_size is only meaningful post-mount, which load_history always is.
        width = max(20, self.content_size.width or 50)
        log.write_lines([format_log_line(entry, width) for entry in entries])

    def clear(self) -> None:
        self.query_one("#log_widget", Log).clear()
