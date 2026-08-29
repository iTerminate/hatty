# hatty — MIT License. See LICENSE file for details.
"""Graph/history state, the detail panel rendering, and saved graphs,
extracted from HACLI."""

import copy
from collections import deque
from datetime import datetime, timedelta, timezone

from hatty.const import (
    BINARY_STATE_MAP,
    CONFIG_KEY_GRAPH_HOURS,
    CONFIG_KEY_GRAPH_TYPE,
    DEFAULT_GRAPH_HOURS,
)
from hatty.types import Entity
from hatty.ui.graph.entity_detail import EntityDetailPanel

#: Bumped if the export payload shape ever changes incompatibly.
EXPORT_FORMAT_VERSION = 1


def _trim_history(buf: deque, hours: float, ts_of=lambda item: item[0]) -> None:
    """Evict entries older than `hours` before the newest entry in `buf`, in place.

    Anchored to the newest entry already in the buffer rather than wall-clock
    now — keeps this correct under clock skew and consistent with fixed-date
    test fixtures.
    """
    if not buf:
        return
    try:
        anchor = datetime.fromisoformat(ts_of(buf[-1]))
    except (ValueError, TypeError):
        return
    cutoff = anchor - timedelta(hours=hours)
    while buf:
        try:
            head_dt = datetime.fromisoformat(ts_of(buf[0]))
        except (ValueError, TypeError):
            buf.popleft()
            continue
        if head_dt < cutoff:
            buf.popleft()
        else:
            break


class GraphController:
    """Owns the numeric/climate history stores, the detail-panel graph state
    (which entity is shown, comparison extras), and the saved-graphs
    collection. Widget lookups and persistence go through the app."""

    def __init__(self, app) -> None:
        self._app = app
        self.entity_history: dict[str, deque] = {}
        self.climate_history: dict[str, deque] = {}
        self.detail_entity_id: str | None = None
        self.graph_extra_ids: list[str] = []
        self.saved_graphs: dict = {}

    # ── Entity classification ────────────────────────────────────────────────

    def is_graphable(self, entity: Entity) -> bool:
        from hatty.ui.entity_table import is_numeric_state

        return (
            is_numeric_state(entity)
            or self.is_climate_entity(entity.get("entity_id", ""))
            or self.is_binary_entity(entity.get("entity_id", ""))
        )

    @staticmethod
    def is_climate_entity(entity_id: str) -> bool:
        return entity_id.split(".")[0] == "climate"

    @staticmethod
    def is_binary_entity(entity_id: str) -> bool:
        return entity_id.split(".")[0] == "binary_sensor"

    def history_fetcher(self, entity_id: str):
        """The right REST history fetcher for an entity: binary entities map
        on/off to 1/0 instead of dropping non-numeric states."""
        if self.is_binary_entity(entity_id):
            return self._app.client.fetch_binary_history
        return self._app.client.fetch_history

    # ── Detail panel ─────────────────────────────────────────────────────────

    def _panel(self) -> EntityDetailPanel:
        return self._app.query_one("#detail_panel", EntityDetailPanel)

    def extras(self) -> dict:
        """entity_id -> (entity, history) for every comparison entity."""
        return {
            eid: (self._app.find_entity(eid), list(self.entity_history.get(eid, []))) for eid in self.graph_extra_ids
        }

    def close_panel(self) -> None:
        """Hide the graph panel and reset its state (shared by the graph
        toggle and both log toggles, which displace the graph)."""
        self._panel().remove_class("-visible")
        self.detail_entity_id = None
        self.graph_extra_ids = []
        self._app.refresh_bindings()

    def render_detail(self, entity_id: str, entity: Entity) -> None:
        """Render the detail panel for an entity, dispatching on its kind
        (climate / binary / numeric) with the current comparison extras."""
        panel = self._panel()
        if self.is_climate_entity(entity_id):
            panel.update_climate(entity, list(self.climate_history.get(entity_id, [])))
        elif self.is_binary_entity(entity_id):
            panel.update_binary(entity, list(self.entity_history.get(entity_id, [])), self.extras())
        else:
            panel.update_multi(entity, list(self.entity_history.get(entity_id, [])), self.extras())

    def _spawn_history_load(self, entity_id: str) -> None:
        if self.is_climate_entity(entity_id):
            self._app.spawn(self.load_climate_graph_history(entity_id))
        else:
            self._app.spawn(self.load_graph_history(entity_id))

    def open_graph_for(self, entity_id: str, entity: Entity) -> None:
        self.detail_entity_id = entity_id
        self._panel().add_class("-visible")
        # Open in the configured default graph type, mirroring the fullscreen graph
        # and dashboard Graph widgets; None falls back to the sparkline Max summary.
        self._panel().apply_saved_graph_type(self._app.app_config.get(CONFIG_KEY_GRAPH_TYPE))
        self.render_detail(entity_id, entity)
        self._spawn_history_load(entity_id)
        self._app.refresh_bindings()

    def follow_cursor(self, entity_id: str, entity: Entity) -> None:
        """The detail panel tracks the table cursor: re-render for the newly
        highlighted entity, or show the unavailable notice for one that can't
        be graphed."""
        self.detail_entity_id = entity_id
        if not self.is_graphable(entity):
            self._panel().update_unavailable(entity)
            return
        self.render_detail(entity_id, entity)
        self._spawn_history_load(entity_id)

    def refresh_detail_panel(self) -> None:
        if not self.detail_entity_id:
            return
        entity = self._app.find_entity(self.detail_entity_id)
        if not entity:
            return
        self.render_detail(self.detail_entity_id, entity)

    # ── History loading ──────────────────────────────────────────────────────

    async def ensure_entity_history(self, entity_id: str) -> bool:
        hours = self._app.graph_hours
        values = await self.history_fetcher(entity_id)(entity_id, hours=hours)
        if values is None:
            return False
        buf: deque = deque(values)
        if values:
            last_ts = values[-1][0]
            for ts, val in self.entity_history.get(entity_id, []):
                if ts > last_ts:
                    buf.append((ts, val))
        _trim_history(buf, hours)
        self.entity_history[entity_id] = buf
        return True

    async def load_graph_history(self, entity_id: str) -> None:
        success = await self.ensure_entity_history(entity_id)

        panel = self._panel()
        if panel.has_class("-visible"):
            if not success:
                entity = self._app.find_entity(entity_id)
                if entity:
                    panel.update(entity, None)
            else:
                self.refresh_detail_panel()

        self.refresh_graph_preview(entity_id)

    async def ensure_climate_history(self, entity_id: str) -> bool:
        hours = self._app.graph_hours
        values = await self._app.client.fetch_climate_history(entity_id, hours=hours)
        if values is None:
            return False
        buf: deque = deque(values)
        _trim_history(buf, hours, ts_of=lambda item: item["ts"])
        self.climate_history[entity_id] = buf
        return True

    async def load_climate_graph_history(self, entity_id: str) -> None:
        success = await self.ensure_climate_history(entity_id)

        panel = self._panel()
        if panel.has_class("-visible") and self.detail_entity_id == entity_id:
            entity = self._app.find_entity(entity_id)
            if entity:
                panel.update_climate(entity, list(self.climate_history.get(entity_id, [])) if success else None)

    async def reload_detail_and_extras(self) -> None:
        entity_id = self.detail_entity_id
        if not entity_id:
            return
        if self.is_climate_entity(entity_id):
            await self.ensure_climate_history(entity_id)
        else:
            await self.ensure_entity_history(entity_id)
            for eid in list(self.graph_extra_ids):
                await self.ensure_entity_history(eid)
        if self._panel().has_class("-visible"):
            self.refresh_detail_panel()

    def record_state(self, entity: Entity) -> None:
        """Append a live state_changed sample to an entity's history buffer
        (only for entities whose history is already loaded)."""
        entity_id = entity.get("entity_id")
        if not entity_id:
            return
        if self.is_binary_entity(entity_id):
            value = BINARY_STATE_MAP.get(entity.get("state", ""))
            if value is None:
                return
        else:
            try:
                value = float(entity.get("state", ""))
            except (ValueError, TypeError):
                return
        ts = entity.get("last_changed") or datetime.now(timezone.utc).isoformat()
        if entity_id in self.entity_history:
            buf = self.entity_history[entity_id]
            buf.append((ts, value))
            _trim_history(buf, self._app.graph_hours)

    # ── Fullscreen preview / duration ────────────────────────────────────────

    def refresh_graph_preview(self, entity_id: str) -> None:
        from hatty.ui.graph.preview_screen import GraphPreviewScreen

        for screen in self._app.screen_stack:
            if isinstance(screen, GraphPreviewScreen):
                screen.refresh_live_data(entity_id, list(self.entity_history.get(entity_id, [])))

    def on_graph_hours_changed(self) -> None:
        self.entity_history.clear()
        self.climate_history.clear()

        if self.detail_entity_id:
            self._app.spawn(self.reload_detail_and_extras())

        from hatty.ui.graph.preview_screen import GraphPreviewScreen

        for s in self._app.screen_stack:
            if isinstance(s, GraphPreviewScreen):
                s.reload()

        from hatty.ui.dashboard.widgets.graph import GraphSlotWidget

        for widget in self._app.query(GraphSlotWidget):
            widget.reload_history()

    # ── Saved graphs ─────────────────────────────────────────────────────────

    def save_graph(
        self, name: str, entity_ids: list[str], graph_type: str, hours: float, colors: dict[str, str] | None = None
    ) -> None:
        entry = {"entity_ids": entity_ids, "graph_type": graph_type, "hours": hours}
        if colors:
            entry["colors"] = colors
        self.saved_graphs[name] = entry
        self._app.persist("saved_graphs")
        self._app.notify(f"Graph saved as '{name}'.", title="Graph Saved")

    # ── Export / import ──────────────────────────────────────────────────────

    def to_export_payload(self, name: str) -> dict:
        """A JSON-serializable snapshot of saved graph `name`, versioned so a
        future format change can be detected on import."""
        return {
            "hatty_graph": EXPORT_FORMAT_VERSION,
            "name": name,
            "graph": copy.deepcopy(self.saved_graphs[name]),
        }

    def import_from_payload(self, payload: dict) -> str:
        """Create a new saved graph from a previously exported payload,
        deduplicating its name against the existing collection. Raises
        `ValueError` (with a user-facing message) if `payload` isn't a
        recognizable export. Returns the final graph name."""
        if not isinstance(payload, dict) or payload.get("hatty_graph") != EXPORT_FORMAT_VERSION:
            raise ValueError("Not a valid hatty saved graph export file.")
        graph = payload.get("graph")
        if not isinstance(graph, dict) or "entity_ids" not in graph:
            raise ValueError("Saved graph export is missing entity_ids.")

        final = self._unique_name(str(payload.get("name") or "Imported"))
        self.saved_graphs[final] = copy.deepcopy(graph)
        self._app.persist("saved_graphs")
        return final

    def _unique_name(self, name: str) -> str:
        """`name`, or `name (2)`, `name (3)`, ... if it's already taken."""
        final = name
        suffix = 2
        while final in self.saved_graphs:
            final = f"{name} ({suffix})"
            suffix += 1
        return final

    def handle_saved_graphs_popup_action(self, result: dict) -> None:
        app = self._app
        action = result.get("action")

        if action == "open":
            name = result.get("name")
            saved = self.saved_graphs.get(name)
            if not saved:
                return
            from hatty.ui.graph.preview_screen import GraphPreviewScreen

            # Replace an already-open fullscreen graph instead of stacking a second one
            # (app.screen is the old graph screen). Pop before overwriting graph_hours
            # so the old screen never reloads against the new window on its way out.
            if isinstance(app.screen, GraphPreviewScreen):
                app.pop_screen()
            app.app_config[CONFIG_KEY_GRAPH_HOURS] = saved.get("hours", DEFAULT_GRAPH_HOURS)
            app.push_screen(
                GraphPreviewScreen(
                    list(saved["entity_ids"]),
                    initial_graph_type=saved.get("graph_type"),
                    saved_graph_name=name,
                    colors=saved.get("colors"),
                )
            )
        elif action == "rename":
            old_name = result.get("old_name")
            new_name = result.get("new_name")
            if old_name not in self.saved_graphs or not new_name or new_name in self.saved_graphs:
                return
            self.saved_graphs[new_name] = self.saved_graphs.pop(old_name)
            app.persist("saved_graphs")
        elif action == "delete":
            name = result.get("name")
            if name not in self.saved_graphs:
                return
            del self.saved_graphs[name]
            app.persist("saved_graphs")
            app.notify(f"Saved graph '{name}' deleted.", title="Graph Deleted")
