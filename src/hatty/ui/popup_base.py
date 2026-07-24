# hatty — MIT License. See LICENSE file for details.
"""Shared modal-popup scaffolding.

Every popup in the app centers a bordered `$panel` container with a bold
title label; that skeleton lives here once. Subclasses mark their dialog
container with the `popup-container` class and keep only their deltas
(width, per-widget rules) in their own DEFAULT_CSS — Textual merges the
class hierarchy's stylesheets, with the subclass winning ties.
"""

from typing import cast

from textual.screen import ModalScreen, ScreenResultType
from textual.widgets import Label, ListItem, ListView


class PopupScreen(ModalScreen[ScreenResultType]):
    """Base modal: centered, panel-styled `.popup-container`, bold title.

    Generic over its dismiss-result type so subclasses that return a value
    (e.g. ``ConfirmPopup(PopupScreen[bool])``) type-check their
    ``push_screen(..., callback)`` calls; subclasses that don't parameterize
    behave as before."""

    DEFAULT_CSS = """
    PopupScreen {
        align: center middle;
    }
    PopupScreen .popup-container {
        width: 50;
        height: auto;
        max-height: 80%;
        background: $panel;
        border: heavy $accent;
        padding: 1 2;
    }
    PopupScreen .popup-title {
        margin-bottom: 1;
        text-style: bold;
    }
    """


class ListPopup(PopupScreen):
    """Base for the name-list popups (lists / dashboards / saved graphs):
    a ListView of names with an optional trailing `*` default marker.

    Owns the selection glue every subclass used to re-implement: `selected_name`
    tracks the highlighted entry, and `_focus_and_preselect` selects the first
    row on mount. Subclasses that carry no default marker (saved graphs) set
    `_strip_default_marker = False`."""

    # Whether a highlighted item's trailing `*` default marker is stripped before
    # it becomes selected_name (lists/dashboards mark a default; saved graphs don't).
    _strip_default_marker = True

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.selected_name: str | None = None

    @staticmethod
    def _item_name(item: ListItem | None, strip_default_marker: bool = True) -> str | None:
        """The name behind a ListView item (the default marker stripped)."""
        if item is None:
            return None
        name = str(cast(Label, item.children[0]).content)
        return name.rstrip("*") if strip_default_marker else name

    def _populate(self, names, default_name: str | None = None) -> None:
        """Fill the popup's ListView, marking the default entry with `*`."""
        list_view = self.query_one(ListView)
        list_view.clear()
        for name in names:
            label = f"{name}*" if name == default_name else name
            list_view.append(ListItem(Label(label)))

    def _relabel(self, names, default_name: str | None = None) -> None:
        """Update each *existing* ListView item's text to match `names`
        positionally, without clearing/remounting. Reordering (issue #212)
        permutes rows in place rather than adding/removing any, so this is
        both cheaper and safer than `_populate` — setting `.index` right after
        a clear+append can post a Highlighted message referencing a ListItem
        whose Label child hasn't finished mounting yet. `names` must be the
        same length as the current row count."""
        list_view = self.query_one(ListView)
        for item, name in zip(list_view.children, names):
            label = f"{name}*" if name == default_name else name
            cast(Label, item.children[0]).update(label)

    def _focus_and_preselect(self, names) -> None:
        """Focus the ListView and select its first row (if any), the on-mount
        preselect the subclasses used to duplicate."""
        list_view = self.query_one(ListView)
        list_view.focus()
        names = list(names)
        if names:
            list_view.index = 0
            self.selected_name = names[0]

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self.selected_name = self._item_name(event.item, strip_default_marker=self._strip_default_marker)
