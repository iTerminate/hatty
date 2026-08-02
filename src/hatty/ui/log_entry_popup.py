# hatty — MIT License. See LICENSE file for details.
"""Browse popup for reading a truncated activity-log line's full text (issue
#23), opened with `V` from either ActivityLogPanel host (the main table and
the fullscreen graph). Takes a snapshot of the panel's retained entries
(`ActivityLogPanel.entries`) — it doesn't stay live against further
appends/scope changes, matching every other popup's fire-and-forget-a-list
shape (ListSelectionPopup, GraphDurationPopup, ...).

Rows reuse `format_log_line` (the same truncated form the panel itself
shows) so the list reads like a zoomed-out mirror of the panel; the detail
pane below tracks the highlighted row via `format_log_detail`, which never
truncates. `OptionList`/`Static` are both constructed with `markup=False` —
a raw log line's `[HH:MM:SS]` prefix would otherwise parse as (invalid)
console markup.

Row width is re-measured and rebuilt on resize, the same width-tracking
pattern as ActivityLogPanel._reflow_lines (issue #22) — necessary here too
since the popup, unlike the docked panel, doesn't have a fixed width."""

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.widgets import Footer, Label, OptionList, Static

from hatty.logbook import LogEntry, format_log_detail, format_log_line
from hatty.ui.popup_base import PopupScreen


class LogEntryPopup(PopupScreen):
    DEFAULT_CSS = """
    LogEntryPopup .popup-container {
        width: 90%;
        height: 80%;
        max-width: 100;
        max-height: 40;
    }
    LogEntryPopup #log_entry_list {
        height: 1fr;
    }
    LogEntryPopup #log_entry_detail_scroll {
        height: auto;
        max-height: 10;
        border-top: solid $accent;
        margin-top: 1;
        padding-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close", show=False),
        Binding("V", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
    ]

    def __init__(self, entries: list[LogEntry], title: str) -> None:
        super().__init__()
        self._entries = entries
        self._title = title
        self._rendered_width = 0

    def compose(self) -> ComposeResult:
        with Container(classes="popup-container"):
            yield Label(self._title, classes="popup-title")
            yield OptionList(id="log_entry_list", markup=False)
            with VerticalScroll(id="log_entry_detail_scroll"):
                yield Static(id="log_entry_detail", markup=False)
            yield Footer()

    def on_mount(self) -> None:
        self._render_options()
        options = self.query_one("#log_entry_list", OptionList)
        options.focus()
        if self._entries:
            options.highlighted = len(self._entries) - 1

    def _line_width(self) -> int:
        options = self.query_one("#log_entry_list", OptionList)
        return max(20, options.scrollable_content_region.width or options.content_size.width or 50)

    def _render_options(self) -> None:
        options = self.query_one("#log_entry_list", OptionList)
        width = self._line_width()
        highlighted = options.highlighted
        options.clear_options()
        options.add_options(format_log_line(entry, width) for entry in self._entries)
        self._rendered_width = width
        if highlighted is not None and highlighted < len(self._entries):
            options.highlighted = highlighted

    def on_resize(self, event: events.Resize) -> None:
        if not self._entries:
            return
        if self._line_width() == self._rendered_width:
            return
        self._render_options()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_index is None:
            return
        entry = self._entries[event.option_index]
        self.query_one("#log_entry_detail", Static).update(format_log_detail(entry))

    def action_close(self) -> None:
        self.dismiss(None)
