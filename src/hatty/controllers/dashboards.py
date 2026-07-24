# hatty — MIT License. See LICENSE file for details.
"""Dashboard state and slot-editing operations, extracted from HACLI."""

import copy
import math

from hatty.ui.dashboard.layout import exceeds_bounds, fits

#: Bumped if the export payload shape ever changes incompatibly.
EXPORT_FORMAT_VERSION = 1


class DashboardController:
    """Owns the dashboards collection (including temp list-preview dashboards)
    and every dashboard/slot mutation. Persistence and notifications go
    through the app reference."""

    # Split dimensions per direction: horizontal divider -> 2 rows, vertical -> 2 cols.
    _SPLIT_FACTORS = {"h": (2, 1), "v": (1, 2), "quad": (2, 2)}

    def __init__(self, app) -> None:
        self._app = app
        self.dashboards: dict = {}
        self.dashboard_names: list = []
        self.default_dashboard_name: str | None = None
        self.current_dashboard_name: str | None = None
        self.temp_dashboard_names: set[str] = set()

    # ── Dashboard CRUD ───────────────────────────────────────────────────────

    def create(self, name: str, rows: int, cols: int, row_height: int | None = None) -> None:
        dashboard = {"rows": rows, "cols": cols, "slots": []}
        if row_height:
            dashboard["row_height"] = row_height
        self.dashboards[name] = dashboard
        self.dashboard_names.append(name)
        self.current_dashboard_name = name
        self._app.persist("dashboards")

    def switch(self, name: str) -> None:
        if name in self.dashboards:
            self.current_dashboard_name = name

    def set_default(self, name: str) -> None:
        if name not in self.dashboards:
            return
        self.default_dashboard_name = name
        self._app.persist("default_dashboard")
        self._app.notify(f"'{name}' set as default dashboard.", title="Default Dashboard Set")

    def reorder_dashboards(self, ordered_names: list[str]) -> None:
        """Reorder the dashboards collection (issue #212, mirrors column
        reordering). Persisted order is the *dict* insertion order of
        dashboards, so this rebuilds the dict alongside dashboard_names rather
        than just resequencing the name list."""
        order = [n for n in ordered_names if n in self.dashboards]
        order += [n for n in self.dashboard_names if n not in order]  # keep any omitted
        self.dashboard_names = order
        self.dashboards = {n: self.dashboards[n] for n in order}
        self._app.persist("dashboards")

    def rename(self, old_name: str, new_name: str) -> None:
        if old_name not in self.dashboards or old_name == new_name:
            return
        if new_name in self.dashboards:
            self._app.notify(f"A dashboard named '{new_name}' already exists.", title="Rename Error", severity="error")
            return
        self.dashboards[new_name] = self.dashboards.pop(old_name)
        self.dashboard_names = [new_name if n == old_name else n for n in self.dashboard_names]
        if self.current_dashboard_name == old_name:
            self.current_dashboard_name = new_name
        if self.default_dashboard_name == old_name:
            self.default_dashboard_name = new_name
        self._app.persist("dashboards", "default_dashboard")
        self._app.notify(f"Renamed dashboard '{old_name}' to '{new_name}'.", title="Dashboard Renamed")

    def resize(self, name: str, rows: int, cols: int) -> None:
        dashboard = self.dashboards[name]
        dashboard["rows"] = rows
        dashboard["cols"] = cols
        dashboard["slots"] = [s for s in dashboard["slots"] if not exceeds_bounds(s, rows, cols)]
        self._app.persist("dashboards")
        self._app.notify(f"Resized dashboard '{name}' to {rows}x{cols}.", title="Dashboard Resized")

    def set_row_height(self, name: str, row_height: int | None) -> None:
        dashboard = self.dashboards[name]
        if row_height:
            dashboard["row_height"] = row_height
        else:
            dashboard.pop("row_height", None)
        self._app.persist("dashboards")

    def delete(self, name: str) -> None:
        if name not in self.dashboards:
            return
        if len(self.dashboards) <= 1:
            self._app.notify("Cannot delete the only remaining dashboard.", title="Delete Error", severity="warning")
            return
        del self.dashboards[name]
        self.dashboard_names.remove(name)
        if self.current_dashboard_name == name:
            self.current_dashboard_name = self.dashboard_names[0]
        if self.default_dashboard_name == name:
            self.default_dashboard_name = None
        self._app.persist("dashboards", "default_dashboard")
        self._app.notify(f"Dashboard '{name}' deleted.", title="Dashboard Deleted")

    # ── Export / import (issue #219) ─────────────────────────────────────────

    def to_export_payload(self, name: str) -> dict:
        """A JSON-serializable snapshot of dashboard `name`, versioned so a
        future format change can be detected on import."""
        return {
            "hatty_dashboard": EXPORT_FORMAT_VERSION,
            "name": name,
            "dashboard": copy.deepcopy(self.dashboards[name]),
        }

    def import_from_payload(self, payload: dict) -> str:
        """Create a new dashboard from a previously exported payload,
        deduplicating its name against the existing collection. Raises
        `ValueError` (with a user-facing message) if `payload` isn't a
        recognizable export. Returns the final dashboard name."""
        if not isinstance(payload, dict) or payload.get("hatty_dashboard") != EXPORT_FORMAT_VERSION:
            raise ValueError("Not a valid hatty dashboard export file.")
        dashboard = payload.get("dashboard")
        if not isinstance(dashboard, dict) or "rows" not in dashboard or "cols" not in dashboard:
            raise ValueError("Dashboard export is missing rows/cols data.")

        dashboard = copy.deepcopy(dashboard)
        dashboard.setdefault("slots", [])
        final = self._unique_name(str(payload.get("name") or "Imported"))
        self.dashboards[final] = dashboard
        self.dashboard_names.append(final)
        self.current_dashboard_name = final
        self._app.persist("dashboards")
        return final

    # ── List preview (temp dashboards) ───────────────────────────────────────

    @staticmethod
    def domain_to_widget_type(entity_id: str) -> str:
        domain = entity_id.split(".")[0]
        return {
            "light": "light",
            "switch": "switch",
            "climate": "thermostat",
            "cover": "cover",
            "binary_sensor": "binary_sensor",
            "weather": "weather",
        }.get(domain, "sensor")

    @staticmethod
    def _pack_grid(count: int) -> tuple[int, int]:
        """Roughly square (rows, cols) for `count` cells, capped at 3 columns."""
        cols = min(3, max(1, round(math.sqrt(count))))
        rows = math.ceil(count / cols)
        return rows, cols

    @classmethod
    def _grid_for(cls, entity_ids: list[str]) -> tuple[int, int, list[dict]]:
        """Auto-layout for a flat entity set: a roughly square grid capped at
        3 columns, one domain-mapped widget slot per entity."""
        rows, cols = cls._pack_grid(len(entity_ids))
        slots = [
            {"row": i // cols, "col": i % cols, "widget_type": cls.domain_to_widget_type(eid), "entity_id": eid}
            for i, eid in enumerate(entity_ids)
        ]
        return rows, cols, slots

    def _unique_name(self, name: str) -> str:
        """`name`, or `name (2)`, `name (3)`, ... if it's already taken."""
        final = name
        suffix = 2
        while final in self.dashboards:
            final = f"{name} ({suffix})"
            suffix += 1
        return final

    def create_populated(self, name: str, entity_ids: list[str]) -> str:
        """Create a persistent dashboard auto-populated from `entity_ids` (the
        area quick-create), deduplicating the name with a numeric suffix.
        Returns the final name."""
        final = self._unique_name(name)
        rows, cols, slots = self._grid_for(entity_ids)
        self.dashboards[final] = {"rows": rows, "cols": cols, "slots": slots}
        self.dashboard_names.append(final)
        self.current_dashboard_name = final
        self._app.persist("dashboards")
        return final

    def preview_list_as_dashboard(self, list_name: str) -> bool:
        entity_ids = self._app.entity_lists.get(list_name, [])
        if not entity_ids:
            self._app.notify(f"List '{list_name}' is empty.", title="Nothing to Preview", severity="warning")
            return False

        rows, cols, slots = self._grid_for(entity_ids)

        name = f"{list_name} (preview)"
        if name in self.dashboards:
            self.cleanup_temp_dashboard(name)

        self.dashboards[name] = {"rows": rows, "cols": cols, "slots": slots}
        self.dashboard_names.append(name)
        self.current_dashboard_name = name
        self.temp_dashboard_names.add(name)
        return True

    def cleanup_temp_dashboards(self) -> None:
        for name in list(self.temp_dashboard_names):
            self.cleanup_temp_dashboard(name)

    def cleanup_temp_dashboard(self, name: str) -> None:
        self.dashboards.pop(name, None)
        if name in self.dashboard_names:
            self.dashboard_names.remove(name)
        self.temp_dashboard_names.discard(name)
        if self.current_dashboard_name == name:
            self.current_dashboard_name = self.dashboard_names[0] if self.dashboard_names else None

    # ── Slot editing ─────────────────────────────────────────────────────────

    def grid_ctx(self, dashboard_name: str, parent: tuple[int, int] | None) -> tuple[list[dict], int, int] | None:
        """The (slots, rows, cols) a slot edit targets: the dashboard's own grid,
        or — when `parent` names a split slot's anchor — that split's child grid."""
        dashboard = self.dashboards[dashboard_name]
        if parent is None:
            return dashboard["slots"], dashboard["rows"], dashboard["cols"]
        split = next(
            (
                s
                for s in dashboard["slots"]
                if (s["row"], s["col"]) == tuple(parent) and s.get("widget_type") == "split"
            ),
            None,
        )
        if split is None:
            return None
        children = split.setdefault("children", {"rows": 1, "cols": 1, "slots": []})
        return children.setdefault("slots", []), children.get("rows", 1), children.get("cols", 1)

    def set_slot(
        self,
        dashboard_name: str,
        row: int,
        col: int,
        widget_type: str,
        entity_id: str | None,
        entity_ids: list[str] | None = None,
        extra: dict | None = None,
        parent: tuple[int, int] | None = None,
    ) -> None:
        ctx = self.grid_ctx(dashboard_name, parent)
        if ctx is None:
            return
        slots, _, _ = ctx
        slots[:] = [s for s in slots if not (s["row"] == row and s["col"] == col)]
        slot = {"row": row, "col": col, "widget_type": widget_type, "entity_id": entity_id}
        if entity_ids is not None:
            slot["entity_ids"] = entity_ids
        if extra:
            slot.update(extra)
        slots.append(slot)
        self._app.persist("dashboards")

    def update_panel_entity_ids(
        self, dashboard_name: str, row: int, col: int, entity_ids: list[str], parent: tuple[int, int] | None = None
    ) -> None:
        ctx = self.grid_ctx(dashboard_name, parent)
        if ctx is None:
            return
        slots, _, _ = ctx
        slot = next((s for s in slots if s["row"] == row and s["col"] == col), None)
        if slot is not None:
            slot["entity_ids"] = list(entity_ids)
            self._app.persist("dashboards")

    def clear_slot(self, dashboard_name: str, row: int, col: int, parent: tuple[int, int] | None = None) -> None:
        ctx = self.grid_ctx(dashboard_name, parent)
        if ctx is None:
            return
        slots, _, _ = ctx
        slots[:] = [s for s in slots if not (s["row"] == row and s["col"] == col)]
        self._app.persist("dashboards")

    def swap_slots(
        self, dashboard_name: str, r1: int, c1: int, r2: int, c2: int, parent: tuple[int, int] | None = None
    ) -> bool:
        # Move/swap a widget between two cells of the same grid (top-level or one
        # split's child grid): reassign each present slot's row/col. Handles
        # occupied↔occupied and occupied↔empty (a missing slot is simply absent).
        # Both slots must fit at their new anchors (span-aware); returns False if not.
        ctx = self.grid_ctx(dashboard_name, parent)
        if ctx is None:
            return False
        slots, rows, cols = ctx
        slot_a = next((s for s in slots if s["row"] == r1 and s["col"] == c1), None)
        slot_b = next((s for s in slots if s["row"] == r2 and s["col"] == c2), None)

        others = [s for s in slots if s is not slot_a and s is not slot_b]
        moved = []
        if slot_a is not None:
            moved.append({**slot_a, "row": r2, "col": c2})
        if slot_b is not None:
            moved.append({**slot_b, "row": r1, "col": c1})
        for candidate in moved:
            occupied = others + [m for m in moved if m is not candidate]
            if not fits(occupied, candidate, rows, cols):
                return False

        if slot_a is not None:
            slot_a["row"], slot_a["col"] = r2, c2
        if slot_b is not None:
            slot_b["row"], slot_b["col"] = r1, c1
        self._app.persist("dashboards")
        return True

    def move_slot_across(
        self,
        dashboard_name: str,
        r1: int,
        c1: int,
        src_parent: tuple[int, int] | None,
        r2: int,
        c2: int,
        dst_parent: tuple[int, int] | None,
    ) -> bool:
        """Move/swap a slot between two *different* grids (top-level <-> a split's
        child grid, or split<->split). An empty destination cell is a move; an
        occupied one swaps the two slots across grids. A split slot may never land
        inside a child grid (splits can't nest). Span keys are dropped when a slot
        enters a child grid (child cells can't span). Returns False (no mutation)
        if either placement wouldn't fit."""
        src = self.grid_ctx(dashboard_name, src_parent)
        dst = self.grid_ctx(dashboard_name, dst_parent)
        if src is None or dst is None:
            return False
        src_slots, src_rows, src_cols = src
        dst_slots, dst_rows, dst_cols = dst
        slot_a = next((s for s in src_slots if s["row"] == r1 and s["col"] == c1), None)
        if slot_a is None:
            return False
        slot_b = next((s for s in dst_slots if s["row"] == r2 and s["col"] == c2), None)

        # A split can't move into any child grid, and can't receive one either
        # (would nest, one level max).
        if dst_parent is not None and slot_a.get("widget_type") == "split":
            return False
        if src_parent is not None and slot_b is not None and slot_b.get("widget_type") == "split":
            return False

        def _place(slot: dict, parent: tuple[int, int] | None, r: int, c: int) -> dict:
            moved = {**slot, "row": r, "col": c}
            if parent is not None:  # child grids reject spans / nested children
                for key in ("row_span", "col_span", "children"):
                    moved.pop(key, None)
            return moved

        new_a = _place(slot_a, dst_parent, r2, c2)
        new_b = _place(slot_b, src_parent, r1, c1) if slot_b is not None else None

        # The two grids are independent (unlike same-grid swap_slots), so each
        # placement is fit-checked against its own grid only.
        if not fits([s for s in dst_slots if s is not slot_b], new_a, dst_rows, dst_cols):
            return False
        if new_b is not None and not fits([s for s in src_slots if s is not slot_a], new_b, src_rows, src_cols):
            return False

        src_slots[:] = [s for s in src_slots if s is not slot_a]
        dst_slots[:] = [s for s in dst_slots if s is not slot_b]
        dst_slots.append(new_a)
        if new_b is not None:
            src_slots.append(new_b)
        self._app.persist("dashboards")
        return True

    def resize_slot(self, dashboard_name: str, row: int, col: int, row_span: int, col_span: int) -> bool:
        """Set a slot's footprint spans, refusing overlaps/out-of-bounds. Span keys
        are dropped at 1 so unspanned slots keep the legacy config shape."""
        dashboard = self.dashboards[dashboard_name]
        slot = next((s for s in dashboard["slots"] if s["row"] == row and s["col"] == col), None)
        if slot is None:
            return False
        candidate = {**slot, "row_span": row_span, "col_span": col_span}
        if not fits(dashboard["slots"], candidate, dashboard["rows"], dashboard["cols"]):
            return False
        for key, value in (("row_span", row_span), ("col_span", col_span)):
            if value > 1:
                slot[key] = value
            else:
                slot.pop(key, None)
        self._app.persist("dashboards")
        return True

    def split_slot(self, name: str, row: int, col: int, direction: str) -> bool:
        """Split the pane at (row, col) into a nested mini-grid local to that pane
        (issue #81, Approach B): the slot becomes a "split" container carrying a
        children fragment; an existing widget moves into child (0, 0) and the
        slot's own top-level footprint (spans) is kept. One level max."""
        child_rows, child_cols = self._SPLIT_FACTORS[direction]
        dashboard = self.dashboards[name]
        slots = dashboard["slots"]
        existing = next((s for s in slots if (s["row"], s["col"]) == (row, col)), None)
        if existing is not None and existing.get("widget_type") == "split":
            return False  # already split; nesting is capped at one level

        children = {"rows": child_rows, "cols": child_cols, "slots": []}
        new_slot = {"row": row, "col": col, "widget_type": "split", "entity_id": None, "children": children}
        if existing is not None:
            for key in ("row_span", "col_span"):
                if key in existing:
                    new_slot[key] = existing[key]
            moved = {k: v for k, v in existing.items() if k not in ("row", "col", "row_span", "col_span")}
            moved["row"], moved["col"] = 0, 0
            children["slots"].append(moved)
            slots.remove(existing)
        slots.append(new_slot)
        self._app.persist("dashboards")
        return True

    def fill_split(self, name: str, row: int, col: int, widget_type: str, entity_ids: list[str]) -> bool:
        """Quick-fill (issue #218): turn the pane at (row, col) into a split
        sized to fit every entity in `entity_ids`, one same-`widget_type` widget
        per cell (row-major, same packing as `_grid_for`). Replaces whatever was
        in the pane (widget or existing split), preserving its top-level spans.
        No-op (returns False) if every id is blank."""
        ids = [eid for eid in entity_ids if eid]
        if not ids:
            return False
        dashboard = self.dashboards[name]
        slots = dashboard["slots"]
        existing = next((s for s in slots if (s["row"], s["col"]) == (row, col)), None)

        child_rows, child_cols = self._pack_grid(len(ids))
        child_slots = [
            {"row": i // child_cols, "col": i % child_cols, "widget_type": widget_type, "entity_id": eid}
            for i, eid in enumerate(ids)
        ]
        children = {"rows": child_rows, "cols": child_cols, "slots": child_slots}
        new_slot = {"row": row, "col": col, "widget_type": "split", "entity_id": None, "children": children}
        if existing is not None:
            for key in ("row_span", "col_span"):
                if key in existing:
                    new_slot[key] = existing[key]
            slots.remove(existing)
        slots.append(new_slot)
        self._app.persist("dashboards")
        return True

    def unsplit_slot(self, name: str, row: int, col: int) -> bool:
        """Collapse a split slot back into a plain slot. Only when at most one
        child holds content — the survivor (or nothing) takes the slot's place,
        keeping the slot's own top-level footprint. Returns False otherwise."""
        dashboard = self.dashboards[name]
        slots = dashboard["slots"]
        slot = next((s for s in slots if (s["row"], s["col"]) == (row, col)), None)
        if slot is None or slot.get("widget_type") != "split":
            return False
        child_slots = (slot.get("children") or {}).get("slots") or []
        if len(child_slots) > 1:
            return False
        slots.remove(slot)
        if child_slots:
            survivor = {k: v for k, v in child_slots[0].items() if k not in ("row", "col", "row_span", "col_span")}
            survivor["row"], survivor["col"] = row, col
            for key in ("row_span", "col_span"):
                if key in slot:
                    survivor[key] = slot[key]
            slots.append(survivor)
        self._app.persist("dashboards")
        return True
