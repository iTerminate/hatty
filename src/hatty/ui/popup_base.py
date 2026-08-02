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
    a ListView of names with an optional trailing `*` default marker (and, for
    lists, a trailing notify marker — see `markers` below).

    Owns the selection glue every subclass used to re-implement: `selected_name`
    tracks the highlighted entry, and `_focus_and_preselect` selects the first
    row on mount. Row → name lookup is by position (`_name_at`/`self._names`)
    rather than parsing the label text back apart, so an arbitrary number of
    trailing markers can be appended without the two ever needing to agree on
    how to strip them back off."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.selected_name: str | None = None
        self._names: list[str] = []

    def _name_at(self, index: int | None) -> str | None:
        """The name backing row `index` (whatever markers its label carries)."""
        if index is None or not (0 <= index < len(self._names)):
            return None
        return self._names[index]

    @staticmethod
    def _label_for(name: str, default_name: str | None, markers: dict[str, str] | None) -> str:
        label = f"{name}*" if name == default_name else name
        if markers and name in markers:
            label += markers[name]
        return label

    def _populate(self, names, default_name: str | None = None, markers: dict[str, str] | None = None) -> None:
        """Fill the popup's ListView, marking the default entry with `*` and any
        `markers`-listed entries with their (per-name) trailing suffix."""
        list_view = self.query_one(ListView)
        list_view.clear()
        self._names = list(names)
        for name in self._names:
            list_view.append(ListItem(Label(self._label_for(name, default_name, markers))))

    def _relabel(self, names, default_name: str | None = None, markers: dict[str, str] | None = None) -> None:
        """Update each *existing* ListView item's text to match `names`
        positionally, without clearing/remounting. Reordering (issue #212)
        permutes rows in place rather than adding/removing any, so this is
        both cheaper and safer than `_populate` — setting `.index` right after
        a clear+append can post a Highlighted message referencing a ListItem
        whose Label child hasn't finished mounting yet. `names` must be the
        same length as the current row count."""
        list_view = self.query_one(ListView)
        self._names = list(names)
        for item, name in zip(list_view.children, self._names):
            cast(Label, item.children[0]).update(self._label_for(name, default_name, markers))

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
        self.selected_name = self._name_at(event.list_view.index)
