# hatty — MIT License. See LICENSE file for details.
"""Keybinding help, opened with `?`. `HACLI.action_show_help` builds one page per
screen as a flat `list[(key, description)]` and hands it to `HelpPopup`; a page
for the currently active screen is built from its live `active_bindings`
(mode-filtered), any other page from its static `BINDINGS` class attr.

A row with an empty key is a section header, not a binding — no real binding
has an empty key — rendered bold instead of as a keybinding (`_render_page`,
`_render_all`). `sectioned_rows` builds these from a screen's `HELP_SECTIONS`
class attr (a title -> action-names mapping); `GraphPreviewScreen` additionally
sets `HELP_ALL_MODES` so its page is always built from the full static
`BINDINGS` — every inspect-mode twin binding alongside its paging counterpart —
regardless of which mode happens to be active (issue #7).
"""

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from rich.table import Table
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, VerticalScroll
from textual.widgets import Footer, Input, Label, Static

from hatty.controllers.keybindings import bindings_for
from hatty.ui.popup_base import PopupScreen

if TYPE_CHECKING:
    from hatty.main import HACLI

# Textual key name -> friendly display, for the few that don't read well raw.
KEY_DISPLAY = {
    "question_mark": "?",
    "escape": "Esc",
    "enter": "Enter",
    "delete": "Del",
    "up": "↑",
    "down": "↓",
    "left": "←",
    "right": "→",
    "plus": "+",
    "minus": "-",
    "space": "Space",
    "tab": "Tab",
    "left_square_bracket": "[",
    "right_square_bracket": "]",
}


def display_key(key: str) -> str:
    return KEY_DISPLAY.get(key, key)


def dedup_rows(rows: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Drop description-less and duplicate (key, description) pairs, preserving order."""
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for key, description in rows:
        if not description or (key, description) in seen:
            continue
        seen.add((key, description))
        result.append((key, description))
    return result


def action_name(action: str) -> str:
    """Strip a call's `(args)` suffix, e.g. `move_cursor(-1, 0)` -> `move_cursor`,
    so bindings that pass different args to the same action still group under
    one HELP_SECTIONS entry."""
    return action.split("(", 1)[0]


def binding_entries(bindings: Iterable[BindingType]) -> list[tuple[str, str, str]]:
    """Convert a screen's BINDINGS into deduped (key, description, action_name)
    triples — the static-page counterpart to the (key, description) pairs
    `active_bindings` already yields for the live page, with the action name
    kept alongside so `sectioned_rows` can group them. Parameter is typed
    `Iterable[BindingType]` only because that's `DOMNode.BINDINGS`'s own
    declared type; every BINDINGS list is actually a plain `Binding` list since
    the keybinding-registry migration (no more bare tuples anywhere), so
    non-Binding entries are skipped defensively rather than parsed."""
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str, str]] = []
    for entry in bindings:
        if not isinstance(entry, Binding):
            continue
        key, description = entry.key, entry.description
        if not description or (key, description) in seen:
            continue
        seen.add((key, description))
        result.append((key, description, action_name(entry.action)))
    return result


def binding_rows(bindings: Iterable[BindingType]) -> list[tuple[str, str]]:
    """Convert a screen's BINDINGS into deduped (key, description) rows — the
    static-page counterpart to the (key, description) pairs `active_bindings`
    already yields for the live page."""
    return [(key, description) for key, description, _ in binding_entries(bindings)]


def sectioned_rows(
    entries: Iterable[tuple[str, str, str]], sections: Sequence[tuple[str, frozenset[str]]]
) -> list[tuple[str, str]]:
    """Group (key, description, action_name) entries under section headers.

    A row with an empty key is a header (no real binding has an empty key) —
    `_render_page`/`_render_all` render these bold instead of as a keybinding.
    Each section keeps its entries in binding-declaration order; an action not
    claimed by any listed section falls into a trailing "Other" section so a
    newly added binding can never silently vanish from a sectioned page."""
    entries = list(entries)
    claimed: set[str] = set()
    result: list[tuple[str, str]] = []
    for title, actions in sections:
        claimed |= actions
        rows = dedup_rows((key, desc) for key, desc, action in entries if action in actions)
        if not rows:
            continue
        result.append(("", title))
        result.extend(rows)
    leftover = dedup_rows((key, desc) for key, desc, action in entries if action not in claimed)
    if leftover:
        result.append(("", "Other"))
        result.extend(leftover)
    return result


def filter_pages(
    pages: list[tuple[str, list[tuple[str, str]]]], term: str
) -> list[tuple[str, list[tuple[str, str]]]]:
    """Pages reduced to the rows whose key or description contains `term`
    (case-insensitive); a page with no surviving rows is dropped entirely.
    An empty term matches everything — the unfiltered show-all view reuses
    this, section headers included. A real search term drops section-header
    rows (empty key) before matching — a header's title text isn't a binding
    and would otherwise show up as an orphaned, key-less "match"."""
    term = term.lower()
    result: list[tuple[str, list[tuple[str, str]]]] = []
    for title, rows in pages:
        if term:
            matched = [(key, desc) for key, desc in rows if key and (term in key.lower() or term in desc.lower())]
        else:
            matched = rows
        if matched:
            result.append((title, matched))
    return result


class HelpPopup(PopupScreen):
    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect

    BINDINGS = bindings_for("help_popup")

    DEFAULT_CSS = """
    #help_container {
        width: 70;
    }
    #help_container #help_title {
        margin-bottom: 0;
        text-style: bold;
    }
    #help_container #help_hint {
        margin-bottom: 1;
        color: $text-muted;
    }
    #help_filter {
        margin-bottom: 1;
    }
    #help_body {
        height: auto;
        max-height: 1fr;
    }
    """

    def __init__(self, pages: list[tuple[str, list[tuple[str, str]]]], active_index: int = 0):
        super().__init__()
        self._pages = pages
        self._active_index = active_index
        self._filter = ""
        self._show_all = False
        # Kept as a plain attribute (not just derived on read) so existing tests
        # that inspect `app.screen._binding_rows` keep working unchanged.
        self._binding_rows = pages[active_index][1] if pages else []

    def _hint_text(self) -> str:
        # left/right/"/"/a are HelpPopup's own fixed keys; only Esc close tracks
        # the live nav.back key, since it shares that id with every other screen.
        return f"←/→ pages · / search all · a show all · {self.app.keys_ctl.display('nav.back')} close"

    def compose(self) -> ComposeResult:
        with Container(id="help_container", classes="popup-container"):
            yield Label(id="help_title")
            yield Label(self._hint_text(), id="help_hint")
            filter_input = Input(placeholder="Search all pages...", id="help_filter")
            filter_input.display = False
            # Screen auto-focus scans descendants regardless of `display`, so keeping
            # this unfocusable until shown lets /, a, left/right reach the screen's bindings.
            filter_input.can_focus = False
            yield filter_input
            with VerticalScroll(id="help_body"):
                yield Static(id="help_table")
            yield Footer()

    def on_mount(self) -> None:
        self._refresh_display()

    # ── rendering ────────────────────────────────────────────────────────────

    def _render_page(self, rows: list[tuple[str, str]]) -> Table:
        table = Table.grid(padding=(0, 2))
        table.add_column(justify="right", style="bold", no_wrap=True)
        table.add_column(justify="left")
        for i, (key, description) in enumerate(rows):
            if not key:
                if i:
                    table.add_row("", "")  # blank spacer before every header but the first
                table.add_row("", f"[bold]{description}[/]")
            else:
                table.add_row(display_key(key), description)
        return table

    def _render_all(self, term: str) -> Table:
        table = Table.grid(padding=(0, 2))
        table.add_column(justify="right", style="bold", no_wrap=True)
        table.add_column(justify="left")
        matched_pages = filter_pages(self._pages, term)
        if not matched_pages:
            table.add_row("", "[dim]— no matches —[/]")
        for title, rows in matched_pages:
            table.add_row("", f"[bold underline]{title}[/]")
            for key, description in rows:
                if not key:
                    table.add_row("", f"[bold]{description}[/]")
                else:
                    table.add_row(display_key(key), description)
        return table

    def _refresh_display(self) -> None:
        body = self.query_one("#help_table", Static)
        if self._filter or self._show_all:
            title = f"Keybindings — Search: '{self._filter}'" if self._filter else "Keybindings — All Pages"
            body.update(self._render_all(self._filter))
        else:
            page_title, rows = self._pages[self._active_index]
            self._binding_rows = rows
            title = f"Keybindings — {page_title}"
            body.update(self._render_page(rows))
        self.query_one("#help_title", Label).update(title)

    # ── actions ──────────────────────────────────────────────────────────────

    def action_next_page(self) -> None:
        if self._filter or self._show_all or not self._pages:
            return
        self._active_index = (self._active_index + 1) % len(self._pages)
        self._refresh_display()

    def action_prev_page(self) -> None:
        if self._filter or self._show_all or not self._pages:
            return
        self._active_index = (self._active_index - 1) % len(self._pages)
        self._refresh_display()

    def action_toggle_all(self) -> None:
        if self._filter:
            return
        self._show_all = not self._show_all
        self._refresh_display()

    def action_focus_filter(self) -> None:
        filter_input = self.query_one("#help_filter", Input)
        filter_input.can_focus = True
        filter_input.display = True
        self._show_all = True
        self._refresh_display()
        filter_input.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._filter = event.value.strip()
        self._refresh_display()

    def _clear_filter(self) -> None:
        filter_input = self.query_one("#help_filter", Input)
        filter_input.value = ""
        filter_input.display = False
        filter_input.can_focus = False
        self._filter = ""
        self._show_all = False
        self._refresh_display()
        self.set_focus(None)

    def action_dismiss(self) -> None:
        filter_input = self.query_one("#help_filter", Input)
        if self._filter or filter_input.display or self._show_all:
            self._clear_filter()
            return
        self.dismiss()
