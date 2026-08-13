# hatty — MIT License. See LICENSE file for details.
"""The activity log side panel: a docked, togglable log of Home Assistant
logbook entries, hosted both on the main entity table (`a`/`i` open it —
list or single-entity scope; scoped to the graphed entity/entities instead
when the inline graph panel is open — and `v` opens a scope popup, issue
#38) and on the fullscreen graph screen (`a` opens it, `v` opens the same
popup, issue #21; its events additionally marked on the plot).

The panel itself is dumb — a title, a bottom hint line (`set_hint`) the host
screen fills in with its own keys (since the two hosts offer different
actions around it), and two mutually-exclusive bodies toggled by
`set_maximized` (issue #38): a passive, non-focusable `Log` ticker while
docked, and a focusable, selectable `LogOptionList` + inline detail region
while maximized — replacing the old `LogEntryPopup`, whose only job was
showing one entry's untruncated text. Both bodies are always mounted (CSS
`display` toggles which shows) so a live append can keep the ticker correct
even while the selectable list is what's on screen. Scope, time-window
paging and live-append all live on the host.

`load_history` renders normalized `LogEntry`s (see `hatty.logbook`) — both the
REST and WS logbook transports get unified to that shape before reaching this
widget, so it never has to know which one an entry came from.

`add_log_entry` is the live-streamed twin of `load_history` (issue #19's
logbook/event_stream) — it dedupes against the last few entries rendered, since
a live push can legitimately overlap the last entry `load_history` already
drew (the window fetch and the stream subscription have no shared cursor).
Appending to the selectable list never moves the current selection, so a live
push while maximized doesn't yank the highlight away from what's being read.

The docked ticker is meant to follow the same rule: it should always show the
newest entry unless the reader has scrolled up away from it. Textual's `Log`
has an `auto_scroll` flag for exactly this, but it only fires when the
*previous* write already ended at the bottom — and `Log.clear()` zeroes
`virtual_size` without resetting `scroll_y`, so every reload/reflow here
(each does `clear()` then re-writes) leaves that precondition false and
auto_scroll silently stops working, including for every live append after
it. `_scroll_log_to_tail` makes the "pin to newest" case explicit instead of
relying on that precondition (issue #44).

The panel retains its rendered entries (`_entries`, capped in lockstep with
the `Log`'s own `max_lines`) so it can re-truncate them to the true width
whenever that width changes — `on_resize` (fired by both `-visible` and
`-maximized` class toggles, since either changes the widget's region size)
and `set_maximized`'s explicit follow-up call are the two triggers (issue
#22: the old code baked truncation width into each line at write time and
never revisited it, so maximizing did nothing for already-written lines).
The two bodies track their rendered width independently (`_rendered_width` /
`_options_rendered_width`) so toggling `-maximized` back and forth never
skips a needed re-render. A reflow preserves the ticker's scroll position
(pinned-to-tail readers stay pinned, scrolled-up readers stay where they
were). Loading a fresh history (a scope/page change) always resets the
selectable list's highlight to the newest entry; a live append leaves it
where it is."""

from collections import deque

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Label, Log, OptionList, Static

from hatty.logbook import LogEntry, format_log_detail, format_log_line

# How many recently-rendered entries add_log_entry checks against — only the
# fetch/stream boundary can overlap, so a handful of slots is ample.
_DEDUPE_WINDOW = 8

# Also Log's own max_lines — _entries is capped the same way so re-render
# from it always matches what Log itself would show.
_MAX_LOG_LINES = 2000


class LogOptionList(OptionList):
    """The maximized panel's selectable list. Deaf to every OptionList
    binding except cursor_up/cursor_down (issue #38) — a falsy check_action
    makes Textual's binding resolution fall through to the next namespace in
    the chain, so left/right/enter/home/end/pageup/pagedown keep reaching
    the *host's* own bindings (paging, inspect mode, …) even while this list
    is focused, instead of being swallowed by OptionList's native scrolling/
    selection keys."""

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action in ("scroll_left", "scroll_right", "select", "first", "last", "page_up", "page_down"):
            return False
        return True


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
    ActivityLogPanel #log_browser {
        display: none;
    }
    ActivityLogPanel.-maximized #log_widget {
        display: none;
    }
    ActivityLogPanel.-maximized #log_browser {
        display: block;
        height: 1fr;
    }
    ActivityLogPanel #log_options {
        height: 1fr;
    }
    ActivityLogPanel #log_detail_scroll {
        height: auto;
        max-height: 10;
        border-top: solid $accent;
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
        self._options_rendered_width = 0
        self._title = ""

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
        with Vertical(id="log_browser"):
            # Same can_focus=False trick as the Log above, and for the same
            # reason: while docked (not maximized) this must be invisible to
            # auto-focus even though it's still mounted. set_maximized flips
            # can_focus on/off in lockstep with the -maximized class.
            options = LogOptionList(id="log_options", markup=False)
            options.can_focus = False
            yield options
            # VerticalScroll defaults can_focus=True (unlike Vertical above) —
            # without this it, not the OptionList, is what app-wide AUTO_FOCUS
            # ("*") lands on first, since it's earlier/equally eligible in the
            # DOM and never otherwise receives an explicit .focus() call.
            detail_scroll = VerticalScroll(id="log_detail_scroll")
            detail_scroll.can_focus = False
            with detail_scroll:
                yield Static(id="log_detail", markup=False)
        yield Label("", id="log_hint")

    def set_title(self, text: str) -> None:
        self._title = text
        self.query_one("#log_title", Label).update(text)

    def set_hint(self, text: str) -> None:
        self.query_one("#log_hint", Label).update(text)

    @property
    def title_text(self) -> str:
        return self._title

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

    def _options_width(self) -> int:
        options = self.query_one("#log_options", OptionList)
        return max(20, options.scrollable_content_region.width or options.content_size.width or 50)

    @staticmethod
    def _scroll_log_to_tail(log: Log) -> None:
        """Pin the ticker to its newest line — see the module docstring for
        why this can't be left to Log's own auto_scroll."""
        log.scroll_end(animate=False, immediate=True, x_axis=False)

    def _render_detail(self, index: int | None) -> None:
        detail = self.query_one("#log_detail", Static)
        if not self._entries:
            detail.update("(no history available)")
        elif index is None:
            detail.update("")
        else:
            detail.update(format_log_detail(self._entries[index]))

    def _render_options(self, *, keep_highlighted: bool) -> None:
        """Rebuild the maximized panel's selectable list at the current
        width. `keep_highlighted=True` (a resize) tries to preserve the
        current selection; `False` (a fresh load_history or an entry into
        maximized mode) always lands on the newest entry."""
        options = self.query_one("#log_options", OptionList)
        previous = options.highlighted if keep_highlighted else None
        width = self._options_width()
        options.clear_options()
        if not self._entries:
            self._options_rendered_width = width
            self._render_detail(None)
            return
        options.add_options(format_log_line(entry, width) for entry in self._entries)
        self._options_rendered_width = width
        if previous is not None and previous < len(self._entries):
            options.highlighted = previous
        else:
            options.highlighted = len(self._entries) - 1

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._render_detail(event.option_index)

    def load_history(self, entries: list[LogEntry]) -> None:
        log = self.query_one("#log_widget", Log)
        log.clear()
        self._recent_keys.clear()
        self._recent_keys.extend(self._dedupe_key(e) for e in entries[-_DEDUPE_WINDOW:])
        self._entries.clear()
        self._entries.extend(entries)
        if not entries:
            log.write_line("(no history available)")
            self._rendered_width = 0
            self._scroll_log_to_tail(log)
            if self.has_class("-maximized"):
                self._render_options(keep_highlighted=False)
            return
        width = self._line_width()
        log.write_lines([format_log_line(entry, width) for entry in entries])
        self._rendered_width = width
        self._scroll_log_to_tail(log)
        if self.has_class("-maximized"):
            self._render_options(keep_highlighted=False)

    def add_log_entry(self, entry: LogEntry) -> None:
        """Live-append a single normalized entry (a logbook/event_stream push)
        — reuses format_log_line so a device event gets the same ⚡ form and
        width truncation as the initial load. Skips an entry already rendered
        in the last _DEDUPE_WINDOW (the fetch/stream boundary can overlap).
        Appending to the selectable list never moves its highlighted index,
        so a live push while maximized can't yank the selection away."""
        key = self._dedupe_key(entry)
        if key in self._recent_keys:
            return
        self._recent_keys.append(key)
        self._entries.append(entry)
        width = self._line_width()
        # write_line's own auto_scroll correctly sticks to the tail (or not)
        # here, since load_history/clear/_reflow_lines keep scroll_y truthful.
        self.query_one("#log_widget", Log).write_line(format_log_line(entry, width))
        self._rendered_width = width
        if self.has_class("-maximized"):
            options = self.query_one("#log_options", OptionList)
            options_width = self._options_width()
            options.add_option(format_log_line(entry, options_width))
            self._options_rendered_width = options_width

    def _reflow_lines(self) -> None:
        """Re-truncate every retained entry to the current width — the
        response to a resize (`-visible`/`-maximized` toggling). A no-op
        while empty (nothing to re-truncate; re-deriving the placeholder here
        would flash it mid-fetch, since opening clears before the load
        completes), and re-renders whichever of the two bodies is currently
        displayed, skipping the other (it'll catch up next time it's shown,
        via load_history/set_maximized rather than this resize path)."""
        if not self._entries:
            return
        if self.has_class("-maximized"):
            if self._options_width() == self._options_rendered_width:
                return
            self._render_options(keep_highlighted=True)
            return
        width = self._line_width()
        if width == self._rendered_width:
            return
        log = self.query_one("#log_widget", Log)
        # format_log_line always yields exactly one line per entry, so the
        # rewritten content has the same line count — scroll position stays
        # meaningful across the clear()/write_lines below.
        at_tail = log.is_vertical_scroll_end
        prior_y = log.scroll_offset.y
        log.clear()
        log.write_lines([format_log_line(entry, width) for entry in self._entries])
        self._rendered_width = width
        if at_tail:
            self._scroll_log_to_tail(log)
        else:
            log.scroll_to(y=prior_y, animate=False, immediate=True)

    def on_resize(self, event: events.Resize) -> None:
        self._reflow_lines()

    def set_maximized(self, maximized: bool) -> None:
        options = self.query_one("#log_options", OptionList)
        if maximized:
            self.set_class(True, "-maximized")
            self._render_options(keep_highlighted=False)
            options.can_focus = True
            options.focus()
        else:
            # can_focus must drop before the class does — Textual's auto-focus
            # rescans regardless of `display`, so a focused, still-focusable
            # OptionList behind a display:none body would keep intercepting
            # keys the host's own bindings expect (see the compose() comment).
            options.can_focus = False
            self.set_class(False, "-maximized")
        # Belt-and-braces: on_resize normally handles this already, but
        # call_after_refresh (post-layout) + the rendered-width guards make
        # this a free no-op when it did, and a correct fallback when a
        # class-driven resize doesn't queue for some reason.
        self.call_after_refresh(self._reflow_lines)

    def clear(self) -> None:
        log = self.query_one("#log_widget", Log)
        log.clear()
        self._scroll_log_to_tail(log)
        self.query_one("#log_options", OptionList).clear_options()
        self.query_one("#log_detail", Static).update("")
        self._recent_keys.clear()
        self._entries.clear()
        self._rendered_width = 0
        self._options_rendered_width = 0
