# hatty — MIT License. See LICENSE file for details.
"""The activity log side panel: a docked, togglable log of Home Assistant
logbook entries, hosted both on the main entity table (`a`/`A`/`i` — list,
device, single-entity scope; scoped to the graphed entity/entities instead
when the inline graph panel is open) and on the fullscreen graph screen
(`a`, its events additionally marked on the plot).

The panel itself is dumb — a title, a scrolling `Log`, and a bottom hint line
(`set_hint`) the host screen fills in with its own keys, since the two hosts
offer different actions around it. Scope, time-window paging and live-append
all live on the host; maximizing goes through `set_maximized` here.

`load_history` renders normalized `LogEntry`s (see `hatty.logbook`) — both the
REST and WS logbook transports get unified to that shape before reaching this
widget, so it never has to know which one an entry came from.

`add_log_entry` is the live-streamed twin of `load_history` (issue #19's
logbook/event_stream) — it dedupes against the last few entries rendered, since
a live push can legitimately overlap the last entry `load_history` already
drew (the window fetch and the stream subscription have no shared cursor).

The panel retains its rendered entries (`_entries`, capped in lockstep with
the `Log`'s own `max_lines`) so it can re-truncate them to the true width
whenever that width changes — `on_resize` (fired by both `-visible` and
`-maximized` class toggles, since either changes the widget's region size)
and `set_maximized`'s explicit follow-up call are the two triggers (issue
#22: the old code baked truncation width into each line at write time and
never revisited it, so maximizing did nothing for already-written lines).
Re-render always scrolls to the newest line — there's no cursor to preserve,
since the log stays outside the focus chain (see below)."""

from collections import deque

from textual import events
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, Log

from hatty.logbook import LogEntry, format_log_line

# How many recently-rendered entries add_log_entry checks against — only the
# fetch/stream boundary can overlap, so a handful of slots is ample.
_DEDUPE_WINDOW = 8

# Also Log's own max_lines — _entries is capped the same way so re-render
# from it always matches what Log itself would show.
_MAX_LOG_LINES = 2000


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
        overflow-x: hidden;
    }
    ActivityLogPanel #log_hint {
        dock: bottom;
        height: 1;
        color: $text-muted;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._recent_keys: deque[tuple[str, str, str]] = deque(maxlen=_DEDUPE_WINDOW)
        self._entries: deque[LogEntry] = deque(maxlen=_MAX_LOG_LINES)
        self._rendered_width = 0

    def compose(self) -> ComposeResult:
        yield Label("Activity Log", id="log_title")
        log = Log(max_lines=_MAX_LOG_LINES, id="log_widget", auto_scroll=True)
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

    @staticmethod
    def _dedupe_key(entry: LogEntry) -> tuple[str, str, str]:
        return (entry["when"], entry["name"], entry["detail"])

    def _line_width(self) -> int:
        # The scrollbar-aware width: Log's CSS is `overflow: scroll`, so its
        # vertical scrollbar is always shown, and content_size doesn't
        # subtract it — measuring the true scrollable region is what keeps a
        # written "…" from landing behind the scrollbar (issue #22).
        log = self.query_one("#log_widget", Log)
        return max(20, log.scrollable_content_region.width or self.content_size.width or 50)

    def load_history(self, entries: list[LogEntry]) -> None:
        log = self.query_one("#log_widget", Log)
        log.clear()
        self._recent_keys.clear()
        self._recent_keys.extend(self._dedupe_key(e) for e in entries[-_DEDUPE_WINDOW:])
        self._entries.clear()
        self._entries.extend(entries)
        if not entries:
            log.write_line("(no history available)")
            return
        width = self._line_width()
        log.write_lines([format_log_line(entry, width) for entry in entries])
        self._rendered_width = width

    def add_log_entry(self, entry: LogEntry) -> None:
        """Live-append a single normalized entry (a logbook/event_stream push)
        — reuses format_log_line so a device event gets the same ⚡ form and
        width truncation as the initial load. Skips an entry already rendered
        in the last _DEDUPE_WINDOW (the fetch/stream boundary can overlap)."""
        key = self._dedupe_key(entry)
        if key in self._recent_keys:
            return
        self._recent_keys.append(key)
        self._entries.append(entry)
        width = self._line_width()
        self.query_one("#log_widget", Log).write_line(format_log_line(entry, width))
        self._rendered_width = width

    def _reflow_lines(self) -> None:
        """Re-truncate every retained entry to the current width — the
        response to a resize (`-visible`/`-maximized` toggling). A no-op
        while empty (nothing to re-truncate; re-deriving the placeholder here
        would flash it mid-fetch, since opening clears before the load
        completes) or when the width hasn't actually changed."""
        if not self._entries:
            return
        width = self._line_width()
        if width == self._rendered_width:
            return
        log = self.query_one("#log_widget", Log)
        log.clear()
        log.write_lines([format_log_line(entry, width) for entry in self._entries])
        self._rendered_width = width

    def on_resize(self, event: events.Resize) -> None:
        self._reflow_lines()

    def set_maximized(self, maximized: bool) -> None:
        self.set_class(maximized, "-maximized")
        # Belt-and-braces: on_resize normally handles this already, but
        # call_after_refresh (post-layout) + the _rendered_width guard make
        # this a free no-op when it did, and a correct fallback when a
        # class-driven resize doesn't queue for some reason.
        self.call_after_refresh(self._reflow_lines)

    def clear(self) -> None:
        self.query_one("#log_widget", Log).clear()
        self._recent_keys.clear()
        self._entries.clear()
        self._rendered_width = 0
