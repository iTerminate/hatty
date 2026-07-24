# hatty — MIT License. See LICENSE file for details.
"""Nested sub-grid slot content (issue #81, Approach B).

A slot with widget_type "split" carries a children fragment
{"rows": r, "cols": c, "slots": [...]} whose child slots are plain slot dicts
with coords relative to the child grid. Nesting is capped at one level: child
slots may not be splits themselves and carry no spans — both are ignored
defensively rather than crashed on.
"""

from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.containers import Container, Grid

if TYPE_CHECKING:
    # Runtime import would be circular (dashboard_screen imports this module);
    # DashboardSlotWidget is only needed to type the string-selector query results.
    from hatty.ui.dashboard.screen import DashboardSlotWidget


def normalized_children(slot: dict) -> tuple[int, int, list[dict]]:
    """Validated (rows, cols, slots) from a split slot's children fragment.
    Out-of-bounds child slots, span keys and further nesting are dropped."""
    children = slot.get("children") or {}
    rows = max(1, int(children.get("rows") or 1))
    cols = max(1, int(children.get("cols") or 1))
    slots = []
    for child in children.get("slots") or []:
        if not isinstance(child, dict) or child.get("widget_type") == "split":
            continue
        if not (0 <= child.get("row", -1) < rows and 0 <= child.get("col", -1) < cols):
            continue
        slots.append({k: v for k, v in child.items() if k not in ("row_span", "col_span", "children")})
    return rows, cols, slots


class SplitSlotWidget(Container):
    """A slot holding its own mini-grid so a split stays local to that pane."""

    DEFAULT_CSS = """
    SplitSlotWidget {
        height: 100%;
    }
    SplitSlotWidget > Grid {
        grid-gutter: 0 1;
        height: 100%;
    }
    SplitSlotWidget DashboardSlotWidget {
        border: round $panel-lighten-2;
    }
    SplitSlotWidget DashboardSlotWidget.-selected {
        border: round $accent;
    }
    """

    def __init__(self, slot: dict):
        super().__init__()
        self.slot = slot
        self.child_rows, self.child_cols, self.child_slots = normalized_children(slot)
        self._selected: tuple[int, int] | None = None

    def compose(self) -> ComposeResult:
        yield Grid(classes="split-grid")

    def on_mount(self) -> None:
        # A full dashboard render rebuilds this widget after the screen already
        # applied cursor highlighting; ask it for the selected child cell.
        sync = getattr(self.screen, "_sync_split_selection", None)
        if sync is not None:
            sync(self)
        self._populate()

    def _populate(self) -> None:
        from hatty.ui.dashboard.screen import populate_grid

        populate_grid(
            self.query_one(Grid),
            self.child_rows,
            self.child_cols,
            self.child_slots,
            is_selected=lambda w: self._selected is not None and (w.row, w.col) == self._selected,
            is_grabbed=lambda w: False,
            nested=True,
        )

    def select_child(self, cell: tuple[int, int] | None) -> None:
        """Highlight the child cell the screen cursor sits on (None clears)."""
        self._selected = cell
        for widget in self.query("DashboardSlotWidget"):
            slot = cast("DashboardSlotWidget", widget)
            slot.set_class(cell is not None and (slot.row, slot.col) == cell, "-selected")

    def child_widget_at(self, row: int, col: int):
        """The nested cell's content widget, mirroring _content_widget_at_cursor."""
        for widget in self.query("DashboardSlotWidget"):
            slot = cast("DashboardSlotWidget", widget)
            if (slot.row, slot.col) == (row, col):
                children = list(widget.children)
                return children[0] if children else None
        return None
