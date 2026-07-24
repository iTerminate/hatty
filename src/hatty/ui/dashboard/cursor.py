# hatty — MIT License. See LICENSE file for details.
"""Pure grid-navigation cursor for the dashboard screen (issue #171).

The dashboard's cursor math — stepping past a spanned slot's footprint, clamping
at edges, descending into / ascending out of a split slot's mini-grid, and
resolving the slot under the cursor — was interleaved with widget highlight and
scroll calls on `DashboardScreen`, so none of it was testable without booting the
screen. `GridCursor` holds just the cursor path and that arithmetic (composing
the pure `dashboard_layout` helpers), leaving the DOM side effects on the screen.

The cursor is a path: `[top_cell]` at the top level, `[top_cell, child_cell]`
while descended into a split slot's mini-grid (capped at one level of nesting).
"""

from hatty.ui.dashboard.layout import footprint, slot_covering
from hatty.ui.dashboard.widgets.split import normalized_children


def find_slot(slots: list[dict], row: int, col: int) -> dict | None:
    """First slot whose (row, col) anchor matches exactly (child grids only —
    their slots carry no spans, so anchor equality is enough)."""
    return next((s for s in slots if s["row"] == row and s["col"] == col), None)


class GridCursor:
    def __init__(self) -> None:
        self.path: list[tuple[int, int]] = [(0, 0)]

    # cursor_row/cursor_col read the path tail so generic navigation code works
    # unchanged whether or not the cursor is descended into a split.
    @property
    def row(self) -> int:
        return self.path[-1][0]

    @row.setter
    def row(self, value: int) -> None:
        self.path[-1] = (value, self.path[-1][1])

    @property
    def col(self) -> int:
        return self.path[-1][1]

    @col.setter
    def col(self, value: int) -> None:
        self.path[-1] = (self.path[-1][0], value)

    def top_cell(self) -> tuple[int, int]:
        return self.path[0]

    def reset(self) -> None:
        self.path = [(0, 0)]

    def in_split(self) -> bool:
        return len(self.path) > 1

    def descend(self) -> None:
        self.path.append((0, 0))

    def ascend(self) -> None:
        self.path = self.path[:1]

    def validate(self, rows: int, cols: int, slots: list[dict]) -> None:
        """Clamp the top cell to the grid and drop a stale descent (the top cell
        no longer holds a split, or the child cell fell out of the child grid)."""
        top_r, top_c = self.top_cell()
        self.path[0] = (max(0, min(rows - 1, top_r)), max(0, min(cols - 1, top_c)))
        if len(self.path) == 1:
            return
        split = slot_covering(slots, *self.top_cell())
        if split is None or split.get("widget_type") != "split":
            self.path = self.path[:1]
            return
        child_rows, child_cols, _ = normalized_children(split)
        child_r, child_c = self.path[1]
        self.path[1] = (max(0, min(child_rows - 1, child_r)), max(0, min(child_cols - 1, child_c)))

    def active_grid_ctx(self, dashboard: dict) -> tuple[int, int, list[dict]]:
        """(rows, cols, slots) of the grid the cursor currently lives in — the
        dashboard itself, or the descended split slot's (normalized) child grid.
        Moving past a child grid's edge never auto-ascends; escape does."""
        if len(self.path) > 1:
            split = slot_covering(dashboard["slots"], *self.top_cell())
            if split is not None and split.get("widget_type") == "split":
                return normalized_children(split)
            self.path = self.path[:1]  # stale descent
        return dashboard["rows"], dashboard["cols"], dashboard["slots"]

    def move(self, d_row: int, d_col: int, rows: int, cols: int, slots: list[dict]) -> bool:
        """Step the cursor by (d_row, d_col) within (rows, cols, slots), skipping
        past the current slot's whole footprint so a spanned slot is exited rather
        than re-selected. Returns True when the cursor position is settled (the
        caller should refresh highlight/scroll); False only when the footprint
        runs into the edge in this direction, leaving the cursor unchanged."""
        current = slot_covering(slots, self.row, self.col)
        current_cells = footprint(current) if current else set()
        new_row, new_col = self.row, self.col
        for _ in range(max(rows, cols)):
            stepped_row = max(0, min(rows - 1, new_row + d_row))
            stepped_col = max(0, min(cols - 1, new_col + d_col))
            if (stepped_row, stepped_col) == (new_row, new_col):
                break  # clamped at the edge
            new_row, new_col = stepped_row, stepped_col
            if (new_row, new_col) not in current_cells:
                break
        if (new_row, new_col) in current_cells and (d_row or d_col):
            return False  # footprint reaches the edge in this direction; nothing beyond it
        self.row, self.col = new_row, new_col
        return True

    def slot_at(self, dashboard: dict) -> dict | None:
        """The slot the cursor rests on: at the top level, the slot whose
        footprint contains the cursor; descended, the exact child slot dict
        (children carry no spans) from the split's raw children fragment."""
        top = slot_covering(dashboard["slots"], *self.top_cell())
        if len(self.path) == 1:
            return top
        if top is None or top.get("widget_type") != "split":
            return None
        child_slots = (top.get("children") or {}).get("slots") or []
        return find_slot(child_slots, *self.path[1])

    def split_anchor(self, slots: list[dict]) -> tuple[int, int] | None:
        """Anchor of the split slot covering the cursor's top cell, if any."""
        split = slot_covering(slots, *self.top_cell())
        if split is not None and split.get("widget_type") == "split":
            return (split["row"], split["col"])
        return None
